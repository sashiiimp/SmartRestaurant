"""RD-1 .. RD-4: the figures the role dashboards show, checked against values worked out by hand from a small dataset.
Today is Fri 25 Sep 2026 (conftest). Safety buffer 10 %, so a forecast of 10.5 becomes 11.55 -> 12 portions."""
from datetime import date, time
from decimal import Decimal

import pytest

from app.extensions import db
from app.models import (FoodWaste, Forecast, ForecastRun, PreOrder, PreparationRecord, PurchaseOrder, SalesRecord,
                        StockRequest, Supplier)
from app.services import dashboard_service as dash
from app.services import recommendation_service as rec
from tests.factories import add_batch, add_recipe, make_ingredient, make_item

D = lambda day: date(2026, 9, day)


def _run(as_of, rows, latest=True):
    """One forecast run made on `as_of` with (item, day, qty) rows."""
    run = ForecastRun(outlet_id=1, as_of_date=as_of, horizon_days=7, trigger_type="cli", status="ok")
    db.session.add(run)
    db.session.flush()
    for item, day, qty in rows:
        db.session.add(Forecast(outlet_id=1, run_id=run.id, menu_item_id=item.id, target_date=day,
                                predicted_qty=Decimal(qty), method="model", is_latest=latest))
    db.session.commit()


@pytest.fixture()
def world(app):
    burger, fries = make_item(name="Burger", price=500), make_item(name="Fries", price=300)
    # recorded sales in the admin period (18-24 Sep)
    for day, item, q in ((20, burger, 30), (20, fries, 20), (22, burger, 40)):
        db.session.add(SalesRecord(outlet_id=1, menu_item_id=item.id, sale_date=D(day), quantity_sold=q,
                                   unit_price=Decimal(item.price), source="import"))
    db.session.commit()
    # forecasts made BEFORE those days (count for accuracy) ...
    _run(D(19), [(burger, D(20), "25"), (fries, D(20), "25"), (burger, D(22), "50")], latest=False)
    # ... and one made AFTER 22 Sep for 22 Sep, which must never count
    _run(D(23), [(burger, D(22), "0")], latest=False)
    # today's and tomorrow's forecast (the latest run)
    _run(D(25), [(burger, D(25), "10.5"), (fries, D(25), "4.5"), (burger, D(26), "12")])
    return {"burger": burger, "fries": fries}


# ---- RD-1 admin: forecasting performance on the reporting period -------------------------------------------------
def test_admin_accuracy_uses_only_forecasts_made_before_the_day(world):
    acc = dash.admin_dashboard(1, 7)["accuracy"]
    # pairs: burger 20 Sep 25 vs 30, fries 20 Sep 25 vs 20, burger 22 Sep 50 vs 40 (the 0 made on 23 Sep is ignored)
    # absolute errors 5, 5, 10 -> MAE 20 / 3 = 6.667; WAPE 20 / 90 = 22.22 %; bias (pred - actual) (-5 + 5 + 10) / 3
    assert acc["pairs"] == 3 and acc["days"] == 2
    assert acc["mae"] == pytest.approx(6.6667, abs=1e-3)
    assert acc["wape"] == pytest.approx(22.222, abs=1e-2)
    assert acc["bias"] == pytest.approx(3.3333, abs=1e-3)


def test_admin_accuracy_is_empty_without_matching_sales(app):
    make_item(name="Tea")
    assert dash.admin_dashboard(1, 7)["accuracy"] is None


# ---- RD-2 kitchen: the day at a glance --------------------------------------------------------------------------
def test_kitchen_day_figures(world):
    b, f = world["burger"], world["fries"]
    db.session.add_all([
        PreparationRecord(outlet_id=1, menu_item_id=b.id, prep_date=D(25), quantity=6),
        FoodWaste(outlet_id=1, menu_item_id=f.id, waste_date=D(25), quantity=1, reason="overproduction", unit_price=Decimal(300)),
        PreOrder(outlet_id=1, menu_item_id=b.id, target_date=D(25), quantity=3, status="confirmed", customer_name="A", pickup_time=time(12)),
        PreOrder(outlet_id=1, menu_item_id=f.id, target_date=D(25), quantity=2, status="pending", customer_name="B", pickup_time=time(13)),
        PreOrder(outlet_id=1, menu_item_id=f.id, target_date=D(25), quantity=5, status="cancelled", customer_name="C", pickup_time=time(14)),
        PreOrder(outlet_id=1, menu_item_id=b.id, target_date=D(26), quantity=4, status="confirmed", customer_name="D", pickup_time=time(12)),
    ])
    db.session.commit()
    k = dash.kitchen_dashboard(1, D(25))
    day = k["day"]
    assert day["forecast_total"] == 15.0                     # 10.5 + 4.5
    assert (day["items_forecast"], day["items_total"], day["undecided"]) == (2, 2, 2)
    assert k["tiles"]["planned_total"] == 17                 # burger ceil(11.55) = 12, fries ceil(4.95) = 5
    assert day["prepared_total"] == 6
    assert day["served_total"] is None                       # nothing recorded: "not recorded", never 0 sold
    assert day["wasted_total"] == 1
    po = day["pre_orders"]                                    # the cancelled one and tomorrow's are left out
    assert [p["customer_name"] for p in po["rows"]] == ["A", "B"]
    assert (po["pending"], po["portions"]) == (1, 3)


def test_kitchen_decisions_and_served_update_the_figures(world):
    b = world["burger"]
    rec.decide(1, {"menu_item_id": b.id, "date": "2026-09-25", "action": "accept"})
    db.session.add(SalesRecord(outlet_id=1, menu_item_id=b.id, sale_date=D(25), quantity_sold=9, unit_price=Decimal(500),
                               source="kitchen"))
    db.session.commit()
    day = dash.kitchen_dashboard(1, D(25))["day"]
    assert day["undecided"] == 1 and day["served_total"] == 9


def test_kitchen_day_without_forecast(app):
    make_item(name="Tea")
    day = dash.kitchen_dashboard(1, D(25))["day"]
    assert (day["items_forecast"], day["items_total"], day["forecast_total"], day["undecided"]) == (0, 1, 0.0, 0)


# ---- RD-3 inventory: full counts behind the short lists -------------------------------------------------------------
def test_inventory_totals_are_not_capped_by_the_lists(world):
    sup = Supplier(outlet_id=1, name="Lanka", lead_time_days=1)
    db.session.add(sup)
    db.session.commit()
    # 7 ingredients below their minimum with no stock: every one needs reordering, the list shows 5
    ings = [make_ingredient(name=f"Ing {i}", min_stock=5, reorder_level=10, supplier_id=sup.id) for i in range(7)]
    # Bun: 1 per burger. Need over 7 days = burger 12 (25 Sep) + 14 (26 Sep: 12 x 1.1 = 13.2 -> 14) = 26 > 15 usable
    bun = make_ingredient(name="Bun", unit="pcs", min_stock=0, reorder_level=0)
    add_recipe(world["burger"], [(bun, 1)])
    add_batch(bun, 15)
    # batches: 2 expired (one with stock left, one used up), 1 expiring in 2 days, 1 in 10 days
    add_batch(ings[0], 3, expiry=D(23))
    used = add_batch(ings[1], 2, expiry=D(22))
    used.qty_remaining = 0
    add_batch(ings[2], 1, expiry=D(27))
    add_batch(ings[3], 1, expiry=date(2026, 10, 5))
    db.session.add_all([StockRequest(outlet_id=1, status=s, reject_reason="no stock" if s == "rejected" else None)
                        for s in ("pending", "pending", "approved", "issued", "rejected")])
    db.session.add_all([PurchaseOrder(outlet_id=1, supplier_id=sup.id, po_number=f"PO-{s}", status=s)
                        for s in ("draft", "sent", "partially_received", "received", "cancelled")])
    db.session.commit()

    r = dash.inventory_dashboard(1)
    t = r["totals"]
    assert len(r["reorder"]) == 5 and t["reorder"] == len(rec.get_reorder_suggestions(1, D(25))) >= 7
    assert t["at_risk"] == 1 and [x["name"] for x in r["need_vs_stock"] if x["need"] > x["usable"]] == ["Bun"]
    assert r["need_vs_stock"][0]["need"] == 26.0
    assert (t["expired_batches"], t["expiring_batches"]) == (1, 1)
    assert r["pending_requests"] == 2 and t["approved_requests"] == 1
    assert [q["status"] for q in r["requests"]] == ["pending", "pending", "approved"]
    assert (t["po_draft"], t["po_awaiting"]) == (1, 2)


# ---- RD-4 the dashboards stay read-only ----------------------------------------------------------------------------
def test_dashboards_write_nothing_but_alerts(world):
    from app.models import Recommendation, StockMovement
    before = (Recommendation.query.count(), StockMovement.query.count(), SalesRecord.query.count(), Forecast.query.count())
    dash.admin_dashboard(1, 7)
    dash.kitchen_dashboard(1, D(25))
    dash.inventory_dashboard(1)
    assert (Recommendation.query.count(), StockMovement.query.count(), SalesRecord.query.count(), Forecast.query.count()) == before
