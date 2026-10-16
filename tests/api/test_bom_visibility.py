"""BOM-1 .. BOM-4: Menu & Recipes (BOM): the admin manages ingredients as well as recipes; inventory keeps its access;
the menu list says how many ingredients each recipe has; the pages open for the admin only."""
from app.models import AuditLog
from tests.conftest import login
from tests.factories import add_recipe, make_ingredient, make_item


def as_user(app, users, role):
    c = app.test_client()
    assert login(c, users[role].username).status_code == 302
    return c


def test_admin_and_inventory_create_and_edit_ingredients_kitchen_cannot(app, users):
    """BOM-1: same API, same validation, audited with the user who did it."""
    admin, inventory, kitchen = (as_user(app, users, r) for r in ("admin", "inventory", "kitchen"))
    body = {"name": "Coconut milk", "unit": "l", "pack_size": 1}
    assert kitchen.post("/api/v1/ingredients", json=body).status_code == 403
    r = admin.post("/api/v1/ingredients", json=body)
    assert r.status_code == 201
    ing = r.get_json()["data"]
    assert admin.patch(f"/api/v1/ingredients/{ing['id']}", json={**body, "reorder_level": 4}).get_json()["data"]["reorder_level"] == 4
    assert inventory.patch(f"/api/v1/ingredients/{ing['id']}", json={**body, "reorder_level": 6}).status_code == 200
    assert kitchen.patch(f"/api/v1/ingredients/{ing['id']}", json=body).status_code == 403
    assert admin.post("/api/v1/ingredients", json={"unit": "kg"}).status_code == 422          # name still required
    assert inventory.post("/api/v1/ingredients", json={"name": "Curry leaves", "unit": "kg"}).status_code == 201
    who = {a.user_id for a in AuditLog.query.filter(AuditLog.action.like("ingredient.%"))}
    assert {users["admin"].id, users["inventory"].id} <= who


def test_menu_items_say_how_many_ingredients_their_recipe_has(app, users):
    """BOM-2: recipe_lines next to has_recipe (read from the same recipe rows)."""
    burger, fries = make_item(name="Chicken Burger"), make_item(name="French Fries")
    add_recipe(burger, [(make_ingredient(name="Bun", unit="pcs"), 1), (make_ingredient(name="Chicken", unit="kg"), 0.12)])
    rows = {i["name"]: i for i in as_user(app, users, "admin").get("/api/v1/menu-items").get_json()["data"]}
    assert (rows["Chicken Burger"]["has_recipe"], rows["Chicken Burger"]["recipe_lines"]) == (True, 2)
    assert (rows["French Fries"]["has_recipe"], rows["French Fries"]["recipe_lines"]) == (False, 0)


def test_menu_and_recipes_tabs_open_for_the_admin_only(app, users):
    """BOM-3: Menu items, BOM overview and Ingredients are tabs of one admin page; other roles are refused."""
    admin, kitchen, inventory = (as_user(app, users, r) for r in ("admin", "kitchen", "inventory"))
    for tab, marker in (("", "Menu items"), ("?tab=items", "Menu items"), ("?tab=bom", "BOM overview"), ("?tab=ingredients", "sr-ingredient-form")):
        r = admin.get("/admin/catalog" + tab)
        assert r.status_code == 200 and marker in r.get_data(as_text=True) and "Menu &amp; Recipes (BOM)" in r.get_data(as_text=True), tab
    assert kitchen.get("/admin/catalog?tab=bom").status_code == 403 and inventory.get("/admin/catalog?tab=ingredients").status_code == 403


def test_admin_dashboard_links_to_the_bom(app, users):
    """BOM-4"""
    html = as_user(app, users, "admin").get("/admin").get_data(as_text=True)
    assert 'href="/admin/catalog?tab=bom"' in html and "Manage BOM" in html
