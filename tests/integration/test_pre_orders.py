"""K10: pre-orders. Confirmed (and later completed) ones count in the preparation quantity (TESTING.md 4.1)."""
from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.extensions import db
from app.models import AuditLog, PreOrder, Recommendation, SalesRecord
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
    return kit.create_pre_order(1, {"menu_item_id": item.id, "target_date": day.isoformat(), "quantity": qty,
                                    "customer_name": "Nimal Perera", "pickup_time": "12:30", **extra})


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
            kit.create_pre_order(1, {"menu_item_id": burger.id, "target_date": TOMORROW.isoformat(), "quantity": 5,
                                     "customer_name": "Nimal Perera", "pickup_time": "12:30", **data})
        return e.value.fields
    assert "target_date" in fail(target_date=(TODAY - timedelta(days=1)).isoformat())
    assert "quantity" in fail(quantity=0)
    assert "quantity" in fail(quantity=2.5)
    assert "status" in fail(status="cancelled")                       # cannot be created as cancelled
    assert "customer_note" in fail(customer_note="x" * 256)
    gone = make_item(name="Old", active=False)
    assert fail(menu_item_id=gone.id) == {"menu_item_id": "is not active"}
    with pytest.raises(NotFoundError):
        kit.create_pre_order(1, {"menu_item_id": 999, "target_date": TOMORROW.isoformat(), "quantity": 1,
                                 "customer_name": "Nimal Perera", "pickup_time": "12:30"})


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
                                    "customer_name": "Nimal Perera", "pickup_time": "12:30",
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


# ---- Preorder Management (13 Oct 2026): customer details, pickup time, completed status -------------------------
def test_customer_name_and_pickup_time_are_required_contact_is_optional(burger):
    def fail(**data):
        with pytest.raises(ValidationError) as e:
            kit.create_pre_order(1, {"menu_item_id": burger.id, "target_date": TOMORROW.isoformat(), "quantity": 5, **data})
        return e.value.fields
    assert set(fail()) == {"customer_name", "pickup_time"}
    assert fail(customer_name="A", pickup_time="25:00") == {"pickup_time": "must be a time (HH:MM)"}
    assert "customer_contact" in fail(customer_name="A", pickup_time="12:00", customer_contact="0" * 61)
    p = add(burger, customer_contact="077 123 4567", pickup_time="18:45")
    assert (p["customer_name"], p["customer_contact"], p["pickup_time"], p["counts_in_plan"]) == (
        "Nimal Perera", "077 123 4567", "18:45", False)


def test_status_flow_and_final_states(burger):
    p = add(burger)
    with pytest.raises(ConflictError):                       # pending cannot jump straight to completed
        kit.update_pre_order(1, p["id"], {"status": "completed"})
    kit.update_pre_order(1, p["id"], {"status": "confirmed"})
    with pytest.raises(ValidationError) as e:                # tomorrow's order cannot be handed over today
        kit.update_pre_order(1, p["id"], {"status": "completed"})
    assert "status" in e.value.fields
    today_order = add(burger, TODAY, 4, status="confirmed")
    done = kit.update_pre_order(1, today_order["id"], {"status": "completed"})
    assert done["status"] == "completed" and done["completed_at"] and done["counts_in_plan"]
    for change in ({"status": "cancelled"}, {"quantity": 1}, {"status": "confirmed"}):
        with pytest.raises(ConflictError):
            kit.update_pre_order(1, today_order["id"], change)
    assert [a.action for a in AuditLog.query.order_by(AuditLog.id)][-2:] == ["preorder.create", "preorder.complete"]


def test_a_past_confirmed_pre_order_can_only_be_completed(burger):
    old = PreOrder(outlet_id=1, menu_item_id=burger.id, target_date=TODAY - timedelta(days=1), quantity=3, status="confirmed")
    db.session.add(old); db.session.commit()
    with pytest.raises(ConflictError):
        kit.update_pre_order(1, old.id, {"status": "completed", "quantity": 4})
    assert kit.update_pre_order(1, old.id, {"status": "completed"})["status"] == "completed"


def test_completed_pre_orders_still_count_for_their_day(burger):
    a = add(burger, TODAY, 50, status="confirmed")
    assert rec._preorder_totals(1, TODAY) == {burger.id: 50}
    kit.update_pre_order(1, a["id"], {"status": "completed"})
    # base 40 x 1.10 = 44 < 50 pre-ordered, so 50 rounded up to the batch of 6 = 54, before and after completion
    assert rec._preorder_totals(1, TODAY) == {burger.id: 50}
    assert recommended(burger, TODAY) == 54


def test_completing_a_pre_order_records_no_sale(burger):
    a = add(burger, TODAY, 5, status="confirmed")
    kit.update_pre_order(1, a["id"], {"status": "completed"})
    assert SalesRecord.query.count() == 0                     # served portions are recorded once, by the kitchen


def test_old_pre_orders_without_customer_details_stay_editable(burger):
    old = PreOrder(outlet_id=1, menu_item_id=burger.id, target_date=TOMORROW, quantity=3, status="pending")
    db.session.add(old); db.session.commit()
    out = kit.update_pre_order(1, old.id, {"quantity": 6, "status": "confirmed"})
    assert (out["quantity"], out["status"], out["customer_name"], out["pickup_time"]) == (6, "confirmed", None, None)


def test_detail_and_upcoming_confirmed(burger, app):
    from tests.factories import make_user
    u = make_user(role="kitchen", username="cook")
    p = kit.create_pre_order(1, {"menu_item_id": burger.id, "target_date": TOMORROW.isoformat(), "quantity": 7,
                                 "customer_name": "Kamala", "pickup_time": "11:15", "status": "confirmed"}, actor_id=u.id)
    add(burger, TOMORROW, 3)                                  # pending: not upcoming
    add(burger, TODAY + timedelta(days=9), 9, status="confirmed")   # outside the 7 days
    d = kit.pre_order_detail(1, p["id"])
    assert d["created_by"] and set(d["allowed_status"]) == {"pending", "completed", "cancelled"}
    up = kit.upcoming_pre_orders(1, 7)
    assert (up["count"], up["portions"], up["by_item"]) == (1, 7, [{"item": "Burger", "quantity": 7}])
