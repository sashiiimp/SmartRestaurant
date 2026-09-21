"""Train and compare candidates on a chronological hold-out (ML_PLAN section 5)."""
from dataclasses import dataclass, field

import numpy as np
import pandas as pd
import sklearn
import xgboost
from sklearn.ensemble import RandomForestRegressor
from xgboost import XGBRegressor

from app.ml.evaluate import metrics
from app.ml.features import LAGS, build_features, climatology, feature_columns
from app.ml.predict import BASELINES, predict

HOLDOUT_DAYS = 56
SEED = 42
ALGO_ORDER = ["naive_lag7", "seasonal_mean4", "random_forest", "xgboost"]  # ties go to the simpler model


def make_model(algorithm: str):
    if algorithm == "random_forest":
        return RandomForestRegressor(n_estimators=300, min_samples_leaf=3, n_jobs=-1, random_state=SEED)
    if algorithm == "xgboost":
        return XGBRegressor(n_estimators=300, max_depth=5, learning_rate=0.05, subsample=0.8, colsample_bytree=0.8,
                            random_state=SEED, n_jobs=2)
    raise ValueError(algorithm)


MODEL_PARAMS = {
    "random_forest": {"n_estimators": 300, "min_samples_leaf": 3, "random_state": SEED},
    "xgboost": {"n_estimators": 300, "max_depth": 5, "learning_rate": 0.05, "subsample": 0.8,
                "colsample_bytree": 0.8, "random_state": SEED},
    "naive_lag7": {}, "seasonal_mean4": {},
}


@dataclass
class TrainResult:
    algorithm: str
    artifact: dict
    beats_baseline: bool
    selection_reason: str
    metrics: dict
    holdout_start: pd.Timestamp
    holdout_end: pd.Timestamp
    train_start: pd.Timestamp
    train_end: pd.Timestamp
    n_train_rows: int
    feature_columns: list = field(default_factory=list)
    params: dict = field(default_factory=dict)


def train_and_compare(sales: pd.DataFrame, holidays: pd.DataFrame, promos: pd.DataFrame, weather: pd.DataFrame,
                      items, holdout_days: int = HOLDOUT_DAYS) -> TrainResult:
    items = sorted(int(i) for i in items)
    if sales.empty:
        raise ValueError("No sales history to train on.")
    last = sales["date"].max()
    first = sales["date"].min()
    dates = pd.date_range(first, last)
    full_clim = climatology(weather)
    df = build_features(sales, holidays, promos, weather, items, dates, items, full_clim, with_target=True, impute=False)
    lag_cols = [f"lag_{k}" for k in LAGS]
    df = df.dropna(subset=["y"] + lag_cols + ["roll_mean_7", "roll_mean_28"]).reset_index(drop=True)

    hold_start = last - pd.Timedelta(days=holdout_days - 1)
    if hold_start <= first + pd.Timedelta(days=60):
        raise ValueError(f"Need more history: at least {holdout_days + 90} days are required to train and evaluate.")
    train = df[df["date"] < hold_start].reset_index(drop=True)
    hold = df[df["date"] >= hold_start].reset_index(drop=True)
    if train.empty or hold.empty:
        raise ValueError("Not enough usable rows to train and evaluate.")

    # Honest evaluation: hold-out weather is the seasonal estimate built from the training period only, because
    # that is what the model sees when it forecasts tomorrow.
    train_weather = weather[pd.to_datetime(weather["date"]) < hold_start] if weather is not None and len(weather) else weather
    train_clim = climatology(train_weather)
    mon = hold["date"].dt.month
    hold["rain_mm"] = mon.map(train_clim["rain"]).fillna(train_clim["overall_rain"]).astype(float)
    hold["temp_c"] = mon.map(train_clim["temp"]).fillna(train_clim["overall_temp"]).astype(float)

    cols = feature_columns(items)
    X_train, y_train = train[cols].to_numpy(dtype=float), train["y"].to_numpy(dtype=float)
    preds, fitted = {}, {}
    for algo in ALGO_ORDER:
        if algo in BASELINES:
            preds[algo] = predict({"algorithm": algo}, hold)
        else:
            model = make_model(algo)
            model.fit(X_train, y_train)
            fitted[algo] = model
            preds[algo] = predict({"algorithm": algo, "model": model, "feature_columns": cols}, hold)

    overall = {a: metrics(hold["y"], preds[a]) for a in ALGO_ORDER}
    winner = min(ALGO_ORDER, key=lambda a: (overall[a]["mae"], ALGO_ORDER.index(a)))
    naive_mae = overall["naive_lag7"]["mae"]
    beats = overall[winner]["mae"] < naive_mae
    if winner in BASELINES:
        reason = f"No trained model beat the naive baseline on hold-out MAE; using {winner}."
    else:
        reason = (f"Lowest hold-out MAE ({overall[winner]['mae']:.2f}) vs naive_lag7 ({naive_mae:.2f}) "
                  f"over {holdout_days} days.")

    per_item = {}
    for item in items:
        mask = (hold["item_id"] == item).to_numpy()
        if mask.any():
            per_item[str(item)] = {"naive_lag7": metrics(hold.loc[mask, "y"], preds["naive_lag7"][mask]),
                                   winner: metrics(hold.loc[mask, "y"], preds[winner][mask])}

    # Refit the winning algorithm on all usable history for the shipped artifact.
    all_X = df[cols].to_numpy(dtype=float)
    all_y = df["y"].to_numpy(dtype=float)
    artifact = {"algorithm": winner, "feature_columns": cols, "item_ids": items, "model": None,
                "library_versions": {"sklearn": sklearn.__version__, "xgboost": xgboost.__version__,
                                     "pandas": pd.__version__, "numpy": np.__version__},
                "climatology": full_clim}
    importance = []
    if winner not in BASELINES:
        final = make_model(winner)
        final.fit(all_X, all_y)
        artifact["model"] = final
        imp = getattr(final, "feature_importances_", None)
        if imp is not None:
            importance = [{"feature": c, "importance": round(float(v), 4)}
                          for c, v in sorted(zip(cols, imp), key=lambda t: -t[1])[:12]]

    all_metrics = {"overall": overall, "per_item": per_item, "holdout_rows": int(len(hold)),
                   "oracle_mae": None, "feature_importance": importance}
    return TrainResult(algorithm=winner, artifact=artifact, beats_baseline=bool(beats), selection_reason=reason,
                       metrics=all_metrics, holdout_start=hold_start, holdout_end=last,
                       train_start=first, train_end=hold_start - pd.Timedelta(days=1), n_train_rows=int(len(train)),
                       feature_columns=cols, params=MODEL_PARAMS[winner])
