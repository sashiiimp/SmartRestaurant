"""flask smartrest seed: outlet, users, settings, catalog. Goes through services (ARCH section 10)."""
import os
import secrets

from app.seed import catalog
from app.services import auth_service, data_management_service as dm, inventory_service as inv
from app.services import outlet_service, settings

USERS = [("admin", "System Administrator", "admin"), ("kitchen1", "Kitchen Manager", "kitchen"),
         ("inventory1", "Inventory Manager", "inventory")]


def seed_base(reset: bool = False) -> dict:
    """Idempotent. Returns {'passwords': {...}} for users created in this run."""
    if reset:
        if os.environ.get("APP_ENV") == "prod":
            raise RuntimeError("--reset is refused when APP_ENV=prod")
        outlet_service.reset_database()
    outlet = outlet_service.ensure_outlet()
    settings.seed_defaults(outlet.id)

    created = {}
    password = os.environ.get("SEED_PASSWORD") or secrets.token_urlsafe(9)
    for username, full_name, role in USERS:
        if not auth_service.username_exists(username):
            auth_service.create_user(outlet.id, full_name, username, role, password)
            created[username] = password

    suppliers = []
    existing = {s.name: s for s in inv.list_suppliers(outlet.id)}
    for s in catalog.SUPPLIERS:
        suppliers.append(existing.get(s["name"]) or inv.create_supplier(outlet.id, s))

    ingredients = {i.name: i for i in inv.list_ingredients(outlet.id)}
    for (name, unit, cat, shelf, sup, mn, ro, pack, moq, _open, _cost) in catalog.INGREDIENTS:
        if name not in ingredients:
            ingredients[name] = inv.create_ingredient(outlet.id, {
                "name": name, "unit": unit, "category": cat, "shelf_life_days": shelf,
                "default_supplier_id": suppliers[sup].id, "min_stock": mn, "reorder_level": ro,
                "pack_size": pack, "reorder_qty": moq})

    items = {m.name: m for m in dm.list_menu_items(outlet.id)}
    for (name, price, batch, shelf, cat, _base) in catalog.MENU:
        if name not in items:
            items[name] = dm.create_menu_item(outlet.id, {
                "name": name, "price": price, "batch_size": batch, "shelf_life_hours": shelf, "category": cat})
    for name, lines in catalog.RECIPES.items():
        item = items[name]
        if not dm.get_recipe(outlet.id, item.id):
            dm.set_recipe(outlet.id, item.id, [
                {"ingredient_id": ingredients[ing].id, "quantity_per_portion": q} for ing, q in lines])
    return {"passwords": created}
