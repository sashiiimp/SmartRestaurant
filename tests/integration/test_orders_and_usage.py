"""K10 daily orders and K8 ingredient usage. Usage numbers follow TESTING.md 4.2 (54 burgers, 30 fried chicken)."""
from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.extensions import db
from app.models import AuditLog, PreparationRecord, StockMovement
from app.services import inventory_service as inv
from app.services import kitchen_service as kit
from app.services import recommendation_service as rec
from app.services.errors import ConflictError, NotFoundError, ValidationError
from tests.factories import add_batch, add_recipe, make_ingredient, make_item

TODAY = date(2026, 9, 25)


# ---- daily orders -----------------------------------------------------------------------------------------
@pytest.fixture()
def burger(app):
    return make_item(name="Burger", batch_size=6)


def order(item, qty=4, **extra):
    return kit.create_order(1, {"menu_item_id": item.id, "quantity": qty, **extra})


def test_create_defaults_to_an_open_order_for_today(burger):
    o = order(burger, customer_note="table 3")
    assert (o["status"], o["order_date"], o["item"], o["quantity"], o["customer_note"]) == ("open", "2026-09-25", "Burger", 4, "table 3")
    assert AuditLog.query.filter_by(action="order.create").count() == 1


def test_create_validation(burger):
    def fail(**data):
        with pytest.raises(ValidationError) as e:
            kit.create_order(1, {"menu_item_id": burger.id, "quantity": 2, **data})
        return e.value.fields
    assert "order_date" in fail(order_date=(TODAY + timedelta(days=1)).isoformat())     # a future day is a pre-order
    assert "quantity" in fail(quantity=0)
    assert "customer_note" in fail(customer_note="x" * 256)
    assert fail(menu_item_id=make_item(name="Gone", active=False).id) == {"menu_item_id": "is not active"}
    with pytest.raises(NotFoundError):
        kit.create_order(1, {"menu_item_id": 999, "quantity": 1})
    assert kit.create_order(1, {"menu_item_id": burger.id, "quantity": 2, "order_date": "2026-09-20"})["order_date"] == "2026-09-20"


def test_only_an_open_order_can_change(burger):
    a, b, c = order(burger), order(burger), order(burger)
    edited = kit.update_order(1, a["id"], {"quantity": 9, "customer_note": "change of plan"})
    assert (edited["quantity"], edited["customer_note"], edited["status"]) == (9, "change of plan", "open")
    assert kit.update_order(1, b["id"], {"status": "fulfilled"})["status"] == "fulfilled"
    assert kit.update_order(1, c["id"], {"status": "cancelled"})["status"] == "cancelled"
    for o in (b, c):
        with pytest.raises(ConflictError):
            kit.update_order(1, o["id"], {"quantity": 1})
    with pytest.raises(ValidationError) as e:
        kit.update_order(1, a["id"], {"quantity": 0, "status": "done", "order_date": "2026-10-01"})
    assert set(e.value.fields) == {"quantity", "status", "order_date"}
    with pytest.raises(NotFoundError):
        kit.update_order(1, 999, {"quantity": 1})


def test_list_filters_and_order(burger):
    fries = make_item(name="Fries")
    a = order(burger, 1, order_date="2026-09-24")
    b = order(fries, 2)
    c = order(burger, 3)
    kit.update_order(1, c["id"], {"status": "fulfilled"})
    assert [o["id"] for o in kit.list_orders(1)] == [c["id"], b["id"], a["id"]]
    assert [o["id"] for o in kit.list_orders(1, TODAY, TODAY)] == [c["id"], b["id"]]
    assert [o["id"] for o in kit.list_orders(1, status="fulfilled")] == [c["id"]]
    assert [o["id"] for o in kit.list_orders(1, item_id=fries.id)] == [b["id"]]
    with pytest.raises(ValidationError):
        kit.list_orders(1, status="bogus")


def test_orders_feed_no_calculation(burger):
    order(burger, 500)
    assert rec._preorder_totals(1, TODAY) == {}
    assert rec.compute_recommended(Decimal(40), Decimal(10), rec._preorder_totals(1, TODAY).get(burger.id, 0), 6) == 48


# ---- ingredient usage --------------------------------------------------------------------------------------
@pytest.fixture()
def kitchen(app):
    burger, fried, milo = make_item(name="Chicken Burger"), make_item(name="Fried Chicken"), make_item(name="Iced Milo")
    chicken = make_ingredient(name="Chicken", unit="kg")
    bun, lettuce, oil = make_ingredient(name="Bun", unit="pcs"), make_ingredient(name="Lettuce", unit="kg"), make_ingredient(name="Oil", unit="L")
    add_recipe(burger, [(chicken, "0.120"), (bun, 1), (lettuce, "0.015")])
    add_recipe(fried, [(chicken, "0.300"), (oil, "0.050")])
    for item, qty in ((burger, 24), (burger, 30), (fried, 30), (milo, 20)):     # burgers were prepared in two batches
        db.session.add(PreparationRecord(outlet_id=1, menu_item_id=item.id, prep_date=TODAY, quantity=qty)); db.session.commit()
    return {"chicken": chicken, "bun": bun, "lettuce": lettuce, "oil": oil}


def rows(day=TODAY):
    out = kit.ingredient_usage_for(1, day)
    return {r["ingredient"]: r for r in out["rows"]}, out


def test_expected_usage_is_prepared_times_recipe(kitchen):
    by, out = rows()
    assert by["Bun"]["expected"] == 54.0                        # 54 burgers x 1
    assert by["Lettuce"]["expected"] == 0.81                    # 54 x 0.015
    assert by["Oil"]["expected"] == 1.5                         # 30 x 0.050
    assert by["Chicken"]["expected"] == 15.48                   # 54 x 0.120 + 30 x 0.300
    assert all(r["recorded"] is None and r["variance"] is None for r in by.values())
    assert out["items_without_recipe"] == ["Iced Milo"] and out["prepared_items"] == 3


def test_record_variance_replace_and_clear(kitchen):
    w = kitchen
    first = kit.record_ingredient_usage(1, {"ingredient_id": w["chicken"].id, "quantity": "16.000", "note": "extra for a big order"})
    assert first["created"] is True
    by, _ = rows()
    assert (by["Chicken"]["recorded"], by["Chicken"]["variance"], by["Chicken"]["note"]) == (16.0, 0.52, "extra for a big order")
    again = kit.record_ingredient_usage(1, {"ingredient_id": w["chicken"].id, "quantity": 14})
    assert again["created"] is False and again["usage_id"] == first["usage_id"]
    by, _ = rows()
    assert (by["Chicken"]["recorded"], by["Chicken"]["variance"], by["Chicken"]["note"]) == (14.0, -1.48, None)
    kit.clear_ingredient_usage(1, first["usage_id"])
    by, _ = rows()
    assert by["Chicken"]["recorded"] is None and by["Chicken"]["expected"] == 15.48
    assert AuditLog.query.filter(AuditLog.action.in_(["usage.record", "usage.clear"])).count() == 3


def test_an_ingredient_with_no_expected_use_can_still_be_recorded(kitchen):
    detergent = make_ingredient(name="Cooking salt", unit="kg")
    kit.record_ingredient_usage(1, {"ingredient_id": detergent.id, "quantity": 0.5})
    by, _ = rows()
    assert (by["Cooking salt"]["expected"], by["Cooking salt"]["recorded"], by["Cooking salt"]["variance"]) == (0.0, 0.5, 0.5)


def test_recording_usage_never_moves_stock(kitchen):
    w = kitchen
    add_batch(w["chicken"], 40)
    kit.record_ingredient_usage(1, {"ingredient_id": w["chicken"].id, "quantity": 15.48})
    assert inv.usable_map(1)[w["chicken"].id] == Decimal("40")
    assert StockMovement.query.filter(StockMovement.movement_type != "stock_in").count() == 0
    assert inv.stock_invariant_violations(1) == []


def test_usage_validation_and_days_without_preparation(kitchen):
    w = kitchen
    def fail(**data):
        with pytest.raises(ValidationError) as e:
            kit.record_ingredient_usage(1, {"ingredient_id": w["chicken"].id, "quantity": 1, **data})
        return e.value.fields
    assert "quantity" in fail(quantity=-1)
    assert "date" in fail(date="2026-10-01")
    assert "note" in fail(note="x" * 256)
    assert fail(ingredient_id=999) == {"ingredient_id": "unknown or inactive ingredient"}
    with pytest.raises(NotFoundError):
        kit.clear_ingredient_usage(1, 999)
    empty = kit.ingredient_usage_for(1, TODAY - timedelta(days=3))
    assert empty["rows"] == [] and empty["prepared_items"] == 0
