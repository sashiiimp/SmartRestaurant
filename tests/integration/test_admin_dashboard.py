"""A1 admin dashboard: expected values worked out by hand from the small dataset below (today is Fri 25 Sep 2026,
so the 7-day period is Fri 18 Sep to Thu 24 Sep and the forecast window is 25 Sep to 1 Oct)."""
from datetime import date
from decimal import Decimal

import pytest

from app.extensions import db
from app.models import Forecast, ForecastRun, FoodWaste, PreparationRecord, SalesRecord
from app.services import dashboard_service as dash
from app.services.errors import ValidationError
from tests.factories import add_batch, make_ingredient, make_item


@pytest.fixture()
def world(app):
    burger, fries = make_item(name="Burger", price=500), make_item(name="Fries", price=300)
    # sales (date, item, qty, price): 17 Sep is before the period and must not count
    for d, item, q, price in ((20, burger, 30, 500), (20, fries, 20, 300), (22, burger, 40, 500), (22, fries, 10, 300),
                              (17, burger, 99, 500)):
        db.session.add(SalesRecord(outlet_id=1, menu_item_id=item.id, sale_date=date(2026, 9, d), quantity_sold=q,
                                   unit_price=Decimal(price), source="import"))
    # production: 25 Sep is today, outside the period
    for d, item, q in ((20, burger, 40), (20, fries, 25), (22, burger, 45), (22, fries, 10), (25, burger, 50)):
        db.session.add(PreparationRecord(outlet_id=1, menu_item_id=item.id, prep_date=date(2026, 9, d), quantity=q))
    for d, item, q, price in ((20, burger, 10, 500), (20, fries, 5, 300), (22, burger, 5, 500)):
        db.session.add(FoodWaste(outlet_id=1, menu_item_id=item.id, waste_date=date(2026, 9, d), quantity=q,
                                 reason="overproduction", unit_price=Decimal(price)))
    run = ForecastRun(outlet_id=1, as_of_date=date(2026, 9, 25), horizon_days=7, trigger_type="cli", status="ok")
    db.session.add(run); db.session.flush()
    for item, d, q, latest in ((burger, 25, "10.5", True), (fries, 25, "4.5", True), (burger, 26, "12", True),
                               (burger, 27, "99", False)):          # an older, replaced forecast is not shown
        db.session.add(Forecast(outlet_id=1, run_id=run.id, menu_item_id=item.id, target_date=date(2026, 9, d),
                                predicted_qty=Decimal(q), method="model", is_latest=latest))
    db.session.commit()

    bun = make_ingredient(name="Bun", unit="pcs", min_stock=2, reorder_level=10)
    chicken = make_ingredient(name="Chicken", min_stock=3, reorder_level=10)
    cheese = make_ingredient(name="Cheese", min_stock=2, reorder_level=5)
    make_ingredient(name="Lettuce", min_stock=1, reorder_level=2)          # no stock at all
    sauce = make_ingredient(name="Sauce", unit="l", min_stock=0, reorder_level=1)
    add_batch(bun, 15)
    add_batch(chicken, 5)
    add_batch(cheese, 1)
    add_batch(sauce, 4, expiry=date(2026, 9, 23))                           # expired, so not usable
    return {"burger": burger, "fries": fries}


def test_period_ends_yesterday_and_totals_are_historical(world):
    r = dash.admin_dashboard(1, 7)
    assert (r["from"], r["to"]) == ("2026-09-18", "2026-09-24")
    assert r["sales"] == {"quantity": 100, "revenue": 44000.0}             # 30+20+40+10; 15000+6000+20000+3000
    assert r["waste"] == {"quantity": 20, "value": 9000.0}                 # 10+5+5; 5000+1500+2500


def test_food_waste_rate_is_wasted_over_prepared(world):
    r = dash.admin_dashboard(1, 7)
    # prepared 40+25+45+10 = 120 (today's 50 excluded); 20 / 120 = 16.67 %
    assert r["waste_rate"] == {"prepared": 120, "wasted": 20, "pct": 16.7}
    assert r["waste_threshold_pct"] == 15.0


def test_waste_rate_is_none_when_nothing_was_prepared(app):
    r = dash.admin_dashboard(1, 30)
    assert r["waste_rate"] == {"prepared": 0, "wasted": 0, "pct": None}
    assert r["coverage"] == {"days": 30, "days_with_sales": 0, "latest_sales_date": None}


def test_coverage_reports_a_partly_recorded_period(world):
    assert dash.admin_dashboard(1, 7)["coverage"] == {"days": 7, "days_with_sales": 2, "latest_sales_date": "2026-09-22"}


def test_forecast_days_mark_missing_days_as_none_not_zero(world):
    r = dash.admin_dashboard(1, 7)
    days = r["forecast_next7"]
    assert [f["date"] for f in days] == ["2026-09-25", "2026-09-26", "2026-09-27", "2026-09-28", "2026-09-29",
                                         "2026-09-30", "2026-10-01"]
    assert days[0] == {"date": "2026-09-25", "qty": 15.0, "items": 2}     # 10.5 + 4.5
    assert days[1] == {"date": "2026-09-26", "qty": 12.0, "items": 1}
    assert all(f["qty"] is None and f["items"] == 0 for f in days[2:])   # 27 Sep only has a replaced forecast
    assert r["forecast_next7_total"] == 27.0
    assert r["menu_items_active"] == 2


def test_stock_summary_lists_out_then_low(world):
    r = dash.admin_dashboard(1, 7)
    s = r["stock"]
    assert (s["ingredients"], s["out"], s["low"]) == (5, 2, 2) and r["low_stock_count"] == 4
    # out first (Lettuce: none, Sauce: only an expired batch), then low by usable / reorder level: Cheese 0.2, Chicken 0.5
    assert [(x["name"], x["status"], x["is_critical"]) for x in s["rows"]] == [
        ("Lettuce", "out", True), ("Sauce", "out", True), ("Cheese", "low", True), ("Chicken", "low", False)]
    sauce = s["rows"][1]
    assert (sauce["usable"], sauce["on_hand"]) == (0.0, 4.0)


def test_range_must_be_7_or_30(app):
    with pytest.raises(ValidationError):
        dash.admin_dashboard(1, 14)


def test_admin_dashboard_api(as_role, world):
    client = as_role("admin")
    resp = client.get("/api/v1/dashboards/admin?range=7")
    assert resp.status_code == 200
    data = resp.get_json()["data"]
    assert data["waste_rate"]["pct"] == 16.7 and len(data["forecast_next7"]) == 7 and data["stock"]["out"] == 2
    assert client.get("/api/v1/dashboards/admin?range=14").status_code == 422
