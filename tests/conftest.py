import os

import pytest

from app import create_app
from app.extensions import db as _db
from app.models import Outlet


@pytest.fixture(autouse=True)
def fixed_today(monkeypatch):
    monkeypatch.setenv("SMARTREST_TODAY", "2026-09-25")
    monkeypatch.setenv("SMARTREST_FAST_HASH", "1")


@pytest.fixture()
def app(request):
    """Fresh app and empty schema per test. SQLite in memory unless the test is marked `mysql`."""
    overrides = None
    if request.node.get_closest_marker("mysql"):
        url = os.environ.get("TEST_DATABASE_URL")
        if not url:
            pytest.skip("TEST_DATABASE_URL not set")
        overrides = {"SQLALCHEMY_DATABASE_URI": url}
    application = create_app("test", overrides)

    @application.before_request
    def _forget_cached_user():
        # The fixture keeps one app context open, and Flask-Login caches the user on `g`.
        from flask import g
        g.pop("_login_user", None)

    with application.app_context():
        if request.node.get_closest_marker("mysql"):
            _db.drop_all()
        _db.create_all()
        _db.session.add(Outlet(id=1, name="Test Outlet"))
        _db.session.commit()
        yield application
        _db.session.remove()
        _db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def users(app):
    """One user per role, password 'password1'."""
    from tests.factories import make_user

    return {role: make_user(role) for role in ("admin", "kitchen", "inventory")}


def login(client, username, password="password1"):
    return client.post("/login", data={"username": username, "password": password}, follow_redirects=False)


@pytest.fixture()
def as_role(client, users):
    def _login(role):
        resp = login(client, users[role].username)
        assert resp.status_code == 302
        return client

    return _login
