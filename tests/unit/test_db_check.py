"""DB-1 .. DB-7: the app runs on MySQL 8.4 where it is required and never falls back to a local SQLite file; the fast
tests keep SQLite in memory."""
import logging
import os

import pytest

from app import create_app
from app.utils.db_check import server_problem


def test_a_missing_database_url_stops_the_app():
    """DB-1: no silent SQLite file."""
    with pytest.raises(RuntimeError, match="DATABASE_URL is not set"):
        create_app("dev", {"SQLALCHEMY_DATABASE_URI": None})


def test_sqlite_is_refused_where_mysql_is_required():
    """DB-2: staging (REQUIRE_MYSQL=1) and production refuse a SQLite URL."""
    with pytest.raises(RuntimeError, match="must be a MySQL 8.4 URL"):
        create_app("dev", {"SQLALCHEMY_DATABASE_URI": "sqlite://", "REQUIRE_MYSQL": True})
    with pytest.raises(RuntimeError, match="must be a MySQL 8.4 URL"):
        create_app("prod", {"SQLALCHEMY_DATABASE_URI": "sqlite://", "SECRET_KEY": "x"})


def test_production_always_requires_mysql_and_tests_never_do():
    """DB-3"""
    from app.config import DevConfig, ProdConfig, TestConfig
    assert ProdConfig.REQUIRE_MYSQL is True and TestConfig.REQUIRE_MYSQL is False and TestConfig.TESTING is True
    assert DevConfig.REQUIRE_MYSQL == (os.environ.get("REQUIRE_MYSQL") == "1")


def test_a_local_sqlite_url_still_works_when_mysql_is_not_required():
    """DB-4: isolated fast tests and throwaway copies may use SQLite on purpose."""
    app = create_app("dev", {"SQLALCHEMY_DATABASE_URI": "sqlite://", "REQUIRE_MYSQL": False})
    assert app.config["DATABASE_SERVER"] is None


@pytest.mark.parametrize("version,ok", [("8.4.11", True), ("8.4.0-commercial", True), ("9.1.0", True),
                                        ("8.0.36", False), ("5.7.44-log", False), ("11.8.6-MariaDB", False),
                                        ("10.11.6-MariaDB-0+deb12u1", False)])
def test_server_version_rule(version, ok):
    """DB-5: MySQL 8.4 or later; MariaDB and older MySQL are refused."""
    assert (server_problem(version) is None) == ok


class _Collect(logging.Handler):
    def __init__(self):
        super().__init__(); self.messages = []

    def emit(self, record):
        self.messages.append(record.getMessage())


def test_an_unreachable_server_at_start_up_only_warns():
    """DB-6: a short database restart during a reload must not stop the web workers from booting (error 2003)."""
    logger, seen = logging.getLogger("smartrest"), _Collect()
    was_disabled, logger.disabled = logger.disabled, False      # Alembic's fileConfig in other tests disables loggers
    logger.addHandler(seen)
    try:
        app = create_app("dev", {"SQLALCHEMY_DATABASE_URI": "mysql+pymysql://nobody:x@127.0.0.1:1/none", "REQUIRE_MYSQL": True,
                                 "SQLALCHEMY_ENGINE_OPTIONS": {"connect_args": {"connect_timeout": 2}}})
    finally:
        logger.removeHandler(seen); logger.disabled = was_disabled
    assert app.config["DATABASE_SERVER"] is None and any("not reachable at start-up" in m for m in seen.messages)


@pytest.mark.mysql
def test_a_wrong_account_or_database_stops_the_app():
    """DB-6b: access denied or an unknown database is a configuration error, not an outage."""
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL not set")
    from sqlalchemy.engine import make_url
    u = make_url(url)
    with pytest.raises(RuntimeError, match="Cannot use the database"):
        create_app("dev", {"SQLALCHEMY_DATABASE_URI": u.set(password="wrong-password").render_as_string(hide_password=False), "REQUIRE_MYSQL": True})
    with pytest.raises(RuntimeError, match="Cannot use the database"):
        create_app("dev", {"SQLALCHEMY_DATABASE_URI": u.set(database="no_such_db").render_as_string(hide_password=False), "REQUIRE_MYSQL": True})


@pytest.mark.mysql
def test_the_test_server_is_mysql_8_4():
    """DB-7 (server suite): the configured test database is MySQL 8.4 or later, not MariaDB."""
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL not set")
    app = create_app("dev", {"SQLALCHEMY_DATABASE_URI": url, "REQUIRE_MYSQL": True})
    assert app.config["DATABASE_SERVER"].startswith(("8.4", "9."))
