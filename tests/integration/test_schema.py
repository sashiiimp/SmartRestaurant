"""DB-level integrity on MariaDB: the constraints are the backstop for service validation (NFR8)."""
from datetime import date

import pytest
from sqlalchemy.exc import DBAPIError  # MariaDB reports CHECK failures as OperationalError (4025)

from app.extensions import db
from app.models import Alert, MenuItem, SalesRecord, StockBatch, StockMovement
from tests.factories import make_ingredient, make_item

pytestmark = pytest.mark.mysql


def _flush_fails():
    with pytest.raises(DBAPIError):
        db.session.commit()
    db.session.rollback()


def test_negative_remaining_rejected(app):
    ing = make_ingredient()
    db.session.add(StockBatch(outlet_id=1, ingredient_id=ing.id, received_date=date(2026, 9, 1),
                              qty_received=5, qty_remaining=-1))
    _flush_fails()


def test_movement_sign_rules(app):
    ing = make_ingredient()
    b = StockBatch(outlet_id=1, ingredient_id=ing.id, received_date=date(2026, 9, 1), qty_received=5, qty_remaining=5)
    db.session.add(b)
    db.session.commit()
    db.session.add(StockMovement(outlet_id=1, ingredient_id=ing.id, batch_id=b.id, movement_type="stock_out",
                                 quantity=3, movement_date=date(2026, 9, 2)))
    _flush_fails()
    db.session.add(StockMovement(outlet_id=1, ingredient_id=ing.id, batch_id=b.id, movement_type="stock_in",
                                 quantity=-3, movement_date=date(2026, 9, 2)))
    _flush_fails()


def test_expiry_before_received_rejected(app):
    ing = make_ingredient()
    db.session.add(StockBatch(outlet_id=1, ingredient_id=ing.id, received_date=date(2026, 9, 10),
                              expiry_date=date(2026, 9, 1), qty_received=5, qty_remaining=5))
    _flush_fails()


def test_one_sales_row_per_item_per_day(app):
    item = make_item()
    for _ in range(2):
        db.session.add(SalesRecord(outlet_id=1, menu_item_id=item.id, sale_date=date(2026, 9, 1), quantity_sold=5,
                                   unit_price=100, source="manual"))
    _flush_fails()


def test_reorder_level_must_cover_min_stock(app):
    db.session.add(make_ingredient.__globals__["Ingredient"](outlet_id=1, name="x", unit="kg", min_stock=5, reorder_level=2))
    _flush_fails()


def test_one_open_alert_per_condition(app):
    def alert(status, open_key):
        return Alert(outlet_id=1, alert_type="low_stock", severity="warning", entity_type="ingredient", entity_id=1,
                     message="m", status=status, dedupe_key="low_stock:ingredient:1", open_key=open_key)

    db.session.add(alert("open", "low_stock:ingredient:1"))
    db.session.commit()
    db.session.add(alert("closed", None))  # closed rows never collide
    db.session.add(alert("closed", None))
    db.session.commit()
    db.session.add(alert("open", "low_stock:ingredient:1"))
    _flush_fails()


def test_unique_menu_item_name(app):
    make_item(name="Dup")
    db.session.add(MenuItem(outlet_id=1, name="Dup", price=1))
    _flush_fails()
