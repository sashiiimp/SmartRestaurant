"""I16 consistency check and A13 inventory reports. Movements of the chicken fixture are worked out by hand."""
from datetime import date
from decimal import Decimal

import pytest

from app.extensions import db
from app.services import dashboard_service as dash
from app.services import inventory_service as inv
from app.services.errors import NotFoundError, ValidationError
from tests.factories import add_batch, make_ingredient


@pytest.fixture()
def chicken(app):
    """Movements: 21 Sep +10, 22 Sep +5 and -3 (issued), 23 Sep -2 (spoiled), 24 Sep an adjustment of +1."""
    ing = make_ingredient(name="Chicken", unit="kg")
    add_batch(ing, 10, received=date(2026, 9, 21), expiry=date(2026, 12, 1), batch_no="B1")
    inv.record_stock_in(1, {"ingredient_id": ing.id, "quantity": 5, "received_date": "2026-09-22", "expiry_date": "2026-12-05"})
    inv.record_stock_out(1, {"ingredient_id": ing.id, "quantity": 3, "movement_date": "2026-09-22"})
    inv.record_wastage(1, {"ingredient_id": ing.id, "quantity": 2, "movement_date": "2026-09-23", "reason": "spoiled"})
    inv.record_adjustment(1, {"ingredient_id": ing.id, "counted_quantity": 11, "movement_date": "2026-09-24", "note": "count"})
    return ing


# ---- I16 data check --------------------------------------------------------------------------------------
def test_clean_data_is_consistent(chicken):
    r = inv.consistency_check(1)
    assert r["consistent"] is True and r["mismatches"] == [] and r["batches_over_received"] == [] and r["expired_with_stock"] == []
    assert (r["ingredients_checked"], r["batches_checked"]) == (1, 3)      # the first two batches plus ADJ


def test_a_batch_changed_behind_the_movements_is_detected(chicken):
    from app.models import StockBatch
    b = StockBatch.query.filter_by(batch_no="B1").one()
    b.qty_remaining = b.qty_remaining + Decimal("8")                        # B1 had 5 kg left; 8 kg appear without a movement
    db.session.commit()
    r = inv.consistency_check(1)
    assert r["consistent"] is False
    m = r["mismatches"][0]
    assert (m["ingredient"], m["movements"], m["batches"], m["difference"]) == ("Chicken", 11.0, 19.0, 8.0)
    assert [x["batch_no"] for x in r["batches_over_received"]] == ["B1"]     # 13 left of 10 received


def test_expired_stock_is_listed_but_is_not_an_inconsistency(app):
    ing = make_ingredient(name="Milk", unit="L")
    add_batch(ing, 6, received=date(2026, 9, 1), expiry=date(2026, 9, 20), batch_no="OLD")
    r = inv.consistency_check(1)
    assert r["consistent"] is True
    assert [(b["ingredient"], b["batch_no"], b["qty_remaining"]) for b in r["expired_with_stock"]] == [("Milk", "OLD", 6.0)]


# ---- A13 inventory trend -----------------------------------------------------------------------------------
def test_trend_is_rebuilt_from_movements_and_ends_at_on_hand(chicken):
    t = dash.inventory_trend(1, chicken.id, date(2026, 9, 20), date(2026, 9, 25))
    assert t["opening"] == 0.0
    rows = {r["date"]: r for r in t["rows"]}
    assert [r["closing"] for r in t["rows"]] == [0.0, 10.0, 12.0, 10.0, 11.0, 11.0]
    assert (rows["2026-09-22"]["stock_in"], rows["2026-09-22"]["stock_out"]) == (5.0, -3.0)
    assert (rows["2026-09-23"]["wastage"], rows["2026-09-24"]["adjustment"]) == (-2.0, 1.0)
    assert t["closing"] == 11.0 == float(inv.on_hand_map(1)[chicken.id])           # trend, table and stock all agree


def test_trend_opening_balance_counts_earlier_movements(chicken):
    t = dash.inventory_trend(1, chicken.id, date(2026, 9, 23), date(2026, 9, 24))
    assert t["opening"] == 12.0 and [r["closing"] for r in t["rows"]] == [10.0, 11.0]


def test_trend_validation(chicken):
    with pytest.raises(ValidationError):
        dash.inventory_trend(1, chicken.id, date(2026, 9, 25), date(2026, 9, 20))
    with pytest.raises(NotFoundError):
        dash.inventory_trend(1, 999, date(2026, 9, 20), date(2026, 9, 25))


# ---- A13 movement report -------------------------------------------------------------------------------------
def test_movement_report_filters_and_limit(chicken):
    r = dash.movement_report(1, date(2026, 9, 20), date(2026, 9, 25))
    assert r["total"] == 5 and r["shown"] == 5
    assert [(m["date"], m["type"], m["quantity"]) for m in r["rows"]][:2] == [("2026-09-24", "adjustment", 1.0), ("2026-09-23", "wastage", -2.0)]
    assert dash.movement_report(1, date(2026, 9, 20), date(2026, 9, 25), mtype="stock_in")["total"] == 2
    assert dash.movement_report(1, date(2026, 9, 23), date(2026, 9, 23))["total"] == 1
    small = dash.movement_report(1, date(2026, 9, 20), date(2026, 9, 25), limit=2)
    assert (small["total"], small["shown"]) == (5, 2)
    assert dash.movement_report(1, date(2026, 9, 20), date(2026, 9, 25), limit=None)["shown"] == 5
    with pytest.raises(ValidationError):
        dash.movement_report(1, date(2026, 9, 20), date(2026, 9, 25), mtype="bogus")
    assert sum(m["quantity"] for m in dash.movement_report(1, date(2026, 9, 1), date(2026, 9, 25), limit=None)["rows"]) == 11.0


def test_stock_levels_report_matches_the_inventory_rows(chicken):
    r = dash.stock_levels_report(1)
    assert r["rows"] == inv.stock_levels(1, date(2026, 9, 25))
