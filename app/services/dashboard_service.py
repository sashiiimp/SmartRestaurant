"""Read-only aggregates for dashboards and reports (Dashboard service). Built up slice by slice."""
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal

from app.extensions import db
from app.models import AuditLog, FoodWaste, Ingredient, MenuItem, SalesRecord, StockBatch, StockMovement
from app.services import alert_service
from app.services import data_management_service as dm
from app.services import forecasting_service as fs
from app.services import inventory_service as inv
from app.services import recommendation_service as rec
from app.services.errors import ValidationError
from app.utils.dates import today


def kitchen_daily_summary(outlet_id: int, day: date) -> dict:
    """Per item: forecast, recommended, final, prepared, served, wasted (S6, K1, K5-K7)."""
    plan = rec.get_prep_plan(outlet_id, day)
    waste = {i: int(q) for i, q in db.session.query(FoodWaste.menu_item_id, db.func.sum(FoodWaste.quantity)).filter(
        FoodWaste.outlet_id == outlet_id, FoodWaste.waste_date == day).group_by(FoodWaste.menu_item_id)}
    rows = []
    for r in plan["items"]:
        flags = []
        if r["served_so_far"] is not None and r["served_so_far"] > r["prepared_so_far"]:
            flags.append("served_exceeds_prepared")
        wasted = waste.get(r["menu_item_id"], 0)
        if wasted > r["prepared_so_far"]:
            flags.append("waste_exceeds_prepared")
        rows.append({"menu_item_id": r["menu_item_id"], "name": r["name"], "forecast_qty": r["forecast_qty"],
                     "recommended_qty": r["recommended_qty"], "final_qty": r["final_qty"], "status": r["status"],
                     "prepared": r["prepared_so_far"], "served": r["served_so_far"], "wasted": wasted, "flags": flags})
    return {"date": day.isoformat(), "items": rows}


# ---- K1, I1 dashboards ---------------------------------------------------------------------------------
def kitchen_dashboard(outlet_id: int, day: date, role: str = "kitchen") -> dict:
    summary = kitchen_daily_summary(outlet_id, day)
    reqs = rec.get_requirements(outlet_id, day)
    alerts = alert_service.list_alerts(outlet_id, role)
    rows = summary["items"]
    planned = sum((r["final_qty"] if r["final_qty"] is not None else (r["recommended_qty"] or 0)) for r in rows)
    shorts = [r for r in reqs["ingredients"] if r["status"] == "short"]
    return {"date": day.isoformat(),
            "tiles": {"items_to_prepare": sum(1 for r in rows if (r["recommended_qty"] or 0) > 0),
                      "planned_total": planned, "prepared_total": sum(r["prepared"] for r in rows),
                      "shortage_count": len(shorts), "open_alerts": len(alerts["rows"])},
            "plan": rows, "shortages": shorts, "cannot_compute": reqs["cannot_compute"], "alerts": alerts["rows"][:8]}


def inventory_dashboard(outlet_id: int, role: str = "inventory") -> dict:
    day = today()
    levels = inv.stock_levels(outlet_id, day)
    counts = {"ok": 0, "low": 0, "out": 0}
    for r in levels:
        counts[r["status"]] += 1
    alerts = alert_service.list_alerts(outlet_id, role)
    forecast = rec.get_ingredient_forecast(outlet_id, day, 7)
    need_vs_stock = sorted(({"name": r["name"], "unit": r["unit"], "need": r["total_need"], "usable": r["usable_stock"]}
                            for r in forecast["ingredients"] if r["total_need"] > 0),
                           key=lambda r: r["usable"] - r["need"])[:10]
    return {"date": day.isoformat(), "counts": counts, "alerts": alerts["rows"][:8], "alert_counts": alerts["counts"],
            "reorder": rec.get_reorder_suggestions(outlet_id, day)[:5], "need_vs_stock": need_vs_stock,
            "expiring": inv.list_batches(outlet_id, expiring_within_days=3)[:10]}


# ---- reports (A8, A11) and the admin dashboard (A1) ------------------------------------------------
def _period(d: date, group_by: str) -> str:
    if group_by == "week":
        return (d - timedelta(days=d.weekday())).isoformat()
    if group_by == "month":
        return d.strftime("%Y-%m")
    return d.isoformat()


def _check_range(start: date, end: date, group_by: str):
    if group_by not in ("day", "week", "month"):
        raise ValidationError("Please fix the highlighted fields.", {"group_by": "must be day, week or month"})
    if end < start:
        raise ValidationError("Please fix the highlighted fields.", {"to": "must not be before the start date"})
    if (end - start).days > 800:
        raise ValidationError("Please fix the highlighted fields.", {"from": "range is too long (max 800 days)"})


def sales_report(outlet_id: int, start: date, end: date, group_by: str = "day", item_id: int | None = None) -> dict:
    """A8: quantity and revenue by period; revenue uses the price stored on each record."""
    _check_range(start, end, group_by)
    q = (db.session.query(SalesRecord, MenuItem.name).join(MenuItem, MenuItem.id == SalesRecord.menu_item_id)
         .filter(SalesRecord.outlet_id == outlet_id, SalesRecord.sale_date >= start, SalesRecord.sale_date <= end))
    if item_id:
        q = q.filter(SalesRecord.menu_item_id == item_id)
    by_period, by_item = defaultdict(lambda: [0, Decimal(0)]), defaultdict(lambda: [0, Decimal(0)])
    for s, name in q:
        rev = s.quantity_sold * s.unit_price
        p = by_period[_period(s.sale_date, group_by)]
        p[0] += s.quantity_sold; p[1] += rev
        i = by_item[name]
        i[0] += s.quantity_sold; i[1] += rev
    rows = [{"period": k, "quantity": v[0], "revenue": float(v[1])} for k, v in sorted(by_period.items())]
    items = sorted(({"item": k, "quantity": v[0], "revenue": float(v[1])} for k, v in by_item.items()),
                   key=lambda r: -r["quantity"])
    return {"from": start.isoformat(), "to": end.isoformat(), "group_by": group_by, "rows": rows,
            "totals": {"quantity": sum(r["quantity"] for r in rows), "revenue": round(sum(r["revenue"] for r in rows), 2)},
            "top_items": items[:5], "bottom_items": list(reversed(items[-5:])) if len(items) > 5 else [],
            "data_source": settings_label(outlet_id)}


def settings_label(outlet_id: int):
    from app.services import settings
    return settings.get(outlet_id, "data_source_label") or "Real data"


def waste_report(outlet_id: int, start: date, end: date, group_by: str = "day") -> dict:
    """A11: prepared-food waste and ingredient wastage, reported separately (assumption A6)."""
    _check_range(start, end, group_by)
    periods, items, reasons = defaultdict(lambda: [0, Decimal(0)]), defaultdict(lambda: [0, Decimal(0)]), defaultdict(int)
    q = (db.session.query(FoodWaste, MenuItem.name).join(MenuItem, MenuItem.id == FoodWaste.menu_item_id)
         .filter(FoodWaste.outlet_id == outlet_id, FoodWaste.waste_date >= start, FoodWaste.waste_date <= end))
    for w, name in q:
        val = w.quantity * w.unit_price
        for bucket, key in ((periods, _period(w.waste_date, group_by)), (items, name)):
            bucket[key][0] += w.quantity; bucket[key][1] += val
        reasons[w.reason] += w.quantity
    food = {"rows": [{"period": k, "quantity": v[0], "value": float(v[1])} for k, v in sorted(periods.items())],
            "top_items": sorted(({"item": k, "quantity": v[0], "value": float(v[1])} for k, v in items.items()),
                                key=lambda r: -r["value"])[:5],
            "by_reason": [{"reason": k, "quantity": v} for k, v in sorted(reasons.items())],
            "totals": {"quantity": sum(v[0] for v in periods.values()), "value": float(sum(v[1] for v in periods.values()))}}
    ip, ing_tot, ir = defaultdict(lambda: [Decimal(0), Decimal(0)]), defaultdict(lambda: [Decimal(0), Decimal(0), ""]), defaultdict(lambda: Decimal(0))
    q2 = (db.session.query(StockMovement, Ingredient, StockBatch.unit_cost)
          .join(Ingredient, Ingredient.id == StockMovement.ingredient_id)
          .join(StockBatch, StockBatch.id == StockMovement.batch_id)
          .filter(StockMovement.outlet_id == outlet_id, StockMovement.movement_type == "wastage",
                  StockMovement.movement_date >= start, StockMovement.movement_date <= end))
    for m, ing, cost in q2:
        qty, val = -m.quantity, -m.quantity * (cost or 0)
        p = ip[_period(m.movement_date, group_by)]
        p[0] += qty; p[1] += val
        t = ing_tot[ing.name]
        t[0] += qty; t[1] += val; t[2] = ing.unit
        ir[m.reason or "other"] += qty
    ingredient = {"rows": [{"period": k, "quantity": float(v[0]), "value": float(v[1])} for k, v in sorted(ip.items())],
                  "by_ingredient": sorted(({"ingredient": k, "unit": v[2], "quantity": float(v[0]), "value": float(v[1])}
                                           for k, v in ing_tot.items()), key=lambda r: -r["value"])[:10],
                  "by_reason": [{"reason": k, "quantity": float(v)} for k, v in sorted(ir.items())],
                  "totals": {"value": float(sum(v[1] for v in ip.values()))}}
    return {"from": start.isoformat(), "to": end.isoformat(), "group_by": group_by, "food": food,
            "ingredient": ingredient, "data_source": settings_label(outlet_id)}


def admin_dashboard(outlet_id: int, range_days: int = 7) -> dict:
    """A1: headline numbers for the last 7 or 30 days, all from the same service methods as the detail pages."""
    if range_days not in (7, 30):
        raise ValidationError("Please fix the highlighted fields.", {"range": "must be 7 or 30"})
    day = today()
    start, end = day - timedelta(days=range_days), day - timedelta(days=1)
    sales = sales_report(outlet_id, start, end, "day")
    waste = waste_report(outlet_id, start, end, "day")
    fmap = fs.forecast_map(outlet_id, day, day + timedelta(days=6))
    alerts = alert_service.list_alerts(outlet_id, "admin")
    levels = inv.stock_levels(outlet_id, day)
    recent = (AuditLog.query.filter_by(outlet_id=outlet_id).order_by(AuditLog.id.desc()).limit(10).all())
    last_run = fs.list_runs(outlet_id, 1)
    active = fs.get_active_model(outlet_id)
    return {"range_days": range_days, "from": start.isoformat(), "to": end.isoformat(),
            "sales": {"quantity": sales["totals"]["quantity"], "revenue": sales["totals"]["revenue"]},
            "forecast_next7_total": round(sum(float(v["qty"]) for v in fmap.values()), 1),
            "low_stock_count": sum(1 for r in levels if r["status"] != "ok"),
            "waste": {"quantity": waste["food"]["totals"]["quantity"], "value": waste["food"]["totals"]["value"]},
            "alert_counts": alerts["counts"], "alerts": alerts["rows"][:6],
            "items_without_recipe": [m.name for m in dm.items_without_recipe(outlet_id)],
            "active_model": None if not active else {"label": active.version_label, "algorithm": active.algorithm,
                                                      "beats_baseline": active.beats_baseline},
            "last_run": last_run[0] if last_run else None,
            "recent_activity": [{"time": a.created_at.isoformat() + "Z", "action": a.action, "entity": a.entity_type,
                                 "entity_id": a.entity_id} for a in recent],
            "data_source": settings_label(outlet_id)}
