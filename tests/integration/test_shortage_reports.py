"""K12: the kitchen reports a shortage; it becomes a critical alert for Inventory and Admin (not Kitchen)."""
from datetime import date

import pytest

from app.extensions import db
from app.models import Alert, AuditLog, StockMovement
from app.services import alert_service as al
from app.services import inventory_service as inv
from app.services.errors import NotFoundError, ValidationError
from tests.factories import add_batch, make_ingredient, make_user


@pytest.fixture()
def chicken(app):
    ing = make_ingredient(name="Chicken", unit="kg", min_stock=1, reorder_level=2)
    add_batch(ing, 50, expiry=date(2026, 12, 1))          # plenty in stock, so no computed alert interferes
    return ing


def manual(role):
    return [a for a in al.list_alerts(1, role, refresh=True)["rows"] if a["alert_type"] == "manual_shortage"]


def test_report_opens_a_critical_alert_for_inventory_and_admin_only(chicken):
    r = al.report_shortage(1, {"ingredient_id": chicken.id, "note": "only 2 kg in the walk-in"}, make_user("kitchen").id)
    assert r["created"] is True and r["severity"] == "critical" and r["status"] == "open"
    assert r["message"] == "Kitchen reports a shortage of Chicken: only 2 kg in the walk-in"
    assert [a["entity_id"] for a in manual("inventory")] == [chicken.id]
    assert [a["entity_id"] for a in manual("admin")] == [chicken.id]
    assert manual("kitchen") == []
    assert AuditLog.query.filter_by(action="shortage.report").count() == 1


def test_second_report_updates_the_open_alert(chicken):
    first = al.report_shortage(1, {"ingredient_id": chicken.id})
    second = al.report_shortage(1, {"ingredient_id": chicken.id, "note": "now 1 kg"})
    assert second["created"] is False and second["id"] == first["id"]
    assert Alert.query.filter_by(alert_type="manual_shortage").count() == 1
    assert manual("inventory")[0]["message"].endswith("now 1 kg")


def test_reporting_again_after_acknowledge_reopens_it(chicken):
    a = al.report_shortage(1, {"ingredient_id": chicken.id})
    al.acknowledge(1, a["id"], "inventory")
    assert Alert.query.get(a["id"]).status == "acknowledged"
    al.report_shortage(1, {"ingredient_id": chicken.id})
    assert Alert.query.get(a["id"]).status == "open"


def test_alert_survives_evaluation_until_the_ingredient_is_restocked(chicken):
    a = al.report_shortage(1, {"ingredient_id": chicken.id})
    al.evaluate(1); al.evaluate(1)
    assert Alert.query.get(a["id"]).status == "open"                      # evaluation alone never closes it
    inv.record_stock_in(1, {"ingredient_id": chicken.id, "quantity": 5, "received_date": "2026-09-25"})
    al.evaluate(1)
    closed = Alert.query.get(a["id"])
    assert (closed.status, closed.closed_reason, closed.open_key) == ("closed", "restocked", None)
    assert manual("inventory") == []
    # a stock-out is not a restock
    b = al.report_shortage(1, {"ingredient_id": chicken.id})
    assert b["created"] is True and b["id"] != a["id"]
    inv.record_stock_out(1, {"ingredient_id": chicken.id, "quantity": 1})
    al.evaluate(1)
    assert Alert.query.get(b["id"]).status == "open"


def test_validation(chicken):
    with pytest.raises(NotFoundError):
        al.report_shortage(1, {"ingredient_id": 999})
    with pytest.raises(ValidationError) as e:
        al.report_shortage(1, {"ingredient_id": chicken.id, "note": "x" * 151})
    assert "note" in e.value.fields
    with pytest.raises(ValidationError):
        al.report_shortage(1, {})


def test_a_restock_in_the_same_second_as_the_report_counts(chicken):
    """DATETIME has whole seconds on MySQL and MariaDB, so the report and the stock-in can carry the same timestamp."""
    a = al.report_shortage(1, {"ingredient_id": chicken.id})
    inv.record_stock_in(1, {"ingredient_id": chicken.id, "quantity": 5, "received_date": "2026-09-25"})
    alert = Alert.query.get(a["id"])
    StockMovement.query.filter_by(ingredient_id=chicken.id).filter(StockMovement.quantity > 0).update(
        {"created_at": alert.created_at})
    db.session.commit()
    al.evaluate(1)
    assert Alert.query.get(a["id"]).closed_reason == "restocked"



def test_stock_from_before_the_report_never_closes_it_even_in_the_same_second(chicken):
    """The opposite edge: the fixture's earlier stock-in given the report's timestamp must not count as a restock."""
    a = al.report_shortage(1, {"ingredient_id": chicken.id})
    alert = Alert.query.get(a["id"])
    StockMovement.query.filter_by(ingredient_id=chicken.id).update({"created_at": alert.created_at})
    db.session.commit()
    al.evaluate(1)
    assert Alert.query.get(a["id"]).status == "open"
    assert a["details"]["last_movement_id"] == StockMovement.query.filter_by(ingredient_id=chicken.id).count()
