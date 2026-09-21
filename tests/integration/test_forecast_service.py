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
