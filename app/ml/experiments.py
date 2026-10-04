"""Research experiments beyond the single hold-out (ML_EVALUATION.md sections 4 to 6).

1. Rolling-origin cross-validation: several consecutive test windows at the end of the history, each model trained
   only on the days before its window, so one lucky or unlucky hold-out cannot decide the comparison.
2. Feature ablation (ML_PLAN section 5, stretch): the winning algorithm trained with calendar and history features
   first, then with holidays, promotions and weather added one group at a time. This answers the proposal's
   question about contextual factors.
3. Segment errors: MAE on holiday days, promotion item-days and wet days, where context should matter most.

Pure functions on DataFrames, called only by ForecastingService. Nothing is stored or activated.
"""
import numpy as np
import pandas as pd

from app.ml.evaluate import metrics
from app.ml.features import CALENDAR, HISTORY, HOLIDAY, PROMOTION, WEATHER, BASE_FEATURES
from app.ml.predict import BASELINES, predict
from app.ml.train import ALGO_ORDER, HOLDOUT_DAYS, make_model, prepare_dataset, with_estimated_weather

FOLDS = 6
FOLD_DAYS = 28
MIN_TRAIN_DAYS = 180
WET_DAY_MM = 5.0  # actual rain at or above this counts as a wet day for the segment errors

# Each set keeps the column order of BASE_FEATURES, so the last one is exactly the shipped feature set.
_GROUPS = [("calendar + history", CALENDAR + HISTORY), ("+ holidays", HOLIDAY), ("+ promotions", PROMOTION),
           ("+ weather (all features)", WEATHER)]


def feature_sets() -> list[tuple[str, list[str]]]:
    """Cumulative feature sets for the ablation, each in BASE_FEATURES order (the item one-hots are always added)."""
    out, chosen = [], set()
    for name, cols in _GROUPS:
        chosen |= set(cols)
        out.append((name, [c for c in BASE_FEATURES if c in chosen]))
    return out


def fold_windows(last: pd.Timestamp, n_folds: int = FOLDS, fold_days: int = FOLD_DAYS) -> list[tuple]:
    """Consecutive, non-overlapping test windows ending at `last`, oldest first: [(start, end), ...]."""
    last = pd.Timestamp(last)
    return [(last - pd.Timedelta(days=(n_folds - i) * fold_days - 1), last - pd.Timedelta(days=(n_folds - i - 1) * fold_days))
            for i in range(n_folds)]


def _fit_predict(algo: str, train: pd.DataFrame, test: pd.DataFrame, cols: list[str]) -> np.ndarray:
    if algo in BASELINES:
        return predict({"algorithm": algo}, test)
    model = make_model(algo)
    model.fit(train[cols].to_numpy(dtype=float), train["y"].to_numpy(dtype=float))
    return predict({"algorithm": algo, "model": model, "feature_columns": cols}, test)


def _split(df: pd.DataFrame, weather: pd.DataFrame, start, end) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Train on everything before `start`; test on [start, end] with the weather the model would have seen."""
    train = df[df["date"] < start].reset_index(drop=True)
    test = df[(df["date"] >= start) & (df["date"] <= end)].reset_index(drop=True)
    test = test.assign(actual_rain_mm=test["rain_mm"])  # kept for the wet-day segment before it is replaced
    return train, with_estimated_weather(test, weather, start)


def _segments(test: pd.DataFrame, pred: np.ndarray) -> dict:
    """MAE on the rows where a context factor is present, next to the MAE on the rest (pooled test rows)."""
    holiday = test[HOLIDAY].to_numpy().any(axis=1)
    promo = (test["promo_discount_pct"] > 0).to_numpy()
    wet = (test["actual_rain_mm"] >= WET_DAY_MM).to_numpy()
    out = {}
    for name, mask in (("holiday days", holiday), ("promotion item-days", promo), ("wet days", wet)):
        out[name] = {"with": metrics(test.loc[mask, "y"], pred[mask]), "without": metrics(test.loc[~mask, "y"], pred[~mask])}
    return out


def _summary(per_fold: list[dict]) -> dict:
    mae = np.array([f["mae"] for f in per_fold], dtype=float)
    wape = np.array([f["wape"] for f in per_fold], dtype=float)
    return {"mae_mean": round(float(mae.mean()), 4), "mae_std": round(float(mae.std(ddof=1)), 4) if len(mae) > 1 else 0.0,
            "wape_mean": round(float(wape.mean()), 3), "wape_std": round(float(wape.std(ddof=1)), 3) if len(wape) > 1 else 0.0}


def run_experiments(sales: pd.DataFrame, holidays: pd.DataFrame, promos: pd.DataFrame, weather: pd.DataFrame, items,
                    n_folds: int = FOLDS, fold_days: int = FOLD_DAYS, ablation_algorithm: str = "xgboost",
                    expected: pd.DataFrame | None = None) -> dict:
    """Cross-validate every candidate, run the ablation for `ablation_algorithm`, report segment errors.

    `expected` ([item_id, date, expected_qty], synthetic data only) adds the noise floor per fold: the MAE of the
    generator's noise-free demand, which no model can beat.
    """
    items = sorted(int(i) for i in items)
    df, _ = prepare_dataset(sales, holidays, promos, weather, items)
    item_cols = [f"item_{i}" for i in items]
    last = sales["date"].max()
    windows = fold_windows(last, n_folds, fold_days)
    if windows[0][0] < df["date"].min() + pd.Timedelta(days=MIN_TRAIN_DAYS):
        raise ValueError(f"Not enough history for {n_folds} folds of {fold_days} days: the first fold needs at least "
                         f"{MIN_TRAIN_DAYS} usable training days before it.")
    full_cols = BASE_FEATURES + item_cols

    # 1. Cross-validation of all candidates.
    splits = [_split(df, weather, start, end) for start, end in windows]
    folds = []
    for (start, end), (train, test) in zip(windows, splits):
        fold = {"test_start": str(start.date()), "test_end": str(end.date()),
                "train_end": str(train["date"].max().date()), "n_train": int(len(train)), "n_test": int(len(test)),
                "metrics": {}}
        for algo in ALGO_ORDER:
            pred = _fit_predict(algo, train, test, full_cols)
            fold["metrics"][algo] = metrics(test["y"], pred)
        if expected is not None and len(expected):
            exp = expected.assign(date=pd.to_datetime(expected["date"]))
            m = test[["item_id", "date", "y"]].merge(exp, on=["item_id", "date"])
            fold["noise_floor_mae"] = round(float((m["y"] - m["expected_qty"]).abs().mean()), 4) if len(m) else None
        winner = min(ALGO_ORDER, key=lambda a: (fold["metrics"][a]["mae"], ALGO_ORDER.index(a)))
        fold["winner"] = winner
        folds.append(fold)
    cv = {a: _summary([f["metrics"][a] for f in folds]) for a in ALGO_ORDER}
    for a in ALGO_ORDER:
        cv[a]["folds_beating_naive"] = sum(f["metrics"][a]["mae"] < f["metrics"]["naive_lag7"]["mae"] for f in folds)
        cv[a]["folds_won"] = sum(f["winner"] == a for f in folds)
    all_test = pd.concat([test for _, test in splits], ignore_index=True)

    # 2. Ablation of the chosen algorithm, on the same folds and on the standard 56-day hold-out.
    hold_start = last - pd.Timedelta(days=HOLDOUT_DAYS - 1)
    h_train, h_test = _split(df, weather, hold_start, last)
    ablation = []
    for name, cols in feature_sets():
        cols = cols + item_cols
        per_fold, preds = [], []
        for train, test in splits:
            p = _fit_predict(ablation_algorithm, train, test, cols)
            per_fold.append(metrics(test["y"], p))
            preds.append(p)
        hold_pred = _fit_predict(ablation_algorithm, h_train, h_test, cols)
        pooled_pred = np.concatenate(preds)
        ablation.append({"feature_set": name, "columns": cols[:len(cols) - len(item_cols)],
                         "cv": _summary(per_fold), "cv_folds": per_fold, "holdout": metrics(h_test["y"], hold_pred),
                         "segments": _segments(all_test, pooled_pred)})

    return {"algorithm_for_ablation": ablation_algorithm, "n_folds": n_folds, "fold_days": fold_days,
            "folds": folds, "cv": cv, "ablation": ablation,
            "segment_rows": {"holiday days": int(all_test[HOLIDAY].to_numpy().any(axis=1).sum()),
                             "promotion item-days": int((all_test["promo_discount_pct"] > 0).sum()),
                             "wet days": int((all_test["actual_rain_mm"] >= WET_DAY_MM).sum()),
                             "total": int(len(all_test))}}
