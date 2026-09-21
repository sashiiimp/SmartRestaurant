"""Ingredients, suppliers, stock (Inventory service). Master data first; movements are added in the stock slice."""
from decimal import Decimal

from app.extensions import db
from app.models import Ingredient, StockMovement, Supplier
from app.services import audit
from app.services.errors import NotFoundError, ValidationError
from app.services.validation import Fields


# ---- suppliers (I10) -------------------------------------------------------------------------
def create_supplier(outlet_id: int, data: dict, actor_id: int | None = None) -> Supplier:
    f = Fields(data)
    f.text("name", max_len=120)
    f.text("contact_person", required=False, max_len=120)
    f.text("phone", required=False, max_len=40)
    f.text("email", required=False, max_len=160)
    f.integer("lead_time_days", required=False, min=0, default=2)
    f.text("notes", required=False)
    v = f.check()
    if Supplier.query.filter_by(outlet_id=outlet_id, name=v["name"]).first():
        raise ValidationError("Please fix the highlighted fields.", {"name": "already exists"})
    supplier = Supplier(outlet_id=outlet_id, **v)
    db.session.add(supplier)
    db.session.commit()
    return supplier


def list_suppliers(outlet_id: int) -> list[Supplier]:
    return Supplier.query.filter_by(outlet_id=outlet_id).order_by(Supplier.name).all()


# ---- ingredients (I2, I4) --------------------------------------------------------------------
def _ingredient_fields(data: dict) -> dict:
    f = Fields(data)
    f.text("name", max_len=120)
    f.text("unit", max_len=20)
    f.text("category", required=False, max_len=60)
    f.integer("shelf_life_days", required=False, min=0)
    f.integer("default_supplier_id", required=False, min=1)
    f.decimal("min_stock", min=0, default=0)
    f.decimal("reorder_level", min=0, default=0)
    f.decimal("pack_size", gt=0, default=1)
    f.decimal("reorder_qty", min=0, default=0)
    v = f.check()
    if v["reorder_level"] < v["min_stock"]:
        raise ValidationError("Please fix the highlighted fields.",
                              {"reorder_level": "must be at least the minimum stock"})
    return v


def list_ingredients(outlet_id: int, active_only: bool = False) -> list[Ingredient]:
    q = Ingredient.query.filter_by(outlet_id=outlet_id)
    if active_only:
        q = q.filter_by(is_active=True)
    return q.order_by(Ingredient.name).all()


def get_ingredient(outlet_id: int, ingredient_id: int) -> Ingredient:
    ing = Ingredient.query.filter_by(id=ingredient_id, outlet_id=outlet_id).first()
    if not ing:
        raise NotFoundError("Ingredient not found.")
    return ing


def _check_supplier(outlet_id: int, supplier_id):
    if supplier_id and not Supplier.query.filter_by(id=supplier_id, outlet_id=outlet_id).first():
        raise ValidationError("Please fix the highlighted fields.", {"default_supplier_id": "unknown supplier"})


def create_ingredient(outlet_id: int, data: dict, actor_id: int | None = None) -> Ingredient:
    v = _ingredient_fields(data)
    if Ingredient.query.filter_by(outlet_id=outlet_id, name=v["name"]).first():
        raise ValidationError("Please fix the highlighted fields.", {"name": "already exists"})
    _check_supplier(outlet_id, v.get("default_supplier_id"))
    ing = Ingredient(outlet_id=outlet_id, **v)
    db.session.add(ing)
    db.session.flush()
    audit.record(outlet_id, actor_id, "ingredient.create", "ingredient", ing.id)
    db.session.commit()
    return ing


def update_ingredient(outlet_id: int, ingredient_id: int, data: dict, actor_id: int | None = None) -> Ingredient:
    ing = get_ingredient(outlet_id, ingredient_id)
    keys = ("name", "unit", "category", "shelf_life_days", "default_supplier_id", "min_stock",
            "reorder_level", "pack_size", "reorder_qty")
    merged = {k: getattr(ing, k) for k in keys}
    merged.update({k: data[k] for k in keys if k in data})
    v = _ingredient_fields(merged)
    if v["unit"] != ing.unit and db.session.query(StockMovement.id).filter_by(ingredient_id=ing.id).first():
        raise ValidationError("Please fix the highlighted fields.",
                              {"unit": "cannot change after stock has been recorded"})
    clash = Ingredient.query.filter(Ingredient.outlet_id == outlet_id, Ingredient.name == v["name"],
                                    Ingredient.id != ing.id).first()
    if clash:
        raise ValidationError("Please fix the highlighted fields.", {"name": "already exists"})
    _check_supplier(outlet_id, v.get("default_supplier_id"))
    for k, val in v.items():
        setattr(ing, k, val)
    if "is_active" in data:
        ing.is_active = bool(data["is_active"])
    audit.record(outlet_id, actor_id, "ingredient.update", "ingredient", ing.id)
    db.session.commit()
    return ing
