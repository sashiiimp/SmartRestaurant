import os
from datetime import timedelta

from dotenv import load_dotenv

load_dotenv()


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-only-change-me")
    # no default: a missing DATABASE_URL stops the app (app/utils/db_check.py) instead of creating a local SQLite file
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL")
    # MySQL 8.4 only (checked at start-up): always in production; staging sets REQUIRE_MYSQL=1 in .env
    REQUIRE_MYSQL = os.environ.get("REQUIRE_MYSQL") == "1"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True}
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = False
    PERMANENT_SESSION_LIFETIME = timedelta(minutes=30)  # idle timeout (C3): refreshed on every request
    JSON_SORT_KEYS = False
    MODEL_DIR = os.environ.get("MODEL_DIR", "instance/models")
    MAX_CONTENT_LENGTH = 5 * 1024 * 1024  # uploads are CSV files; a 60,000-row sales file is about 2 MB
    # Number of reverse proxies in front of the app (0 = none). Set it only behind a proxy such as nginx for HTTPS,
    # so the login lockout sees the client's address instead of the proxy's.
    TRUST_PROXY = int(os.environ.get("TRUST_PROXY", "0"))
    DEFAULT_OUTLET_ID = 1


class DevConfig(Config):
    DEBUG = False


class TestConfig(Config):
    TESTING = True
    REQUIRE_MYSQL = False
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SQLALCHEMY_ENGINE_OPTIONS = {}
    WTF_CSRF_ENABLED = False
    SECRET_KEY = "test-secret"
    MODEL_DIR = "instance/test_models"


class ProdConfig(Config):
    SESSION_COOKIE_SECURE = True
    REQUIRE_MYSQL = True


CONFIGS = {"dev": DevConfig, "test": TestConfig, "prod": ProdConfig}


def get_config(name: str | None = None):
    return CONFIGS[name or os.environ.get("APP_ENV", "dev")]
