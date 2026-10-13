"""VAL-7 .. VAL-9 (NFR3, NFR8): upper limits, bounded ranges and type checks found by the 4 Oct 2026 audit.

Every case here used to be accepted (and then distort the plan or overflow a MariaDB column) or answered with a 500.
"""
from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.models import ForecastRun, PreOrder, SalesRecord, StockBatch, User
from app.services import data_management_service as dm
from app.services.errors import ValidationError
from app.services.validation import MAX_INT, MAX_PORTIONS, MAX_STOCK_QTY, Fields
from tests.factories import make_ingredient, make_item

TODAY = date(2026, 9, 25)


def fields_error(name, value, method, **kw):
    f = Fields({name: value})
    getattr(f, method)(name, **kw)
    return f.errors.get(name)


# ---- the validator itself ---------------------------------------------------------------------------
def test_validator_limits_and_places():
    assert fields_error("q", MAX_PORTIONS, "portions", gt=0) is None
    assert fields_error("q", MAX_PORTIONS + 1, "portions", gt=0) == "must be at most 10,000"
    assert fields_error("q", "1000000.000", "stock_qty", gt=0) is None
    assert fields_error("q", "1000000.001", "stock_qty", gt=0) == "must be at most 1,000,000"
    assert fields_error("q", "0.001", "stock_qty", gt=0) is None
    assert fields_error("q", "0.0001", "stock_qty", gt=0) == "must have at most 3 decimal places"
    assert fields_error("p", "650.50", "money") is None
    assert fields_error("p", "650.505", "money") == "must have at most 2 decimal places"
    assert fields_error("id", MAX_INT + 1, "integer", gt=0) == "must be at most 2,147,483,647"
    assert fields_error("n", {"a": 1}, "text") == "must be text"
    assert fields_error("n", ["x"], "text") == "must be text"
    assert fields_error("n", True, "text") == "must be text"
    assert fields_error("n", 42, "text") is None  # a number typed into a text field is still usable text


# ---- fix 1: upper limits through the API --------------------------------------------------------------
@pytest.mark.parametrize("url,body", [
    ("/api/v1/kitchen/prepared", {"date": "2026-09-25", "quantity": MAX_PORTIONS + 1}),
    ("/api/v1/kitchen/waste", {"date": "2026-09-25", "quantity": MAX_PORTIONS + 1, "reason": "overproduction"}),
    ("/api/v1/kitchen/pre-orders", {"target_date": "2026-09-26", "quantity": 10**9}),
    ("/api/v1/kitchen/orders", {"order_date": "2026-09-25", "quantity": 10**9}),
])
def test_kitchen_quantities_have_an_upper_limit(as_role, url, body):
    client = as_role("kitchen")
    item = make_item(name="Burger")
    r = client.post(url, json={"menu_item_id": item.id, **body})
    assert r.status_code == 422, r.get_json()
    assert "must be at most 10,000" in r.get_json()["error"]["fields"]["quantity"]


def test_served_quantity_has_an_upper_limit(as_role):
    client = as_role("kitchen")
    item = make_item(name="Burger")
    r = client.post("/api/v1/sales/served", json={"date": "2026-09-25",
                                                  "lines": [{"menu_item_id": item.id, "quantity": 10**12}]})
    assert r.status_code == 422
    assert SalesRecord.query.count() == 0


def test_absurd_pre_order_can_no_longer_reach_the_reorder_screen(as_role):
    # The audit's case: one 1,000,000,000-portion pre-order turned into "order 999,999,999,100 burger buns".
    client = as_role("kitchen")
    item = make_item(name="Burger")
    r = client.post("/api/v1/kitchen/pre-orders", json={"menu_item_id": item.id, "target_date": "2026-09-26",
                                                        "quantity": 10**9, "status": "confirmed", "customer_name": "Nimal Perera", "pickup_time": "12:30"})
    assert r.status_code == 422 and PreOrder.query.count() == 0
    ok = client.post("/api/v1/kitchen/pre-orders", json={"menu_item_id": item.id, "target_date": "2026-09-26",
                                                         "quantity": 120, "status": "confirmed", "customer_name": "Nimal Perera", "pickup_time": "12:30"})
    assert ok.status_code == 201


@pytest.mark.parametrize("quantity,message", [
    ("1e15", "must be at most 1,000,000"),
    ("0.0001", "must have at most 3 decimal places"),
])
def test_stock_in_quantity_is_bounded(as_role, quantity, message):
    client = as_role("inventory")
    ing = make_ingredient(name="Chicken")
    r = client.post("/api/v1/stock/in", json={"ingredient_id": ing.id, "quantity": quantity})
    assert r.status_code == 422 and r.get_json()["error"]["fields"]["quantity"] == message
    assert StockBatch.query.count() == 0


def test_stock_limit_on_ingredient_master_data(as_role):
    client = as_role("inventory")
    r = client.post("/api/v1/ingredients", json={"name": "Oil", "unit": "l", "reorder_qty": MAX_STOCK_QTY * 10})
    assert r.status_code == 422 and "reorder_qty" in r.get_json()["error"]["fields"]


def test_money_places_on_menu_price(as_role):
    admin = as_role("admin")
    r = admin.post("/api/v1/menu-items", json={"name": "Pizza", "price": "650.555"})
    assert r.status_code == 422 and r.get_json()["error"]["fields"]["price"] == "must have at most 2 decimal places"


def test_override_quantity_has_an_upper_limit(app):
    f = Fields({"final_qty": 10**12})
    f.portions("final_qty", min=0)
    assert f.errors == {"final_qty": "must be at most 10,000"}


# ---- fix 1: plausibility check on the sales import ------------------------------------------------------
@pytest.fixture()
def burger(app):
    return make_item(name="Burger", price=650)


def _history(start, days, qty=40):
    return "date,item,quantity\n" + "".join(f"{start + timedelta(days=i)},Burger,{qty}\n" for i in range(days))


def test_import_rejects_quantities_above_the_hard_limit(burger):
    r = dm.import_sales_csv(1, "date,item,quantity\n2026-09-01,Burger,999999999\n", dry_run=True)
    assert r["accepted"] == 0 and r["errors"][0]["message"] == "must be at most 10,000"


def test_import_rejects_a_day_far_above_the_stored_history(burger):
    dm.import_sales_csv(1, _history(date(2026, 8, 1), 10, qty=40), dry_run=False)   # highest stored day: 40
    csv = "date,item,quantity\n2026-09-01,Burger,400\n2026-09-02,Burger,401\n"       # 400 = 10 x 40 is allowed
    r = dm.import_sales_csv(1, csv, dry_run=True)
    assert (r["accepted"], r["rejected"]) == (1, 1)
    assert r["errors"][0]["row"] == 3
    assert "more than 10 times the highest day on record for Burger (40)" in r["errors"][0]["message"]


def test_import_without_history_compares_with_the_file_itself(burger):
    # Seven days of 40 and one of 4000 (an extra zero): the median of the eight rows is 40, and 4000 > 10 x 40.
    csv = _history(date(2026, 9, 1), 7, qty=40) + "2026-09-08,Burger,4000\n"
    r = dm.import_sales_csv(1, csv, dry_run=False)
    assert (r["accepted"], r["rejected"]) == (7, 1)
    assert "the typical day in this file" in r["errors"][0]["message"]
    assert SalesRecord.query.count() == 7


def test_import_with_too_few_rows_and_no_history_only_uses_the_hard_limit(burger):
    r = dm.import_sales_csv(1, "date,item,quantity\n2026-09-01,Burger,5\n2026-09-02,Burger,900\n", dry_run=True)
    assert (r["accepted"], r["rejected"]) == (2, 0)


# ---- fix 2: bounded ranges ------------------------------------------------------------------------------
@pytest.mark.parametrize("days,status", [("0", 422), ("-5", 422), ("32", 422), ("100000", 422), ("31", 200), ("1", 200)])
def test_ingredient_forecast_window_is_bounded(as_role, days, status):
    client = as_role("inventory")
    r = client.get(f"/api/v1/recommendations/ingredient-forecast?days={days}")
    assert r.status_code == status, r.get_json()
    if status == 422:
        assert r.get_json()["error"]["fields"]["days"] == "must be between 1 and 31"


@pytest.mark.parametrize("horizon", ["abc", 0, -3, 15, 100000, True])
def test_bad_forecast_horizon_is_rejected_before_a_run_is_recorded(as_role, horizon):
    client = as_role("admin")
    r = client.post("/api/v1/forecast-runs", json={"horizon_days": horizon})
    assert r.status_code == 422, r.get_json()
    assert "horizon_days" in r.get_json()["error"]["fields"]
    assert ForecastRun.query.count() == 0   # no failed run, so no forecast_failed alert either


def test_out_of_range_integer_arguments_are_a_validation_error(as_role):
    client = as_role("admin")
    r = client.get("/api/v1/forecast-runs?limit=99999999999999999999")
    assert r.status_code == 422 and r.get_json()["error"]["fields"]["limit"] == "is out of range"
    assert client.get("/api/v1/forecast-runs?limit=-5").status_code == 200


def test_negative_movement_limit_does_not_return_everything(app):
    from app.services import inventory_service as inv
    from tests.factories import add_batch
    ing = make_ingredient(name="Chicken")
    for _ in range(3):
        add_batch(ing, 5)
    assert len(inv.list_movements(1, limit=-1)["rows"]) == 1   # SQLite treats LIMIT -1 as "no limit"
    assert len(inv.list_movements(1, limit=2, offset=-4)["rows"]) == 2


# ---- fix 3: type checks on users, menu and settings ----------------------------------------------------------
@pytest.mark.parametrize("body,field", [
    ({"full_name": 5, "username": "t1", "role": "kitchen", "password": "password123"}, None),
    ({"full_name": "A", "username": ["x"], "role": "kitchen", "password": "password123"}, "username"),
    ({"full_name": "A", "username": "t3", "role": "kitchen", "password": 123456789}, "password"),
    ({"full_name": {"a": 1}, "username": "t4", "role": "kitchen", "password": "password123"}, "full_name"),
    ({"full_name": "A", "username": "has space", "role": "kitchen", "password": "password123"}, "username"),
    ({"full_name": "A", "username": "t6", "role": "kitchen", "password": "password123", "email": "nope"}, "email"),
    ({"full_name": "A", "username": "t7", "role": ["admin"], "password": "password123"}, "role"),
])
def test_create_user_rejects_wrong_types_without_a_500(as_role, body, field):
    client = as_role("admin")
    r = client.post("/api/v1/users", json=body)
    if field is None:   # a number is acceptable text for a name
        assert r.status_code == 201 and r.get_json()["data"]["full_name"] == "5"
        return
    assert r.status_code == 422, r.get_json()
    assert field in r.get_json()["error"]["fields"]


def test_update_user_needs_a_real_boolean_and_a_valid_email(as_role, users):
    client = as_role("admin")
    target = users["inventory"]
    r = client.patch(f"/api/v1/users/{target.id}", json={"is_active": "false"})
    assert r.status_code == 422 and r.get_json()["error"]["fields"]["is_active"] == "must be true or false"
    assert User.query.get(target.id).is_active is True
    r = client.patch(f"/api/v1/users/{target.id}", json={"email": "not-an-email"})
    assert r.status_code == 422
    r = client.patch(f"/api/v1/users/{target.id}", json={"email": "inv@example.lk", "full_name": "  Nimal  "})
    assert r.status_code == 200 and r.get_json()["data"]["full_name"] == "Nimal"
    r = client.patch(f"/api/v1/users/{target.id}", json={"is_active": False})
    assert r.status_code == 200 and r.get_json()["data"]["is_active"] is False


def test_password_reset_needs_a_text_password(as_role, users):
    client = as_role("admin")
    r = client.post(f"/api/v1/users/{users['kitchen'].id}/password", json={"password": 12345678})
    assert r.status_code == 422 and "password" in r.get_json()["error"]["fields"]


def test_menu_item_is_active_needs_a_real_boolean(as_role):
    client = as_role("admin")
    item = make_item(name="Burger")
    r = client.patch(f"/api/v1/menu-items/{item.id}", json={"is_active": "no"})
    assert r.status_code == 422 and r.get_json()["error"]["fields"]["is_active"] == "must be true or false"


def test_settings_alert_switches_must_be_an_object(as_role):
    client = as_role("admin")
    r = client.put("/api/v1/settings", json={"alerts": ["alert.low_stock.enabled"]})
    assert r.status_code == 422 and "alerts" in r.get_json()["error"]["fields"]


# ---- bounded forecast range (audit 7 Oct 2026, S3) ----------------------------------------------------------
@pytest.mark.parametrize("role", ["kitchen", "inventory", "admin"])
@pytest.mark.parametrize("query,status", [
    ("from=2026-09-27&to=2026-10-03", 200),                    # the 7 days the pages ask for
    ("from=2026-09-01&to=2026-11-01", 200),                    # 62 days, the limit
    ("from=2026-09-01&to=2026-11-02", 422),                    # 63 days
    ("from=0001-01-01&to=9999-12-31", 422),                    # would list millions of missing dates
    ("from=2026-10-03&to=2026-09-27", 422),                    # end before start
])
def test_forecast_range_is_bounded(as_role, role, query, status):
    r = as_role(role).get(f"/api/v1/forecasts?{query}")
    assert r.status_code == status, r.get_json()
    if status == 422:
        assert "to" in r.get_json()["error"]["fields"]


def test_forecast_run_for_a_past_date_is_refused_by_the_api(as_role):
    r = as_role("admin").post("/api/v1/forecast-runs?as_of=2020-01-01", json={})
    assert r.status_code == 422 and "as_of" in r.get_json()["error"]["fields"]
    assert ForecastRun.query.count() == 0
