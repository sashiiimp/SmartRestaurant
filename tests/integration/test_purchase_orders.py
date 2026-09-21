"""I11: purchase orders. Numbers follow TESTING.md 4.3 (chicken R1: suggested 25 kg, R3: 10 kg on order gives 15)."""
import threading
from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.extensions import db
from app.models import AuditLog, StockBatch, StockMovement, Supplier
from app.services import inventory_service as inv
from app.services.errors import ConflictError, NotFoundError, ValidationError
from tests.factories import make_ingredient
from tests.integration.test_requirements_reorder_alerts import kitchen_world, plan_days, reorder_for  # noqa: F401

TODAY = date(2026, 9, 25)


@pytest.fixture()
def po_world(app):
    sup = inv.create_supplier(1, {"name": "Ceylon Poultry", "lead_time_days": 2})
    chicken = make_ingredient(name="Chicken", unit="kg", min_stock=5, reorder_level=10, pack_size=5,
                              supplier_id=sup.id)
    rice = make_ingredient(name="Rice", unit="kg", supplier_id=sup.id)
    return {"sup": sup, "chicken": chicken, "rice": rice}


def make_po(w, chicken=25, rice=None, **extra):
    lines = [{"ingredient_id": w["chicken"].id, "qty_ordered": chicken}]
    if rice:
        lines.append({"ingredient_id": w["rice"].id, "qty_ordered": rice, "unit_cost": "180.50"})
    return inv.create_purchase_order(1, {"supplier_id": w["sup"].id, "lines": lines, **extra})


def receive(po, lines, **extra):
    return inv.receive_purchase_order(1, po["id"], {"lines": lines, **extra})


def line_id(po, name):
    return next(l["id"] for l in po["lines"] if l["ingredient"] == name)


# ---- create ------------------------------------------------------------------------------------
def test_create_numbers_orders_and_starts_as_draft(po_world):
    a, b = make_po(po_world), make_po(po_world, rice=40)
    assert (a["po_number"], b["po_number"]) == ("PO-20260925-01", "PO-20260925-02")
    assert a["status"] == "draft" and a["order_date"] == "2026-09-25" and a["supplier"] == "Ceylon Poultry"
    assert [(l["ingredient"], l["qty_ordered"], l["qty_received"], l["qty_outstanding"]) for l in b["lines"]] == [
        ("Chicken", 25.0, 0.0, 25.0), ("Rice", 40.0, 0.0, 40.0)]
    assert b["lines"][1]["unit_cost"] == 180.5
    assert AuditLog.query.filter_by(action="purchase_order.create").count() == 2


def test_create_validation(po_world):
    w = po_world
    ok = {"ingredient_id": w["chicken"].id, "qty_ordered": 5}
    def fail(**data):
        with pytest.raises(ValidationError) as e:
            inv.create_purchase_order(1, {"supplier_id": w["sup"].id, "lines": [ok], **data})
        return e.value.fields
    assert "lines" in fail(lines=[])
    assert "lines[0]" in fail(lines=[{"ingredient_id": w["chicken"].id, "qty_ordered": 0}])
    assert "lines[1]" in fail(lines=[ok, ok])                                          # same ingredient twice
    assert "lines[0]" in fail(lines=[{"ingredient_id": 999, "qty_ordered": 1}])
    assert "expected_date" in fail(expected_date="2026-09-01")
    assert "supplier_id" in fail(supplier_id=999)
    inv.update_supplier(1, w["sup"].id, {"is_active": False})
    assert fail() == {"supplier_id": "supplier is inactive"}
    w["rice"].is_active = False; db.session.commit()
    inv.update_supplier(1, w["sup"].id, {"is_active": True})
    assert "lines[0]" in fail(lines=[{"ingredient_id": w["rice"].id, "qty_ordered": 1}])


# ---- on order feeds the reorder formula (no formula change) ---------------------------------------
def test_open_order_lowers_the_reorder_suggestion(kitchen_world):
    w = kitchen_world
    sup = inv.create_supplier(1, {"name": "Ceylon Poultry", "lead_time_days": 2})
    w["chicken"].default_supplier_id = sup.id; w["chicken"].reorder_qty = Decimal("10"); db.session.commit()
    plan_days(w)
    assert reorder_for()["suggested_qty"] == 25.0                               # R1 without any order
    po = inv.create_purchase_order(1, {"supplier_id": sup.id, "lines": [{"ingredient_id": w["chicken"].id, "qty_ordered": 10}]})
    r = reorder_for()
    assert (r["on_order"], r["suggested_qty"], r["supplier_id"]) == (10.0, 15.0, sup.id)   # R3
    inv.cancel_purchase_order(1, po["id"])
    assert reorder_for()["suggested_qty"] == 25.0                               # cancelled order no longer counts
    po = inv.create_purchase_order(1, {"supplier_id": sup.id, "lines": [{"ingredient_id": w["chicken"].id, "qty_ordered": 25}]})
    assert reorder_for() is None                                                # 29.52 + 5 - 12 - 25 < 0
    inv.receive_purchase_order(1, po["id"], {"lines": [{"line_id": po["lines"][0]["id"], "quantity": 25}]})
    assert reorder_for() is None                                                # stock arrived, nothing on order


# ---- send / cancel -------------------------------------------------------------------------------
def test_send_only_from_draft(po_world):
    po = make_po(po_world)
    assert inv.send_purchase_order(1, po["id"])["status"] == "sent"
    with pytest.raises(ConflictError):
        inv.send_purchase_order(1, po["id"])
    with pytest.raises(NotFoundError):
        inv.send_purchase_order(1, 999)


def test_cancel_rules(po_world):
    draft, sent, part = make_po(po_world), make_po(po_world), make_po(po_world)
    assert inv.cancel_purchase_order(1, draft["id"])["status"] == "cancelled"
    inv.send_purchase_order(1, sent["id"])
    assert inv.cancel_purchase_order(1, sent["id"])["status"] == "cancelled"
    receive(part, [{"line_id": part["lines"][0]["id"], "quantity": 5}])
    with pytest.raises(ConflictError):
        inv.cancel_purchase_order(1, part["id"])                                 # something was received
    with pytest.raises(ConflictError):
        inv.cancel_purchase_order(1, draft["id"])                                # already cancelled
    with pytest.raises(ConflictError):
        receive(draft, [{"line_id": draft["lines"][0]["id"], "quantity": 1}])    # cancelled orders cannot receive


# ---- receive -------------------------------------------------------------------------------------
def test_full_receipt_creates_linked_batches_and_movements(po_world):
    w = po_world
    po = make_po(w, rice=40)
    out = receive(po, [{"line_id": line_id(po, "Chicken"), "quantity": 25, "expiry_date": "2026-10-05"},
                       {"line_id": line_id(po, "Rice"), "quantity": 40}])
    assert out["purchase_order"]["status"] == "received"
    chicken_batch = StockBatch.query.filter_by(ingredient_id=w["chicken"].id).one()
    assert (chicken_batch.qty_received, chicken_batch.qty_remaining) == (Decimal("25"), Decimal("25"))
    assert chicken_batch.purchase_order_id == po["id"] and chicken_batch.supplier_id == w["sup"].id
    assert chicken_batch.batch_no == po["po_number"] and chicken_batch.expiry_date == date(2026, 10, 5)
    rice_batch = StockBatch.query.filter_by(ingredient_id=w["rice"].id).one()
    assert rice_batch.unit_cost == Decimal("180.50")                              # from the order line
    moves = StockMovement.query.all()
    assert {(m.movement_type, m.reference_type, m.reference_id) for m in moves} == {("stock_in", "purchase_order", po["id"])}
    assert inv.usable_map(1)[w["chicken"].id] == Decimal("25")
    assert inv.on_order_map(1) == {}
    assert inv.stock_invariant_violations(1) == []


def test_partial_receipts_until_complete(po_world):
    w = po_world
    po = make_po(w)
    lid = po["lines"][0]["id"]
    first = receive(po, [{"line_id": lid, "quantity": 10}])["purchase_order"]
    assert first["status"] == "partially_received" and first["lines"][0]["qty_outstanding"] == 15.0
    assert inv.on_order_map(1)[w["chicken"].id] == Decimal("15")
    second = receive(po, [{"line_id": lid, "quantity": 15, "unit_cost": "900"}])["purchase_order"]
    assert second["status"] == "received" and second["lines"][0]["unit_cost"] == 900.0
    assert StockBatch.query.count() == 2 and inv.usable_map(1)[w["chicken"].id] == Decimal("25")
    with pytest.raises(ConflictError):
        receive(po, [{"line_id": lid, "quantity": 1}])                           # nothing left to receive
    assert inv.stock_invariant_violations(1) == []


def test_over_receipt_and_bad_lines_write_nothing(po_world):
    w = po_world
    po = make_po(w, rice=10)
    lc, lr = line_id(po, "Chicken"), line_id(po, "Rice")
    def fail(lines, **extra):
        with pytest.raises(ValidationError) as e:
            receive(po, lines, **extra)
        return e.value.fields
    assert fail([{"line_id": lc, "quantity": 26}]) == {"lines[0]": "only 25 can still be received"}
    assert "lines[1]" in fail([{"line_id": lc, "quantity": 1}, {"line_id": 99999, "quantity": 1}])
    assert "lines[1]" in fail([{"line_id": lc, "quantity": 1}, {"line_id": lc, "quantity": 1}])
    assert "lines[0]" in fail([{"line_id": lc, "quantity": 1, "expiry_date": "2026-09-01"}])
    assert "received_date" in fail([{"line_id": lc, "quantity": 1}], received_date="2026-10-01")
    assert "lines" in fail([])
    assert StockBatch.query.count() == 0 and StockMovement.query.count() == 0      # one bad line rejects the whole receipt
    assert receive(po, [{"line_id": lr, "quantity": 10}])["purchase_order"]["status"] == "partially_received"


def test_receiving_needs_no_send_step_and_is_audited(po_world):
    po = make_po(po_world)                      # still a draft
    receive(po, [{"line_id": po["lines"][0]["id"], "quantity": 25}])
    assert AuditLog.query.filter_by(action="purchase_order.receive").count() == 1


def test_list_and_get(po_world):
    a, b = make_po(po_world), make_po(po_world)
    inv.send_purchase_order(1, b["id"])
    assert [p["po_number"] for p in inv.list_purchase_orders(1)] == [b["po_number"], a["po_number"]]
    assert [p["id"] for p in inv.list_purchase_orders(1, "sent")] == [b["id"]]
    assert "lines" not in inv.list_purchase_orders(1)[0]
    assert inv.purchase_order_dict(inv.get_purchase_order(1, a["id"]))["line_count"] == 1
    with pytest.raises(ValidationError):
        inv.list_purchase_orders(1, "bogus")


@pytest.mark.mysql
def test_concurrent_receipts_cannot_exceed_the_order(app):
    """Two parallel receipts of 20 against 25 ordered: exactly one succeeds, stock ends at 20."""
    sup = inv.create_supplier(1, {"name": "S"})
    ing = make_ingredient(name="Chicken", unit="kg", supplier_id=sup.id)
    po = inv.create_purchase_order(1, {"supplier_id": sup.id, "lines": [{"ingredient_id": ing.id, "qty_ordered": 25}]})
    po_id, lid, ing_id = po["id"], po["lines"][0]["id"], ing.id
    barrier, results = threading.Barrier(2), []

    def worker():
        with app.app_context():
            barrier.wait()
            try:
                inv.receive_purchase_order(1, po_id, {"lines": [{"line_id": lid, "quantity": 20}]})
                results.append("ok")
            except ValidationError:
                results.append("rejected")
            except Exception as exc:
                results.append(f"error: {type(exc).__name__}: {exc}")
            finally:
                db.session.remove()

    threads = [threading.Thread(target=worker) for _ in range(2)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert sorted(results) == ["ok", "rejected"]
    db.session.rollback()
    assert inv.usable_map(1)[ing_id] == Decimal("20")
    assert inv.stock_invariant_violations(1) == []
