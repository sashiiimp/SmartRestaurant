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
from app.ml import experiments, registry
from app.ml.evaluate import metrics, oracle_mae
from app.ml.experiments import FOLD_DAYS, FOLDS
from app.ml.features import build_features
from app.ml.predict import BASELINES, predict
from app.ml.train import HOLDOUT_DAYS, train_and_compare
from app.models import Forecast, ForecastRun, Holiday, MenuItem, ModelVersion, Outlet
from app.models.base import utcnow
from app.services import audit, settings
from app.services import data_management_service as dm
from app.services.errors import NotFoundError, ValidationError
from app.services.validation import Fields
from app.utils.dates import today

log = logging.getLogger("smartrest")

ORACLE_PATH = "data/synthetic/oracle_expected.csv"
MAX_HORIZON_DAYS = 14  # a short-term forecast (FR4); lags beyond 7 days ahead are already imputed
MAX_RUNS_LISTED = 200
MAX_FORECAST_RANGE_DAYS = 62  # the pages ask for 7 days; the cap stops one request listing millions of missing dates
DAILY_MAX_FAILURES = 3      # the scheduled run stops retrying for the day after this many failed runs
STALE_RUN_MINUTES = 30      # a run still marked running after this long is treated as crashed, not in progress


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


def run_experiments(outlet_id: int, n_folds: int = FOLDS, fold_days: int = FOLD_DAYS,
                    oracle_path: str | None = ORACLE_PATH) -> dict:
    """Cross-validation, feature ablation and segment errors (ML_EVALUATION.md). Read-only: stores nothing."""
    if n_folds < 2 or fold_days < 7:
        raise ValidationError("Use at least 2 folds of at least 7 days.", code="invalid_folds")
    data = _load_data(outlet_id)
    items = sorted(int(i) for i in data.sales["item_id"].unique()) if len(data.sales) else []
    if not items:
        raise ValidationError("There is no sales history to evaluate. Import or generate sales data first.",
                              code="no_data")
    expected = pd.read_csv(oracle_path, parse_dates=["date"]) if oracle_path and os.path.exists(oracle_path) else None
    try:
        result = experiments.run_experiments(data.sales, data.holidays, data.promos, data.weather, items,
                                             n_folds=n_folds, fold_days=fold_days, expected=expected)
    except ValueError as e:
        raise ValidationError(str(e), code="not_enough_data")
    names = {m.id: m.name for m in MenuItem.query.filter_by(outlet_id=outlet_id)}
    result["items"] = [names.get(i, str(i)) for i in items]
    result["data_end"] = data.sales["date"].max().date().isoformat()
    return _num(result)


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
    if as_of > today():
        raise ValidationError("A forecast run cannot start in the future.", {"as_of": "must not be after today"})
    if as_of < today() and trigger != "backfill":
        # The shipped model was refit on all history, so it has seen the sales of every past day: a forecast for one
        # would be in-sample and flatter the accuracy figures. Past days are covered by the backfill instead.
        raise ValidationError("A forecast for a past date would come from a model that has already seen that day's sales. "
                              "Use the backfill for past dates.", {"as_of": "must be today (use the backfill for past dates)"})
    if horizon is None:
        horizon = settings.get_int(outlet_id, "forecast_horizon_days")
    else:  # checked before the run row exists, so a bad value never shows up as a failed run or an alert
        f = Fields({"horizon_days": horizon})
        horizon = f.integer("horizon_days", min=1, max=MAX_HORIZON_DAYS)
        f.check()
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
        summary = _do_run(outlet_id, run, mv, as_of, horizon, use_estimated_weather, _data,
                          use_eval_model=(trigger == "backfill"))
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


def _do_run(outlet_id, run, mv, as_of, horizon, use_estimated_weather, data, use_eval_model=False) -> dict:
    artifact = registry.load_active(mv.id, mv.artifact_path)
    if use_eval_model and artifact.get("eval_model") is not None:
        # Backfill uses the copy fitted on the training period only, so forecasts for the hold-out days are
        # genuinely out-of-sample. The shipped model was refit on all history and has seen those days.
        artifact = {**artifact, "model": artifact["eval_model"]}
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
        # Two runs at once (the daily timer and the "Run forecast now" button) would each flip the old rows and leave
        # two "latest" rows per item and day. Locking the outlet row makes the second run wait and then replace the first.
        db.session.query(Outlet).filter(Outlet.id == outlet_id).with_for_update().one()
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


def run_daily_forecast(outlet_id: int) -> dict:
    """The scheduled run (deploy/systemd/smartrest-forecast.timer calls `flask smartrest forecast-daily` every hour).
    It forecasts today and the next six days once per Asia/Colombo day and is safe to call any number of times:
    it does nothing when today's forecast already succeeded with the active model (from an earlier timer run or the
    "Run forecast now" button), when another run for today is still in progress, or after 3 failed runs today."""
    day = today()
    mv = get_active_model(outlet_id)
    if mv is None:
        log.warning("Daily forecast for %s not run: no active model", day)
        return {"action": "not_run", "reason": "No active model. Train and activate a model first.", "as_of": day.isoformat()}
    horizon = settings.get_int(outlet_id, "forecast_horizon_days")
    runs = ForecastRun.query.filter(ForecastRun.outlet_id == outlet_id, ForecastRun.as_of_date == day,
                                    ForecastRun.trigger_type != "backfill").all()
    if any(r.status in ("ok", "partial") and r.model_version_id == mv.id and r.horizon_days >= horizon for r in runs):
        return {"action": "already_done", "as_of": day.isoformat()}
    cutoff = utcnow() - timedelta(minutes=STALE_RUN_MINUTES)
    if any(r.status == "running" and r.created_at >= cutoff for r in runs):
        log.info("Daily forecast for %s not started: another run is in progress", day)
        return {"action": "in_progress", "as_of": day.isoformat()}
    failures = sum(1 for r in runs if r.status == "failed")
    if failures >= DAILY_MAX_FAILURES:
        log.error("Daily forecast for %s not retried: %s runs failed today. Check the log, then use Run forecast now",
                  day, failures)
        return {"action": "gave_up", "failures": failures, "as_of": day.isoformat()}
    log.info("Daily forecast for %s starting (model %s)", day, mv.version_label)
    r = run_forecast(outlet_id, as_of=day, horizon=horizon, trigger="cli")
    level = logging.ERROR if r["status"] in ("failed", "skipped") else logging.INFO
    log.log(level, "Daily forecast for %s finished: %s, %s items, %s ms%s", day, r["status"], r["items_forecast"],
            r["duration_ms"], f" ({r['reason']})" if r["reason"] else "")
    return {"action": "ran", **r}


def _check_backfill_out_of_sample(outlet_id: int, start: date) -> None:
    """Backfill forecasts with the copy of the model fitted before its hold-out. Days before the hold-out were part of
    that copy's training data, so forecasts for them would be in-sample; they are refused rather than mixed in."""
    mv = get_active_model(outlet_id)
    if mv is None or mv.algorithm in BASELINES:
        return  # nothing trained (the run is skipped) or a baseline, which learns nothing from past sales
    artifact = registry.load_active(mv.id, mv.artifact_path)
    if artifact.get("eval_model") is None:
        first_unseen = mv.holdout_end + timedelta(days=1) if mv.holdout_end else today()
    else:
        first_unseen = mv.holdout_start
    if first_unseen and start < first_unseen:
        raise ValidationError("Please fix the highlighted fields.",
                              {"from": f"must not be before {first_unseen.isoformat()}: the active model was trained "
                                       f"on earlier days, so their forecasts would not be out-of-sample"})


def backfill(outlet_id: int, start: date, end: date, actor_id: int | None = None) -> dict:
    """One single-day run per past date, so forecast-vs-actual has out-of-sample history (ML_PLAN section 7)."""
    if end >= today():
        raise ValidationError("Backfill can only cover past dates.", {"to": "must be before today"})
    if end < start:
        raise ValidationError("Please fix the highlighted fields.", {"to": "must not be before the start date"})
    _check_backfill_out_of_sample(outlet_id, start)
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
    if end < start:
        raise ValidationError("Please fix the highlighted fields.", {"to": "must not be before the start date"})
    if (end - start).days + 1 > MAX_FORECAST_RANGE_DAYS:
        raise ValidationError("Please fix the highlighted fields.",
                              {"to": f"range is too long (max {MAX_FORECAST_RANGE_DAYS} days)"})
    # Forecasts from a run dated after today (e.g. left over from a demo clock override) are never shown.
    q = (db.session.query(Forecast, MenuItem.name).join(MenuItem, MenuItem.id == Forecast.menu_item_id)
         .join(ForecastRun, ForecastRun.id == Forecast.run_id)
         .filter(Forecast.outlet_id == outlet_id, Forecast.is_latest.is_(True), ForecastRun.as_of_date <= today(),
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
    # A run can never be "later" than the date being viewed or than today, whichever is earlier.
    cap = min(start, today())
    last = (ForecastRun.query.filter(ForecastRun.outlet_id == outlet_id, ForecastRun.as_of_date <= cap)
            .order_by(ForecastRun.as_of_date.desc(), ForecastRun.id.desc()).first())
    latest_date = (db.session.query(db.func.max(Forecast.target_date)).join(ForecastRun, ForecastRun.id == Forecast.run_id)
                   .filter(Forecast.outlet_id == outlet_id, Forecast.is_latest.is_(True),
                           ForecastRun.as_of_date <= today()).scalar())
    meta = {"active_model": (f"{active.version_label} ({active.algorithm})" if active else None),
            "last_run": None if not last else {"status": last.status, "reason": last.reason,
                                               "as_of": last.as_of_date.isoformat()},
            "missing_dates": missing, "last_forecast_date": latest_date.isoformat() if latest_date else None}
    # The holiday features read the imported calendar; past its last date every day looks like an ordinary day.
    cal_end = db.session.query(db.func.max(Holiday.holiday_date)).filter(Holiday.outlet_id == outlet_id).scalar()
    meta["holiday_calendar_ends"] = cal_end.isoformat() if cal_end else None
    meta["beyond_holiday_calendar"] = cal_end is None or end > cal_end
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
    # Same rule as get_forecasts: a run dated after today (leftover from a demo clock override) is never listed.
    rows = (ForecastRun.query.filter(ForecastRun.outlet_id == outlet_id, ForecastRun.as_of_date <= today())
            .order_by(ForecastRun.id.desc()).limit(min(max(limit, 1), MAX_RUNS_LISTED)).all())
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


# ---- forecast accuracy (A9) ----------------------------------------------------------------------
def accuracy(outlet_id: int, start: date, end: date, item_id: int | None = None) -> dict:
    """Actual vs the latest forecast whose run has as_of_date <= target date, so a forecast made after the fact never
    counts (DATABASE.md 2.6). Reports MAE, RMSE, MAPE, WAPE, bias overall and per item, plus a daily series."""
    from app.models import SalesRecord

    fq = (db.session.query(Forecast.menu_item_id, Forecast.target_date, Forecast.predicted_qty, Forecast.run_id,
                           ForecastRun.trigger_type)
          .join(ForecastRun, ForecastRun.id == Forecast.run_id)
          .filter(Forecast.outlet_id == outlet_id, Forecast.target_date >= start, Forecast.target_date <= end,
                  ForecastRun.as_of_date <= Forecast.target_date, ForecastRun.status.in_(("ok", "partial"))))
    if item_id:
        fq = fq.filter(Forecast.menu_item_id == item_id)
    best: dict = {}
    for mid, d, qty, run_id, trig in fq.order_by(Forecast.run_id):
        best[(mid, d)] = (float(qty), trig)          # later runs overwrite earlier ones
    sq = db.session.query(SalesRecord.menu_item_id, SalesRecord.sale_date, SalesRecord.quantity_sold).filter(
        SalesRecord.outlet_id == outlet_id, SalesRecord.sale_date >= start, SalesRecord.sale_date <= end)
    actual = {(m, d): q for m, d, q in sq}
    names = {m.id: m.name for m in MenuItem.query.filter_by(outlet_id=outlet_id)}
    keys = sorted(k for k in best if k in actual)
    if not keys:
        return {"overall": None, "per_item": [], "series": [], "error_series": [], "pairs": 0,
                "note": "No forecast has a matching actual sale yet."}
    yt = [actual[k] for k in keys]
    yp = [best[k][0] for k in keys]
    overall = _num(metrics(yt, yp))
    per_item = []
    for mid in sorted({k[0] for k in keys}, key=lambda i: names.get(i, "")):
        ks = [k for k in keys if k[0] == mid]
        per_item.append({"menu_item_id": mid, "item": names.get(mid, str(mid)),
                         **_num(metrics([actual[k] for k in ks], [best[k][0] for k in ks]))})
    by_day: dict = {}
    for k in keys:
        f, a = by_day.get(k[1], (0.0, 0))
        by_day[k[1]] = (f + best[k][0], a + actual[k])
    series = [{"date": d.isoformat(), "forecast": round(f, 1), "actual": a} for d, (f, a) in sorted(by_day.items())]
    # error by day across the items forecast that day: mean absolute error per item and WAPE (share of the day's sales)
    day_err: dict = {}
    for k in keys:
        e = day_err.setdefault(k[1], [0.0, 0.0, 0])
        e[0] += abs(best[k][0] - actual[k]); e[1] += actual[k]; e[2] += 1
    error_series = [{"date": d.isoformat(), "mae": round(a / n, 2), "wape": round(a / act * 100, 1) if act > 0 else None}
                    for d, (a, act, n) in sorted(day_err.items())]
    sources = sorted({best[k][1] for k in keys})
    return {"overall": overall, "per_item": per_item, "series": series, "error_series": error_series, "pairs": len(keys),
            "run_types": sources}
