"""A12 analytics: every figure is a plain average or ratio, checked by hand against the small dataset below."""
from datetime import date
from decimal import Decimal

import pytest

from app.extensions import db
from app.models import Forecast, ForecastRun, FoodWaste, Holiday, PreparationRecord, Promotion, SalesRecord
from app.services import dashboard_service as dash
from app.services.errors import ValidationError
from tests.factories import make_item

START, END = date(2026, 9, 1), date(2026, 9, 24)


@pytest.fixture()
def world(app):
    a, b = make_item(name="Burger"), make_item(name="Fries")
    # (date, burger, fries): Mon 7 Sep 100, Mon 14 Sep 120, Sat 12 Sep 200, Sat 19 Sep 180, Wed 16 Sep 90
    for d, qa, qb in ((7, 60, 40), (14, 70, 50), (12, 120, 80), (19, 100, 80), (16, 50, 40)):
        for item, q in ((a, qa), (b, qb)):
            db.session.add(SalesRecord(outlet_id=1, menu_item_id=item.id, sale_date=date(2026, 9, d), quantity_sold=q,
                                       unit_price=Decimal("500"), source="import"))
    db.session.add_all([Holiday(outlet_id=1, holiday_date=date(2026, 9, 12), name="Test public", holiday_type="public"),
                        Holiday(outlet_id=1, holiday_date=date(2026, 9, 14), name="Test poya", holiday_type="poya")])
    db.session.add(Promotion(outlet_id=1, name="Weekend deal", start_date=date(2026, 9, 18), end_date=date(2026, 9, 20),
                             applies_to_all=True, discount_pct=Decimal("10"), is_active=True))
    db.session.add(Promotion(outlet_id=1, name="Switched off", start_date=date(2026, 9, 7), end_date=date(2026, 9, 7),
                             applies_to_all=True, discount_pct=Decimal("10"), is_active=False))
    for d, qty, waste in ((7, 50, 5), (14, 40, 0)):
        db.session.add(PreparationRecord(outlet_id=1, menu_item_id=a.id, prep_date=date(2026, 9, d), quantity=qty))
        if waste:
            db.session.add(FoodWaste(outlet_id=1, menu_item_id=a.id, waste_date=date(2026, 9, d), quantity=waste, reason="overproduction", unit_price=Decimal("500")))
    run = ForecastRun(outlet_id=1, as_of_date=date(2026, 9, 1), horizon_days=7, trigger_type="cli", status="ok")
    db.session.add(run); db.session.flush()
    for item, q in ((a, 55), (b, 45)):                      # 7 Sep: forecast 55 and 45 against 60 and 40
        db.session.add(Forecast(outlet_id=1, run_id=run.id, menu_item_id=item.id, target_date=date(2026, 9, 7),
                                predicted_qty=Decimal(q), method="model", is_latest=True))
    db.session.commit()
    return {"a": a, "b": b}


def test_demand_by_weekday(world):
    r = dash.analytics(1, START, END)
    by = {w["weekday"]: (w["days"], w["average"]) for w in r["weekday"]}
    assert by["Monday"] == (2, 110.0)              # (100 + 120) / 2
    assert by["Saturday"] == (2, 190.0)            # (200 + 180) / 2
    assert by["Wednesday"] == (1, 90.0)
    assert by["Tuesday"] == (0, None)
    assert r["days_with_sales"] == 5 and [w["weekday"] for w in r["weekday"]][0] == "Monday"


def test_holiday_groups_against_ordinary_days(world):
    r = dash.analytics(1, START, END)
    by = {c["group"]: (c["days"], c["average"]) for c in r["calendar"]}
    assert by["Public holiday"] == (1, 200.0)      # Sat 12 Sep
    assert by["Poya day"] == (1, 120.0)            # Mon 14 Sep
    assert by["School holiday"] == (0, None)
    assert by["Ordinary day"] == (3, 123.3)        # (100 + 180 + 90) / 3


def test_promotion_days_use_only_active_promotions(world):
    r = dash.analytics(1, START, END)
    by = {c["group"]: (c["days"], c["average"]) for c in r["promotion"]}
    assert by["Promotion running"] == (1, 180.0)   # Sat 19 Sep is inside 18-20 Sep; the switched-off one is ignored
    assert by["No promotion"] == (4, 127.5)        # (100 + 120 + 200 + 90) / 4


def test_forecast_error_by_day(world):
    r = dash.analytics(1, START, END)
    assert r["forecast_error"] == [{"date": "2026-09-07", "mae": 5.0, "wape": 10.0}]   # |55-60| + |45-40| = 10 over 2 items and 100 sold
    assert r["forecast_pairs"] == 2


def test_waste_rate_by_day_only_where_food_was_prepared(world):
    r = dash.analytics(1, START, END)
    assert r["waste"] == [{"date": "2026-09-07", "prepared": 50, "wasted": 5, "rate": 10.0},
                          {"date": "2026-09-14", "prepared": 40, "wasted": 0, "rate": 0.0}]


def test_range_limits_the_data_and_labels_the_source(world):
    r = dash.analytics(1, date(2026, 9, 10), date(2026, 9, 15))
    assert r["days_with_sales"] == 2 and {w["weekday"]: w["days"] for w in r["weekday"]}["Monday"] == 1     # Sat 12 and Mon 14 only
    assert r["data_source"] == "Synthetic demo data" and r["from"] == "2026-09-10"
    with pytest.raises(ValidationError):
        dash.analytics(1, END, START)


def test_empty_period_gives_empty_but_valid_results(app):
    r = dash.analytics(1, START, END)
    assert r["days_with_sales"] == 0 and r["forecast_error"] == [] and r["waste"] == []
    assert all(w["average"] is None for w in r["weekday"])
