"""Read-only aggregates for dashboards and reports (Dashboard service). Built up slice by slice."""
from datetime import date

from app.extensions import db
from app.models import FoodWaste, PreparationRecord, SalesRecord
from app.services import recommendation_service as rec


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
