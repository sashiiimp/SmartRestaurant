"""Preparation quantities, ingredient requirements, reorder suggestions (Recommendation service).
Formulas are specified in ML_PLAN.md Part B and tested against hand calculations (TESTING.md section 4)."""
from datetime import date, timedelta
from decimal import ROUND_CEILING, Decimal

from app.extensions import db
from app.models import PreOrder, PreparationRecord, RecipeLine, Recommendation, SalesRecord
from app.models.base import utcnow
from app.services import audit, settings
from app.services import data_management_service as dm
from app.services import forecasting_service as fs
from app.services import inventory_service as inv
from app.services.errors import NotFoundError, ValidationError
from app.services.validation import Fields
from app.utils.dates import today


def _ceil_div(a: Decimal, b: Decimal) -> int:
    return int((a / b).to_integral_value(rounding=ROUND_CEILING))


# ---- B1: preparation quantity ----------------------------------------------------------------
def compute_recommended(forecast_qty, buffer_pct, preorders: int, batch_size: int) -> int | None:
    """recommended = ceil(max(forecast*(1+buffer/100), preorders) / batch) * batch. None when there is no forecast."""
    if forecast_qty is None:
        return None
    batch = max(int(batch_size or 1), 1)
    base = Decimal(str(forecast_qty)) * (Decimal(1) + Decimal(str(buffer_pct)) / Decimal(100))
    need = max(base, Decimal(int(preorders or 0)))
    if need <= 0:
        return 0
    return _ceil_div(need, Decimal(batch)) * batch


def _preorder_totals(outlet_id: int, day: date) -> dict:
    rows = (db.session.query(PreOrder.menu_item_id, db.func.sum(PreOrder.quantity))
            .filter(PreOrder.outlet_id == outlet_id, PreOrder.target_date == day, PreOrder.status == "confirmed")
            .group_by(PreOrder.menu_item_id).all())
    return {i: int(q) for i, q in rows}


def _day_totals(model, outlet_id: int, day: date, date_col, qty_col) -> dict:
    rows = (db.session.query(model.menu_item_id, db.func.sum(qty_col))
            .filter(model.outlet_id == outlet_id, date_col == day).group_by(model.menu_item_id).all())
    return {i: int(q) for i, q in rows}


def get_prep_plan(outlet_id: int, day: date) -> dict:
    """One row per active menu item, computed live (no writes). Decisions are read from `recommendations`."""
    buffer_pct = settings.get_decimal(outlet_id, "safety_buffer_pct")
    fmap = fs.forecast_map(outlet_id, day, day)
    pre = _preorder_totals(outlet_id, day)
    decisions = {r.menu_item_id: r for r in Recommendation.query.filter_by(outlet_id=outlet_id, target_date=day)}
    prepared = _day_totals(PreparationRecord, outlet_id, day, PreparationRecord.prep_date, PreparationRecord.quantity)
    served = {i: int(q) for i, q in (db.session.query(SalesRecord.menu_item_id, SalesRecord.quantity_sold)
                                     .filter(SalesRecord.outlet_id == outlet_id, SalesRecord.sale_date == day))}
    active = fs.get_active_model(outlet_id)
    rows = []
    for item in dm.list_menu_items(outlet_id, active_only=True):
        f = fmap.get((item.id, day))
        pre_q = pre.get(item.id, 0)
        rec_qty = compute_recommended(f["qty"] if f else None, buffer_pct, pre_q, item.batch_size)
        d = decisions.get(item.id)
        status = d.status if d else ("suggested" if f else "no_forecast")
        rows.append({
            "menu_item_id": item.id, "name": item.name, "batch_size": item.batch_size, "is_available": item.is_available,
            "forecast_qty": float(f["qty"]) if f else None, "forecast_method": f["method"] if f else None,
            "weather_estimated": f["weather_estimated"] if f else False,
            "preorder_qty": pre_q, "buffer_pct": float(buffer_pct), "recommended_qty": rec_qty,
            "status": status, "final_qty": d.final_qty if d else None,
            "override_reason": d.override_reason if d else None,
            "prepared_so_far": prepared.get(item.id, 0), "served_so_far": served.get(item.id),
        })
    return {"date": day.isoformat(), "buffer_pct": float(buffer_pct),
            "model": f"{active.version_label} ({active.algorithm})" if active else None, "items": rows}


def decide(outlet_id: int, data: dict, actor_id: int | None = None) -> dict:
    """Accept or override the recommendation for one item and date (K3). Upserts one row per item and date."""
    f = Fields(data)
    item_id = f.integer("menu_item_id", gt=0)
    day = f.date("date")
    action = f.choice("action", ("accept", "override"))
    f.check()
    if day < today():
        raise ValidationError("Please fix the highlighted fields.", {"date": "cannot decide a plan for a past date"})
    item = dm.get_menu_item(outlet_id, item_id)
    if not item.is_active:
        raise ValidationError("That menu item is not active.", {"menu_item_id": "is not active"})
    buffer_pct = settings.get_decimal(outlet_id, "safety_buffer_pct")
    fc = fs.forecast_map(outlet_id, day, day).get((item.id, day))
    if not fc:
        raise ValidationError("There is no forecast for this item and date yet.", {"date": "No forecast yet"},
                              code="no_forecast")
    pre_q = _preorder_totals(outlet_id, day).get(item.id, 0)
    recommended = compute_recommended(fc["qty"], buffer_pct, pre_q, item.batch_size)
    warnings = []
    if action == "accept":
        final, reason = recommended, None
    else:
        g = Fields(data)
        final = g.integer("final_qty", min=0)
        reason = g.text("reason", max_len=255)
        g.check()
        if final < pre_q:
            warnings.append(f"The quantity is below confirmed pre-orders ({pre_q}).")
    status = "accepted" if action == "accept" else "overridden"
    rec = Recommendation.query.filter_by(outlet_id=outlet_id, menu_item_id=item.id, target_date=day).first()
    if rec is None:
        rec = Recommendation(outlet_id=outlet_id, menu_item_id=item.id, target_date=day)
        db.session.add(rec)
    rec.forecast_id, rec.forecast_qty, rec.buffer_pct = fc["id"], fc["qty"], buffer_pct
    rec.preorder_qty, rec.batch_size, rec.recommended_qty = pre_q, item.batch_size, recommended
    rec.final_qty, rec.status, rec.override_reason, rec.decided_by = final, status, reason, actor_id
    rec.decided_at = utcnow()
    audit.record(outlet_id, actor_id, f"recommendation.{action}", "menu_item", item.id,
                 {"date": day.isoformat(), "recommended": recommended, "final": final})
    db.session.commit()
    return {"menu_item_id": item.id, "date": day.isoformat(), "status": status, "recommended_qty": recommended,
            "final_qty": final, "override_reason": reason, "warnings": warnings}


# ---- B2 / B3: ingredient requirements, ingredient forecast, reorder ------------------------------
ZERO = Decimal("0")


def _recipes(outlet_id: int) -> dict:
    """{menu_item_id: [(ingredient_id, quantity_per_portion)]}"""
    out: dict = {}
    for line in RecipeLine.query.join(RecipeLine.menu_item).filter_by(outlet_id=outlet_id):
        out.setdefault(line.menu_item_id, []).append((line.ingredient_id, line.quantity_per_portion))
    return out


def _plan_quantities(outlet_id: int, day: date) -> tuple[dict, dict, list]:
    """(qty per item, basis per item, items without forecast) using the accepted quantity when a decision exists."""
    qty, basis, no_forecast = {}, {}, []
    for r in get_prep_plan(outlet_id, day)["items"]:
        if r["final_qty"] is not None:
            qty[r["menu_item_id"]], basis[r["menu_item_id"]] = r["final_qty"], "final_qty"
        elif r["recommended_qty"] is not None:
            qty[r["menu_item_id"]], basis[r["menu_item_id"]] = r["recommended_qty"], "recommended_qty"
        else:
            no_forecast.append({"menu_item_id": r["menu_item_id"], "name": r["name"], "reason": "no_forecast"})
    return qty, basis, no_forecast


def _requirements_for(outlet_id: int, day: date, recipes: dict, names: dict) -> tuple[dict, dict, list]:
    qty, basis, cannot = _plan_quantities(outlet_id, day)
    required: dict = {}
    for item_id, q in qty.items():
        if q <= 0:
            continue
        lines = recipes.get(item_id)
        if not lines:
            cannot.append({"menu_item_id": item_id, "name": names[item_id], "reason": "no_recipe"})
            continue
        for ing_id, per in lines:
            required[ing_id] = required.get(ing_id, ZERO) + Decimal(q) * per
    return required, basis, cannot


def get_requirements(outlet_id: int, day: date) -> dict:
    """K9 / S3: required vs usable stock for the day's plan."""
    recipes = _recipes(outlet_id)
    names = {m.id: m.name for m in dm.list_menu_items(outlet_id)}
    required, basis, cannot = _requirements_for(outlet_id, day, recipes, names)
    usable = inv.usable_map(outlet_id, today())
    ings = {i.id: i for i in inv.list_ingredients(outlet_id)}
    rows = []
    for ing_id, req in sorted(required.items(), key=lambda kv: ings[kv[0]].name):
        ing = ings[ing_id]
        have = usable.get(ing_id, ZERO)
        short = max(ZERO, req - have)
        rows.append({"ingredient_id": ing_id, "name": ing.name, "unit": ing.unit, "required": float(req),
                     "usable_stock": float(have), "status": "short" if short > 0 else "sufficient",
                     "short_by": float(short)})
    return {"date": day.isoformat(), "ingredients": rows, "cannot_compute": cannot,
            "basis": {str(k): v for k, v in basis.items()}}


def _daily_needs(outlet_id: int, start: date, days: int) -> tuple[dict, dict, list]:
    """({ingredient_id: [need per day]}, {(day index): cannot list}, unknown item names)."""
    recipes = _recipes(outlet_id)
    names = {m.id: m.name for m in dm.list_menu_items(outlet_id)}
    per_ing: dict = {}
    unknown = {}
    for i in range(days):
        required, _basis, cannot = _requirements_for(outlet_id, start + timedelta(days=i), recipes, names)
        for c in cannot:
            if c["reason"] == "no_recipe":
                unknown[c["menu_item_id"]] = c["name"]
        for ing_id, req in required.items():
            per_ing.setdefault(ing_id, [ZERO] * days)[i] = req
    return per_ing, unknown


def first_shortfall(needs: list, usable: Decimal, start: date) -> tuple[date, Decimal] | None:
    """First day whose cumulative need exceeds usable stock, and by how much."""
    running = ZERO
    for i, n in enumerate(needs):
        running += n
        if running > usable:
            return start + timedelta(days=i), running - usable
    return None


def get_ingredient_forecast(outlet_id: int, start: date, days: int = 7) -> dict:
    """I7: per ingredient per day requirement, days of cover and the first shortfall."""
    per_ing, unknown = _daily_needs(outlet_id, start, days)
    usable = inv.usable_map(outlet_id, today())
    rows = []
    for ing in inv.list_ingredients(outlet_id, active_only=True):
        needs = per_ing.get(ing.id, [ZERO] * days)
        total = sum(needs, ZERO)
        avg = total / days
        have = usable.get(ing.id, ZERO)
        sf = first_shortfall(needs, have, start)
        rows.append({"ingredient_id": ing.id, "name": ing.name, "unit": ing.unit, "usable_stock": float(have),
                     "daily": [float(n) for n in needs], "total_need": float(total),
                     "days_of_cover": None if avg == 0 else round(float(have / avg), 1),
                     "first_shortfall_date": sf[0].isoformat() if sf else None,
                     "short_by": float(sf[1]) if sf else 0.0})
    return {"from": start.isoformat(), "days": days, "ingredients": rows,
            "unknown_items": [{"menu_item_id": k, "name": v} for k, v in unknown.items()]}


def get_reorder_suggestions(outlet_id: int, start: date | None = None) -> list[dict]:
    """I9 / B3: need over the lead time + safety stock - usable - on order, rounded up to pack size."""
    start = start or today()
    horizon = 7
    per_ing, _unknown = _daily_needs(outlet_id, start, horizon)
    usable, on_order = inv.usable_map(outlet_id, today()), inv.on_order_map(outlet_id)
    default_lead = settings.get_int(outlet_id, "default_lead_time_days")
    out = []
    for ing in inv.list_ingredients(outlet_id, active_only=True):
        lead = ing.default_supplier.lead_time_days if ing.default_supplier else default_lead
        lead = min(max(lead, 1), horizon)
        needs = per_ing.get(ing.id, [ZERO] * horizon)
        need_l = sum(needs[:lead], ZERO)
        have, ordered = usable.get(ing.id, ZERO), on_order.get(ing.id, ZERO)
        raw = need_l + ing.min_stock - have - ordered
        if raw <= 0:
            continue
        pack = ing.pack_size
        suggested = max(_ceil_div(raw, pack) * pack, _ceil_div(ing.reorder_qty, pack) * pack)
        out.append({"ingredient_id": ing.id, "name": ing.name, "unit": ing.unit,
                    "supplier": ing.default_supplier.name if ing.default_supplier else None,
                    "supplier_id": ing.default_supplier_id,
                    "lead_time_days": lead, "need_over_lead_time": float(need_l), "safety_stock": float(ing.min_stock),
                    "usable_stock": float(have), "on_order": float(ordered), "raw_qty": float(raw),
                    "pack_size": float(pack), "min_order_qty": float(ing.reorder_qty),
                    "suggested_qty": float(suggested)})
    out.sort(key=lambda r: r["name"])
    return out
