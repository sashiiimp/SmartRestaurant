"""USE-1 .. USE-6: Actual Food Usage Recording (K14): portions used other than sold or wasted, and the daily balance
prepared = served + wasted + other use + unaccounted. Expected values are worked out by hand in each test."""
from datetime import date, timedelta

import pytest

from app.extensions import db
from app.models import AuditLog, FoodUsage, SalesRecord
from app.services import dashboard_service as dash
from app.services import kitchen_service as kit
from app.services.errors import NotFoundError, ValidationError
from tests.factories import make_item

TODAY = date(2026, 9, 25)


@pytest.fixture()
def burger(app):
    return make_item(name="Chicken Burger", batch_size=6, price=650)


def use(item, usage_type, qty, day=TODAY, note=None):
    return kit.record_food_usage(1, {"menu_item_id": item.id, "date": day.isoformat(), "usage_type": usage_type,
                                     "quantity": qty, "note": note})


def day_of(item, day=TODAY, prepared=(40, 20), served=48, wasted=5):
    for q in prepared:
        kit.record_prepared(1, {"menu_item_id": item.id, "date": day.isoformat(), "quantity": q})
    if served is not None:
        kit.record_served(1, {"date": day.isoformat(), "lines": [{"menu_item_id": item.id, "quantity": served}]})
    if wasted:
        kit.record_waste(1, {"menu_item_id": item.id, "date": day.isoformat(), "quantity": wasted, "reason": "quality"})


def balance(item, day=TODAY):
    return next(r for r in kit.food_usage_for(1, day)["balance"] if r["menu_item_id"] == item.id)


def test_daily_balance_matches_the_hand_calculation(burger):
    """USE-1: prepared 40 + 20 = 60; served 48; waste 5; staff meals 3; complimentary 2 -> other use 5, unaccounted 2."""
    day_of(burger)
    use(burger, "staff_meal", 3)
    out = use(burger, "complimentary", 2)
    assert out["warnings"] == []
    b = balance(burger)
    assert (b["prepared"], b["served"], b["wasted"], b["other_total"], b["unaccounted"]) == (60, 48, 5, 5, 2)
    assert b["other_use"] == {"staff_meal": 3, "complimentary": 2, "sample": 0, "other": 0}
    assert b["flags"] == []


def test_using_more_than_was_prepared_is_saved_with_a_warning_and_a_flag(burger):
    """USE-2: served 58 + waste 5 + other 5 = 68 > prepared 60 -> unaccounted -8."""
    day_of(burger, served=58)
    use(burger, "staff_meal", 3)
    out = use(burger, "complimentary", 2)
    assert out["warnings"] == ["Chicken Burger: served (58), waste (5) and other use (5) add up to 68, "
                               "more than the 60 prepared."]
    b = balance(burger)
    assert b["unaccounted"] == -8 and b["flags"] == ["used_more_than_prepared"]


def test_before_served_is_recorded_the_balance_is_open(burger):
    """USE-3: no served figure yet -> unaccounted is unknown (None), but waste + other above prepared still warns."""
    day_of(burger, prepared=(6,), served=None, wasted=4)
    assert balance(burger)["unaccounted"] is None
    out = use(burger, "staff_meal", 3)
    assert out["warnings"] == ["Chicken Burger: waste (4) and other use (3) add up to 7, more than the 6 prepared."]


def test_recording_again_replaces_the_figure_for_that_type(burger):
    """USE-4: one figure per item, day and type; staff meals 3 then 4 -> 4, a single row."""
    assert use(burger, "staff_meal", 3)["created"] is True
    out = use(burger, "staff_meal", 4, note="late shift")
    assert out["created"] is False
    rows = FoodUsage.query.all()
    assert len(rows) == 1 and rows[0].quantity == 4 and rows[0].note == "late shift"
    assert [a.action for a in AuditLog.query.order_by(AuditLog.id)][-2:] == ["food_usage.record", "food_usage.record"]


def test_clearing_a_figure(burger):
    uid = use(burger, "sample", 2)["usage_id"]
    assert kit.clear_food_usage(1, uid)["cleared"] == uid
    assert FoodUsage.query.count() == 0
    with pytest.raises(NotFoundError):
        kit.clear_food_usage(1, uid)


@pytest.mark.parametrize("data,field", [
    ({"usage_type": "staff_meal", "quantity": 0}, "quantity"),
    ({"usage_type": "staff_meal", "quantity": -2}, "quantity"),
    ({"usage_type": "staff_meal", "quantity": 1.5}, "quantity"),
    ({"usage_type": "staff_meal", "quantity": 10001}, "quantity"),
    ({"usage_type": "party", "quantity": 2}, "usage_type"),
    ({"usage_type": "staff_meal", "quantity": 2, "date": (TODAY + timedelta(days=1)).isoformat()}, "date"),
])
def test_validation(burger, data, field):
    """USE-5"""
    with pytest.raises(ValidationError) as e:
        kit.record_food_usage(1, {"menu_item_id": burger.id, "date": TODAY.isoformat(), **data})
    assert field in e.value.fields


def test_food_usage_never_changes_sales_or_waste(burger):
    """USE-6: sales stay the measure of demand (the forecast's input); other use is recorded beside them."""
    day_of(burger)
    use(burger, "staff_meal", 3)
    assert SalesRecord.query.one().quantity_sold == 48
    s = next(r for r in dash.kitchen_daily_summary(1, TODAY)["items"] if r["menu_item_id"] == burger.id)
    assert (s["served"], s["wasted"], s["other_use"], s["unaccounted"]) == (48, 5, 3, 4)


def test_report_totals_by_type_and_item(burger):
    """Two days: staff meals 3 + 1, complimentary 2 -> staff_meal 4, complimentary 2, total 6."""
    fries = make_item(name="French Fries", batch_size=10)
    use(burger, "staff_meal", 3)
    use(burger, "complimentary", 2)
    use(fries, "staff_meal", 1, day=TODAY - timedelta(days=1))
    r = dash.food_usage_report(1, TODAY - timedelta(days=6), TODAY)
    assert r["by_type"] == {"staff_meal": 4, "complimentary": 2, "sample": 0, "other": 0}
    assert r["total"] == 6
    assert [(i["item"], i["total"]) for i in r["by_item"]] == [("Chicken Burger", 5), ("French Fries", 1)]
    db.session.rollback()
