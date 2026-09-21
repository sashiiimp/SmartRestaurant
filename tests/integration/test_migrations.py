"""DB-1 (migrations = models) and DB-2 (outlet_id rule, DATABASE.md DB5)."""
import os

from flask_migrate import upgrade
from sqlalchemy import create_engine, inspect

from app import create_app
from app.extensions import db

CHILD_TABLES = {"recipe_lines", "purchase_order_lines", "promotion_items", "stock_request_lines"}   # inherit the outlet via their parent
NO_OUTLET = {"outlets", "login_attempts", "model_versions_unused"}          # global by nature


def test_migrations_create_the_same_tables_as_the_models(tmp_path):
    url = f"sqlite:///{tmp_path}/mig.db"
    application = create_app("test", {"SQLALCHEMY_DATABASE_URI": url})
    with application.app_context():
        upgrade(directory=os.path.join(os.path.dirname(__file__), "..", "..", "migrations"))
        migrated = set(inspect(create_engine(url)).get_table_names()) - {"alembic_version"}
        assert migrated == set(db.metadata.tables), migrated ^ set(db.metadata.tables)


def test_every_operational_table_carries_outlet_id():
    missing = [name for name, t in db.metadata.tables.items()
               if name not in CHILD_TABLES | NO_OUTLET and "outlet_id" not in t.c]
    assert not missing, f"tables without outlet_id: {missing}"
