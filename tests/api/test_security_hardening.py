"""SEC-13 .. SEC-18: hardening after the 4 Oct 2026 audit (sessions, headers, CSV export, uploads, passwords, lockout)."""
import io
import os

from flask_migrate import upgrade
from sqlalchemy import create_engine, inspect

from app import create_app
from app.extensions import db
from app.models import Outlet
from app.services import auth_service
from app.utils.responses import csv_safe
from tests.conftest import login
from tests.factories import make_ingredient, make_user


def _login_from(app, username, ip, password="password1"):
    c = app.test_client()
    r = c.post("/login", data={"username": username, "password": password}, environ_base={"REMOTE_ADDR": ip})
    return c, r.status_code


def _copied_cookie_client(app, client):
    copy = app.test_client()
    copy.set_cookie("session", client.get_cookie("session").value)
    return copy


# ---- SEC-13: sessions end on the server --------------------------------------------------------------
def test_logout_ends_a_copied_session_cookie(app, users):
    c = app.test_client()
    assert login(c, users["kitchen"].username).status_code == 302
    copy = _copied_cookie_client(app, c)
    assert copy.get("/api/v1/me").status_code == 200
    c.post("/logout")
    assert copy.get("/api/v1/me").status_code == 401
    # logging in again works and gives a new, valid session
    c2 = app.test_client()
    assert login(c2, users["kitchen"].username).status_code == 302 and c2.get("/api/v1/me").status_code == 200


def test_password_reset_ends_the_users_sessions(app, users, as_role):
    k = app.test_client()
    assert login(k, users["kitchen"].username).status_code == 302
    admin = as_role("admin")
    r = admin.post(f"/api/v1/users/{users['kitchen'].id}/password", json={"password": "Kitchen#2026"})
    assert r.status_code == 200
    assert k.get("/api/v1/me").status_code == 401
    assert admin.get("/api/v1/me").status_code == 200   # the admin's own session is untouched


def test_deactivation_ends_the_session_and_reactivation_needs_a_new_login(app, users, as_role):
    k = app.test_client()
    assert login(k, users["kitchen"].username).status_code == 302
    admin = as_role("admin")
    admin.patch(f"/api/v1/users/{users['kitchen'].id}", json={"is_active": False})
    admin.patch(f"/api/v1/users/{users['kitchen'].id}", json={"is_active": True})
    assert k.get("/api/v1/me").status_code == 401


def test_session_ids_in_the_old_or_a_broken_format_are_refused(app, users):
    uid = users["admin"].id
    assert auth_service.get_user(f"{uid}:0").id == uid
    for bad in (str(uid), f"{uid}:1", f"{uid}:x", "x:0", ":", ""):
        assert auth_service.get_user(bad) is None, bad


# ---- SEC-14: security headers ----------------------------------------------------------------------
def test_security_headers_on_pages_and_api(app, client, as_role):
    for resp in (client.get("/login"), client.get("/api/v1/me")):
        csp = resp.headers["Content-Security-Policy"]
        assert "frame-ancestors 'none'" in csp and "object-src 'none'" in csp
        script_src = csp.split("script-src")[1].split(";")[0]
        assert "'unsafe-inline'" not in script_src
        assert resp.headers["X-Frame-Options"] == "DENY"
        assert resp.headers["X-Content-Type-Options"] == "nosniff"
        assert resp.headers["Referrer-Policy"] == "same-origin"


def test_no_inline_script_on_any_page(app, users):
    """The CSP forbids inline script, so every <script> must have a src (otherwise it silently stops working)."""
    import re
    pages = {"admin": ["/admin", "/admin/users", "/admin/catalog", "/admin/data", "/admin/models", "/admin/monitor",
                       "/admin/settings", "/admin/inventory"],
             "kitchen": ["/kitchen", "/kitchen/prep", "/kitchen/forecast", "/kitchen/orders", "/kitchen/requirements",
                         "/kitchen/stock-requests", "/kitchen/record"],
             "inventory": ["/inventory", "/inventory/stock", "/inventory/movements", "/inventory/forecast",
                           "/inventory/reorder", "/inventory/purchase-orders", "/inventory/requests", "/inventory/suppliers"]}
    anon = app.test_client().get("/login").get_data(as_text=True)
    assert not re.findall(r"<script(?![^>]*\bsrc=)[^>]*>", anon)
    for role, paths in pages.items():
        c = app.test_client()
        assert login(c, users[role].username).status_code == 302
        for path in paths:
            html = c.get(path).get_data(as_text=True)
            assert not re.findall(r"<script(?![^>]*\bsrc=)[^>]*>", html), path
            assert not re.findall(r"\son[a-z]+=\"", html), path


# ---- SEC-15: CSV export ----------------------------------------------------------------------------
def test_csv_cells_that_look_like_formulas_are_neutralised():
    assert csv_safe('=HYPERLINK("http://x","y")') == '\'=HYPERLINK("http://x","y")'
    assert csv_safe("+1+1") == "'+1+1" and csv_safe("@SUM(A1)") == "'@SUM(A1)" and csv_safe("-x") == "'-x"
    assert csv_safe("-3.5") == "-3.5" and csv_safe(-3.5) == -3.5 and csv_safe("Chicken") == "Chicken"
    assert csv_safe(None) is None


def test_stock_level_export_neutralises_a_formula_name(as_role):
    make_ingredient(name="=1+1", unit="kg")
    client = as_role("admin")
    text = client.get("/api/v1/reports/stock-levels?format=csv").get_data(as_text=True)
    assert text.splitlines()[1].startswith("'=1+1,")


# ---- SEC-16: upload size ---------------------------------------------------------------------------
def test_upload_over_five_megabytes_is_refused_with_json(as_role):
    client = as_role("admin")
    big = b"date,item,quantity\n" + b"2026-01-01,Burger,1\n" * 300_000   # about 6 MB
    r = client.post("/api/v1/sales/import", data={"file": (io.BytesIO(big), "s.csv")}, content_type="multipart/form-data")
    assert r.status_code == 413 and r.get_json()["error"]["code"] == "too_large"


# ---- SEC-17: password rule -------------------------------------------------------------------------
def test_weak_passwords_are_refused_with_the_reason(as_role):
    client = as_role("admin")
    base = {"full_name": "New Cook", "username": "cook2", "role": "kitchen"}
    for pw, msg in (("cook2pass!", "must not contain the username"), ("Cook2Pass!", "must not contain the username"),
                    ("aaaaaaaa", "must not be one character repeated"), ("kitchenpass", "must contain at least one digit or symbol"),
                    ("short1", "must be text of 8 to 128 characters"), ("x1" * 70, "must be text of 8 to 128 characters")):
        r = client.post("/api/v1/users", json={**base, "password": pw})
        assert r.status_code == 422 and r.get_json()["error"]["fields"]["password"] == msg, pw
    assert client.post("/api/v1/users", json={**base, "password": "Kitchen#2026"}).status_code == 201


def test_password_reset_applies_the_same_rule(as_role, users):
    client = as_role("admin")
    name = users["kitchen"].username
    r = client.post(f"/api/v1/users/{users['kitchen'].id}/password", json={"password": f"{name}-2026"})
    assert r.status_code == 422 and r.get_json()["error"]["fields"]["password"] == "must not contain the username"


# ---- SEC-18: lockout by username and address -------------------------------------------------------
def test_failures_from_one_address_do_not_lock_the_user_out_elsewhere(app, users):
    name = users["kitchen"].username
    for _ in range(5):
        assert _login_from(app, name, "203.0.113.9", "wrong-pass1")[1] == 401
    assert _login_from(app, name, "203.0.113.9")[1] == 429        # the guessing address is locked
    assert _login_from(app, name, "192.168.1.20")[1] == 302       # the restaurant terminal is not


def test_one_address_guessing_many_usernames_is_locked(app, users):
    for i in range(20):   # 4 attempts per name stays under the per-username limit of 5
        assert _login_from(app, f"guess{i % 5}", "198.51.100.7", "wrong-pass1")[1] == 401
    assert _login_from(app, users["admin"].username, "198.51.100.7")[1] == 429
    assert _login_from(app, users["admin"].username, "192.168.1.20")[1] == 302


def test_behind_a_proxy_the_forwarded_address_is_used(monkeypatch):
    monkeypatch.setenv("TRUST_PROXY", "1")
    import importlib
    import app.config as cfg
    importlib.reload(cfg)
    try:
        application = create_app("test")
        assert application.config["TRUST_PROXY"] == 1
        with application.app_context():
            db.create_all()
            db.session.add(Outlet(id=1, name="x"))
            db.session.commit()
            make_user("kitchen", username="proxycook")
            c = application.test_client()
            for _ in range(5):
                c.post("/login", data={"username": "proxycook", "password": "wrong-pass1"},
                       headers={"X-Forwarded-For": "203.0.113.50"})
            locked = c.post("/login", data={"username": "proxycook", "password": "password1"},
                            headers={"X-Forwarded-For": "203.0.113.50"})
            other = application.test_client().post("/login", data={"username": "proxycook", "password": "password1"},
                                                   headers={"X-Forwarded-For": "192.168.1.20"})
            assert (locked.status_code, other.status_code) == (429, 302)
            db.drop_all()
    finally:
        monkeypatch.delenv("TRUST_PROXY")
        importlib.reload(cfg)


# ---- DB-1 for the new column -----------------------------------------------------------------------
def test_migration_adds_the_session_version_column(tmp_path):
    url = f"sqlite:///{tmp_path}/mig.db"
    application = create_app("test", {"SQLALCHEMY_DATABASE_URI": url})
    with application.app_context():
        upgrade(directory=os.path.join(os.path.dirname(__file__), "..", "..", "migrations"))
        cols = {c["name"]: c for c in inspect(create_engine(url)).get_columns("users")}
        assert "session_version" in cols and not cols["session_version"]["nullable"]
