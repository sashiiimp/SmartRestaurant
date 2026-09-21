"""A4, A5, A15: menu, recipes and promotions."""
from datetime import date

import pytest

from app.models import RecipeLine
from app.services import data_management_service as dm
from app.services.errors import NotFoundError, ValidationError
from tests.factories import make_ingredient, make_item


def test_menu_item_create_update_deactivate(app):
    item = dm.create_menu_item(1, {"name": "Wrap", "price": "720", "batch_size": 6})
    assert item.batch_size == 6 and item.is_active
    with pytest.raises(ValidationError) as e:
        dm.create_menu_item(1, {"name": "Wrap", "price": 1})
    assert "name" in e.value.fields
    with pytest.raises(ValidationError):
        dm.create_menu_item(1, {"name": "Free", "price": -1})
    with pytest.raises(ValidationError):
        dm.create_menu_item(1, {"name": "Zero batch", "price": 1, "batch_size": 0})
    dm.update_menu_item(1, item.id, {"price": "750", "is_active": False})
    assert float(dm.get_menu_item(1, item.id).price) == 750 and not dm.get_menu_item(1, item.id).is_active
    assert dm.list_menu_items(1, active_only=True) == []
    with pytest.raises(NotFoundError):
        dm.get_menu_item(1, 999)


def test_recipe_is_replaced_atomically_and_validated(app):
    item = make_item(name="Burger")
    chicken, bun = make_ingredient(name="Chicken"), make_ingredient(name="Bun", unit="pcs")
    dm.set_recipe(1, item.id, [{"ingredient_id": chicken.id, "quantity_per_portion": "0.12"},
                               {"ingredient_id": bun.id, "quantity_per_portion": 1}])
    assert RecipeLine.query.count() == 2 and dm.items_without_recipe(1) == []
    for bad in ([{"ingredient_id": chicken.id, "quantity_per_portion": 0}],
                [{"ingredient_id": chicken.id, "quantity_per_portion": 1}, {"ingredient_id": chicken.id, "quantity_per_portion": 2}],
                [{"ingredient_id": 9999, "quantity_per_portion": 1}]):
        with pytest.raises(ValidationError):
            dm.set_recipe(1, item.id, bad)
    assert RecipeLine.query.count() == 2                  # a failed replace leaves the old recipe untouched
    dm.set_recipe(1, item.id, [{"ingredient_id": bun.id, "quantity_per_portion": 2}])
    assert [float(r.quantity_per_portion) for r in dm.get_recipe(1, item.id)] == [2.0]
    dm.set_recipe(1, item.id, [])
    assert [m.name for m in dm.items_without_recipe(1)] == ["Burger"]


def test_promotion_validation_and_frame(app):
    a, b = make_item(name="A"), make_item(name="B")
    with pytest.raises(ValidationError):
        dm.create_promotion(1, {"name": "P", "start_date": "2026-09-10", "end_date": "2026-09-01", "discount_pct": 10,
                                "item_ids": [a.id]})
    with pytest.raises(ValidationError) as e:
        dm.create_promotion(1, {"name": "P", "start_date": "2026-09-01", "end_date": "2026-09-02", "discount_pct": 10})
    assert "item_ids" in e.value.fields
    dm.create_promotion(1, {"name": "P", "start_date": "2026-09-01", "end_date": "2026-09-03", "discount_pct": 15,
                            "item_ids": [a.id]})
    dm.create_promotion(1, {"name": "All", "start_date": "2026-09-02", "end_date": "2026-09-02", "discount_pct": 5,
                            "applies_to_all": True})
    frame = dm.load_promotions_frame(1)
    assert len(frame) == 3 + 2                            # A for 3 days, plus both items on the 2nd
    assert frame[(frame.item_id == a.id) & (frame.date == "2026-09-02")]["discount_pct"].max() == 15
    promo = dm.list_promotions(1)[0]
    dm.set_promotion_active(1, promo.id, False)
    assert len(dm.load_promotions_frame(1)) < 5


def test_availability_toggle(app):
    item = make_item(name="Burger")
    assert dm.set_availability(1, item.id, False).is_available is False
