"""Small builders so formula tests never depend on the seed data (TESTING.md section 2)."""
from datetime import date
from decimal import Decimal

from app.extensions import db
from app.models import Ingredient, MenuItem, RecipeLine, StockBatch, StockMovement, User
from app.services import auth_service

OUTLET = 1
_counter = {"n": 0}


def _n():
    _counter["n"] += 1
    return _counter["n"]


def make_user(role="admin", username=None, password="password1", active=True):
    user = auth_service.create_user(OUTLET, f"{role.title()} User", username or f"{role}{_n()}", role, password)
    if not active:
        user.is_active = False
        db.session.commit()
    return user


def make_item(name=None, price=500, batch_size=1, active=True, **kw):
    item = MenuItem(outlet_id=OUTLET, name=name or f"Item {_n()}", price=Decimal(str(price)),
                    batch_size=batch_size, is_active=active, **kw)
    db.session.add(item)
    db.session.commit()
    return item


def make_ingredient(name=None, unit="kg", min_stock=0, reorder_level=0, pack_size=1, reorder_qty=0,
                    supplier_id=None, **kw):
    ing = Ingredient(outlet_id=OUTLET, name=name or f"Ingredient {_n()}", unit=unit, min_stock=Decimal(str(min_stock)),
                     reorder_level=Decimal(str(reorder_level)), pack_size=Decimal(str(pack_size)),
                     reorder_qty=Decimal(str(reorder_qty)), default_supplier_id=supplier_id, **kw)
    db.session.add(ing)
    db.session.commit()
    return ing


def add_recipe(item, lines):
    """lines: [(ingredient, quantity_per_portion)]"""
    for ing, qty in lines:
        db.session.add(RecipeLine(menu_item_id=item.id, ingredient_id=ing.id, quantity_per_portion=Decimal(str(qty))))
    db.session.commit()
    db.session.expire(item)


def add_batch(ing, qty, received=date(2026, 9, 20), expiry=None, batch_no=None, cost=None):
    """Insert a batch plus its stock_in movement directly (fixture only; services do the real thing)."""
    qty = Decimal(str(qty))
    batch = StockBatch(outlet_id=OUTLET, ingredient_id=ing.id, batch_no=batch_no or f"B{_n()}", received_date=received,
                       expiry_date=expiry, qty_received=qty, qty_remaining=qty, unit_cost=cost)
    db.session.add(batch)
    db.session.flush()
    db.session.add(StockMovement(outlet_id=OUTLET, ingredient_id=ing.id, batch_id=batch.id, movement_type="stock_in",
                                 quantity=qty, movement_date=received))
    db.session.commit()
    return batch
