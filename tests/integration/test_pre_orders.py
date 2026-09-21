"""K10: pre-orders. Only confirmed ones count in the preparation quantity (TESTING.md 4.1)."""
from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.extensions import db
from app.models import AuditLog, PreOrder, Recommendation
from app.services import kitchen_service as kit
from app.services import recommendation_service as rec
from app.services.errors import ConflictError, NotFoundError, ValidationError
from tests.factories import make_item

TODAY = date(2026, 9, 25)
TOMORROW = TODAY + timedelta(days=1)


@pytest.fixture()
def burger(app):
    return make_item(name="Burger", batch_size=6)


def add(item, day=TOMORROW, qty=10, **extra):
    return kit.create_pre_order(1, {"menu_item_id": item.id, "target_date": day.isoformat(), "quantity": qty, **extra})


def recommended(item, day=TOMORROW, forecast=40):
    """Prep quantity for a 40-portion forecast, 10 % buffer, batch 6 (base 44)."""
    return rec.compute_recommended(Decimal(forecast), Decimal(10), rec._preorder_totals(1, day).get(item.id, 0), item.batch_size)


def test_create_defaults_to_pending_and_is_audited(burger):
    p = add(burger, customer_note="birthday order")
    assert (p["status"], p["item"], p["quantity"], p["target_date"], p["customer_note"]) == (
        "pending", "Burger", 10, TOMORROW.isoformat(), "birthday order")
    assert p["warnings"] == []
    assert AuditLog.query.filter_by(action="preorder.create").count() == 1


def test_create_validation(burger):
    def fail(**data):
        with pytest.raises(ValidationError) as e:
            kit.create_pre_order(1, {"menu_item_id": burger.id, "target_date": TOMORROW.isoformat(), "quantity": 5, **data})
        return e.value.fields
    assert "target_date" in fail(target_date=(TODAY - timedelta(days=1)).isoformat())
    assert "quantity" in fail(quantity=0)
    assert "quantity" in fail(quantity=2.5)
    assert "status" in fail(status="cancelled")                       # cannot be created as cancelled
    assert "customer_note" in fail(customer_note="x" * 256)
    gone = make_item(name="Old", active=False)
    assert fail(menu_item_id=gone.id) == {"menu_item_id": "is not active"}
    with pytest.raises(NotFoundError):
        kit.create_pre_order(1, {"menu_item_id": 999, "target_date": TOMORROW.isoformat(), "quantity": 1})


def test_only_confirmed_pre_orders_change_the_prep_quantity(burger):
    big = add(burger, qty=58)                                          # pending: ignored
    assert recommended(burger) == 48                                   # ceil(44 / 6) * 6
    kit.update_pre_order(1, big["id"], {"status": "confirmed"})
    assert recommended(burger) == 60                                   # max(44, 58) = 58, ceil(58 / 6) * 6
    kit.update_pre_order(1, big["id"], {"quantity": 30})
    assert recommended(burger) == 48                                   # 30 < 44: the forecast wins again
    kit.update_pre_order(1, big["id"], {"status": "cancelled"})
    assert rec._preorder_totals(1, TOMORROW) == {}


def test_confirmed_pre_orders_of_one_item_and_day_add_up(burger):
    a, b = add(burger, qty=20, status="confirmed"), add(burger, qty=25, status="confirmed")
    assert rec._preorder_totals(1, TOMORROW) == {burger.id: 45}
    assert recommended(burger) == 48                                   # max(44, 45) = 45, ceil(45 / 6) * 6


def test_move_to_another_date_moves_the_effect(burger):
    p = add(burger, qty=58, status="confirmed")
    later = TOMORROW + timedelta(days=2)
    kit.update_pre_order(1, p["id"], {"target_date": later.isoformat()})
    assert rec._preorder_totals(1, TOMORROW) == {} and rec._preorder_totals(1, later) == {burger.id: 58}


def test_cancelled_and_past_pre_orders_are_read_only(burger):
    p = add(burger)
    kit.update_pre_order(1, p["id"], {"status": "cancelled"})
    with pytest.raises(ConflictError):
        kit.update_pre_order(1, p["id"], {"quantity": 5})
    old = PreOrder(outlet_id=1, menu_item_id=burger.id, target_date=TODAY - timedelta(days=1), quantity=3, status="confirmed")
    db.session.add(old); db.session.commit()
    with pytest.raises(ConflictError):
        kit.update_pre_order(1, old.id, {"status": "cancelled"})
    with pytest.raises(NotFoundError):
        kit.update_pre_order(1, 999, {"quantity": 5})


def test_update_validation(burger):
    p = add(burger)
    with pytest.raises(ValidationError) as e:
        kit.update_pre_order(1, p["id"], {"quantity": 0, "target_date": (TODAY - timedelta(days=1)).isoformat(), "status": "done"})
    assert set(e.value.fields) == {"quantity", "target_date", "status"}


def test_warning_when_the_plan_was_already_decided(burger):
    p = add(burger, qty=58)
    db.session.add(Recommendation(outlet_id=1, menu_item_id=burger.id, target_date=TOMORROW, forecast_qty=Decimal("40"),
                                  buffer_pct=Decimal("10"), preorder_qty=0, batch_size=6, recommended_qty=48,
                                  final_qty=48, status="accepted"))
    db.session.commit()
    assert kit.update_pre_order(1, p["id"], {"customer_note": "call back"})["warnings"] == []   # still pending
    out = kit.update_pre_order(1, p["id"], {"status": "confirmed"})
    assert out["warnings"] and "Prep plan" in out["warnings"][0]
    assert kit.create_pre_order(1, {"menu_item_id": burger.id, "target_date": TOMORROW.isoformat(), "quantity": 2,
                                    "status": "confirmed"})["warnings"]


def test_list_filters_and_order(burger):
    fries = make_item(name="Fries")
    a = add(burger, TOMORROW + timedelta(days=2), 5, status="confirmed")
    b = add(fries, TOMORROW, 7)
    c = add(burger, TOMORROW, 9)
    kit.update_pre_order(1, c["id"], {"status": "cancelled"})
    assert [p["id"] for p in kit.list_pre_orders(1, TODAY)] == [b["id"], c["id"], a["id"]]
    assert [p["id"] for p in kit.list_pre_orders(1, TODAY, TOMORROW)] == [b["id"], c["id"]]
    assert [p["id"] for p in kit.list_pre_orders(1, TODAY, status="confirmed")] == [a["id"]]
    assert [p["id"] for p in kit.list_pre_orders(1, TODAY, item_id=fries.id)] == [b["id"]]
    assert kit.list_pre_orders(1, TODAY + timedelta(days=30)) == []
    with pytest.raises(ValidationError):
        kit.list_pre_orders(1, status="bogus")
