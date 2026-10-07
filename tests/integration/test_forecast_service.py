"""ML-6, ML-7, ML-9 and the run behaviour of S1 / S5 on a small dataset."""
import os
from datetime import date, timedelta

import pytest

from app.models import Forecast, ForecastRun
from app.services import data_management_service as dm
from app.services import forecasting_service as fs
from tests.factories import make_item, sales_csv

TODAY = date(2026, 9, 25)


@pytest.fixture()
def world(app, tmp_path):
    items = [make_item(name="Burger", price=650), make_item(name="Fries", price=450)]
    dm.import_sales_csv(1, sales_csv(items), dry_run=False)
    return {"items": items, "dir": str(tmp_path / "models")}


def train(world, activate=True):
    return fs.train_model(1, world["dir"], activate=activate, oracle_path=None)


def test_no_active_model_skips_without_error(world):
    """ML-7"""
    r = fs.run_forecast(1)
    assert r["status"] == "skipped" and "No active model" in r["reason"]
    assert Forecast.query.count() == 0
    assert ForecastRun.query.one().status == "skipped"


def test_train_activate_and_seven_day_forecast_for_every_item(world):
    res = train(world)
    assert res["active"] and {m["model"] for m in res["comparison"]} >= {"naive_lag7", "xgboost", "random_forest"}
    r = fs.run_forecast(1)
    assert r["status"] == "ok" and r["items_forecast"] == 2
    rows = Forecast.query.filter_by(is_latest=True).all()
    assert len(rows) == 2 * 7
    assert {f.target_date for f in rows} == {TODAY + timedelta(days=i) for i in range(7)}
    assert all(f.predicted_qty >= 0 and f.input_snapshot["weather_estimated"] for f in rows)


def test_rerun_keeps_old_rows_and_flips_is_latest(world):
    """ML-9"""
    train(world)
    fs.run_forecast(1)
    fs.run_forecast(1)
    assert Forecast.query.count() == 28
    assert Forecast.query.filter_by(is_latest=True).count() == 14


def test_activation_swaps_the_active_model(world):
    """ML-9"""
    a = train(world)
    b = train(world, activate=False)
    assert fs.get_active_model(1).id == a["version_id"]
    fs.activate_model(1, b["version_label"])
    assert fs.get_active_model(1).id == b["version_id"]
    old = [m for m in fs.list_model_versions(1) if m.id == a["version_id"]][0]
    assert old.status == "retired"
    fs.run_forecast(1)
    assert Forecast.query.first().model_version_id == b["version_id"]


def test_short_history_gets_baseline_or_nothing(world):
    """ML-6: 7-34 days -> baseline; under 7 -> no row and status partial. Items added after training are not in the model."""
    train(world)
    short = make_item(name="Short", price=100)
    tiny = make_item(name="Tiny", price=100)
    dm.import_sales_csv(1, sales_csv([short], start=TODAY - timedelta(days=20), end=date(2026, 9, 24)), dry_run=False)
    dm.import_sales_csv(1, sales_csv([tiny], start=TODAY - timedelta(days=3), end=date(2026, 9, 24)), dry_run=False)
    r = fs.run_forecast(1)
    assert r["status"] == "partial" and "Tiny" in r["reason"]
    by_item = {}
    for f in Forecast.query.filter_by(is_latest=True):
        by_item.setdefault(f.menu_item_id, set()).add(f.method)
    assert by_item[short.id] == {"baseline"}
    assert tiny.id not in by_item
    assert all(by_item[i.id] == {"model"} for i in world["items"])


def test_failed_run_is_recorded_with_a_readable_reason(world):
    """NFR3: a broken artifact never produces a stack trace for the user."""
    train(world)
    mv = fs.get_active_model(1)
    os.remove(mv.artifact_path)
    from app.ml import registry
    registry.clear_cache()
    r = fs.run_forecast(1)
    assert r["status"] == "failed" and r["reason"].startswith("The forecast could not be generated")
    assert ForecastRun.query.order_by(ForecastRun.id.desc()).first().status == "failed"


def test_backfill_creates_out_of_sample_history_for_past_dates(world):
    train(world)
    out = fs.backfill(1, date(2026, 9, 10), date(2026, 9, 14))
    assert out["ok"] == 5
    rows = Forecast.query.filter(Forecast.target_date <= date(2026, 9, 14)).all()
    assert len(rows) == 10 and all(r.run.trigger_type == "backfill" for r in rows)
    from app.services.errors import ValidationError
    with pytest.raises(ValidationError):
        fs.backfill(1, date(2026, 9, 20), date(2026, 9, 25))


def test_get_forecasts_reports_missing_dates_and_active_model(world):
    train(world)
    fs.run_forecast(1, horizon=3)
    out = fs.get_forecasts(1, TODAY, TODAY + timedelta(days=6))
    assert len(out["rows"]) == 6
    assert out["meta"]["missing_dates"] == [(TODAY + timedelta(days=i)).isoformat() for i in range(3, 7)]
    assert out["meta"]["active_model"].startswith("v20260925-")


def test_future_run_is_rejected(world):
    train(world)
    from app.services.errors import ValidationError
    with pytest.raises(ValidationError):
        fs.run_forecast(1, as_of=TODAY + timedelta(days=4))


def test_last_run_shown_is_never_later_than_today_or_the_selected_date(world):
    from app.extensions import db
    train(world)
    fs.run_forecast(1)
    # a stray run dated in the future (e.g. inserted by an old CLI call) must not be reported as the last run
    db.session.add(ForecastRun(outlet_id=1, as_of_date=TODAY + timedelta(days=4), horizon_days=7,
                               trigger_type="cli", status="ok"))
    db.session.commit()
    assert fs.get_forecasts(1, TODAY, TODAY + timedelta(days=6))["meta"]["last_run"]["as_of"] == TODAY.isoformat()
    assert fs.get_forecasts(1, TODAY + timedelta(days=7), TODAY + timedelta(days=13))["meta"]["last_run"]["as_of"] == TODAY.isoformat()
    # viewing an earlier week caps the run at that date
    assert fs.get_forecasts(1, TODAY - timedelta(days=3), TODAY + timedelta(days=3))["meta"]["last_run"] is None


def test_forecasts_from_a_future_dated_run_are_not_shown(world):
    from app.extensions import db
    train(world)
    fs.run_forecast(1)
    future = ForecastRun(outlet_id=1, as_of_date=TODAY + timedelta(days=4), horizon_days=7, trigger_type="cli", status="ok")
    db.session.add(future)
    db.session.flush()
    src = Forecast.query.filter_by(is_latest=True).first()
    db.session.add(Forecast(outlet_id=1, run_id=future.id, model_version_id=src.model_version_id, menu_item_id=src.menu_item_id,
                            target_date=TODAY + timedelta(days=10), predicted_qty=1, method="baseline", is_latest=True))
    db.session.commit()
    meta = fs.get_forecasts(1, TODAY, TODAY + timedelta(days=13))["meta"]
    assert meta["last_forecast_date"] == (TODAY + timedelta(days=6)).isoformat()


def test_run_history_never_lists_a_future_dated_run(world):
    from app.extensions import db
    train(world)
    fs.run_forecast(1)
    db.session.add(ForecastRun(outlet_id=1, as_of_date=TODAY + timedelta(days=4), horizon_days=7,
                               trigger_type="cli", status="ok", reason="Simple estimate (same day last week) used for some or all items."))
    db.session.commit()
    runs = fs.list_runs(1)
    assert runs and all(r["as_of"] <= TODAY.isoformat() for r in runs)


def test_simple_estimate_only_when_no_model_forecast_is_possible(world):
    """A '*' (method=baseline) row exists only if the active model is itself a baseline, or the item is not in the
    model / has too little history. With enough history for every item and an ML model active, none appear."""
    res = train(world)
    mv = fs.get_active_model(1)
    fs.run_forecast(1)
    methods = {f.method for f in Forecast.query.filter_by(is_latest=True)}
    if mv.algorithm in ("naive_lag7", "seasonal_mean4"):
        assert methods == {"baseline"}
    else:
        assert methods == {"model"}
        assert ForecastRun.query.one().reason is None


def test_backfill_uses_the_train_only_model(world):
    """The shipped model is refit on all history; backfill must use the copy that never saw the hold-out days."""
    train(world)
    from app.ml import registry
    art = registry.load_artifact(fs.get_active_model(1).artifact_path)
    assert art["eval_model"] is not None and art["eval_model"] is not art["model"]
    seen = []
    import app.services.forecasting_service as mod
    real = mod.predict
    mod.predict = lambda a, f: (seen.append(a.get("model")) or real(a, f))
    try:
        fs.backfill(1, date(2026, 9, 20), date(2026, 9, 20))
        fs.run_forecast(1)
    finally:
        mod.predict = real
    assert seen[0] is not None and seen[1] is not None and seen[0] is not seen[1]   # eval copy vs shipped model


# ---- forecast-vs-actual stays out-of-sample (review 7 Oct 2026, B8) ----------------------------------------------
def test_backfill_before_the_holdout_is_refused_and_records_nothing(world):
    train(world)
    hold_start = fs.get_active_model(1).holdout_start
    from app.services.errors import ValidationError
    with pytest.raises(ValidationError) as e:
        fs.backfill(1, hold_start - timedelta(days=1), hold_start + timedelta(days=1))
    assert "from" in e.value.fields
    assert ForecastRun.query.count() == 0
    assert fs.backfill(1, hold_start, hold_start + timedelta(days=1))["ok"] == 2   # the hold-out itself is allowed


def test_a_normal_run_for_a_past_date_is_refused_before_a_run_is_recorded(world):
    train(world)
    from app.services.errors import ValidationError
    for trigger in ("cli", "admin"):
        with pytest.raises(ValidationError) as e:
            fs.run_forecast(1, as_of=TODAY - timedelta(days=1), trigger=trigger)
        assert "as_of" in e.value.fields
    assert ForecastRun.query.count() == 0
    assert fs.run_forecast(1, as_of=TODAY)["status"] == "ok"


def test_forecasts_say_when_they_go_past_the_holiday_calendar(world):
    """R6 / C26 (review 7 Oct 2026): past the calendar's last date, holidays are unknown to the forecast."""
    train(world)
    fs.run_forecast(1)
    meta = fs.get_forecasts(1, TODAY, TODAY + timedelta(days=6))["meta"]
    assert meta["holiday_calendar_ends"] is None and meta["beyond_holiday_calendar"] is True   # nothing imported
    dm.import_holidays_csv(1, f"date,name,type\n{(TODAY + timedelta(days=3)).isoformat()},Test Poya,poya\n", dry_run=False)
    meta = fs.get_forecasts(1, TODAY, TODAY + timedelta(days=6))["meta"]
    assert meta["holiday_calendar_ends"] == (TODAY + timedelta(days=3)).isoformat() and meta["beyond_holiday_calendar"] is True
    assert fs.get_forecasts(1, TODAY, TODAY + timedelta(days=2))["meta"]["beyond_holiday_calendar"] is False
