"""Which database the app may run on (DATABASE.md DB1): MySQL 8.4 in production and staging, never a silent fallback.

check_url runs before the database extension is set up; check_server asks the server once at start-up. Tests
(TESTING) are exempt: the fast suite uses SQLite in memory and the server suite sets its own TEST_DATABASE_URL."""
import logging
import re

from sqlalchemy import text
from sqlalchemy.exc import OperationalError

MIN_MYSQL = (8, 4)
# MySQL client errors that mean "the server cannot be reached right now" (can't connect, gone away, lost connection).
# Anything else at start-up (access denied 1044/1045, unknown database 1049, ...) is a configuration error.
UNREACHABLE = {2002, 2003, 2006, 2013}


def mysql_required(config) -> bool:
    return bool(config.get("REQUIRE_MYSQL")) and not config.get("TESTING")


def check_url(config) -> None:
    """A database URL must be set (no local SQLite file is created by default); MySQL when it is required."""
    if config.get("TESTING"):
        return
    url = config.get("SQLALCHEMY_DATABASE_URI")
    if not url:
        raise RuntimeError("DATABASE_URL is not set. SmartRestaurant does not fall back to a local SQLite file: set "
                           "DATABASE_URL in .env (MySQL 8.4: mysql+pymysql://user:password@host:port/database).")
    if mysql_required(config) and not str(url).startswith("mysql+pymysql://"):
        raise RuntimeError(f"DATABASE_URL must be a MySQL 8.4 URL (mysql+pymysql://...) here (APP_ENV=prod or "
                           f"REQUIRE_MYSQL=1), not {str(url).split(':', 1)[0]}.")


def server_problem(version: str) -> str | None:
    """None when `SELECT VERSION()` names MySQL 8.4 or later, else why not."""
    if "mariadb" in version.lower():
        return f"the server is MariaDB ({version}), not MySQL"
    m = re.match(r"(\d+)\.(\d+)", version)
    if not m or (int(m.group(1)), int(m.group(2))) < MIN_MYSQL:
        return f"the server is MySQL {version}; {MIN_MYSQL[0]}.{MIN_MYSQL[1]} or later is required"
    return None


def check_server(app, db) -> str | None:
    """Refuse to start on the wrong server or with a wrong account or database. Only when the server cannot be
    reached at start-up (for example during a short restart) does the app log a warning and start anyway: requests then
    fail and recover with the database, as before."""
    if not mysql_required(app.config):
        return None
    try:
        with app.app_context():
            version = db.session.execute(text("SELECT VERSION()")).scalar()
            db.session.remove()
    except OperationalError as exc:
        orig = getattr(exc, "orig", None)
        code = orig.args[0] if orig is not None and getattr(orig, "args", None) else None
        if code not in UNREACHABLE:
            raise RuntimeError(f"Cannot use the database: {orig or exc}. Check DATABASE_URL (account, password, database).") from exc
        logging.getLogger("smartrest").warning("Database server not reachable at start-up, version not checked: %s", orig)
        return None
    problem = server_problem(str(version))
    if problem:
        raise RuntimeError(f"Wrong database server: {problem}. Check DATABASE_URL.")
    return str(version)
