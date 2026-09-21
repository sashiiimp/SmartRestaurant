"""INV-1, INV-2, INV-3, VAL-5, VAL-6: stock movements, FEFO and integrity (TESTING.md 4.5)."""
import threading
from datetime import date
from decimal import Decimal

import pytest

from app.extensions import db
from app.models import StockBatch, StockMovement
from app.services import inventory_service as inv
from app.services.errors import ValidationError
from tests.factories import add_batch, make_ingredient

TODAY = date(2026, 9, 25)


def check_invariant():
    assert inv.stock_invariant_violations(1) == []


@pytest.fixture()
def chicken(app):
    ing = make_ingredient(name="Chicken", unit="kg", min_stock=5, reorder_level=10)
    b1 = add_batch(ing, 3, received=date(2026, 9, 20), expiry=date(2026, 10, 10), batch_no="B1")
    b2 = add_batch(ing, 4, received=date(2026, 9, 21), expiry=date(2026, 10, 5), batch_no="B2")
    b3 = add_batch(ing, 10, received=date(2026, 9, 22), expiry=None, batch_no="B3")
    b4 = add_batch(ing, 6, received=date(2026, 9, 10), expiry=date(2026, 9, 20), batch_no="B4")
    return ing, {"B1": b1, "B2": b2, "B3": b3, "B4": b4}


def remaining(batches):
    return {k: float(db.session.get(StockBatch, b.id).qty_remaining) for k, b in batches.items()}


def test_usable_excludes_expired_and_on_hand_includes_it(chicken):
    ing, _ = chicken
    assert inv.usable_map(1, TODAY)[ing.id] == Decimal("17")     # 3 + 4 + 10
    assert inv.on_hand_map(1)[ing.id] == Decimal("23")           # plus the expired 6
    check_invariant()


def test_fefo_scenario_from_the_test_plan(chicken):
    ing, b = chicken
    out = inv.record_stock_out(1, {"ingredient_id": ing.id, "quantity": 5, "reason": "issued_to_kitchen"})
    assert out["batches"] == [{"batch_id": b["B2"].id, "quantity": 4.0}, {"batch_id": b["B1"].id, "quantity": 1.0}]
    assert remaining(b) == {"B1": 2.0, "B2": 0.0, "B3": 10.0, "B4": 6.0}
    moves = StockMovement.query.filter_by(movement_type="stock_out").order_by(StockMovement.id).all()
    assert [float(m.quantity) for m in moves] == [-4.0, -1.0]
    check_invariant()
    with pytest.raises(ValidationError) as e:      # usable is 12 (B1 2 + B3 10); the expired batch does not count
        inv.record_stock_out(1, {"ingredient_id": ing.id, "quantity": 20})
    assert e.value.code == "insufficient_stock" and e.value.extra["available"] == 12.0
    assert remaining(b) == {"B1": 2.0, "B2": 0.0, "B3": 10.0, "B4": 6.0}   # no partial deduction
    inv.record_wastage(1, {"ingredient_id": ing.id, "quantity": 6, "reason": "expired"})
    assert remaining(b)["B4"] == 0.0
    check_invariant()


def test_stock_in_creates_batch_and_movement(app):
    ing = make_ingredient(name="Oil", unit="L")
    out = inv.record_stock_in(1, {"ingredient_id": ing.id, "quantity": "12.5", "received_date": "2026-09-24",
                                  "expiry_date": "2026-12-01", "unit_cost": "640"})
    assert out["usable"] == 12.5
    b = StockBatch.query.one()
    assert (b.qty_received, b.qty_remaining, b.unit_cost) == (Decimal("12.500"), Decimal("12.500"), Decimal("640.00"))
    assert float(StockMovement.query.one().quantity) == 12.5
    check_invariant()


@pytest.mark.parametrize("data,field", [
    ({"quantity": 0}, "quantity"), ({"quantity": -1}, "quantity"), ({"quantity": "abc"}, "quantity"),
    ({"quantity": 5, "received_date": "2026-09-30"}, "received_date"),
    ({"quantity": 5, "received_date": "2026-09-10", "expiry_date": "2026-09-01"}, "expiry_date"),
])
def test_stock_in_validation(app, data, field):
    ing = make_ingredient()
    with pytest.raises(ValidationError) as e:
        inv.record_stock_in(1, {"ingredient_id": ing.id, **data})
    assert field in e.value.fields
    assert StockBatch.query.count() == 0


def test_wastage_reason_required_and_validated(chicken):
    ing, _ = chicken
    with pytest.raises(ValidationError) as e:
        inv.record_wastage(1, {"ingredient_id": ing.id, "quantity": 1, "reason": "fun"})
    assert "reason" in e.value.fields


def test_ingredient_rules(app):
    """VAL-5, VAL-6"""
    with pytest.raises(ValidationError) as e:
        inv.create_ingredient(1, {"name": "X", "unit": "kg", "min_stock": 10, "reorder_level": 5})
    assert "reorder_level" in e.value.fields
    ing = inv.create_ingredient(1, {"name": "Y", "unit": "kg", "min_stock": 1, "reorder_level": 2})
    inv.update_ingredient(1, ing.id, {"unit": "g"})   # allowed before any movement
    inv.record_stock_in(1, {"ingredient_id": ing.id, "quantity": 1})
    with pytest.raises(ValidationError) as e:
        inv.update_ingredient(1, ing.id, {"unit": "kg"})
    assert "unit" in e.value.fields
    with pytest.raises(ValidationError):
        inv.create_ingredient(1, {"name": "Y", "unit": "kg"})   # duplicate name


def test_stock_levels_status(app):
    a = make_ingredient(name="A", min_stock=5, reorder_level=10)
    b = make_ingredient(name="B", min_stock=5, reorder_level=10)
    c = make_ingredient(name="C", min_stock=5, reorder_level=10)
    d = make_ingredient(name="D", min_stock=5, reorder_level=10)
    add_batch(a, 12); add_batch(b, 8); add_batch(c, 4)
    got = {r["name"]: (r["status"], r["is_critical"]) for r in inv.stock_levels(1, TODAY)}
    assert got == {"A": ("ok", False), "B": ("low", False), "C": ("low", True), "D": ("out", True)}


@pytest.mark.mysql
def test_concurrent_stock_outs_never_go_negative(app):
    """INV-3: two parallel stock-outs of 8 against 10 usable: exactly one succeeds."""
    ing = make_ingredient(name="Chicken", unit="kg")
    add_batch(ing, 10, received=date(2026, 9, 20), expiry=date(2026, 12, 1))
    ing_id = ing.id
    barrier, results = threading.Barrier(2), []

    def worker():
        with app.app_context():
            barrier.wait()
            try:
                inv.record_stock_out(1, {"ingredient_id": ing_id, "quantity": 8})
                results.append("ok")
            except ValidationError:
                results.append("rejected")
            except Exception as exc:  # surface anything unexpected instead of hiding it in the thread
                results.append(f"error: {type(exc).__name__}: {exc}")
            finally:
                db.session.remove()

    threads = [threading.Thread(target=worker) for _ in range(2)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert sorted(results) == ["ok", "rejected"]
    db.session.rollback()   # end this session's old REPEATABLE READ snapshot before re-reading
    assert db.session.query(StockBatch).one().qty_remaining == Decimal("2.000")
    check_invariant()
