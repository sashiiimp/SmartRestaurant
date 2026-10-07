"""Supplementary research evaluation (docs/ML_EVALUATION_SUPPLEMENT.md). Read-only; nothing is stored or activated.

Four analyses that the main evaluation (ML_EVALUATION.md) does not contain:

1. Policy simulation on the active model's hold-out: preparation quantities from the synthetic history, from naive
   and seasonal baselines and from the backfilled model forecasts, each turned into a quantity with the production
   formula (recommendation_service.compute_recommended) at several safety buffers, scored for waste and stock-outs.
2. Error by forecast horizon (1 to 14 days ahead) with the model copy fitted before the hold-out.
3. Diebold-Mariano tests on daily loss differentials (absolute error), hold-out and pooled cross-validation days.
4. Robustness across synthetic-data seeds: each seed is generated into its own in-memory SQLite database (the live
   database is never written), then trained, cross-validated and ablated with the same code as `flask smartrest
   evaluate`.

Parts 1 to 3 read the configured database (the demo data). Run from the project folder as the app user:
    runuser -u smartrest -- .venv/bin/python scripts/research_supplement.py --json /tmp/out.json [--seeds 42,7,123]
"""
import argparse
import json
import os
import sys
import tempfile
import time
import warnings
from datetime import date, timedelta
from decimal import Decimal

import numpy as np
import pandas as pd
from scipy import stats

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
warnings.filterwarnings("ignore")

from app import create_app  # noqa: E402

BUFFERS = (0, 5, 10, 15, 20, 30)
HORIZONS = 14
SEED_START, SEED_END = date(2024, 9, 1), date(2026, 10, 3)   # the demo history (ML_EVALUATION.md section 1)


# ---- statistics --------------------------------------------------------------------------------------------------
def dm_test(diff, h: int = 1) -> dict:
    """Diebold-Mariano test on a loss-differential series (A minus B; negative mean = A better), with a Newey-West
    (Bartlett) long-run variance and the Harvey, Leybourne and Newbold small-sample correction; two-sided t p-value."""
    d = np.asarray(diff, dtype=float)
    n = len(d)
    mean = d.mean()
    lag = int(np.floor(n ** (1 / 3)))
    dev = d - mean
    # autocovariances divided by n (not n - k), as in Newey and West (1987), which keeps the variance non-negative
    var = (dev @ dev) / n + 2 * sum((1 - k / (lag + 1)) * (dev[k:] @ dev[:-k]) / n for k in range(1, lag + 1))
    stat = mean / np.sqrt(var / n) * np.sqrt((n + 1 - 2 * h + h * (h - 1) / n) / n)
    return {"mean_diff": round(float(mean), 4), "dm": round(float(stat), 3),
            "p_value": float(f"{2 * stats.t.sf(abs(stat), n - 1):.3g}"), "days": n, "nw_lag": lag}


def daily_abs_error(frame: pd.DataFrame, pred_col: str) -> pd.Series:
    """Mean absolute error across items, per day."""
    return (frame[pred_col] - frame["y"]).abs().groupby(frame["date"]).mean()


# ---- 1 to 3: the demo data ---------------------------------------------------------------------------------------
def live_analyses() -> dict:
    from app.extensions import db
    from app.ml import registry
    from app.ml.features import build_features, climatology
    from app.models import Forecast, ForecastRun, MenuItem, PreparationRecord
    from app.services import forecasting_service as fs
    from app.services.recommendation_service import compute_recommended

    mv = fs.get_active_model(1)
    art = registry.load_artifact(mv.artifact_path)
    hs, he = mv.holdout_start, mv.holdout_end
    data = fs._load_data(1)
    sales = data.sales
    items = {m.id: m for m in MenuItem.query.filter_by(outlet_id=1)}

    # actual demand (synthetic sales are not limited by stock), history-based baselines, backfilled model forecasts
    hold = sales[(sales["date"] >= pd.Timestamp(hs)) & (sales["date"] <= pd.Timestamp(he))].rename(columns={"qty": "y"})
    by = sales.set_index(["item_id", "date"])["qty"]

    def lag(df, k):
        return [by.get((i, d - pd.Timedelta(days=k)), np.nan) for i, d in zip(df["item_id"], df["date"])]

    hold = hold.assign(naive=lag(hold, 7))
    hold = hold.assign(seasonal=np.nanmean(np.column_stack([lag(hold, k) for k in (7, 14, 21, 28)]), axis=1))
    rows = (db.session.query(Forecast.menu_item_id, Forecast.target_date, Forecast.predicted_qty, Forecast.run_id)
            .join(ForecastRun, ForecastRun.id == Forecast.run_id)
            .filter(ForecastRun.trigger_type == "backfill", ForecastRun.status.in_(("ok", "partial")),
                    Forecast.target_date >= hs, Forecast.target_date <= he).order_by(Forecast.run_id).all())
    model = {(m, pd.Timestamp(d)): float(q) for m, d, q, _ in rows}   # later runs win, as in the accuracy view
    hold = hold.assign(model=[model.get((i, d), np.nan) for i, d in zip(hold["item_id"], hold["date"])])
    prep = {(m, pd.Timestamp(d)): int(q) for m, d, q in db.session.query(
        PreparationRecord.menu_item_id, PreparationRecord.prep_date, db.func.sum(PreparationRecord.quantity))
        .filter(PreparationRecord.prep_date >= hs, PreparationRecord.prep_date <= he)
        .group_by(PreparationRecord.menu_item_id, PreparationRecord.prep_date)}
    hold = hold.assign(history=[prep.get((i, d), np.nan) for i, d in zip(hold["item_id"], hold["date"])])
    hold = hold.dropna(subset=["naive", "seasonal", "model", "history"]).reset_index(drop=True)

    def score(qty: np.ndarray) -> dict:
        y = hold["y"].to_numpy(dtype=float)
        price = np.array([float(items[i].price) for i in hold["item_id"]])
        waste, short = np.maximum(qty - y, 0), np.maximum(y - qty, 0)
        return {"prepared": int(qty.sum()), "waste": int(waste.sum()), "waste_pct_of_prepared": round(100 * waste.sum() / qty.sum(), 2),
                "waste_value_lkr": round(float((waste * price).sum()), 0), "short": int(short.sum()),
                "short_pct_of_demand": round(100 * short.sum() / y.sum(), 2),
                "item_days_short_pct": round(100 * float((short > 0).mean()), 1),
                "fill_rate_pct": round(100 * (y - short).sum() / y.sum(), 2)}

    def policy(col: str, buffer: int) -> np.ndarray:
        return np.array([compute_recommended(Decimal(str(round(f, 2))), Decimal(buffer), 0, items[i].batch_size)
                         for i, f in zip(hold["item_id"], hold[col])], dtype=float)

    sim = {"history (synthetic preparation records)": score(hold["history"].to_numpy(dtype=float))}
    for col, label in (("naive", "naive same weekday last week"), ("seasonal", "mean of last 4 same weekdays"),
                       ("model", "model (backfilled eval forecasts)")):
        for b in BUFFERS:
            sim[f"{label} + {b}%"] = score(policy(col, b))

    # error by horizon: forecasts made at each origin with only the sales before it, as in production
    clim = climatology(data.weather[pd.to_datetime(data.weather["date"]) < pd.Timestamp(hs)])
    eval_art = {**art, "model": art["eval_model"]}
    from app.ml.predict import predict
    per_h = {h: [] for h in range(1, HORIZONS + 1)}
    imputed = {h: [] for h in range(1, HORIZONS + 1)}
    origin = pd.Timestamp(hs)
    while origin + pd.Timedelta(days=HORIZONS - 1) <= pd.Timestamp(he):
        past = sales[sales["date"] < origin]
        dates = [origin + pd.Timedelta(days=k) for k in range(HORIZONS)]
        f = build_features(past, data.holidays, data.promos, data.weather, art["item_ids"], dates, art["item_ids"], clim,
                           force_estimated=True)
        f["pred"] = predict(eval_art, f)
        f = f.merge(sales.rename(columns={"qty": "y"}), on=["item_id", "date"])
        for h in range(1, HORIZONS + 1):
            part = f[f["date"] == origin + pd.Timedelta(days=h - 1)]
            per_h[h].extend((part["pred"] - part["y"]).abs().tolist())
            imputed[h].extend(part["lags_imputed"].tolist())
        origin += pd.Timedelta(days=1)
    horizon = [{"h": h, "mae": round(float(np.mean(v)), 3), "n": len(v), "lags_imputed_pct": round(100 * float(np.mean(imputed[h])), 1)}
               for h, v in per_h.items()]

    # Diebold-Mariano on the hold-out: the backfilled model against each baseline
    dm = {f"model vs {b}": dm_test(daily_abs_error(hold, "model") - daily_abs_error(hold, b)) for b in ("naive", "seasonal")}
    return {"holdout": [str(hs), str(he)], "item_days": int(len(hold)), "model_version": mv.version_label,
            "policy_simulation": sim, "horizon": horizon, "dm_holdout": dm}


# ---- 4: other seeds ----------------------------------------------------------------------------------------------
def seed_analysis(seed: int) -> dict:
    from app.extensions import db
    from app.ml import experiments as ex
    from app.ml.features import BASE_FEATURES
    from app.ml.train import ALGO_ORDER, prepare_dataset, train_and_compare
    from app.seed.generate import generate
    from app.seed.seeder import seed_base
    from app.services import forecasting_service as fs

    app = create_app("test", {"SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})
    with app.app_context(), tempfile.TemporaryDirectory() as out:
        db.create_all()
        seed_base()
        generate(1, SEED_START, SEED_END, seed=seed, out_dir=out)
        data = fs._load_data(1)
        expected = pd.read_csv(os.path.join(out, "oracle_expected.csv"), parse_dates=["date"])
        items = sorted(int(i) for i in data.sales["item_id"].unique())
        tr = train_and_compare(data.sales, data.holidays, data.promos, data.weather, items)
        res = ex.run_experiments(data.sales, data.holidays, data.promos, data.weather, items, expected=expected)
        # pooled cross-validation days for the significance tests (same folds and fits as run_experiments)
        df, _ = prepare_dataset(data.sales, data.holidays, data.promos, data.weather, items)
        cols = BASE_FEATURES + [f"item_{i}" for i in items]
        pooled = []
        for start, end in ex.fold_windows(data.sales["date"].max()):
            train, test = ex._split(df, data.weather, start, end)
            for algo in ALGO_ORDER:
                test[algo] = ex._fit_predict(algo, train, test, cols)
            pooled.append(test)
        pooled = pd.concat(pooled, ignore_index=True)
        err = {a: daily_abs_error(pooled, a) for a in ALGO_ORDER}
        dm = {"xgboost vs random_forest": dm_test(err["xgboost"] - err["random_forest"]),
              "xgboost vs naive_lag7": dm_test(err["xgboost"] - err["naive_lag7"]),
              "random_forest vs naive_lag7": dm_test(err["random_forest"] - err["naive_lag7"])}
        abl = res["ablation"]
        steps = {}
        for prev, cur in zip(abl, abl[1:]):
            steps[cur["feature_set"]] = {
                "folds_improved": sum(c["mae"] < p["mae"] for p, c in zip(prev["cv_folds"], cur["cv_folds"])),
                "cv_mae_change": round(cur["cv"]["mae_mean"] - prev["cv"]["mae_mean"], 3)}
        return {"seed": seed, "winner": tr.algorithm,
                "holdout_mae": {a: m["mae"] for a, m in tr.metrics["overall"].items()},
                "holdout_wape": {a: m["wape"] for a, m in tr.metrics["overall"].items()},
                "cv": {a: {"mae_mean": s["mae_mean"], "mae_std": s["mae_std"], "folds_won": s["folds_won"],
                           "folds_beating_naive": s["folds_beating_naive"]} for a, s in res["cv"].items()},
                "noise_floor_cv": round(float(np.mean([f["noise_floor_mae"] for f in res["folds"]])), 3),
                "ablation_steps": steps, "dm_cv": dm}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--json", required=True)
    p.add_argument("--seeds", default="42,7,123,2024,31337")
    p.add_argument("--skip-live", action="store_true")
    a = p.parse_args()
    os.environ["SMARTREST_FAST_HASH"] = "1"   # in-memory seed users only; scrypt is deliberately slow
    out = {"generated": time.strftime("%Y-%m-%d %H:%M"), "note": "synthetic data; supplementary, read-only analyses"}
    if not a.skip_live:
        app = create_app()
        with app.app_context():
            t = time.time(); out["live"] = live_analyses(); print(f"live analyses {time.time() - t:.0f}s", flush=True)
    out["seeds"] = []
    for s in [int(x) for x in a.seeds.split(",") if x]:
        t = time.time(); out["seeds"].append(seed_analysis(s)); print(f"seed {s} {time.time() - t:.0f}s", flush=True)
    with open(a.json, "w") as fh:
        json.dump(out, fh, indent=1, default=str)
    print("written", a.json)


if __name__ == "__main__":
    main()
