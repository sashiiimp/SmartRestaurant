"""Read-only aggregates for dashboards and reports (Dashboard service). Built up slice by slice."""
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal

from app.extensions import db
from app.models import (Alert, AuditLog, FoodUsage, FoodWaste, ForecastRun, Holiday, Ingredient, MenuItem, PreparationRecord,
                        Promotion, Recommendation, SalesRecord, StockBatch, StockMovement, User)
from app.services import alert_service
from app.services import data_management_service as dm
from app.services import forecasting_service as fs
from app.services import inventory_service as inv
from app.services import kitchen_service as kit
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
    collected = kit.collected_pre_orders(outlet_id, day)      # handed-over pre-orders: part of the served total
    rows = []
    for r in plan["items"]:
        flags = []
        if r["served_so_far"] is not None and r["served_so_far"] > r["prepared_so_far"]:
            flags.append("served_exceeds_prepared")
        wasted, used_other = waste.get(r["menu_item_id"], 0), other.get(r["menu_item_id"], 0)
        if wasted > r["prepared_so_far"]:
            flags.append("waste_exceeds_prepared")
        pre_done = collected.get(r["menu_item_id"], 0)
        if r["served_so_far"] is not None and r["served_so_far"] < pre_done:
            flags.append("served_below_preorders")
        unaccounted = None if r["served_so_far"] is None else r["prepared_so_far"] - r["served_so_far"] - wasted - used_other
        rows.append({"menu_item_id": r["menu_item_id"], "name": r["name"], "forecast_qty": r["forecast_qty"],
                     "recommended_qty": r["recommended_qty"], "final_qty": r["final_qty"], "status": r["status"],
                     "prep_status": r["prep_status"], "prepared": r["prepared_so_far"], "served": r["served_so_far"], "wasted": wasted,
                     "other_use": used_other, "unaccounted": unaccounted, "flags": flags, "preorders_collected": pre_done,
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
    return {"date": day.isoformat(), "day": _kitchen_day(outlet_id, day, rows),
            "tiles": {"planned_total": planned, "prepared_total": sum(r["prepared"] for r in rows),
                      "items_planned": sum(1 for r in rows if r["prep_status"]),
                      "items_done": sum(1 for r in rows if r["prep_status"] == "done"),
                      "shortage_count": len(shorts)},
            "plan": rows, "shortages": shorts, "cannot_compute": reqs["cannot_compute"], "alerts": alerts["rows"][:8]}


def _kitchen_day(outlet_id: int, day: date, rows: list[dict]) -> dict:
    """The day at a glance for the kitchen dashboard, from the same rows as the plan table: the forecast, how many
    items still wait for a decision, what was prepared, served and wasted, and the day's pre-orders. Served is None
    until something is recorded, so "not recorded yet" is never shown as 0 sold."""
    forecast = [r for r in rows if r["status"] != "no_forecast"]
    served = [r["served"] for r in rows if r["served"] is not None]
    pre = [p for p in kit.list_pre_orders(outlet_id, day, day) if p["status"] != "cancelled"]
    return {"forecast_total": round(sum(float(r["forecast_qty"] or 0) for r in forecast), 1),
            "items_forecast": len(forecast), "items_total": len(rows),
            "undecided": sum(1 for r in forecast if r["status"] not in ("accepted", "overridden")),
            "prepared_total": sum(r["prepared"] for r in rows),
            "served_total": sum(served) if served else None,
            "wasted_total": sum(r["wasted"] for r in rows),
            "pre_orders": {"rows": pre, "pending": sum(1 for p in pre if p["status"] == "pending"),
                           "portions": sum(p["quantity"] for p in pre if p["status"] in ("confirmed", "completed"))}}


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
    reorder = rec.get_reorder_suggestions(outlet_id, day)
    expiring = inv.list_batches(outlet_id, expiring_within_days=3)
    open_requests = inv.list_stock_requests(outlet_id, "pending") + inv.list_stock_requests(outlet_id, "approved")
    pos = inv.list_purchase_orders(outlet_id)
    return {"date": day.isoformat(), "counts": counts, "alerts": alerts["rows"][:8], "alert_counts": alerts["counts"],
            "reorder": reorder[:5], "need_vs_stock": need_vs_stock,
            "expiring": expiring[:10],
            "pending_requests": inv.pending_request_count(outlet_id),
            # full counts behind the shortened lists above, so a figure never stops at the list length
            "totals": {"reorder": len(reorder),
                       "at_risk": sum(1 for r in forecast["ingredients"] if r["total_need"] > r["usable_stock"]),
                       "expired_batches": sum(1 for b in expiring if b["expired"]),
                       "expiring_batches": sum(1 for b in expiring if not b["expired"]),
                       "approved_requests": sum(1 for r in open_requests if r["status"] == "approved"),
                       "po_draft": sum(1 for p in pos if p["status"] == "draft"),
                       "po_awaiting": sum(1 for p in pos if p["status"] in ("sent", "partially_received"))},
            "requests": open_requests[:5]}


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
    food["by_item"] = _waste_by_item(outlet_id, start, end)
    return {"from": start.isoformat(), "to": end.isoformat(), "group_by": group_by, "food": food,
            "ingredient": ingredient, "data_source": settings_label(outlet_id)}


def _waste_by_item(outlet_id: int, start: date, end: date) -> list[dict]:
    """Per menu item over the period: planned (accepted or overridden plans only), prepared, sold, wasted, the waste
    rate (wasted / prepared x 100) and, above the waste-risk limit, a suggestion. The suggestion is advice for the
    person deciding the plan; it never changes a forecast or a stored plan."""
    from app.services import settings
    limit = settings.get_decimal(outlet_id, "waste_risk_threshold_pct")

    def per_item(model, qty_col, date_col):
        return {i: int(q) for i, q in db.session.query(model.menu_item_id, db.func.sum(qty_col)).filter(
            model.outlet_id == outlet_id, date_col >= start, date_col <= end).group_by(model.menu_item_id)}
    prepared = per_item(PreparationRecord, PreparationRecord.quantity, PreparationRecord.prep_date)
    sold = per_item(SalesRecord, SalesRecord.quantity_sold, SalesRecord.sale_date)
    wasted = per_item(FoodWaste, FoodWaste.quantity, FoodWaste.waste_date)
    planned = per_item(Recommendation, Recommendation.final_qty, Recommendation.target_date)
    prep_days = {i: int(n) for i, n in db.session.query(PreparationRecord.menu_item_id,
                                                         db.func.count(db.distinct(PreparationRecord.prep_date))).filter(
        PreparationRecord.outlet_id == outlet_id, PreparationRecord.prep_date >= start,
        PreparationRecord.prep_date <= end).group_by(PreparationRecord.menu_item_id)}
    rows = []
    for item in MenuItem.query.filter_by(outlet_id=outlet_id).order_by(MenuItem.name):
        p, w = prepared.get(item.id, 0), wasted.get(item.id, 0)
        if not (p or w or sold.get(item.id)):
            continue
        rate = round(w * 100 / p, 1) if p else None
        tip = None
        if rate is not None and rate > limit and prep_days.get(item.id):
            per_day = round(w / prep_days[item.id], 1)
            tip = (f"About {per_day:g} portions a day were wasted. Consider planning that many fewer, or override the "
                   f"recommendation on days you expect lower demand.")
        rows.append({"item": item.name, "planned": planned.get(item.id), "prepared": p, "sold": sold.get(item.id, 0),
                     "wasted": w, "waste_pct": rate, "days_prepared": prep_days.get(item.id, 0), "suggestion": tip})
    return sorted(rows, key=lambda r: -(r["waste_pct"] or 0))


def admin_dashboard(outlet_id: int, range_days: int = 7) -> dict:
    """A1: headline numbers for the last 7 or 30 days, all from the same service methods as the detail pages.
    The period ends yesterday, because today's sales and waste are still being recorded. Historical figures (sales,
    waste, production) and predicted figures (forecasts for today and the next 6 days) are kept in separate keys."""
    if range_days not in (7, 30):
        raise ValidationError("Please fix the highlighted fields.", {"range": "must be 7 or 30"})
    day = today()
    start, end = day - timedelta(days=range_days), day - timedelta(days=1)
    sales = sales_report(outlet_id, start, end, "day")
    waste = waste_report(outlet_id, start, end, "day")
    fmap = fs.forecast_map(outlet_id, day, day + timedelta(days=6))
    alerts = alert_service.list_alerts(outlet_id, "admin")
    levels = inv.stock_levels(outlet_id, day)
    last_run = fs.list_runs(outlet_id, 1)
    active = fs.get_active_model(outlet_id)
    # the 7-day total is the sum of the displayed day values, so the card total and the chart always agree
    fdays = _forecast_days(fmap, day)
    from app.services import settings
    return {"range_days": range_days, "from": start.isoformat(), "to": end.isoformat(),
            "sales": {"quantity": sales["totals"]["quantity"], "revenue": sales["totals"]["revenue"]},
            "forecast_next7": fdays,
            "forecast_next7_total": round(sum(f["qty"] for f in fdays if f["qty"] is not None), 1),
            "menu_items_active": MenuItem.query.filter_by(outlet_id=outlet_id, is_active=True).count(),
            "stock": _stock_summary(levels),
            "inventory_alerts": _inventory_alerts(outlet_id, levels, day),
            "pre_orders": kit.upcoming_pre_orders(outlet_id, 7),
            "waste": {"quantity": waste["food"]["totals"]["quantity"], "value": waste["food"]["totals"]["value"]},
            "waste_rate": _waste_rate(outlet_id, start, end, waste["food"]["totals"]["quantity"]),
            "waste_threshold_pct": float(settings.get_decimal(outlet_id, "waste_risk_threshold_pct")),
            "coverage": _coverage(outlet_id, start, end),
            "alert_counts": alerts["counts"], "alerts": alerts["rows"][:6],
            "items_without_recipe": [m.name for m in dm.items_without_recipe(outlet_id)],
            "active_model": None if not active else {"label": active.version_label, "algorithm": active.algorithm,
                                                      "beats_baseline": active.beats_baseline},
            "last_run": last_run[0] if last_run else None,
            "recent_activity": recent_activity(outlet_id),
            # actual sales against the forecast made before each day (the Forecast accuracy report, same period)
            "accuracy": _recent_accuracy(outlet_id, start, end),
            "data_source": settings_label(outlet_id)}


def _recent_accuracy(outlet_id: int, start: date, end: date) -> dict | None:
    acc = fs.accuracy(outlet_id, start, end)
    if not acc["overall"]:
        return None
    o = acc["overall"]
    return {"mae": o.get("mae"), "wape": o.get("wape"), "bias": o.get("bias"), "pairs": acc["pairs"],
            "days": len(acc["series"]), "run_types": acc.get("run_types", [])}


ALERT_INGREDIENT_TYPES = ("low_stock", "critical_stock", "projected_stockout", "expiry_warning", "manual_shortage")


def _inventory_alerts(outlet_id: int, levels: list[dict], day: date) -> list[dict]:
    """One row per ingredient that needs attention, putting together what is true NOW (usable stock against the
    reorder level and minimum), what the FORECAST says (the first day the plan needs more than usable stock) and
    EXPIRY (expired or soon-expiring batches). Built from the open alerts that alert_service has just evaluated, so it
    always agrees with the alert list; it adds no rule of its own."""
    by_ing: dict = {}
    batch_ing = {}
    alerts = Alert.query.filter(Alert.outlet_id == outlet_id, Alert.status.in_(("open", "acknowledged")),
                                Alert.alert_type.in_(ALERT_INGREDIENT_TYPES)).all()
    batch_ids = [a.entity_id for a in alerts if a.entity_type == "batch"]
    if batch_ids:
        batch_ing = {b.id: b for b in StockBatch.query.filter(StockBatch.id.in_(batch_ids))}
    for a in alerts:
        if a.entity_type == "batch":
            b = batch_ing.get(a.entity_id)
            if b is None:
                continue
            row = by_ing.setdefault(b.ingredient_id, {"alerts": [], "expiry": []})
            row["expiry"].append({"batch_no": b.batch_no, "qty": float(b.qty_remaining), "date": b.expiry_date.isoformat(),
                                  "expired": b.expiry_date < day})
        else:
            row = by_ing.setdefault(a.entity_id, {"alerts": [], "expiry": []})
            if a.alert_type == "projected_stockout":
                row["forecast"] = {"date": a.target_date.isoformat() if a.target_date else None,
                                   "short_by": (a.details or {}).get("short_by")}
            if a.alert_type == "manual_shortage":
                row["reported"] = True
        row["alerts"].append({"id": a.id, "severity": a.severity, "status": a.status})
    rows = []
    for lv in levels:
        extra = by_ing.get(lv["id"])
        if lv["status"] == "ok" and not lv["is_critical"] and not extra:
            continue
        extra = extra or {"alerts": [], "expiry": []}
        sev = "critical" if any(x["severity"] == "critical" for x in extra["alerts"]) or lv["status"] == "out" else "warning"
        rows.append({"id": lv["id"], "name": lv["name"], "unit": lv["unit"], "usable": lv["usable"],
                     "reorder_level": lv["reorder_level"], "min_stock": lv["min_stock"], "status": lv["status"],
                     "is_critical": lv["is_critical"], "forecast": extra.get("forecast"),
                     "expiry": sorted(extra["expiry"], key=lambda e: e["date"]), "reported": extra.get("reported", False),
                     "severity": sev, "alert_ids": [x["id"] for x in extra["alerts"]],
                     "all_acknowledged": bool(extra["alerts"]) and all(x["status"] == "acknowledged" for x in extra["alerts"])})
    order = {"out": 0, "low": 1, "ok": 2}
    return sorted(rows, key=lambda r: (r["severity"] != "critical", order[r["status"]], r["name"]))


def recent_activity(outlet_id: int, limit: int = 10) -> list[dict]:
    """The latest stored events, newest first: audit log entries, forecast runs (not the bulk backfill) and stock
    movements entered by a user. Nothing is generated; each row points at a stored record. Names are looked up
    here so the page can write a plain sentence (admin_dashboard.js)."""
    users = {u.id: (u.full_name or u.username) for u in User.query.filter_by(outlet_id=outlet_id)}
    items = {m.id: m.name for m in MenuItem.query.filter_by(outlet_id=outlet_id)}
    ings = {i.id: (i.name, i.unit) for i in Ingredient.query.filter_by(outlet_id=outlet_id)}
    out = []
    for a in AuditLog.query.filter_by(outlet_id=outlet_id).order_by(AuditLog.id.desc()).limit(limit):
        eid = int(a.entity_id) if a.entity_id and str(a.entity_id).isdigit() else None
        name = None
        if a.entity_type == "menu_item":
            name = items.get(eid)
        elif a.entity_type == "ingredient":
            name = ings.get(eid, (None, None))[0]
        out.append({"time": a.created_at.isoformat() + "Z", "kind": "audit", "action": a.action, "entity": a.entity_type,
                    "entity_id": a.entity_id, "name": name, "detail": a.detail or {}, "user": users.get(a.user_id)})
    for r in (ForecastRun.query.filter(ForecastRun.outlet_id == outlet_id, ForecastRun.trigger_type != "backfill",
                                       ForecastRun.as_of_date <= today())
              .order_by(ForecastRun.id.desc()).limit(limit)):
        out.append({"time": r.started_at.isoformat() + "Z", "kind": "forecast_run", "action": "forecast.run",
                    "entity": "forecast_run", "entity_id": r.id, "name": None, "user": users.get(r.created_by),
                    "detail": {"from": r.as_of_date.isoformat(),
                               "to": (r.as_of_date + timedelta(days=r.horizon_days - 1)).isoformat(),
                               "days": r.horizon_days, "items": r.items_forecast, "status": r.status,
                               "trigger": r.trigger_type, "model": r.model_version.version_label if r.model_version else None}})
    for m in (StockMovement.query.filter(StockMovement.outlet_id == outlet_id, StockMovement.created_by.isnot(None))
              .order_by(StockMovement.id.desc()).limit(limit)):
        name, unit = ings.get(m.ingredient_id, (None, None))
        out.append({"time": m.created_at.isoformat() + "Z", "kind": "stock", "action": f"stock.{m.movement_type}",
                    "entity": "ingredient", "entity_id": m.ingredient_id, "name": name, "user": users.get(m.created_by),
                    "detail": {"quantity": float(m.quantity), "unit": unit, "reason": m.reason}})
    out.sort(key=lambda e: e["time"], reverse=True)
    return out[:limit]


def _forecast_days(fmap: dict, day: date) -> list[dict]:
    """Predicted portions per day, today and the next 6 days, from the latest stored forecasts. A day with no forecast
    rows has qty None (shown as "no forecast"), never 0, so a missing forecast is not mistaken for zero demand."""
    totals, counts = defaultdict(Decimal), defaultdict(int)
    for (_, d), v in fmap.items():
        totals[d] += v["qty"]
        counts[d] += 1
    days = [day + timedelta(days=i) for i in range(7)]
    return [{"date": d.isoformat(), "qty": round(float(totals[d]), 1) if counts[d] else None, "items": counts[d]}
            for d in days]


def _stock_summary(levels: list[dict]) -> dict:
    """Counts by status and the ingredients that need attention: out of stock first, then lowest usable stock
    relative to the reorder level. Status comes from inventory_service.stock_status (usable, non-expired stock)."""
    at_risk = [r for r in levels if r["status"] != "ok"]
    at_risk.sort(key=lambda r: (r["status"] != "out", r["usable"] / r["reorder_level"] if r["reorder_level"] else 0, r["name"]))
    return {"ingredients": len(levels), "out": sum(1 for r in levels if r["status"] == "out"),
            "low": sum(1 for r in levels if r["status"] == "low"),
            "rows": [{"id": r["id"], "name": r["name"], "unit": r["unit"], "usable": r["usable"], "on_hand": r["on_hand"],
                      "min_stock": r["min_stock"], "reorder_level": r["reorder_level"], "status": r["status"],
                      "is_critical": r["is_critical"]} for r in at_risk]}


def _waste_rate(outlet_id: int, start: date, end: date, wasted: int) -> dict:
    """Food waste rate = portions wasted / portions prepared x 100 over the period (the same ratio as the Analytics
    waste-rate chart and the waste-risk alert). None when nothing was prepared, rather than a misleading 0%."""
    prepared = int(db.session.query(db.func.coalesce(db.func.sum(PreparationRecord.quantity), 0)).filter(
        PreparationRecord.outlet_id == outlet_id, PreparationRecord.prep_date >= start,
        PreparationRecord.prep_date <= end).scalar())
    return {"prepared": prepared, "wasted": wasted, "pct": round(wasted * 100 / prepared, 1) if prepared else None}


def _coverage(outlet_id: int, start: date, end: date) -> dict:
    """How many days of the period have sales records, and the latest sales date overall, so the dashboard can say
    when a period is only partly recorded instead of presenting a short total as a full one."""
    days = db.session.query(db.func.count(db.distinct(SalesRecord.sale_date))).filter(
        SalesRecord.outlet_id == outlet_id, SalesRecord.sale_date >= start, SalesRecord.sale_date <= end).scalar()
    latest = db.session.query(db.func.max(SalesRecord.sale_date)).filter(
        SalesRecord.outlet_id == outlet_id, SalesRecord.sale_date <= end).scalar()
    return {"days": (end - start).days + 1, "days_with_sales": int(days or 0),
            "latest_sales_date": latest.isoformat() if latest else None}


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
