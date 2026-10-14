"""HTTP behaviour and RBAC of the Tier 1 functions (PLAN.md section 3A)."""
from tests.factories import make_ingredient


def test_suppliers_over_http_and_roles(as_role, app, users):
    inv = as_role("inventory")
    r = inv.post("/api/v1/suppliers", json={"name": "Ceylon Poultry", "lead_time_days": 1})
    assert r.status_code == 201 and r.get_json()["data"]["lead_time_days"] == 1
    sid = r.get_json()["data"]["id"]
    dup = inv.post("/api/v1/suppliers", json={"name": "Ceylon Poultry"})
    assert dup.status_code == 422 and dup.get_json()["error"]["fields"] == {"name": "already exists"}
    r = inv.patch(f"/api/v1/suppliers/{sid}", json={"is_active": False})
    assert r.status_code == 200 and r.get_json()["data"]["is_active"] is False
    assert inv.get("/api/v1/suppliers?active=true").get_json()["meta"]["total"] == 0
    assert inv.get("/api/v1/suppliers").get_json()["meta"]["total"] == 1
    assert inv.patch("/api/v1/suppliers/999", json={"notes": "x"}).status_code == 404


def test_supplier_writes_are_inventory_only(app, users):
    from tests.conftest import login
    for role in ("admin", "kitchen"):
        c = app.test_client()
        assert login(c, users[role].username).status_code == 302
        assert c.post("/api/v1/suppliers", json={"name": "X"}).status_code == 403
        assert c.patch("/api/v1/suppliers/1", json={"notes": "x"}).status_code == 403
    admin = app.test_client()
    login(admin, users["admin"].username)
    assert admin.get("/api/v1/suppliers").status_code == 200          # admin may read
    kitchen = app.test_client()
    login(kitchen, users["kitchen"].username)
    assert kitchen.get("/api/v1/suppliers").status_code == 403          # kitchen may not


def test_suppliers_page_is_inventory_only(app, users):
    from tests.conftest import login
    inv = app.test_client(); login(inv, users["inventory"].username)
    assert inv.get("/inventory/reorder?tab=suppliers").status_code == 200    # Suppliers is a tab of Purchasing
    for role in ("admin", "kitchen"):
        c = app.test_client(); login(c, users[role].username)
        assert c.get("/inventory/reorder?tab=suppliers").status_code == 403


def test_adjustment_over_http_and_roles(as_role, app, users):
    from datetime import date
    from tests.factories import add_batch
    from tests.conftest import login
    ing = make_ingredient(name="Chicken", unit="kg")
    add_batch(ing, 10, received=date(2026, 9, 20))
    c = as_role("inventory")
    r = c.post("/api/v1/stock/adjustments", json={"ingredient_id": ing.id, "counted_quantity": 8, "note": "count"})
    assert r.status_code == 201 and r.get_json()["data"]["difference"] == -2.0
    same = c.post("/api/v1/stock/adjustments", json={"ingredient_id": ing.id, "counted_quantity": 8, "note": "again"})
    assert same.status_code == 422 and "counted_quantity" in same.get_json()["error"]["fields"]
    nonote = c.post("/api/v1/stock/adjustments", json={"ingredient_id": ing.id, "counted_quantity": 5})
    assert nonote.status_code == 422 and "note" in nonote.get_json()["error"]["fields"]
    moves = c.get("/api/v1/stock/movements?type=adjustment").get_json()
    assert moves["meta"]["total"] == 1
    for role in ("admin", "kitchen"):
        other = app.test_client(); login(other, users[role].username)
        assert other.post("/api/v1/stock/adjustments", json={"ingredient_id": ing.id, "counted_quantity": 1, "note": "x"}).status_code == 403


def test_purchase_orders_over_http_and_roles(as_role, app, users):
    from tests.conftest import login
    from app.services import inventory_service as inv
    sup = inv.create_supplier(1, {"name": "Ceylon Poultry"})
    chicken = make_ingredient(name="Chicken", unit="kg", supplier_id=sup.id)
    c = as_role("inventory")
    body = {"supplier_id": sup.id, "lines": [{"ingredient_id": chicken.id, "qty_ordered": 20}]}
    r = c.post("/api/v1/purchase-orders", json=body)
    assert r.status_code == 201
    po = r.get_json()["data"]
    assert po["status"] == "draft" and po["po_number"].startswith("PO-")
    assert c.post("/api/v1/purchase-orders", json={**body, "lines": []}).status_code == 422
    assert c.get(f"/api/v1/purchase-orders/{po['id']}").get_json()["data"]["lines"][0]["qty_outstanding"] == 20.0
    assert c.get("/api/v1/purchase-orders?status=draft").get_json()["meta"]["total"] == 1
    assert c.get("/api/v1/purchase-orders?status=bogus").status_code == 422
    assert c.post(f"/api/v1/purchase-orders/{po['id']}/send").get_json()["data"]["status"] == "sent"
    assert c.post(f"/api/v1/purchase-orders/{po['id']}/send").status_code == 409
    lid = po["lines"][0]["id"]
    over = c.post(f"/api/v1/purchase-orders/{po['id']}/receive", json={"lines": [{"line_id": lid, "quantity": 21}]})
    assert over.status_code == 422
    got = c.post(f"/api/v1/purchase-orders/{po['id']}/receive", json={"lines": [{"line_id": lid, "quantity": 8}]})
    assert got.status_code == 200 and got.get_json()["data"]["purchase_order"]["status"] == "partially_received"
    assert c.post(f"/api/v1/purchase-orders/{po['id']}/cancel").status_code == 409
    assert c.get("/api/v1/purchase-orders/999").status_code == 404
    admin = app.test_client(); login(admin, users["admin"].username)
    assert admin.get("/api/v1/purchase-orders").status_code == 200                  # admin may read
    assert admin.post("/api/v1/purchase-orders", json=body).status_code == 403      # but not write
    assert admin.post(f"/api/v1/purchase-orders/{po['id']}/receive", json={}).status_code == 403
    kitchen = app.test_client(); login(kitchen, users["kitchen"].username)
    assert kitchen.get("/api/v1/purchase-orders").status_code == 403


def test_pre_orders_over_http_and_roles(as_role, app, users):
    from tests.conftest import login
    from tests.factories import make_item
    item = make_item(name="Burger", batch_size=6)
    c = as_role("kitchen")
    r = c.post("/api/v1/kitchen/pre-orders", json={"menu_item_id": item.id, "target_date": "2026-09-26", "quantity": 12, "customer_name": "Nimal Perera", "pickup_time": "12:30"})
    assert r.status_code == 201 and r.get_json()["data"]["status"] == "pending"
    pid = r.get_json()["data"]["id"]
    bad = c.post("/api/v1/kitchen/pre-orders", json={"menu_item_id": item.id, "target_date": "2026-09-01", "quantity": 12, "customer_name": "Nimal Perera", "pickup_time": "12:30"})
    assert bad.status_code == 422 and "target_date" in bad.get_json()["error"]["fields"]
    r = c.patch(f"/api/v1/kitchen/pre-orders/{pid}", json={"status": "confirmed", "quantity": 15})
    assert r.status_code == 200 and (r.get_json()["data"]["status"], r.get_json()["data"]["quantity"]) == ("confirmed", 15)
    assert c.patch(f"/api/v1/kitchen/pre-orders/{pid}", json={"status": "sent"}).status_code == 422
    lst = c.get("/api/v1/kitchen/pre-orders?from=2026-09-25&to=2026-09-30").get_json()
    assert lst["meta"]["total"] == 1 and lst["data"][0]["item"] == "Burger"
    c.patch(f"/api/v1/kitchen/pre-orders/{pid}", json={"status": "cancelled"})
    assert c.patch(f"/api/v1/kitchen/pre-orders/{pid}", json={"quantity": 1}).status_code == 409
    assert c.patch("/api/v1/kitchen/pre-orders/999", json={"quantity": 1}).status_code == 404
    admin = app.test_client(); login(admin, users["admin"].username)
    assert admin.get("/api/v1/kitchen/pre-orders").status_code == 200
    assert admin.post("/api/v1/kitchen/pre-orders", json={"menu_item_id": item.id, "target_date": "2026-09-26", "quantity": 1}).status_code == 403
    inv = app.test_client(); login(inv, users["inventory"].username)
    assert inv.get("/api/v1/kitchen/pre-orders").status_code == 403


def test_availability_over_http_and_audit(as_role, app, users):
    from app.models import AuditLog
    from tests.conftest import login
    from tests.factories import make_item
    item = make_item(name="Burger")
    c = as_role("kitchen")
    r = c.patch(f"/api/v1/menu-items/{item.id}/availability", json={"is_available": False})
    assert r.status_code == 200 and r.get_json()["data"]["is_available"] is False
    assert AuditLog.query.filter_by(action="menu.availability").count() == 1
    assert c.patch(f"/api/v1/menu-items/{item.id}/availability", json={"is_available": "no"}).status_code == 422
    rows = c.get("/api/v1/kitchen/daily-summary?date=2026-09-25").get_json()["data"]["items"]
    assert rows[0]["is_available"] is False
    inactive = make_item(name="Gone", active=False)
    assert c.patch(f"/api/v1/menu-items/{inactive.id}/availability", json={"is_available": False}).status_code == 422
    for role in ("admin", "inventory"):
        other = app.test_client(); login(other, users[role].username)
        assert other.patch(f"/api/v1/menu-items/{item.id}/availability", json={"is_available": True}).status_code == 403


def test_new_tier1_pages_are_role_restricted(app, users):
    from tests.conftest import login
    pages = {"admin": ["/admin/monitor?tab=stock"], "kitchen": ["/kitchen/orders"],
             "inventory": ["/inventory/reorder?tab=suppliers", "/inventory/reorder?tab=orders"]}
    for owner, urls in pages.items():
        for role in ("admin", "kitchen", "inventory"):
            c = app.test_client(); login(c, users[role].username)
            for url in urls:
                assert c.get(url).status_code == (200 if role == owner else 403), (role, url)


def test_admin_can_read_the_inventory_data_the_page_uses(as_role):
    from datetime import date
    from tests.factories import add_batch
    ing = make_ingredient(name="Chicken", unit="kg", min_stock=5, reorder_level=10)
    add_batch(ing, 12, received=date(2026, 9, 20))
    c = as_role("admin")
    for url in ("/api/v1/stock/levels", "/api/v1/stock/batches", "/api/v1/stock/movements?limit=50",
                "/api/v1/recommendations/ingredient-forecast?from=2026-09-25&days=7"):
        assert c.get(url).status_code == 200, url
    assert c.post("/api/v1/stock/in", json={"ingredient_id": ing.id, "quantity": 1}).status_code == 403   # read-only
