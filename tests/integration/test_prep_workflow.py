"""PREP-1 .. PREP-6: the food preparation workflow (Food Preparation Management, K4): planned -> in progress -> done.

Hand-worked values: Chicken Burger, forecast 47.3, buffer 10%, batch 6 -> recommended 54 (TESTING.md 4.1, P1).
"""
from datetime import date, timedelta

import pytest

from app.extensions import db
from app.models import AuditLog, Recommendation
from app.services import dashboard_service as dash
from app.services import kitchen_service as kit
from app.services import recommendation_service as rec
from app.services.errors import ConflictError, ValidationError
from tests.factories import make_item
from tests.integration.test_kitchen_recommendation import add_forecast

TODAY = date(2026, 9, 25)


@pytest.fixture()
def burger(app):
    item = make_item(name="Chicken Burger", batch_size=6)
    add_forecast(item, TODAY, "47.3")
    add_forecast(item, TODAY + timedelta(days=1), "47.3")
    return item


def row(item, day=TODAY):
    return next(r for r in rec.get_prep_plan(1, day)["items"] if r["menu_item_id"] == item.id)


def status(item, action, day=TODAY):
    return rec.set_prep_status(1, {"menu_item_id": item.id, "date": day.isoformat(), "action": action}, actor_id=None)


def prepare(item, qty, day=TODAY):
    return kit.record_prepared(1, {"menu_item_id": item.id, "date": day.isoformat(), "quantity": qty})


def test_undecided_item_has_no_preparation_status_and_cannot_start(burger):
    """PREP-1: the workflow starts with a plan; without one there is nothing to start."""
    assert row(burger)["prep_status"] is None
    with pytest.raises(ValidationError) as e:
        status(burger, "start")
    assert e.value.code == "no_plan"


def test_accepting_plans_the_item(burger):
    """PREP-2"""
    rec.decide(1, {"menu_item_id": burger.id, "date": TODAY.isoformat(), "action": "accept"})
    r = row(burger)
    assert (r["status"], r["final_qty"], r["prep_status"]) == ("accepted", 54, "planned")


def test_recording_the_first_prepared_quantity_starts_preparation(burger):
    """PREP-3: no extra click needed; a second entry keeps the status and adds up (24 + 30 = 54)."""
    rec.decide(1, {"menu_item_id": burger.id, "date": TODAY.isoformat(), "action": "accept"})
    prepare(burger, 24)
    assert row(burger)["prep_status"] == "in_progress"
    prepare(burger, 30)
    r = row(burger)
    assert (r["prep_status"], r["prepared_so_far"]) == ("in_progress", 54)
    assert Recommendation.query.one().prep_started_at is not None


def test_start_and_done_with_the_full_plan_has_no_warning(burger):
    """PREP-4"""
    rec.decide(1, {"menu_item_id": burger.id, "date": TODAY.isoformat(), "action": "accept"})
    assert status(burger, "start")["prep_status"] == "in_progress"
    prepare(burger, 54)
    out = status(burger, "done")
    assert (out["prep_status"], out["prepared"], out["final_qty"], out["warnings"]) == ("done", 54, 54, [])
    r = Recommendation.query.one()
    assert r.prep_done_at is not None
    assert {a.action for a in AuditLog.query} >= {"prep.start", "prep.done"}


def test_done_below_or_above_the_plan_is_saved_with_a_warning(burger):
    """PREP-5: 48 of 54 -> 6 short; an override to 42 and 48 prepared -> 6 more than planned."""
    rec.decide(1, {"menu_item_id": burger.id, "date": TODAY.isoformat(), "action": "accept"})
    prepare(burger, 48)
    out = status(burger, "done")
    assert out["prep_status"] == "done" and out["warnings"] == ["Prepared (48) is 6 below the plan (54)."]
    status(burger, "reopen")
    rec.decide(1, {"menu_item_id": burger.id, "date": TODAY.isoformat(), "action": "override", "final_qty": 42,
                   "reason": "Rain"})
    out = status(burger, "done")
    assert out["warnings"] == ["Prepared (48) is 6 above the plan (42)."]


def test_done_needs_a_prepared_quantity(burger):
    rec.decide(1, {"menu_item_id": burger.id, "date": TODAY.isoformat(), "action": "accept"})
    with pytest.raises(ValidationError) as e:
        status(burger, "done")
    assert "quantity" in e.value.fields


def test_invalid_transitions_are_refused(burger):
    """PREP-6: start twice, reopen when not done, start or re-plan when done."""
    rec.decide(1, {"menu_item_id": burger.id, "date": TODAY.isoformat(), "action": "accept"})
    with pytest.raises(ConflictError):
        status(burger, "reopen")
    status(burger, "start")
    with pytest.raises(ConflictError):
        status(burger, "start")
    prepare(burger, 54)
    status(burger, "done")
    with pytest.raises(ConflictError):
        status(burger, "start")
    with pytest.raises(ConflictError) as e:
        rec.decide(1, {"menu_item_id": burger.id, "date": TODAY.isoformat(), "action": "accept"})
    assert e.value.code == "prep_done"
    assert status(burger, "reopen")["prep_status"] == "in_progress"
    assert Recommendation.query.one().prep_done_at is None


def test_changing_the_plan_after_preparation_started_warns(burger):
    rec.decide(1, {"menu_item_id": burger.id, "date": TODAY.isoformat(), "action": "accept"})
    prepare(burger, 24)
    out = rec.decide(1, {"menu_item_id": burger.id, "date": TODAY.isoformat(), "action": "override", "final_qty": 36,
                         "reason": "Quiet day"})
    assert out["warnings"] == ["Preparation has already started (24 prepared so far)."]
    assert row(burger)["prep_status"] == "in_progress"


def test_future_dates_cannot_be_started(burger):
    tomorrow = TODAY + timedelta(days=1)
    rec.decide(1, {"menu_item_id": burger.id, "date": tomorrow.isoformat(), "action": "accept"})
    with pytest.raises(ValidationError) as e:
        status(burger, "start", tomorrow)
    assert "date" in e.value.fields


def test_bad_input_is_a_validation_error(burger):
    with pytest.raises(ValidationError):
        rec.set_prep_status(1, {"menu_item_id": burger.id, "date": TODAY.isoformat(), "action": "finish"})
    with pytest.raises(ValidationError):
        rec.set_prep_status(1, {"menu_item_id": "x", "date": "yesterday", "action": "start"})


def test_daily_summary_and_kitchen_dashboard_count_finished_items(burger):
    other = make_item(name="Fries", batch_size=10)
    add_forecast(other, TODAY, "20")
    for item in (burger, other):
        rec.decide(1, {"menu_item_id": item.id, "date": TODAY.isoformat(), "action": "accept"})
    prepare(burger, 54)
    status(burger, "done")
    summary = {r["name"]: r["prep_status"] for r in dash.kitchen_daily_summary(1, TODAY)["items"]}
    assert summary == {"Chicken Burger": "done", "Fries": "planned"}
    tiles = dash.kitchen_dashboard(1, TODAY)["tiles"]
    assert (tiles["items_done"], tiles["items_planned"]) == (1, 2)
    db.session.rollback()
