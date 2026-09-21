"""Menu, recipes, sales import, contextual data (Data Management service, ARCH section 3)."""
from decimal import Decimal

from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import Ingredient, MenuItem, RecipeLine
from app.services import audit
from app.services.errors import ConflictError, NotFoundError, ValidationError
from app.services.validation import Fields


# ---- menu (A4) -------------------------------------------------------------------------------
def list_menu_items(outlet_id: int, active_only: bool = False) -> list[MenuItem]:
    q = MenuItem.query.filter_by(outlet_id=outlet_id)
    if active_only:
        q = q.filter_by(is_active=True)
    return q.order_by(MenuItem.id).all()


def get_menu_item(outlet_id: int, item_id: int) -> MenuItem:
    item = MenuItem.query.filter_by(id=item_id, outlet_id=outlet_id).first()
    if not item:
        raise NotFoundError("Menu item not found.")
    return item


def _menu_fields(data: dict, partial: bool = False) -> dict:
    f = Fields(data)
    f.text("name", required=not partial, max_len=120)
    f.text("category", required=False, max_len=60)
    f.decimal("price", required=not partial, min=0)
    f.text("portion_unit", required=False, max_len=30, default="portion")
    f.integer("shelf_life_hours", required=False, min=0)
    f.integer("batch_size", required=False, min=1, default=1)
    return f.check()


def create_menu_item(outlet_id: int, data: dict, actor_id: int | None = None) -> MenuItem:
    v = _menu_fields(data)
    if MenuItem.query.filter_by(outlet_id=outlet_id, name=v["name"]).first():
        raise ValidationError("Please fix the highlighted fields.", {"name": "already exists"})
    item = MenuItem(outlet_id=outlet_id, **v)
    db.session.add(item)
    db.session.flush()
    audit.record(outlet_id, actor_id, "menu.create", "menu_item", item.id)
    db.session.commit()
    return item


def update_menu_item(outlet_id: int, item_id: int, data: dict, actor_id: int | None = None) -> MenuItem:
    item = get_menu_item(outlet_id, item_id)
    merged = {"name": item.name, "category": item.category, "price": item.price,
              "portion_unit": item.portion_unit, "shelf_life_hours": item.shelf_life_hours,
              "batch_size": item.batch_size, **{k: v for k, v in data.items() if k in
              ("name", "category", "price", "portion_unit", "shelf_life_hours", "batch_size")}}
    v = _menu_fields(merged)
    clash = MenuItem.query.filter(MenuItem.outlet_id == outlet_id, MenuItem.name == v["name"],
                                  MenuItem.id != item.id).first()
    if clash:
        raise ValidationError("Please fix the highlighted fields.", {"name": "already exists"})
    for k, val in v.items():
        setattr(item, k, val)
    if "is_active" in data:
        item.is_active = bool(data["is_active"])
    audit.record(outlet_id, actor_id, "menu.update", "menu_item", item.id)
    db.session.commit()
    return item


def set_availability(outlet_id: int, item_id: int, is_available: bool) -> MenuItem:
    item = get_menu_item(outlet_id, item_id)
    item.is_available = bool(is_available)
    db.session.commit()
    return item


# ---- recipes (A5) ----------------------------------------------------------------------------
def get_recipe(outlet_id: int, item_id: int) -> list[RecipeLine]:
    item = get_menu_item(outlet_id, item_id)
    return sorted(item.recipe_lines, key=lambda r: r.id)


def set_recipe(outlet_id: int, item_id: int, lines: list[dict], actor_id: int | None = None) -> list[RecipeLine]:
    """Replace all recipe lines atomically. Quantities are in each ingredient's base unit."""
    item = get_menu_item(outlet_id, item_id)
    if not isinstance(lines, list):
        raise ValidationError("Please fix the highlighted fields.", {"lines": "must be a list"})
    errors, seen, clean = {}, set(), []
    for i, raw in enumerate(lines):
        f = Fields(raw if isinstance(raw, dict) else {})
        ing_id = f.integer("ingredient_id")
        qty = f.decimal("quantity_per_portion", gt=0)
        if f.errors:
            errors[f"lines[{i}]"] = "; ".join(f"{k} {m}" for k, m in f.errors.items())
            continue
        if ing_id in seen:
            errors[f"lines[{i}]"] = "ingredient appears twice"
            continue
        seen.add(ing_id)
        if not Ingredient.query.filter_by(id=ing_id, outlet_id=outlet_id).first():
            errors[f"lines[{i}]"] = "unknown ingredient"
            continue
        clean.append((ing_id, qty))
    if errors:
        raise ValidationError("Please fix the highlighted fields.", errors)
    RecipeLine.query.filter_by(menu_item_id=item.id).delete()
    db.session.flush()
    db.session.expire(item)
    for ing_id, qty in clean:
        db.session.add(RecipeLine(menu_item_id=item.id, ingredient_id=ing_id, quantity_per_portion=qty))
    audit.record(outlet_id, actor_id, "recipe.update", "menu_item", item.id, {"lines": len(clean)})
    db.session.commit()
    return get_recipe(outlet_id, item_id)


def items_without_recipe(outlet_id: int) -> list[MenuItem]:
    return [m for m in list_menu_items(outlet_id, active_only=True) if not m.recipe_lines]
