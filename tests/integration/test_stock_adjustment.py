"""I14: stock adjustment. Hand-calculated against the batches below (TESTING.md style)."""
from datetime import date
from decimal import Decimal

import pytest

from app.models import AuditLog, StockBatch, StockMovement
from app.services import inventory_service as inv
from app.services.errors import NotFoundError, ValidationError
from tests.factories import add_batch, make_ingredient

TODAY = date(2026, 9, 25)


def remaining(batches):
    return {k: b.qty_remaining for k, b in batches.items()}


@pytest.fixture()
def chicken(app):
    """On hand 23 kg: B4 6 (expired 20 Sep), B2 4 (exp 5 Oct), B1 3 (exp 10 Oct), B3 10 (no expiry)."""
    ing = make_ingredient(name="Chicken", unit="kg", min_stock=5, reorder_level=10)
    b = {"B1": add_batch(ing, 3, received=date(2026, 9, 20), expiry=date(2026, 10, 10), batch_no="B1"),
         "B2": add_batch(ing, 4, received=date(2026, 9, 21), expiry=date(2026, 10, 5), batch_no="B2"),
         "B3": add_batch(ing, 10, received=date(2026, 9, 22), expiry=None, batch_no="B3"),
         "B4": add_batch(ing, 6, received=date(2026, 9, 10), expiry=date(2026, 9, 20), batch_no="B4")}
    return ing, b


def adjust(ing, counted, note="stock take", **extra):
    return inv.record_adjustment(1, {"ingredient_id": ing.id, "counted_quantity": counted, "note": note, **extra})


def test_small_shortfall_takes_the_expired_batch_first(chicken):
    ing, b = chicken
    r = adjust(ing, 20)
    assert r["difference"] == -3.0 and r["on_hand_before"] == 23.0
    assert remaining(b) == {"B1": 3, "B2": 4, "B3": 10, "B4": 3}
    m = StockMovement.query.filter_by(movement_type="adjustment").one()
    assert m.quantity == Decimal("-3") and m.batch_id == b["B4"].id and m.note == "stock take"
    assert inv.stock_invariant_violations(1) == []


def test_large_shortfall_walks_batches_by_earliest_expiry(chicken):
    ing, b = chicken
    r = adjust(ing, 12)              # difference -11 = B4 6 + B2 4 + B1 1
    assert r["difference"] == -11.0
    assert remaining(b) == {"B1": 2, "B2": 0, "B3": 10, "B4": 0}
    assert sorted(x["quantity"] for x in r["batches"]) == [1.0, 4.0, 6.0]
    assert inv.stock_invariant_violations(1) == []


def test_count_of_zero_empties_everything(chicken):
    ing, b = chicken
    adjust(ing, 0)
    assert all(v == 0 for v in remaining(b).values())
    assert inv.stock_invariant_violations(1) == []


def test_surplus_creates_a_batch_without_expiry(chicken):
    ing, b = chicken
    r = adjust(ing, 30)              # +7
    assert r["difference"] == 7.0 and r["usable"] == 24.0     # 3 + 4 + 10 usable, plus the new 7
    new = StockBatch.query.filter_by(batch_no="ADJ-20260925").one()
    assert (new.qty_received, new.qty_remaining, new.expiry_date) == (Decimal("7"), Decimal("7"), None)
    m = StockMovement.query.filter_by(batch_id=new.id).one()
    assert m.movement_type == "adjustment" and m.quantity == Decimal("7")
    assert inv.stock_invariant_violations(1) == []


def test_usable_after_adjustment_excludes_expired_stock(chicken):
    ing, b = chicken
    r = adjust(ing, 20)              # B4 (expired) 6 -> 3, usable is still 17
    assert r["usable"] == 17.0


def test_no_difference_is_rejected_and_nothing_is_written(chicken):
    ing, b = chicken
    with pytest.raises(ValidationError) as e:
        adjust(ing, 23)
    assert "counted_quantity" in e.value.fields
    assert StockMovement.query.filter_by(movement_type="adjustment").count() == 0


def test_validation(chicken):
    ing, _ = chicken
    with pytest.raises(ValidationError) as e:
        inv.record_adjustment(1, {"ingredient_id": ing.id, "counted_quantity": -1, "movement_date": "2026-10-01"})
    assert set(e.value.fields) == {"counted_quantity", "movement_date", "note"}
    with pytest.raises(NotFoundError):
        inv.record_adjustment(1, {"ingredient_id": 999, "counted_quantity": 1, "note": "x"})


def test_ingredient_with_no_batches_can_gain_stock(app):
    ing = make_ingredient(name="Salt")
    adjust(ing, 5)
    assert inv.usable_map(1)[ing.id] == Decimal("5")
    with pytest.raises(ValidationError):
        adjust(ing, 5)


def test_adjustment_is_audited_and_listed_by_type(chicken):
    ing, _ = chicken
    adjust(ing, 20)
    assert AuditLog.query.filter_by(action="stock.adjust").count() == 1
    rows = inv.list_movements(1, ingredient_id=ing.id, mtype="adjustment")["rows"]
    assert [(r["type"], r["quantity"]) for r in rows] == [("adjustment", -3.0)]
