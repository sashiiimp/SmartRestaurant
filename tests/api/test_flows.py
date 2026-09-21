"""API behaviour through the HTTP layer: envelope, status codes, validation, CSRF, escaping (API.md, TESTING 5.1-5.3)."""
import io
import time
from datetime import date, timedelta
from decimal import Decimal

import pytest

from app import create_app
from app.extensions import db
from app.models import Alert, Outlet
from tests.conftest import login
from tests.factories import add_batch, make_ingredient, make_item, make_user

TODAY = date(2026, 9, 25)


def _client(app, user):
    c = app.test_client()
    assert login(c, user.username).status_code == 302
    return c


def post(client, url, body=None):
    return client.post(url, json=body if body is not None else {})


def test_kitchen_recording_over_http(as_role):
    client = as_role("kitchen")
    item = make_item(name="Burger", batch_size=6)
    r = post(client, "/api/v1/kitchen/prepared", {"menu_item_id": item.id, "date": "2026-09-25", "quantity": 24})
    assert r.status_code == 201 and r.get_json()["data"]["total_prepared"] == 24
    bad = post(client, "/api/v1/kitchen/prepared", {"menu_item_id": item.id, "date": "2026-09-25", "quantity": -1})
    body = bad.get_json()
    assert bad.status_code == 422 and body["error"]["code"] == "validation_error"
    assert "quantity" in body["error"]["fields"]
    served = {"date": "2026-09-25", "lines": [{"menu_item_id": item.id, "quantity": 30}]}
    r = post(client, "/api/v1/sales/served", served)
    assert r.status_code == 201 and r.get_json()["meta"]["warnings"]
    dup = post(client, "/api/v1/sales/served", {**served, "lines": [{"menu_item_id": item.id, "quantity": 31}]})
    assert dup.status_code == 409 and dup.get_json()["error"]["code"] == "duplicate_record"
    assert dup.get_json()["error"]["conflicts"][0]["existing"] == 30
    ok = post(client, "/api/v1/sales/served", {**served, "lines": [{"menu_item_id": item.id, "quantity": 31}],
                                                 "confirm_overwrite": True})
    assert ok.status_code == 201


def test_inventory_over_http(as_role):
    client = as_role("inventory")
    ing = make_ingredient(name="Chicken", unit="kg", min_stock=5, reorder_level=10)
    r = post(client, "/api/v1/stock/in", {"ingredient_id": ing.id, "quantity": 12, "received_date": "2026-09-25",
                                            "expiry_date": "2026-10-10"})
    assert r.status_code == 201
    over = post(client, "/api/v1/stock/out", {"ingredient_id": ing.id, "quantity": 99})
    err = over.get_json()["error"]
    assert over.status_code == 422 and err["code"] == "insufficient_stock" and err["available"] == 12.0
    levels = client.get("/api/v1/stock/levels").get_json()
    assert levels["meta"]["counts"] == {"ok": 0, "low": 1, "out": 0} or levels["meta"]["counts"]["low"] + levels["meta"]["counts"]["ok"] == 1


def test_admin_import_multipart_dry_run_then_commit(as_role):
    client = as_role("admin")
    make_item(name="Burger")
    csv = b"date,item,quantity\n2026-09-01,Burger,40\n2026-09-02,Ghost,5\n"
    r = client.post("/api/v1/sales/import", data={"file": (io.BytesIO(csv), "s.csv")}, content_type="multipart/form-data")
    d = r.get_json()["data"]
    assert r.status_code == 200 and d["dry_run"] is True and (d["accepted"], d["rejected"]) == (1, 1)
    r = client.post("/api/v1/sales/import", data={"file": (io.BytesIO(csv), "s.csv"), "dry_run": "false"},
                    content_type="multipart/form-data")
    assert r.get_json()["data"]["dry_run"] is False
    missing = client.post("/api/v1/sales/import", data={}, content_type="multipart/form-data")
    assert missing.status_code == 422 and missing.get_json()["error"]["code"] == "bad_file"


def test_users_api_and_duplicate(as_role):
    client = as_role("admin")
    body = {"full_name": "New Kitchen", "username": "newk", "role": "kitchen", "password": "longenough1"}
    assert post(client, "/api/v1/users", body).status_code == 201
    dup = post(client, "/api/v1/users", body)
    assert dup.status_code == 409 and dup.get_json()["error"]["code"] == "duplicate_record"
    short = post(client, "/api/v1/users", {**body, "username": "other", "password": "x"})
    assert short.status_code == 422 and "password" in short.get_json()["error"]["fields"]
    listed = client.get("/api/v1/users").get_json()
    assert all("password" not in u and "password_hash" not in u for u in listed["data"])


def test_error_envelopes(as_role):
    client = as_role("admin")
    r = client.get("/api/v1/menu-items/99999/recipe")
    assert r.status_code == 404 and r.get_json()["error"]["code"] == "not_found"
    r = client.delete("/api/v1/menu-items")
    assert r.status_code == 405 and r.get_json()["error"]["code"] == "method_not_allowed"
    r = client.post("/api/v1/menu-items", data="[1, 2]", content_type="application/json")
    assert r.status_code == 422 or r.status_code == 400
    r = client.post("/api/v1/menu-items", data="{not json", content_type="application/json")
    assert r.status_code == 422 and r.get_json()["error"]["code"] == "validation_error"
    assert "X-Request-ID" in r.headers
    r = client.get("/api/v1/forecasts?from=not-a-date")
    assert r.status_code == 422 and "from" in r.get_json()["error"]["fields"]


def test_csrf_on_api_writes():
    """SEC-7: API writes without the token are refused with a JSON error."""
    application = create_app("test")
    application.config["WTF_CSRF_ENABLED"] = True
    with application.app_context():
        db.create_all()
        db.session.add(Outlet(id=1, name="x"))
        db.session.commit()
        make_user("admin", username="csrfadmin")
        c = application.test_client()
        token = c.get("/login").get_data(as_text=True).split('name="csrf_token" value="')[1].split('"')[0]
        c.post("/login", data={"username": "csrfadmin", "password": "password1", "csrf_token": token})
        r = c.post("/api/v1/menu-items", json={"name": "X", "price": 1})
        assert r.status_code == 400 and r.get_json()["error"]["code"] == "csrf_failed"
        r = c.post("/api/v1/menu-items", json={"name": "X", "price": 1}, headers={"X-CSRFToken": token})
        assert r.status_code == 201
        db.drop_all()


def test_output_is_escaped_and_quotes_are_harmless(app, as_role, users):
    """SEC-8, SEC-9"""
    client = as_role("admin")
    from app.services import auth_service
    auth_service.update_user(1, users["admin"].id, full_name="<script>alert(1)</script>")
    page = client.get("/admin").get_data(as_text=True)
    assert "<script>alert(1)" not in page and "&lt;script&gt;alert(1)" in page
    assert client.get("/api/v1/stock/movements?type=%27%20OR%201%3D1%20--").status_code == 422
    assert client.get("/api/v1/forecasts?item_id=1%27").status_code == 422
    assert login(app.test_client(), "x' OR '1'='1").status_code == 401
    r = post(client, "/api/v1/menu-items", {"name": "Robert'); DROP TABLE menu_items;--", "price": 5})
    assert r.status_code == 201 and client.get("/api/v1/menu-items").get_json()["meta"]["total"] == 1


def test_idle_timeout_ends_the_session(app, users):
    """SEC-10 (C3)"""
    app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(seconds=1)
    client = app.test_client()
    assert login(client, users["kitchen"].username).status_code == 302
    assert client.get("/api/v1/me").status_code == 200
    time.sleep(3)   # session timestamps have one-second resolution
    r = client.get("/api/v1/me")
    assert r.status_code == 401 and r.get_json()["error"]["code"] == "unauthenticated"


def test_empty_database_never_gives_500_or_a_blank_page(app, users):
    """NEG-1 / NFR3: no forecasts, no model, no stock, no sales: every GET is a 200 or a readable 4xx."""
    for role in ("admin", "kitchen", "inventory"):
        client = app.test_client()
        login(client, users[role].username)
        for rule in app.url_map.iter_rules():
            if "GET" not in rule.methods or rule.endpoint in ("static", "auth.login") or "<" in rule.rule:
                continue
            resp = client.get(rule.rule)
            assert resp.status_code in (200, 302, 403, 422), (role, rule.rule, resp.status_code)
            if resp.status_code == 200 and rule.rule.startswith("/api/"):
                assert "data" in resp.get_json()
            if resp.status_code == 200 and not rule.rule.startswith("/api/"):
                assert len(resp.get_data()) > 200


def test_alerts_endpoint_filters_by_role(app, as_role, users):
    ing = make_ingredient(name="Chicken", min_stock=5, reorder_level=10)
    add_batch(ing, 4, expiry=TODAY + timedelta(days=30))
    inv_client = as_role("inventory")
    body = inv_client.get("/api/v1/alerts").get_json()
    assert [a["alert_type"] for a in body["data"]] == ["critical_stock"] and body["meta"]["counts"]["critical"] == 1
    alert_id = body["data"][0]["id"]
    kitchen = _client(app, users["kitchen"])
    assert kitchen.get("/api/v1/alerts").get_json()["data"] == []
    assert kitchen.post(f"/api/v1/alerts/{alert_id}/acknowledge", json={}).status_code == 404
