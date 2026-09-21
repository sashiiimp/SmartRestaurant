"""I10: supplier management. Deactivation keeps existing links but blocks new ones."""
import pytest

from app.models import AuditLog
from app.services import inventory_service as inv
from app.services.errors import NotFoundError, ValidationError
from tests.factories import make_ingredient


def test_create_and_list_with_defaults(app):
    s = inv.create_supplier(1, {"name": "Ceylon Poultry", "phone": "011 111"})
    assert s.lead_time_days == 2 and s.is_active is True
    assert [x.name for x in inv.list_suppliers(1)] == ["Ceylon Poultry"]
    assert AuditLog.query.filter_by(action="supplier.create").count() == 1


def test_name_is_required_and_unique(app):
    inv.create_supplier(1, {"name": "A"})
    with pytest.raises(ValidationError) as e:
        inv.create_supplier(1, {"name": "A"})
    assert e.value.fields == {"name": "already exists"}
    with pytest.raises(ValidationError) as e:
        inv.create_supplier(1, {"name": " ", "lead_time_days": -1})
    assert set(e.value.fields) == {"name", "lead_time_days"}


def test_update_details_and_rename_clash(app):
    a = inv.create_supplier(1, {"name": "A", "lead_time_days": 1})
    b = inv.create_supplier(1, {"name": "B"})
    inv.update_supplier(1, a.id, {"lead_time_days": 3, "notes": "cash on delivery"})
    assert (a.lead_time_days, a.notes, a.name) == (3, "cash on delivery", "A")
    with pytest.raises(ValidationError):
        inv.update_supplier(1, b.id, {"name": "A"})
    with pytest.raises(NotFoundError):
        inv.update_supplier(1, 999, {"name": "Z"})


def test_deactivate_keeps_existing_link_but_blocks_new_ones(app):
    old = inv.create_supplier(1, {"name": "Old"})
    new = inv.create_supplier(1, {"name": "New"})
    ing = make_ingredient(name="Chicken", supplier_id=old.id)
    inv.update_supplier(1, old.id, {"is_active": False})
    assert [s.name for s in inv.list_suppliers(1, active_only=True)] == ["New"]
    # the ingredient may keep its (now inactive) supplier while other fields change
    inv.update_ingredient(1, ing.id, {"min_stock": 2, "reorder_level": 4})
    assert ing.default_supplier_id == old.id
    # but nobody can newly choose an inactive supplier
    other = make_ingredient(name="Rice")
    with pytest.raises(ValidationError) as e:
        inv.update_ingredient(1, other.id, {"default_supplier_id": old.id})
    assert e.value.fields == {"default_supplier_id": "supplier is inactive"}
    with pytest.raises(ValidationError) as e:
        inv.record_stock_in(1, {"ingredient_id": other.id, "quantity": 5, "supplier_id": old.id})
    assert e.value.fields == {"supplier_id": "supplier is inactive"}
    inv.update_ingredient(1, other.id, {"default_supplier_id": new.id})
    inv.update_supplier(1, old.id, {"is_active": True})
    assert [s.name for s in inv.list_suppliers(1, active_only=True)] == ["New", "Old"]


def test_is_active_must_be_boolean(app):
    s = inv.create_supplier(1, {"name": "A"})
    with pytest.raises(ValidationError):
        inv.update_supplier(1, s.id, {"is_active": "yes"})
