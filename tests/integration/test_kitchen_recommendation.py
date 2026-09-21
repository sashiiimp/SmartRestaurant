"""REC-2, KIT-1, KIT-2, VAL-1, VAL-3, VAL-4: decisions and kitchen recording."""
from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.extensions import db
from app.models import AuditLog, ForecastRun, Forecast, PreOrder, Recommendation, SalesRecord
from app.services import dashboard_service as dash
from app.services import kitchen_service as kit
from app.services import recommendation_service as rec
from app.services import settings
from app.services.errors import ConflictError, ValidationError
from tests.factories import make_item, make_user

TODAY = date(2026, 9, 25)


def add_forecast(item, day, qty, method="model"):
    run = ForecastRun(outlet_id=1, as_of_date=day, horizon_days=1, trigger_type="cli", status="ok")
    db.session.add(run)
    db.session.flush()
    f = Forecast(outlet_id=1, run_id=run.id, menu_item_id=item.id, target_date=day, predicted_qty=Decimal(str(qty)),
                 method=method, input_snapshot={"weather_estimated": True}, is_latest=True)
    db.session.add(f)
    db.session.commit()
    return f


@pytest.fixture()
def burger(app):
    item = make_item(name="Chicken Burger", batch_size=6)
    add_forecast(item, TODAY, "47.3")
    return item


def row(plan, item):
    return next(r for r in plan["items"] if r["menu_item_id"] == item.id)


def test_plan_shows_forecast_buffer_and_recommendation(burger):
    r = row(rec.get_prep_plan(1, TODAY), burger)
    assert (r["forecast_qty"], r["buffer_pct"], r["recommended_qty"], r["status"]) == (47.3, 10.0, 54, "suggested")


def test_no_forecast_means_no_number(burger):
    r = row(rec.get_prep_plan(1, TODAY + timedelta(days=3)), burger)
    assert r["status"] == "no_forecast" and r["recommended_qty"] is None and r["forecast_qty"] is None


def test_buffer_setting_changes_the_recommendation(burger):
    settings.set_value(1, "safety_buffer_pct", 30)  # 47.3 * 1.3 = 61.49 -> 66
    assert row(rec.get_prep_plan(1, TODAY), burger)["recommended_qty"] == 66


def test_confirmed_preorders_count_but_pending_do_not(burger):
    db.session.add(PreOrder(outlet_id=1, menu_item_id=burger.id, target_date=TODAY, quantity=58, status="confirmed"))
    db.session.add(PreOrder(outlet_id=1, menu_item_id=burger.id, target_date=TODAY, quantity=500, status="pending"))
    db.session.commit()
    assert row(rec.get_prep_plan(1, TODAY), burger)["recommended_qty"] == 60


def test_inactive_items_are_excluded(burger):
    make_item(name="Old", active=False)
    assert [r["name"] for r in rec.get_prep_plan(1, TODAY)["items"]] == ["Chicken Burger"]


def test_accept_stores_recommended_as_final_and_audits(burger):
    user = make_user("kitchen")
    out = rec.decide(1, {"menu_item_id": burger.id, "date": "2026-09-25", "action": "accept"}, user.id)
    assert out["status"] == "accepted" and out["final_qty"] == 54
    saved = Recommendation.query.one()
    assert (saved.forecast_qty, saved.recommended_qty, saved.final_qty, saved.batch_size) == (Decimal("47.30"), 54, 54, 6)
    assert AuditLog.query.filter_by(action="recommendation.accept").count() == 1
    r = row(rec.get_prep_plan(1, TODAY), burger)
    assert r["status"] == "accepted" and r["final_qty"] == 54


def test_override_needs_a_reason_and_second_decision_updates_the_same_row(burger):
    with pytest.raises(ValidationError) as e:
        rec.decide(1, {"menu_item_id": burger.id, "date": "2026-09-25", "action": "override", "final_qty": 40})
    assert "reason" in e.value.fields
    out = rec.decide(1, {"menu_item_id": burger.id, "date": "2026-09-25", "action": "override",
                         "final_qty": 40, "reason": "Rain expected"})
    assert out["status"] == "overridden" and out["recommended_qty"] == 54 and out["final_qty"] == 40
    rec.decide(1, {"menu_item_id": burger.id, "date": "2026-09-25", "action": "accept"})
    assert Recommendation.query.count() == 1 and Recommendation.query.one().status == "accepted"


def test_override_below_preorders_warns(burger):
    db.session.add(PreOrder(outlet_id=1, menu_item_id=burger.id, target_date=TODAY, quantity=50, status="confirmed"))
    db.session.commit()
    out = rec.decide(1, {"menu_item_id": burger.id, "date": "2026-09-25", "action": "override",
                         "final_qty": 30, "reason": "x"})
    assert out["warnings"] and "pre-orders" in out["warnings"][0]


def test_cannot_decide_without_forecast_or_in_the_past(burger):
    with pytest.raises(ValidationError) as e:
        rec.decide(1, {"menu_item_id": burger.id, "date": "2026-09-27", "action": "accept"})
    assert e.value.code == "no_forecast"
    with pytest.raises(ValidationError):
        rec.decide(1, {"menu_item_id": burger.id, "date": "2026-09-20", "action": "accept"})


# ---- kitchen recording --------------------------------------------------------------------------
def test_prepared_entries_for_a_day_are_summed(burger):
    kit.record_prepared(1, {"menu_item_id": burger.id, "date": "2026-09-25", "quantity": 24})
    out = kit.record_prepared(1, {"menu_item_id": burger.id, "date": "2026-09-25", "quantity": 30})
    assert out["total_prepared"] == 54
    assert row(rec.get_prep_plan(1, TODAY), burger)["prepared_so_far"] == 54


@pytest.mark.parametrize("qty", ["0", "-5", "abc", "", None, 2.5])
def test_prepared_quantity_must_be_a_positive_whole_number(burger, qty):
    with pytest.raises(ValidationError) as e:
        kit.record_prepared(1, {"menu_item_id": burger.id, "date": "2026-09-25", "quantity": qty})
    assert "quantity" in e.value.fields


def test_future_dates_are_rejected_for_actuals(burger):
    for fn, body in ((kit.record_prepared, {"quantity": 5}), (kit.record_waste, {"quantity": 5, "reason": "other"})):
        with pytest.raises(ValidationError) as e:
            fn(1, {"menu_item_id": burger.id, "date": "2026-09-26", **body})
        assert "date" in e.value.fields


def test_served_writes_a_kitchen_sales_record_and_warns_when_above_prepared(burger):
    kit.record_prepared(1, {"menu_item_id": burger.id, "date": "2026-09-25", "quantity": 20})
    out = kit.record_served(1, {"date": "2026-09-25", "lines": [{"menu_item_id": burger.id, "quantity": 25}]})
    assert out["saved"] == 1 and "flagged for review" in out["warnings"][0]
    s = SalesRecord.query.one()
    assert (s.source, s.quantity_sold, s.unit_price) == ("kitchen", 25, Decimal("500.00"))


def test_served_duplicate_needs_confirmation(burger):
    body = {"date": "2026-09-25", "lines": [{"menu_item_id": burger.id, "quantity": 25}]}
    kit.record_served(1, body)
    kit.record_served(1, body)  # identical resend: no conflict
    changed = {"date": "2026-09-25", "lines": [{"menu_item_id": burger.id, "quantity": 30}]}
    with pytest.raises(ConflictError) as e:
        kit.record_served(1, changed)
    assert e.value.code == "duplicate_record" and e.value.extra["conflicts"][0]["existing"] == 25
    kit.record_served(1, {**changed, "confirm_overwrite": True})
    assert SalesRecord.query.one().quantity_sold == 30


def test_served_zero_is_allowed_negative_is_not(burger):
    kit.record_served(1, {"date": "2026-09-25", "lines": [{"menu_item_id": burger.id, "quantity": 0}]})
    with pytest.raises(ValidationError):
        kit.record_served(1, {"date": "2026-09-24", "lines": [{"menu_item_id": burger.id, "quantity": -1}]})


def test_waste_above_prepared_warns_but_saves(burger):
    kit.record_prepared(1, {"menu_item_id": burger.id, "date": "2026-09-25", "quantity": 10})
    out = kit.record_waste(1, {"menu_item_id": burger.id, "date": "2026-09-25", "quantity": 12, "reason": "overproduction"})
    assert out["total_waste"] == 12 and out["warnings"]
    with pytest.raises(ValidationError):
        kit.record_waste(1, {"menu_item_id": burger.id, "date": "2026-09-25", "quantity": 1, "reason": "bored"})


def test_daily_summary_equals_underlying_rows(burger):
    """KIT-2 / S6"""
    kit.record_prepared(1, {"menu_item_id": burger.id, "date": "2026-09-25", "quantity": 50})
    kit.record_served(1, {"date": "2026-09-25", "lines": [{"menu_item_id": burger.id, "quantity": 48}]})
    kit.record_waste(1, {"menu_item_id": burger.id, "date": "2026-09-25", "quantity": 2, "reason": "quality"})
    r = dash.kitchen_daily_summary(1, TODAY)["items"][0]
    assert (r["forecast_qty"], r["recommended_qty"], r["prepared"], r["served"], r["wasted"]) == (47.3, 54, 50, 48, 2)
    assert r["flags"] == []
