"""HTTP behaviour and RBAC of the Tier 2 functions (PLAN.md section 3A)."""
from datetime import date

from tests.conftest import login
from tests.factories import add_batch, make_ingredient


def as_user(app, users, role):
    c = app.test_client()
    assert login(c, users[role].username).status_code == 302
    return c


def test_stock_requests_end_to_end_over_http(app, users):
    chicken = make_ingredient(name="Chicken", unit="kg")
    add_batch(chicken, 20, received=date(2026, 9, 20), expiry=date(2026, 12, 1))
    kitchen, inventory = as_user(app, users, "kitchen"), as_user(app, users, "inventory")
    r = kitchen.post("/api/v1/kitchen/stock-requests", json={"note": "rush", "lines": [{"ingredient_id": chicken.id, "quantity": 12}]})
    assert r.status_code == 201
    req = r.get_json()["data"]
    assert kitchen.post("/api/v1/kitchen/stock-requests", json={"lines": []}).status_code == 422
    listed = kitchen.get("/api/v1/kitchen/stock-requests").get_json()
    assert listed["meta"]["total"] == 1 and listed["data"][0]["lines"][0]["ingredient"] == "Chicken"
    assert inventory.get("/api/v1/stock-requests").get_json()["meta"]["pending"] == 1
    assert inventory.get(f"/api/v1/stock-requests/{req['id']}").get_json()["data"]["lines"][0]["usable_stock"] == 20.0
    lid = req["lines"][0]["id"]
    assert inventory.post(f"/api/v1/stock-requests/{req['id']}/reject", json={}).status_code == 422
    over = inventory.post(f"/api/v1/stock-requests/{req['id']}/issue", json={"lines": [{"line_id": lid, "quantity": 13}]})
    assert over.status_code == 422
    part = inventory.post(f"/api/v1/stock-requests/{req['id']}/issue", json={"lines": [{"line_id": lid, "quantity": 5}]})
    assert part.status_code == 200 and part.get_json()["data"]["stock_request"]["status"] == "approved"
    assert kitchen.post(f"/api/v1/kitchen/stock-requests/{req['id']}/cancel").status_code == 409
    done = inventory.post(f"/api/v1/stock-requests/{req['id']}/issue", json={"lines": [{"line_id": lid, "quantity": 7}]})
    assert done.get_json()["data"]["stock_request"]["status"] == "issued"
    assert inventory.post(f"/api/v1/stock-requests/{req['id']}/approve").status_code == 409
    assert inventory.get("/api/v1/stock-requests/999").status_code == 404
    assert inventory.get("/api/v1/stock-requests?status=bogus").status_code == 422
    assert inventory.get("/api/v1/stock/levels").get_json()["data"][0]["usable"] == 8.0


def test_stock_request_roles(app, users):
    chicken = make_ingredient(name="Chicken", unit="kg")
    kitchen, inventory, admin = (as_user(app, users, r) for r in ("kitchen", "inventory", "admin"))
    body = {"lines": [{"ingredient_id": chicken.id, "quantity": 1}]}
    rid = kitchen.post("/api/v1/kitchen/stock-requests", json=body).get_json()["data"]["id"]
    # kitchen creates and cancels only; it cannot decide or issue
    for path in ("approve", "reject", "issue"):
        assert kitchen.post(f"/api/v1/stock-requests/{rid}/{path}", json={}).status_code == 403
    assert kitchen.get("/api/v1/stock-requests").status_code == 403
    # inventory decides but cannot create through the kitchen route
    assert inventory.post("/api/v1/kitchen/stock-requests", json=body).status_code == 403
    assert inventory.post(f"/api/v1/kitchen/stock-requests/{rid}/cancel").status_code == 403
    # admin is read-only
    assert admin.get("/api/v1/stock-requests").status_code == 200
    assert admin.get("/api/v1/kitchen/stock-requests").status_code == 200
    for method, url in (("post", f"/api/v1/stock-requests/{rid}/approve"), ("post", "/api/v1/kitchen/stock-requests"),
                        ("post", f"/api/v1/stock-requests/{rid}/issue")):
        assert getattr(admin, method)(url, json=body).status_code == 403


def test_shortage_report_over_http_and_roles(app, users):
    chicken = make_ingredient(name="Chicken", unit="kg")
    kitchen, inventory, admin = (as_user(app, users, r) for r in ("kitchen", "inventory", "admin"))
    r = kitchen.post("/api/v1/kitchen/shortage-reports", json={"ingredient_id": chicken.id, "note": "walk-in is empty"})
    assert r.status_code == 201 and r.get_json()["data"]["alert_type"] == "manual_shortage"
    assert kitchen.post("/api/v1/kitchen/shortage-reports", json={"ingredient_id": chicken.id}).status_code == 200
    assert kitchen.post("/api/v1/kitchen/shortage-reports", json={"ingredient_id": 999}).status_code == 404
    assert kitchen.post("/api/v1/kitchen/shortage-reports", json={}).status_code == 422
    seen = lambda c: [a["alert_type"] for a in c.get("/api/v1/alerts?refresh=true").get_json()["data"]]
    assert "manual_shortage" in seen(inventory) and "manual_shortage" in seen(admin)
    assert "manual_shortage" not in seen(kitchen)
    assert inventory.post("/api/v1/kitchen/shortage-reports", json={"ingredient_id": chicken.id}).status_code == 403
    assert admin.post("/api/v1/kitchen/shortage-reports", json={"ingredient_id": chicken.id}).status_code == 403


def test_tier2_pages_are_role_restricted(app, users):
    pages = {"kitchen": ["/kitchen/stock-requests"], "inventory": ["/inventory/requests"]}
    for owner, urls in pages.items():
        for role in ("admin", "kitchen", "inventory"):
            c = as_user(app, users, role)
            for url in urls:
                assert c.get(url).status_code == (200 if role == owner else 403), (role, url)


def test_inventory_dashboard_counts_pending_requests(app, users):
    chicken = make_ingredient(name="Chicken", unit="kg")
    kitchen, inventory = as_user(app, users, "kitchen"), as_user(app, users, "inventory")
    assert inventory.get("/api/v1/dashboards/inventory").get_json()["data"]["pending_requests"] == 0
    kitchen.post("/api/v1/kitchen/stock-requests", json={"lines": [{"ingredient_id": chicken.id, "quantity": 1}]})
    assert inventory.get("/api/v1/dashboards/inventory").get_json()["data"]["pending_requests"] == 1


def test_consistency_endpoint_roles_and_content(app, users):
    ing = make_ingredient(name="Chicken", unit="kg")
    add_batch(ing, 10, received=date(2026, 9, 20), expiry=date(2026, 12, 1))
    for role in ("inventory", "admin"):
        r = as_user(app, users, role).get("/api/v1/stock/consistency")
        assert r.status_code == 200 and r.get_json()["data"]["consistent"] is True
    assert as_user(app, users, "kitchen").get("/api/v1/stock/consistency").status_code == 403


def test_inventory_reports_csv_and_roles(app, users):
    from app.services import inventory_service as inv
    ing = make_ingredient(name="Chicken", unit="kg")
    add_batch(ing, 10, received=date(2026, 9, 20), expiry=date(2026, 12, 1))
    inv.record_wastage(1, {"ingredient_id": ing.id, "quantity": 2, "movement_date": "2026-09-22", "reason": "spoiled"})
    admin = as_user(app, users, "admin")
    q = f"ingredient_id={ing.id}&from=2026-09-20&to=2026-09-25"
    js = admin.get(f"/api/v1/reports/inventory-trend?{q}").get_json()["data"]
    assert js["closing"] == 8.0
    csv = admin.get(f"/api/v1/reports/inventory-trend?{q}&format=csv")
    assert csv.mimetype == "text/csv" and csv.get_data(as_text=True).splitlines()[0] == "date,stock_in,stock_out,wastage,adjustment,closing_on_hand"
    assert csv.get_data(as_text=True).splitlines()[-1].endswith(",8.0")               # the CSV equals the screen
    mv = admin.get("/api/v1/reports/movements?from=2026-09-20&to=2026-09-25").get_json()
    assert mv["meta"]["total"] == 2 and len(mv["data"]) == 2
    mcsv = admin.get("/api/v1/reports/movements?from=2026-09-20&to=2026-09-25&type=wastage&format=csv").get_data(as_text=True).splitlines()
    assert len(mcsv) == 2 and "spoiled" in mcsv[1]
    lv = admin.get("/api/v1/reports/stock-levels?format=csv").get_data(as_text=True).splitlines()
    assert lv[0].startswith("ingredient,unit,usable") and lv[1].startswith("Chicken,kg,8.0,8.0")
    assert admin.get("/api/v1/reports/inventory-trend?from=2026-09-20&to=2026-09-25").status_code == 422   # no ingredient
    assert admin.get(f"/api/v1/reports/inventory-trend?ingredient_id=999").status_code == 404
    for role in ("inventory", "kitchen"):
        c = as_user(app, users, role)
        for url in ("/api/v1/reports/stock-levels", f"/api/v1/reports/inventory-trend?{q}", "/api/v1/reports/movements"):
            assert c.get(url).status_code == 403, (role, url)


def test_restaurant_information(app, users):
    from app.models import AuditLog, Outlet
    from app.extensions import db
    admin = as_user(app, users, "admin")
    got = admin.get("/api/v1/restaurant").get_json()["data"]
    assert got["name"] == "Test Outlet" and got["timezone"] == "Asia/Colombo"
    r = admin.put("/api/v1/restaurant", json={"name": "Lanka Bites", "address": "12 Galle Road, Colombo 3", "contact": "011 234 5678",
                                              "opening_days": "Mon-Sun", "opening_hours": "10:00-22:00", "timezone": "UTC"})
    assert r.status_code == 200 and r.get_json()["data"]["name"] == "Lanka Bites"
    assert db.session.get(Outlet, 1).timezone == "Asia/Colombo"                    # the time zone cannot be edited
    assert AuditLog.query.filter_by(action="restaurant.update").count() == 1
    bad = admin.put("/api/v1/restaurant", json={"name": " ", "address": "x" * 256})
    assert bad.status_code == 422 and set(bad.get_json()["error"]["fields"]) == {"name", "address"}
    partial = admin.put("/api/v1/restaurant", json={"contact": "011 999"}).get_json()["data"]
    assert partial["contact"] == "011 999" and partial["name"] == "Lanka Bites"      # other fields are kept
    page = admin.get("/admin/settings").get_data(as_text=True)
    assert "Lanka Bites" in page                                                     # shown in the sidebar
    for role in ("inventory", "kitchen"):
        c = as_user(app, users, role)
        assert c.get("/api/v1/restaurant").status_code == 403
        assert c.put("/api/v1/restaurant", json={"name": "X"}).status_code == 403
        assert "Lanka Bites" in c.get({"inventory": "/inventory", "kitchen": "/kitchen"}[role]).get_data(as_text=True)
