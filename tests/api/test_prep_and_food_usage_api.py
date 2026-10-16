"""HTTP behaviour and roles of the preparation workflow (K4) and Actual Food Usage (K14), added 9 Oct 2026."""
from datetime import date

from tests.conftest import login
from tests.factories import make_item
from tests.integration.test_kitchen_recommendation import add_forecast

TODAY = date(2026, 9, 25)


def as_user(app, users, role):
    c = app.test_client()
    assert login(c, users[role].username).status_code == 302
    return c


def test_prep_workflow_over_http_and_roles(app, users):
    burger = make_item(name="Chicken Burger", batch_size=6)
    add_forecast(burger, TODAY, "47.3")
    kitchen, admin = as_user(app, users, "kitchen"), as_user(app, users, "admin")
    body = {"menu_item_id": burger.id, "date": TODAY.isoformat()}
    assert kitchen.post("/api/v1/recommendations/prep/status", json={**body, "action": "start"}).get_json()["error"]["code"] == "no_plan"
    assert kitchen.post("/api/v1/recommendations/prep/decisions", json={**body, "action": "accept"}).status_code == 201
    assert kitchen.post("/api/v1/kitchen/prepared", json={**body, "quantity": 48}).status_code == 201
    plan = kitchen.get("/api/v1/recommendations/prep", query_string={"date": TODAY.isoformat()}).get_json()["data"]
    assert plan["items"][0]["prep_status"] == "in_progress"
    r = kitchen.post("/api/v1/recommendations/prep/status", json={**body, "action": "done"})
    assert r.status_code == 200 and r.get_json()["meta"]["warnings"] == ["Prepared (48) is 6 below the plan (54)."]
    assert kitchen.post("/api/v1/recommendations/prep/status", json={**body, "action": "done"}).status_code == 409
    assert kitchen.post("/api/v1/recommendations/prep/decisions", json={**body, "action": "accept"}).status_code == 409
    assert kitchen.post("/api/v1/recommendations/prep/status", json={**body, "action": "finish"}).status_code == 422
    assert admin.post("/api/v1/recommendations/prep/status", json={**body, "action": "reopen"}).status_code == 403
    tiles = admin.get("/api/v1/dashboards/kitchen", query_string={"date": TODAY.isoformat()}).get_json()["data"]["tiles"]
    assert (tiles["items_done"], tiles["items_planned"]) == (1, 1)


def test_food_usage_over_http_and_roles(app, users):
    burger = make_item(name="Chicken Burger", batch_size=6)
    kitchen, admin, inventory = (as_user(app, users, r) for r in ("kitchen", "admin", "inventory"))
    day = TODAY.isoformat()
    assert kitchen.post("/api/v1/kitchen/prepared", json={"menu_item_id": burger.id, "date": day, "quantity": 6}).status_code == 201
    body = {"menu_item_id": burger.id, "date": day, "usage_type": "staff_meal", "quantity": 4}
    first = kitchen.post("/api/v1/kitchen/food-usage", json=body)
    assert first.status_code == 201 and first.get_json()["meta"]["warnings"] == []
    again = kitchen.post("/api/v1/kitchen/food-usage", json={**body, "quantity": 7})
    assert again.status_code == 200
    assert again.get_json()["meta"]["warnings"] == ["Chicken Burger: waste (0) and other use (7) add up to 7, more than the 6 prepared."]
    assert kitchen.post("/api/v1/kitchen/food-usage", json={**body, "usage_type": "party"}).status_code == 422
    assert admin.post("/api/v1/kitchen/food-usage", json=body).status_code == 403
    assert inventory.get("/api/v1/kitchen/food-usage").status_code == 403
    got = admin.get("/api/v1/kitchen/food-usage", query_string={"date": day}).get_json()["data"]
    assert got["entries"][0]["quantity"] == 7 and got["balance"][0]["flags"] == ["used_more_than_prepared"]
    rep = admin.get("/api/v1/reports/food-usage", query_string={"from": day, "to": day}).get_json()["data"]
    assert rep["by_type"]["staff_meal"] == 7 and rep["total"] == 7
    csv = admin.get("/api/v1/reports/food-usage", query_string={"from": day, "to": day, "format": "csv"})
    assert csv.status_code == 200 and "Chicken Burger,7,0,0,0,7" in csv.get_data(as_text=True)
    assert kitchen.get("/api/v1/reports/food-usage").status_code == 403
    uid = got["entries"][0]["usage_id"]
    assert kitchen.delete(f"/api/v1/kitchen/food-usage/{uid}").status_code == 200
    assert kitchen.delete(f"/api/v1/kitchen/food-usage/{uid}").status_code == 404


def test_first_prepared_entry_accepts_automatically_over_http(app, users):
    """PREP-AUTO over HTTP: the response says the plan was accepted; the plan row says it was automatic; inventory
    users still cannot record prepared portions."""
    burger = make_item(name="Chicken Burger", batch_size=6)
    add_forecast(burger, TODAY, "47.3")
    kitchen, inventory = as_user(app, users, "kitchen"), as_user(app, users, "inventory")
    body = {"menu_item_id": burger.id, "date": TODAY.isoformat(), "quantity": 12}
    assert inventory.post("/api/v1/kitchen/prepared", json=body).status_code == 403
    r = kitchen.post("/api/v1/kitchen/prepared", json=body)
    assert r.status_code == 201 and r.get_json()["data"]["auto_accepted"] == {"final_qty": 54}
    item = kitchen.get("/api/v1/recommendations/prep", query_string={"date": TODAY.isoformat()}).get_json()["data"]["items"][0]
    assert (item["status"], item["final_qty"], item["prep_status"], item["decision_source"]) == ("accepted", 54, "in_progress", "auto")
