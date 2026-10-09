"""Read-only aggregates for dashboards and reports (Dashboard service). Built up slice by slice."""
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal

from app.extensions import db
from app.models import (AuditLog, FoodUsage, FoodWaste, Holiday, Ingredient, MenuItem, PreparationRecord, Promotion, SalesRecord,
                        StockBatch, StockMovement)
from app.services import alert_service
from app.services import data_management_service as dm
from app.services import forecasting_service as fs
from app.services import inventory_service as inv
from app.services import recommendation_service as rec
from app.models.inventory import MOVEMENT_TYPES
from app.models.kitchen import FOOD_USAGE_TYPES
from app.services.errors import ValidationError
from app.utils.dates import today


def kitchen_daily_summary(outlet_id: int, day: date) -> dict:
    """Per item: forecast, recommended, final, prepared, served, wasted, other use and what is unaccounted
    (S6, K1, K5-K7, K14)."""
    plan = rec.get_prep_plan(outlet_id, day)
    waste = {i: int(q) for i, q in db.session.query(FoodWaste.menu_item_id, db.func.sum(FoodWaste.quantity)).filter(
        FoodWaste.outlet_id == outlet_id, FoodWaste.waste_date == day).group_by(FoodWaste.menu_item_id)}
    other = {i: int(q) for i, q in db.session.query(FoodUsage.menu_item_id, db.func.sum(FoodUsage.quantity)).filter(
        FoodUsage.outlet_id == outlet_id, FoodUsage.usage_date == day).group_by(FoodUsage.menu_item_id)}
    rows = []
    for r in plan["items"]:
        flags = []
        if r["served_so_far"] is not None and r["served_so_far"] > r["prepared_so_far"]:
            flags.append("served_exceeds_prepared")
        wasted, used_other = waste.get(r["menu_item_id"], 0), other.get(r["menu_item_id"], 0)
        if wasted > r["prepared_so_far"]:
            flags.append("waste_exceeds_prepared")
        unaccounted = None if r["served_so_far"] is None else r["prepared_so_far"] - r["served_so_far"] - wasted - used_other
        rows.append({"menu_item_id": r["menu_item_id"], "name": r["name"], "forecast_qty": r["forecast_qty"],
                     "recommended_qty": r["recommended_qty"], "final_qty": r["final_qty"], "status": r["status"],
                     "prep_status": r["prep_status"], "prepared": r["prepared_so_far"], "served": r["served_so_far"], "wasted": wasted,
                     "other_use": used_other, "unaccounted": unaccounted, "flags": flags,
                     "is_available": r["is_available"]})
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
                      "items_planned": sum(1 for r in rows if r["prep_status"]),
                      "items_done": sum(1 for r in rows if r["prep_status"] == "done"),
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
            "expiring": inv.list_batches(outlet_id, expiring_within_days=3)[:10],
            "pending_requests": inv.pending_request_count(outlet_id)}


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


def food_usage_report(outlet_id: int, start: date, end: date) -> dict:
    """K14 / A11: other food use (staff meals, complimentary, samples, other) in a period, by type and by item."""
    _check_range(start, end, "day")
    q = (db.session.query(FoodUsage.usage_type, MenuItem.name, db.func.sum(FoodUsage.quantity))
         .join(MenuItem, MenuItem.id == FoodUsage.menu_item_id)
         .filter(FoodUsage.outlet_id == outlet_id, FoodUsage.usage_date >= start, FoodUsage.usage_date <= end)
         .group_by(FoodUsage.usage_type, MenuItem.name))
    by_type = {t: 0 for t in FOOD_USAGE_TYPES}
    by_item: dict = {}
    for usage_type, name, qty in q:
        by_type[usage_type] += int(qty)
        row = by_item.setdefault(name, {"item": name, **{t: 0 for t in FOOD_USAGE_TYPES}, "total": 0})
        row[usage_type] += int(qty)
        row["total"] += int(qty)
    return {"from": start.isoformat(), "to": end.isoformat(), "by_type": by_type, "total": sum(by_type.values()),
            "by_item": sorted(by_item.values(), key=lambda r: (-r["total"], r["item"])),
            "data_source": settings_label(outlet_id)}


# ---- inventory reports (A13) -------------------------------------------------------------------------------
MOVEMENT_LIMIT_ON_SCREEN = 500


def stock_levels_report(outlet_id: int) -> dict:
    """Snapshot of every ingredient today: the same rows as the inventory pages (A10)."""
    rows = inv.stock_levels(outlet_id, today())
    return {"as_of": today().isoformat(), "rows": rows}


def inventory_trend(outlet_id: int, ingredient_id: int, start: date, end: date) -> dict:
    """Stock of one ingredient day by day, rebuilt from the immutable movements: opening balance, the day's movements
    by type (signed), and the closing on-hand quantity."""
    _check_range(start, end, "day")
    if not ingredient_id:
        raise ValidationError("Please fix the highlighted fields.", {"ingredient_id": "is required"})
    ing = inv.get_ingredient(outlet_id, ingredient_id)
    base = StockMovement.query.filter(StockMovement.outlet_id == outlet_id, StockMovement.ingredient_id == ing.id)
    opening = base.with_entities(db.func.coalesce(db.func.sum(StockMovement.quantity), 0)).filter(
        StockMovement.movement_date < start).scalar()
    per_day: dict = defaultdict(lambda: defaultdict(lambda: Decimal(0)))
    for d, t, q in base.with_entities(StockMovement.movement_date, StockMovement.movement_type,
                                      db.func.sum(StockMovement.quantity)).filter(
            StockMovement.movement_date >= start, StockMovement.movement_date <= end).group_by(
            StockMovement.movement_date, StockMovement.movement_type):
        per_day[d][t] += q
    running, rows = Decimal(opening), []
    d = start
    while d <= end:
        day = per_day.get(d, {})
        running += sum(day.values(), Decimal(0))
        rows.append({"date": d.isoformat(), **{t: float(day.get(t, 0)) for t in ("stock_in", "stock_out", "wastage", "adjustment")},
                     "closing": float(running)})
        d += timedelta(days=1)
    return {"ingredient_id": ing.id, "ingredient": ing.name, "unit": ing.unit, "from": start.isoformat(), "to": end.isoformat(),
            "opening": float(opening), "closing": float(running), "rows": rows}


def movement_report(outlet_id: int, start: date, end: date, ingredient_id: int | None = None, mtype: str | None = None,
                    limit: int | None = MOVEMENT_LIMIT_ON_SCREEN) -> dict:
    """Stock movements in a period (A13). limit=None returns every row (used by the CSV export)."""
    _check_range(start, end, "day")
    if mtype and mtype not in MOVEMENT_TYPES:
        raise ValidationError("Please fix the highlighted fields.", {"type": "unknown movement type"})
    q = (db.session.query(StockMovement, Ingredient).join(Ingredient, Ingredient.id == StockMovement.ingredient_id)
         .filter(StockMovement.outlet_id == outlet_id, StockMovement.movement_date >= start, StockMovement.movement_date <= end))
    if ingredient_id:
        q = q.filter(StockMovement.ingredient_id == ingredient_id)
    if mtype:
        q = q.filter(StockMovement.movement_type == mtype)
    total = q.count()
    q = q.order_by(StockMovement.movement_date.desc(), StockMovement.id.desc())
    if limit:
        q = q.limit(limit)
    rows = [{"date": m.movement_date.isoformat(), "ingredient": i.name, "unit": i.unit, "type": m.movement_type,
             "quantity": float(m.quantity), "reason": m.reason, "note": m.note, "reference": (f"{m.reference_type} #{m.reference_id}" if m.reference_type else None)}
            for m, i in q.all()]
    return {"from": start.isoformat(), "to": end.isoformat(), "total": total, "shown": len(rows), "rows": rows}


# ---- analytics (A12) --------------------------------------------------------------------------------------------
WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
MIN_DAYS_FOR_COMPARISON = 3     # fewer days in a group than this are shown but flagged as too few to compare


def _avg(values: list) -> float | None:
    return round(sum(values) / len(values), 1) if values else None


def analytics(outlet_id: int, start: date, end: date) -> dict:
    """Descriptive analytics over a period, every figure a plain average or ratio of recorded data (no modelling):
    demand by weekday, ordinary days against holiday and promotion days, forecast error over time, waste rate over time.
    Differences between day groups describe the data; they do not prove that a holiday or a promotion caused them."""
    _check_range(start, end, "day")
    day_total = {d: int(q) for d, q in db.session.query(SalesRecord.sale_date, db.func.sum(SalesRecord.quantity_sold)).filter(
        SalesRecord.outlet_id == outlet_id, SalesRecord.sale_date >= start, SalesRecord.sale_date <= end).group_by(SalesRecord.sale_date)}

    by_weekday = [[] for _ in range(7)]
    for d, q in day_total.items():
        by_weekday[d.weekday()].append(q)
    weekday = [{"weekday": WEEKDAYS[i], "days": len(v), "average": _avg(v)} for i, v in enumerate(by_weekday)]

    types_by_day: dict = defaultdict(set)
    for h in Holiday.query.filter(Holiday.outlet_id == outlet_id, Holiday.holiday_date >= start, Holiday.holiday_date <= end):
        types_by_day[h.holiday_date].add(h.holiday_type)
    calendar = []
    for label, kinds in (("Public holiday", {"public"}), ("Poya day", {"poya"}), ("School holiday", {"school"})):
        vals = [q for d, q in day_total.items() if types_by_day.get(d, set()) & kinds]
        calendar.append({"group": label, "days": len(vals), "average": _avg(vals)})
    ordinary = [q for d, q in day_total.items() if not types_by_day.get(d, set()) & {"public", "poya", "school"}]
    calendar.append({"group": "Ordinary day", "days": len(ordinary), "average": _avg(ordinary)})

    promo_days: set = set()
    for p in Promotion.query.filter(Promotion.outlet_id == outlet_id, Promotion.is_active.is_(True),
                                    Promotion.end_date >= start, Promotion.start_date <= end):
        d = max(p.start_date, start)
        while d <= min(p.end_date, end):
            promo_days.add(d)
            d += timedelta(days=1)
    on = [q for d, q in day_total.items() if d in promo_days]
    off = [q for d, q in day_total.items() if d not in promo_days]
    promotion = [{"group": "Promotion running", "days": len(on), "average": _avg(on)},
                 {"group": "No promotion", "days": len(off), "average": _avg(off)}]

    acc = fs.accuracy(outlet_id, start, end)
    prepared = {d: int(q) for d, q in db.session.query(PreparationRecord.prep_date, db.func.sum(PreparationRecord.quantity)).filter(
        PreparationRecord.outlet_id == outlet_id, PreparationRecord.prep_date >= start, PreparationRecord.prep_date <= end).group_by(PreparationRecord.prep_date)}
    wasted = {d: int(q) for d, q in db.session.query(FoodWaste.waste_date, db.func.sum(FoodWaste.quantity)).filter(
        FoodWaste.outlet_id == outlet_id, FoodWaste.waste_date >= start, FoodWaste.waste_date <= end).group_by(FoodWaste.waste_date)}
    waste = [{"date": d.isoformat(), "prepared": prepared[d], "wasted": wasted.get(d, 0),
              "rate": round(wasted.get(d, 0) / prepared[d] * 100, 1)} for d in sorted(prepared)]
    return {"from": start.isoformat(), "to": end.isoformat(), "data_source": settings_label(outlet_id),
            "days_with_sales": len(day_total), "min_days_for_comparison": MIN_DAYS_FOR_COMPARISON,
            "weekday": weekday, "calendar": calendar, "promotion": promotion,
            "forecast_error": acc["error_series"], "forecast_pairs": acc["pairs"], "waste": waste}
