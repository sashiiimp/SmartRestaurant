"""Alerts, reorder and stock views: the numbers behind the screens, with the hand-calculated values of
the TESTING.md 4.2 / 4.3 world (chicken: 12 kg usable, 5 kg expired, need 15.48 today, 98.04 over 7 days)."""
from datetime import timedelta
from decimal import Decimal

from app.extensions import db
from app.models import Alert, StockRequest, Supplier
from app.models.inventory import PurchaseOrder, PurchaseOrderLine
from app.services import alert_service as al
from app.services import dashboard_service as dash
from app.services import inventory_service as inv
from app.services import recommendation_service as rec
from tests.integration.test_requirements_reorder_alerts import TODAY, kitchen_world, plan_days  # noqa: F401 (fixture)


def _critical_chicken(w):
    """Chicken stays at 12 kg usable but its minimum is raised to 15, so it is critical now and short in the plan."""
    w["chicken"].min_stock, w["chicken"].reorder_level = Decimal("15"), Decimal("20"); db.session.commit()
    plan_days(w)


def test_one_alert_row_per_ingredient_for_roles_that_see_both(kitchen_world):
    """A2: critical stock + projected stockout for the same ingredient are one row for admin and inventory; the kitchen
    (which never sees stock alerts) keeps its projected row. Both stay in the database."""
    w = kitchen_world
    _critical_chicken(w)
    admin = [r for r in al.list_alerts(1, "admin", refresh=True)["rows"] if r["entity_id"] == w["chicken"].id]
    assert len(admin) == 1 and admin[0]["alert_type"] == "critical_stock" and admin[0]["severity"] == "critical"
    assert admin[0]["message"] == f"Chicken is critically low: 12 kg usable (minimum 15); short by 3.48 on {TODAY.isoformat()}"
    assert len(admin[0]["merged_ids"]) == 1
    kitchen = [r for r in al.list_alerts(1, "kitchen")["rows"] if r["entity_id"] == w["chicken"].id]
    assert [r["alert_type"] for r in kitchen] == ["projected_stockout"]
    assert kitchen[0]["message"] == f"Chicken will run short on {TODAY.isoformat()} (short by 3.48 kg)"   # not 3.48 with 2dp padding
    assert Alert.query.filter(Alert.entity_id == w["chicken"].id, Alert.status == "open").count() == 2


def test_alert_counts_are_one_number_everywhere(kitchen_world):
    """A1: the bell, the severity badges, the Open tab and "Show all" use the same rule: every unresolved alert,
    acknowledged or not. "new" counts the ones nobody has acknowledged yet."""
    w = kitchen_world
    _critical_chicken(w)
    out = al.list_alerts(1, "inventory", refresh=True)
    c = out["counts"]
    assert c["total"] == len(out["rows"]) == c["critical"] + c["warning"] + c["info"] and c["new"] == c["total"]
    row = next(r for r in out["rows"] if r["entity_id"] == w["chicken"].id)
    al.acknowledge(1, row["id"], "inventory")
    after = al.list_alerts(1, "inventory")
    assert after["counts"]["total"] == c["total"] and after["counts"]["new"] == c["new"] - 1          # still unresolved
    chicken = next(r for r in after["rows"] if r["entity_id"] == w["chicken"].id)
    assert chicken["status"] == "acknowledged"
    # acknowledging the stock row also acknowledges the projected shortfall shown in it
    assert all(r["status"] == "acknowledged" for r in al.list_alerts(1, "kitchen")["rows"] if r["entity_id"] == w["chicken"].id)


def _supplier_for_chicken(w, lead=2):
    sup = Supplier(outlet_id=1, name="Ceylon Poultry", lead_time_days=lead)
    db.session.add(sup); db.session.commit()
    w["chicken"].default_supplier_id = sup.id; db.session.commit()
    return sup


def test_draft_order_that_covers_a_need_is_named_not_dropped(kitchen_world):
    """I1: raw = 29.52 + 5 - 12 = 22.52 kg. A 30 kg draft covers it, so nothing is suggested, and the page says so,
    with the order and its status. The dashboard row keeps the real 7-day shortfall."""
    w = kitchen_world
    sup = _supplier_for_chicken(w)
    plan_days(w)
    po = PurchaseOrder(outlet_id=1, supplier_id=sup.id, po_number="PO-1", status="draft")
    po.lines = [PurchaseOrderLine(ingredient_id=w["chicken"].id, qty_ordered=Decimal("30"), qty_received=0)]
    db.session.add(po); db.session.commit()
    view = rec.get_reorder_view(1, TODAY)
    assert all(r["name"] != "Chicken" for r in view["rows"])
    cov = next(c for c in view["covered_by_orders"] if c["name"] == "Chicken")
    assert (cov["need_over_lead_time"], cov["safety_stock"], cov["usable_stock"], cov["on_order"]) == (29.52, 5.0, 12.0, 30.0)
    assert cov["orders"] == [{"id": po.id, "status": "draft", "qty": 30.0}]
    row = next(r for r in dash.inventory_dashboard(1)["requirements"] if r["name"] == "Chicken")
    assert (row["need"], row["usable"], row["covered_pct"], row["why"]) == (98.04, 12.0, 12, "short")   # 12 / 98.04 = 12%
    assert row["suggestion"] is None and row["on_order"] == 30.0 and row["orders"][0]["status"] == "draft"
    # once sent, the same order still covers it and is no longer a draft
    po.status = "sent"; db.session.commit()
    assert rec.get_reorder_view(1, TODAY)["covered_by_orders"][0]["orders"][0]["status"] == "sent"
    # a 10 kg order no longer covers it: suggested again, 22.52 - 10 = 12.52 -> 15 (pack 5)
    po.lines[0].qty_ordered = Decimal("10"); db.session.commit()
    assert next(r for r in rec.get_reorder_view(1, TODAY)["rows"] if r["name"] == "Chicken")["suggested_qty"] == 15.0


def test_dashboard_rows_carry_the_real_need_for_every_ingredient(kitchen_world):
    """I4: an ingredient listed only because it is below its minimum still shows its 7-day need (oil: 32 fried
    portions x 0.05 L = 1.6 L, 4 L usable, minimum 5). Without a supplier the suggestion says so (no supplier_id)."""
    w = kitchen_world
    w["oil"].min_stock, w["oil"].reorder_level = Decimal("5"), Decimal("8"); db.session.commit()
    plan_days(w)
    rows = dash.inventory_dashboard(1)["requirements"]
    oil = next(r for r in rows if r["name"] == "Oil")
    assert (oil["need"], oil["usable"], oil["why"], oil["covered_pct"]) == (1.6, 4.0, "below_minimum", 100)
    assert oil["suggestion"]["supplier"] is None and oil["suggestion"]["supplier_id"] is None
    # most short first; below-minimum rows after every shortfall
    whys = [r["why"] for r in rows]
    assert whys == sorted(whys, key=lambda x: x != "short")
    assert dash.inventory_dashboard(1)["totals"]["requirements"] == len(rows)


def test_stock_levels_say_how_much_has_expired(kitchen_world):
    """I2: chicken has 17 kg on hand, 5 kg of it expired, so 12 kg usable."""
    chicken = next(r for r in inv.stock_levels(1, TODAY) if r["name"] == "Chicken")
    assert (chicken["on_hand"], chicken["usable"], chicken["expired"]) == (17.0, 12.0, 5.0)
    bun = next(r for r in inv.stock_levels(1, TODAY) if r["name"] == "Bun")
    assert bun["expired"] == 0.0


def test_open_request_past_its_date_is_overdue(app):
    """I3: open (pending or approved) and needed before today = overdue; issued, or needed today, is not."""
    def req(status, days):
        r = StockRequest(outlet_id=1, status=status, needed_date=TODAY + timedelta(days=days))
        db.session.add(r); db.session.commit()
        return inv.stock_request_dict(r, detail=False)["overdue"]
    assert req("approved", -1) is True and req("pending", -3) is True
    assert req("approved", 0) is False and req("issued", -1) is False
    r = StockRequest(outlet_id=1, status="pending"); db.session.add(r); db.session.commit()
    assert inv.stock_request_dict(r, detail=False)["overdue"] is False                                   # no date
