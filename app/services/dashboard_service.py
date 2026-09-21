"""Read-only aggregates for dashboards and reports (Dashboard service). Built up slice by slice."""
from datetime import date

from app.extensions import db
from app.models import FoodWaste
from app.services import alert_service
from app.services import inventory_service as inv
from app.services import recommendation_service as rec
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
