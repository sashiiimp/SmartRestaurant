"""Forecast runs, model training and versions. The ONLY caller of app/ml (ARCH section 6)."""
import logging
import os
import time
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from types import SimpleNamespace

import numpy as np
import pandas as pd

from app.extensions import db
from app.ml import registry
from app.ml.evaluate import oracle_mae
from app.ml.features import build_features
from app.ml.predict import BASELINES, predict
from app.ml.train import HOLDOUT_DAYS, train_and_compare
from app.models import Forecast, ForecastRun, MenuItem, ModelVersion
from app.models.base import utcnow
from app.services import audit, settings
from app.services import data_management_service as dm
from app.services.errors import NotFoundError, ValidationError
from app.utils.dates import today

log = logging.getLogger("smartrest")

ORACLE_PATH = "data/synthetic/oracle_expected.csv"


def _num(x):
    if isinstance(x, dict):
        return {str(k): _num(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_num(v) for v in x]
    if isinstance(x, (np.floating, np.integer)):
        return x.item()
    return x


def _q2(x) -> Decimal:
    return Decimal(str(round(float(x), 4))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _load_data(outlet_id: int) -> SimpleNamespace:
    return SimpleNamespace(sales=dm.load_sales_frame(outlet_id), holidays=dm.load_holidays_frame(outlet_id),
                           promos=dm.load_promotions_frame(outlet_id), weather=dm.load_weather_frame(outlet_id))


# ---- model versions (A16) --------------------------------------------------------------------
def get_active_model(outlet_id: int) -> ModelVersion | None:
    return ModelVersion.query.filter_by(outlet_id=outlet_id, status="active").first()


def list_model_versions(outlet_id: int) -> list[ModelVersion]:
    return ModelVersion.query.filter_by(outlet_id=outlet_id).order_by(ModelVersion.id.desc()).all()


def _next_label(outlet_id: int) -> str:
    stem = f"v{today():%Y%m%d}"
    n = ModelVersion.query.filter(ModelVersion.outlet_id == outlet_id, ModelVersion.version_label.like(f"{stem}-%")).count()
    return f"{stem}-{n + 1}"


def train_model(outlet_id: int, model_dir: str, actor_id: int | None = None, activate: bool = False,
                oracle_path: str | None = ORACLE_PATH) -> dict:
    data = _load_data(outlet_id)
    items = sorted(int(i) for i in data.sales["item_id"].unique()) if len(data.sales) else []
    if not items:
        raise ValidationError("There is no sales history to train on. Import or generate sales data first.",
                              code="no_data")
    try:
        result = train_and_compare(data.sales, data.holidays, data.promos, data.weather, items)
    except ValueError as e:
        raise ValidationError(str(e), code="not_enough_data")
    metrics = _num(result.metrics)
    if oracle_path and os.path.exists(oracle_path):
        exp = pd.read_csv(oracle_path, parse_dates=["date"])
        metrics["oracle_mae"] = oracle_mae(data.sales, exp, result.holdout_start)
    label = _next_label(outlet_id)
    path = registry.save_artifact(model_dir, label, result.artifact)
    mv = ModelVersion(
        outlet_id=outlet_id, version_label=label, algorithm=result.algorithm, status="trained",
        trained_at=utcnow(), train_start=result.train_start.date(), train_end=result.train_end.date(),
        holdout_start=result.holdout_start.date(), holdout_end=result.holdout_end.date(),
        n_train_rows=result.n_train_rows, feature_set={"columns": result.feature_columns},
        params=_num(result.params), metrics=metrics, beats_baseline=result.beats_baseline,
        selection_reason=result.selection_reason, artifact_path=os.path.abspath(path), created_by=actor_id)
    db.session.add(mv)
    db.session.flush()
    audit.record(outlet_id, actor_id, "model.train", "model_version", mv.id, {"algorithm": result.algorithm})
    db.session.commit()
    if activate:
        activate_model(outlet_id, mv.id, actor_id)
    overall = metrics["overall"]
    return {"version_id": mv.id, "version_label": label, "algorithm": result.algorithm,
            "beats_baseline": result.beats_baseline, "selection_reason": result.selection_reason,
            "holdout": {"start": mv.holdout_start.isoformat(), "end": mv.holdout_end.isoformat(),
                        "days": HOLDOUT_DAYS},
            "comparison": [{"model": name, **m} for name, m in overall.items()],
            "oracle_mae": metrics.get("oracle_mae"), "active": bool(activate)}


def activate_model(outlet_id: int, ref, actor_id: int | None = None) -> ModelVersion:
    """ref is a version id or label. The previous active version is kept as 'retired' for rollback."""
    q = ModelVersion.query.filter_by(outlet_id=outlet_id)
    mv = q.filter_by(id=int(ref)).first() if str(ref).isdigit() else q.filter_by(version_label=str(ref)).first()
    if not mv:
        raise NotFoundError("Model version not found.")
    if not mv.artifact_path or not os.path.exists(mv.artifact_path):
        raise ValidationError("The model file for this version is missing, so it cannot be activated.",
                              code="artifact_missing")
    for other in q.filter(ModelVersion.status == "active", ModelVersion.id != mv.id):
        other.status = "retired"
    mv.status = "active"
    audit.record(outlet_id, actor_id, "model.activate", "model_version", mv.id, {"label": mv.version_label})
    db.session.commit()
    registry.clear_cache()
    return mv


# ---- forecast runs (S1, S5) ------------------------------------------------------------------
def _summary(run: ForecastRun, model_label, duration_ms, items_total=0, missing_items=None) -> dict:
    return {"run_id": run.id, "status": run.status, "reason": run.reason, "as_of": run.as_of_date.isoformat(),
            "horizon_days": run.horizon_days, "model": model_label, "items_forecast": run.items_forecast,
            "items_total": items_total, "items_without_forecast": missing_items or [],
            "duration_ms": duration_ms}


def run_forecast(outlet_id: int, as_of: date | None = None, horizon: int | None = None, trigger: str = "cli",
                 use_estimated_weather: bool = False, actor_id: int | None = None, _data=None) -> dict:
    """Forecast every active item for as_of .. as_of+horizon-1 with the active model. Never trains."""
    started = time.perf_counter()
    as_of = as_of or today()
    horizon = horizon or settings.get_int(outlet_id, "forecast_horizon_days")
    run = ForecastRun(outlet_id=outlet_id, as_of_date=as_of, horizon_days=horizon, trigger_type=trigger,
                      status="running", created_by=actor_id)
    db.session.add(run)
    mv = get_active_model(outlet_id)
    if mv is None:
        run.status, run.reason, run.finished_at = "skipped", "No active model. Train and activate a model first.", utcnow()
        db.session.commit()
        return _summary(run, None, _ms(started))
    run.model_version_id = mv.id
    db.session.commit()
    run_id = run.id
    try:
        summary = _do_run(outlet_id, run, mv, as_of, horizon, use_estimated_weather, _data)
        summary["duration_ms"] = _ms(started)
        return summary
    except Exception as exc:  # readable message for the user, full trace in the log (NFR3)
        log.exception("Forecast run %s failed", run_id)
        db.session.rollback()
        failed = db.session.get(ForecastRun, run_id)
        failed.status, failed.finished_at = "failed", utcnow()
        failed.reason = ("The forecast could not be generated: " + str(exc))[:250]
        db.session.commit()
        return _summary(failed, mv.version_label, _ms(started))


def _ms(started) -> int:
    return int((time.perf_counter() - started) * 1000)


def _do_run(outlet_id, run, mv, as_of, horizon, use_estimated_weather, data) -> dict:
    artifact = registry.load_active(mv.id, mv.artifact_path)
    data = data or _load_data(outlet_id)
    sales = data.sales[data.sales["date"] < pd.Timestamp(as_of)]
    items = [m for m in MenuItem.query.filter_by(outlet_id=outlet_id, is_active=True).order_by(MenuItem.id)]
    item_ids = [m.id for m in items]
    dates = [as_of + timedelta(days=i) for i in range(horizon)]
    min_hist = settings.get_int(outlet_id, "min_history_days")
    hist_days = sales.groupby("item_id")["date"].nunique().to_dict()

    feats = build_features(sales, data.holidays, data.promos, data.weather, item_ids, dates, artifact["item_ids"],
                           artifact["climatology"], force_estimated=use_estimated_weather)
    algo = artifact["algorithm"]
    in_model = set(artifact["item_ids"])

    def route(item_id):
        h = hist_days.get(item_id, 0)
        if algo in BASELINES:
            return algo if h >= 7 else None
        if item_id in in_model and h >= min_hist:
            return "model"
        return "naive_lag7" if h >= 7 else None

    feats["route"] = feats["item_id"].map(route)
    feats = feats[feats["route"].notna()].copy()
    feats["pred"] = 0.0
    for r in feats["route"].unique():
        mask = feats["route"] == r
        art = artifact if r == "model" else {"algorithm": r}
        feats.loc[mask, "pred"] = predict(art, feats[mask])

    now = utcnow()
    rows = []
    for rec in feats.itertuples(index=False):
        rows.append({
            "outlet_id": outlet_id, "run_id": run.id, "model_version_id": mv.id, "menu_item_id": int(rec.item_id),
            "target_date": rec.date.date(), "predicted_qty": _q2(rec.pred),
            "method": "model" if rec.route == "model" else "baseline",
            "input_snapshot": {"is_public_holiday": int(rec.is_public_holiday), "is_poya": int(rec.is_poya),
                               "is_school_holiday": int(rec.is_school_holiday),
                               "promo_discount_pct": float(rec.promo_discount_pct), "rain_mm": round(float(rec.rain_mm), 1),
                               "temp_c": round(float(rec.temp_c), 1), "weather_estimated": bool(rec.weather_estimated),
                               "lags_imputed": bool(rec.lags_imputed)},
            "generated_at": now, "is_latest": True})
    if rows:
        Forecast.query.filter(Forecast.outlet_id == outlet_id, Forecast.menu_item_id.in_({r["menu_item_id"] for r in rows}),
                              Forecast.target_date.in_({r["target_date"] for r in rows}),
                              Forecast.is_latest.is_(True)).update({"is_latest": False}, synchronize_session=False)
        db.session.bulk_insert_mappings(Forecast, rows)

    forecast_items = {r["menu_item_id"] for r in rows}
    missing = [m.name for m in items if m.id not in forecast_items]
    all_model = all(r["method"] == "model" for r in rows) and algo not in BASELINES
    run.items_forecast = len(forecast_items)
    run.finished_at = utcnow()
    if not rows:
        run.status, run.reason = "skipped", "No item has enough sales history to forecast."
    elif missing:
        run.status = "partial"
        run.reason = "Not enough history for: " + ", ".join(missing)
    else:
        run.status = "ok"
        if not all_model:
            run.reason = "Simple estimate (same day last week) used for some or all items."
    db.session.commit()
    return _summary(run, mv.version_label, 0, len(items), missing)


def backfill(outlet_id: int, start: date, end: date, actor_id: int | None = None) -> dict:
    """One single-day run per past date, so forecast-vs-actual has out-of-sample history (ML_PLAN section 7)."""
    if end >= today():
        raise ValidationError("Backfill can only cover past dates.", {"to": "must be before today"})
    if end < start:
        raise ValidationError("Please fix the highlighted fields.", {"to": "must not be before the start date"})
    data = _load_data(outlet_id)
    counts = {"ok": 0, "partial": 0, "skipped": 0, "failed": 0}
    d = start
    while d <= end:
        r = run_forecast(outlet_id, as_of=d, horizon=1, trigger="backfill", use_estimated_weather=True,
                         actor_id=actor_id, _data=data)
        counts[r["status"]] = counts.get(r["status"], 0) + 1
        d += timedelta(days=1)
    return {"days": (end - start).days + 1, **counts}


# ---- reading forecasts (K2, S1) --------------------------------------------------------------
def get_forecasts(outlet_id: int, start: date, end: date, item_id: int | None = None) -> dict:
    q = (db.session.query(Forecast, MenuItem.name).join(MenuItem, MenuItem.id == Forecast.menu_item_id)
         .filter(Forecast.outlet_id == outlet_id, Forecast.is_latest.is_(True),
                 Forecast.target_date >= start, Forecast.target_date <= end))
    if item_id:
        q = q.filter(Forecast.menu_item_id == item_id)
    rows, have_dates = [], set()
    for f, name in q.order_by(Forecast.target_date, Forecast.menu_item_id).all():
        have_dates.add(f.target_date)
        snap = f.input_snapshot or {}
        rows.append({"menu_item_id": f.menu_item_id, "item": name, "date": f.target_date.isoformat(),
                     "predicted_qty": float(f.predicted_qty), "method": f.method,
                     "model_version": f.model_version.version_label if f.model_version else None,
                     "generated_at": f.generated_at.isoformat() + "Z",
                     "weather_estimated": bool(snap.get("weather_estimated")), "rain_mm": snap.get("rain_mm"),
                     "is_poya": bool(snap.get("is_poya")), "is_public_holiday": bool(snap.get("is_public_holiday")),
                     "promo_discount_pct": snap.get("promo_discount_pct", 0)})
    all_days = [start + timedelta(days=i) for i in range((end - start).days + 1)]
    missing = [d.isoformat() for d in all_days if d not in have_dates]
    active = get_active_model(outlet_id)
    last = ForecastRun.query.filter_by(outlet_id=outlet_id).order_by(ForecastRun.id.desc()).first()
    latest_date = db.session.query(db.func.max(Forecast.target_date)).filter(
        Forecast.outlet_id == outlet_id, Forecast.is_latest.is_(True)).scalar()
    meta = {"active_model": (f"{active.version_label} ({active.algorithm})" if active else None),
            "last_run": None if not last else {"status": last.status, "reason": last.reason,
                                               "as_of": last.as_of_date.isoformat()},
            "missing_dates": missing, "last_forecast_date": latest_date.isoformat() if latest_date else None}
    return {"rows": rows, "meta": meta}


def forecast_map(outlet_id: int, start: date, end: date) -> dict:
    """{(menu_item_id, date): {"qty": Decimal, "id": forecast id, "method": ..., "weather_estimated": bool}} (latest)."""
    out = {}
    for f in Forecast.query.filter(Forecast.outlet_id == outlet_id, Forecast.is_latest.is_(True),
                                   Forecast.target_date >= start, Forecast.target_date <= end):
        out[(f.menu_item_id, f.target_date)] = {"qty": f.predicted_qty, "id": f.id, "method": f.method,
                                                "weather_estimated": bool((f.input_snapshot or {}).get("weather_estimated"))}
    return out


def list_runs(outlet_id: int, limit: int = 30) -> list[dict]:
    rows = ForecastRun.query.filter_by(outlet_id=outlet_id).order_by(ForecastRun.id.desc()).limit(limit).all()
    return [{"id": r.id, "as_of": r.as_of_date.isoformat(), "horizon_days": r.horizon_days, "trigger": r.trigger_type,
             "status": r.status, "reason": r.reason, "items_forecast": r.items_forecast,
             "model": r.model_version.version_label if r.model_version else None,
             "started_at": r.started_at.isoformat() + "Z"} for r in rows]


def model_version_dict(mv: ModelVersion) -> dict:
    overall = (mv.metrics or {}).get("overall", {})
    return {"id": mv.id, "version_label": mv.version_label, "algorithm": mv.algorithm, "status": mv.status,
            "trained_at": mv.trained_at.isoformat() + "Z", "beats_baseline": mv.beats_baseline,
            "selection_reason": mv.selection_reason,
            "holdout": {"start": mv.holdout_start.isoformat() if mv.holdout_start else None,
                        "end": mv.holdout_end.isoformat() if mv.holdout_end else None},
            "metrics": {"comparison": [{"model": k, **v} for k, v in overall.items()],
                        "oracle_mae": (mv.metrics or {}).get("oracle_mae"),
                        "feature_importance": (mv.metrics or {}).get("feature_importance", [])}}
