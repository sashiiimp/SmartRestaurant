import os
from datetime import timedelta

from dotenv import load_dotenv

load_dotenv()


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-only-change-me")
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL", "sqlite:///smartrest_dev.db")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True}
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = False
    PERMANENT_SESSION_LIFETIME = timedelta(minutes=30)  # idle timeout (C3): refreshed on every request
    JSON_SORT_KEYS = False
    MODEL_DIR = os.environ.get("MODEL_DIR", "instance/models")
    DEFAULT_OUTLET_ID = 1


class DevConfig(Config):
    DEBUG = False


class TestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SQLALCHEMY_ENGINE_OPTIONS = {}
    WTF_CSRF_ENABLED = False
    SECRET_KEY = "test-secret"
    MODEL_DIR = "instance/test_models"


class ProdConfig(Config):
    SESSION_COOKIE_SECURE = True


CONFIGS = {"dev": DevConfig, "test": TestConfig, "prod": ProdConfig}


def get_config(name: str | None = None):
    return CONFIGS[name or os.environ.get("APP_ENV", "dev")]
