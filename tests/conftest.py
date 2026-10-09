import os

import pytest

from app import create_app
from app.extensions import db as _db
from app.models import Outlet


def pytest_collection_modifyitems(config, items):
    """The perf tests run against the seeded dev database and write a forecast run to it, so they run only when asked
    for by name (`-m perf`), never as part of `-m "not mysql"` or a plain `pytest`."""
    if "perf" in (config.option.markexpr or ""):
        return
    skip = pytest.mark.skip(reason="timing test against the dev database; run with -m perf")
    for item in items:
        if item.get_closest_marker("perf"):
            item.add_marker(skip)


@pytest.fixture(autouse=True)
def fixed_today(monkeypatch):
    monkeypatch.setenv("SMARTREST_TODAY", "2026-09-25")
    monkeypatch.setenv("SMARTREST_FAST_HASH", "1")


_server_schema_ready = False


def _fresh_server_schema():
    """On MySQL/MariaDB, build the schema once per session, then empty every table before each test: dropping and
    creating 30 tables per test takes about 8 s on MySQL 8.4. TRUNCATE also resets the AUTO_INCREMENT counters, so
    each test still starts from an empty database with ids from 1."""
    global _server_schema_ready
    if not _server_schema_ready:
        # Drop every table in the test database, including ones another branch's models created (their foreign keys
        # would otherwise block dropping ours), then build this branch's schema.
        with _db.engine.begin() as con:
            con.exec_driver_sql("SET FOREIGN_KEY_CHECKS = 0")
            for (name,) in con.exec_driver_sql("SHOW TABLES").fetchall():
                con.exec_driver_sql(f"DROP TABLE `{name}`")
            con.exec_driver_sql("SET FOREIGN_KEY_CHECKS = 1")
        _db.create_all()
        _server_schema_ready = True
        return
    with _db.engine.begin() as con:
        con.exec_driver_sql("SET FOREIGN_KEY_CHECKS = 0")
        for table in _db.metadata.sorted_tables:
            con.exec_driver_sql(f"TRUNCATE TABLE `{table.name}`")
        con.exec_driver_sql("SET FOREIGN_KEY_CHECKS = 1")


@pytest.fixture()
def app(request):
    """Fresh app and empty schema per test. SQLite in memory unless the test is marked `mysql`, or every test when
    TEST_ALL_ON_DATABASE=1 (used to run the whole suite against MySQL 8.4 and MariaDB)."""
    overrides = None
    on_server = bool(request.node.get_closest_marker("mysql")) or os.environ.get("TEST_ALL_ON_DATABASE") == "1"
    if on_server:
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
        if on_server:
            _fresh_server_schema()
        else:
            _db.create_all()
        _db.session.add(Outlet(id=1, name="Test Outlet"))
        _db.session.commit()
        yield application
        _db.session.remove()
        if on_server:
            # Every test builds a new app and connection pool; close it, or a full run on a database server
            # exhausts max_connections (40 on both private instances).
            _db.engine.dispose()
        else:
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
