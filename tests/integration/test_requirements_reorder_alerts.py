"""REQ-1, REQ-2, ROR-1, ALT-1..ALT-3 with the hand-calculated numbers of TESTING.md 4.2 - 4.4."""
from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.extensions import db
from app.models import Alert, FoodWaste, ForecastRun, PreparationRecord, Recommendation, Supplier
from app.models.inventory import PurchaseOrder, PurchaseOrderLine
from app.services import alert_service as al
from app.services import inventory_service as inv
from app.services import recommendation_service as rec
from tests.factories import add_batch, add_recipe, make_ingredient, make_item, make_user

TODAY = date(2026, 9, 25)


def decide_row(item, day, qty, recommended=None):
    db.session.add(Recommendation(outlet_id=1, menu_item_id=item.id, target_date=day, forecast_qty=Decimal("1"),
                                  buffer_pct=Decimal("10"), preorder_qty=0, batch_size=1,
                                  recommended_qty=recommended if recommended is not None else qty,
                                  final_qty=qty, status="accepted"))
    db.session.commit()


@pytest.fixture()
def kitchen_world(app):
    """TESTING.md 4.2: recipes, plan 54 / 30 / 20 (Iced Milo has no recipe) and stock incl. an expired batch."""
    w = {}
    w["burger"] = make_item(name="Chicken Burger")
    w["fried"] = make_item(name="Fried Chicken 2 pc")
    w["milo"] = make_item(name="Iced Milo")
    w["chicken"] = make_ingredient(name="Chicken", unit="kg", min_stock=5, reorder_level=10, pack_size=5, reorder_qty=10)
    w["bun"] = make_ingredient(name="Bun", unit="pcs")
    w["lettuce"] = make_ingredient(name="Lettuce", unit="kg")
    w["oil"] = make_ingredient(name="Oil", unit="L")
    add_recipe(w["burger"], [(w["chicken"], "0.120"), (w["bun"], 1), (w["lettuce"], "0.015")])
    add_recipe(w["fried"], [(w["chicken"], "0.300"), (w["oil"], "0.050")])
    add_batch(w["chicken"], 12, received=TODAY - timedelta(days=1), expiry=TODAY + timedelta(days=5))
    add_batch(w["chicken"], 5, received=TODAY - timedelta(days=6), expiry=TODAY - timedelta(days=1))   # expired
    add_batch(w["bun"], 60)
    add_batch(w["lettuce"], "0.5")
    add_batch(w["oil"], 4)
    return w


def test_requirements_match_the_hand_calculation(kitchen_world):
    """REQ-1"""
    w = kitchen_world
    decide_row(w["burger"], TODAY, 54); decide_row(w["fried"], TODAY, 30); decide_row(w["milo"], TODAY, 20)
    out = rec.get_requirements(1, TODAY)
    by = {r["name"]: r for r in out["ingredients"]}
    assert (by["Chicken"]["required"], by["Chicken"]["usable_stock"], by["Chicken"]["short_by"]) == (15.48, 12.0, 3.48)
    assert by["Chicken"]["status"] == "short"
    assert (by["Bun"]["required"], by["Bun"]["status"]) == (54.0, "sufficient")
    assert (by["Lettuce"]["required"], by["Lettuce"]["short_by"]) == (0.81, 0.31)
    assert (by["Oil"]["required"], by["Oil"]["status"]) == (1.5, "sufficient")
    assert out["cannot_compute"] == [{"menu_item_id": w["milo"].id, "name": "Iced Milo", "reason": "no_recipe"}]
    assert set(out["basis"].values()) == {"final_qty"}


def test_accepted_quantity_beats_recommended_quantity(kitchen_world):
    """REQ-2"""
    w = kitchen_world
    decide_row(w["burger"], TODAY, 10, recommended=54)   # manager overrode down to 10
    by = {r["name"]: r for r in rec.get_requirements(1, TODAY)["ingredients"]}
    assert by["Bun"]["required"] == 10.0


def test_items_without_forecast_are_listed_not_ignored(kitchen_world):
    out = rec.get_requirements(1, TODAY)
    assert {c["reason"] for c in out["cannot_compute"]} == {"no_forecast"}
    assert out["ingredients"] == []


def plan_days(w):
    """TESTING.md 4.3: chicken need 15.48 on day 1, 14.04 on day 2, then 68.52 over days 3-7 (98.04 in total)."""
    burger_qty = [54, 112, 114, 114, 114, 114, 115]
    fried_qty = [30, 2, 0, 0, 0, 0, 0]
    for i in range(7):
        d = TODAY + timedelta(days=i)
        decide_row(w["burger"], d, burger_qty[i])
        decide_row(w["fried"], d, fried_qty[i])


def test_days_of_cover_and_first_shortfall(kitchen_world):
    """R5, R6"""
    plan_days(kitchen_world)
    chicken = next(r for r in rec.get_ingredient_forecast(1, TODAY, 7)["ingredients"] if r["name"] == "Chicken")
    assert chicken["daily"][:2] == [15.48, 14.04] and round(chicken["total_need"], 2) == 98.04
    assert chicken["days_of_cover"] == 0.9                     # 12 / (98.04 / 7) = 0.857
    assert chicken["first_shortfall_date"] == TODAY.isoformat() and round(chicken["short_by"], 2) == 3.48


def reorder_for(name="Chicken"):
    return next((r for r in rec.get_reorder_suggestions(1, TODAY) if r["name"] == name), None)


def test_reorder_rows_r1_to_r4(kitchen_world):
    w = kitchen_world
    sup = Supplier(outlet_id=1, name="Ceylon Poultry", lead_time_days=2)
    db.session.add(sup); db.session.commit()
    w["chicken"].default_supplier_id = sup.id; db.session.commit()
    plan_days(w)
    r1 = reorder_for()
    assert (r1["need_over_lead_time"], r1["raw_qty"], r1["suggested_qty"]) == (29.52, 22.52, 25.0)   # R1
    w["chicken"].reorder_qty = Decimal("30"); db.session.commit()
    assert reorder_for()["suggested_qty"] == 30.0                                                    # R2
    w["chicken"].reorder_qty = Decimal("10"); db.session.commit()
    po = PurchaseOrder(outlet_id=1, supplier_id=sup.id, po_number="PO-1", status="sent")
    po.lines = [PurchaseOrderLine(ingredient_id=w["chicken"].id, qty_ordered=Decimal("10"), qty_received=0)]
    db.session.add(po); db.session.commit()
    assert reorder_for()["suggested_qty"] == 15.0 and reorder_for()["on_order"] == 10.0             # R3
    po.status = "cancelled"; db.session.commit()
    Recommendation.query.delete(); db.session.commit()
    decide_row(w["burger"], TODAY, 30)          # need 3.6 kg today, nothing later: raw = 3.6 + 5 - 12 < 0
    assert reorder_for() is None                                                                     # R4


# ---- alerts ----------------------------------------------------------------------------------------
@pytest.fixture()
def stock_world(app):
    ing = make_ingredient(name="Chicken", unit="kg", min_stock=5, reorder_level=10)
    return ing


def types(role="admin"):
    return sorted(a["alert_type"] for a in al.list_alerts(1, role, refresh=True)["rows"])


def set_usable(ing, qty):
    from app.models import StockBatch, StockMovement
    StockMovement.query.delete(); StockBatch.query.delete(); db.session.commit()
    if qty:
        add_batch(ing, qty, expiry=TODAY + timedelta(days=30))


@pytest.mark.parametrize("usable,expected", [(12, []), (8, ["low_stock"]), (4, ["critical_stock"]), (0, ["critical_stock"])])
def test_stock_level_alert_conditions(stock_world, usable, expected):
    """ALT-1 (table 4.4)"""
    set_usable(stock_world, usable)
    assert types() == expected


def test_projected_stockout_when_the_plan_needs_more_than_usable(kitchen_world):
    w = kitchen_world
    plan_days(w)
    got = [a for a in al.list_alerts(1, "admin", refresh=True)["rows"] if a["alert_type"] == "projected_stockout"
           and a["entity_id"] == w["chicken"].id]
    assert len(got) == 1 and got[0]["severity"] == "critical" and got[0]["target_date"] == TODAY.isoformat()


def test_alert_closes_when_the_condition_clears_and_never_duplicates(stock_world):
    """ALT-2"""
    set_usable(stock_world, 4)
    for _ in range(3):
        assert types() == ["critical_stock"]
    assert Alert.query.filter_by(status="open").count() == 1
    inv.record_stock_in(1, {"ingredient_id": stock_world.id, "quantity": 10, "received_date": "2026-09-25"})
    assert types() == []
    closed = Alert.query.filter_by(alert_type="critical_stock").one()
    assert closed.status == "closed" and closed.closed_reason == "cleared" and closed.open_key is None
    set_usable(stock_world, 4)
    assert types() == ["critical_stock"] and Alert.query.count() == 2   # a new open alert, the old one stays closed


def test_low_to_critical_replaces_the_alert(stock_world):
    set_usable(stock_world, 8)
    assert types() == ["low_stock"]
    set_usable(stock_world, 3)
    assert types() == ["critical_stock"]
    assert Alert.query.filter_by(alert_type="low_stock", status="closed").count() == 1


def test_expiry_alerts_and_expired_message(stock_world):
    add_batch(stock_world, 50, expiry=TODAY + timedelta(days=2), batch_no="SOON")
    add_batch(stock_world, 30, received=TODAY - timedelta(days=9), expiry=TODAY - timedelta(days=1), batch_no="OLD")
    rows = {a["message"].split(":")[1].split()[1]: a for a in al.list_alerts(1, "admin", refresh=True)["rows"]
            if a["alert_type"] == "expiry_warning"}
    assert rows["SOON"]["severity"] == "warning" and rows["OLD"]["severity"] == "critical"
    assert "wastage" in rows["OLD"]["message"]


def test_waste_risk_needs_rate_and_volume(app):
    a, b = make_item(name="A"), make_item(name="B")
    for item, prepared, wasted in ((a, 100, 20), (b, 15, 10)):
        db.session.add(PreparationRecord(outlet_id=1, menu_item_id=item.id, prep_date=TODAY - timedelta(days=2), quantity=prepared))
        db.session.add(FoodWaste(outlet_id=1, menu_item_id=item.id, waste_date=TODAY - timedelta(days=2), quantity=wasted,
                                 reason="overproduction", unit_price=1))
    db.session.commit()
    got = [a_["entity_id"] for a_ in al.list_alerts(1, "admin", refresh=True)["rows"] if a_["alert_type"] == "waste_risk"]
    assert got == [a.id]        # 20% of 100 is above 15%; 10 of 15 is a big rate but under the volume floor


def test_forecast_failed_alert(app):
    db.session.add(ForecastRun(outlet_id=1, as_of_date=TODAY, horizon_days=7, trigger_type="cli", status="failed",
                               reason="boom"))
    db.session.commit()
    assert types() == ["forecast_failed"]
    db.session.add(ForecastRun(outlet_id=1, as_of_date=TODAY, horizon_days=7, trigger_type="cli", status="ok"))
    db.session.commit()
    assert types() == []


def test_role_visibility_and_disabled_types(stock_world):
    """ALT-3"""
    set_usable(stock_world, 4)
    assert types("inventory") == ["critical_stock"] and types("kitchen") == []
    from app.services import settings
    settings.set_value(1, "alert.low_stock.enabled", 0)
    set_usable(stock_world, 8)
    assert "low_stock" not in types()          # nothing new is opened for a disabled type
    settings.set_value(1, "alert.low_stock.enabled", 1)


def test_acknowledge_only_for_visible_alerts(stock_world):
    from app.services.errors import NotFoundError
    set_usable(stock_world, 4)
    alert = al.list_alerts(1, "admin", refresh=True)["rows"][0]
    with pytest.raises(NotFoundError):
        al.acknowledge(1, alert["id"], "kitchen")
    assert al.acknowledge(1, alert["id"], "inventory")["status"] == "acknowledged"
    assert al.list_alerts(1, "inventory")["counts"]["critical"] == 0      # acknowledged alerts leave the open count
    assert len(al.list_alerts(1, "inventory")["rows"]) == 1                # but stay listed until the condition clears


def test_lazy_refresh(stock_world):
    """ALT-4: reading alerts re-evaluates when the last evaluation is older than 60 seconds."""
    from datetime import datetime
    from app.models import Setting
    set_usable(stock_world, 4)
    assert len(al.list_alerts(1, "admin")["rows"]) == 1        # first read evaluates
    set_usable(stock_world, 50)
    assert len(al.list_alerts(1, "admin")["rows"]) == 1        # fresh: not re-evaluated
    row = Setting.query.filter_by(setting_key="alerts_last_run_at").one()
    row.value = (datetime.utcnow() - timedelta(seconds=120)).isoformat(); db.session.commit()
    assert al.list_alerts(1, "admin")["rows"] == []            # stale: re-evaluated, condition cleared


def test_items_without_a_forecast_are_reported_not_hidden(kitchen_world):
    """C9 (review 7 Oct 2026): an item with a recipe but no forecast adds no ingredient need, so it is named."""
    w = kitchen_world
    decide_row(w["burger"], TODAY, 54)   # Chicken Burger planned today only; Fried Chicken never has a forecast
    fc = rec.get_ingredient_forecast(1, TODAY, 7)
    missing = {i["name"]: i["days"] for i in fc["items_without_forecast"]}
    assert missing["Fried Chicken 2 pc"] == 7 and missing["Chicken Burger"] == 6
    view = rec.get_reorder_view(1, TODAY)
    assert view["rows"] == rec.get_reorder_suggestions(1, TODAY)          # quantities unchanged
    assert {i["name"] for i in view["items_without_forecast"]} >= {"Fried Chicken 2 pc", "Chicken Burger"}
