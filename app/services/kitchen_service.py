"""Prepared / served / waste recording (Kitchen Operations service, ARCH section 3)."""
from datetime import datetime, timedelta
from decimal import Decimal

from app.extensions import db
from app.models import (FoodUsage, FoodWaste, Ingredient, IngredientUsage, MenuItem, Order, PreOrder, PreparationRecord,
                        RecipeLine, Recommendation, SalesRecord, User)
from app.models.base import utcnow
from app.models.kitchen import FOOD_USAGE_TYPES, WASTE_REASONS
from app.models.sales import ORDER_STATUSES, PREORDER_STATUSES
from app.services import audit
from app.services import data_management_service as dm
from app.services import inventory_service as inv
from app.services.errors import ConflictError, NotFoundError, ValidationError
from app.services.validation import Fields
from app.utils.dates import today


def bulk_load_history(outlet_id: int, prep_rows: list[dict], waste_rows: list[dict], source: str = "synthetic") -> dict:
    """Load historical preparation and waste rows in bulk (used by the synthetic-data generator only)."""
    if prep_rows:
        db.session.bulk_insert_mappings(PreparationRecord, [{"outlet_id": outlet_id, **r} for r in prep_rows])
    if waste_rows:
        db.session.bulk_insert_mappings(FoodWaste, [{"outlet_id": outlet_id, **r} for r in waste_rows])
    audit.record(outlet_id, None, "history.bulk_load", "kitchen", None,
                 {"prepared": len(prep_rows), "waste": len(waste_rows), "source": source})
    db.session.commit()
    return {"prepared": len(prep_rows), "waste": len(waste_rows)}


def _prepared_total(outlet_id: int, item_id: int, day) -> int:
    return int(db.session.query(db.func.coalesce(db.func.sum(PreparationRecord.quantity), 0)).filter(
        PreparationRecord.outlet_id == outlet_id, PreparationRecord.menu_item_id == item_id,
        PreparationRecord.prep_date == day).scalar())


def _waste_total(outlet_id: int, item_id: int, day) -> int:
    return int(db.session.query(db.func.coalesce(db.func.sum(FoodWaste.quantity), 0)).filter(
        FoodWaste.outlet_id == outlet_id, FoodWaste.menu_item_id == item_id, FoodWaste.waste_date == day).scalar())


def collected_pre_orders(outlet_id: int, day) -> dict:
    """{menu_item_id: portions} of the day's completed (handed over) pre-orders. They record no sale, so the served
    total for the day must include them; the forecast learns total demand from served totals (ML_PLAN.md B1)."""
    rows = (db.session.query(PreOrder.menu_item_id, db.func.sum(PreOrder.quantity))
            .filter(PreOrder.outlet_id == outlet_id, PreOrder.target_date == day, PreOrder.status == "completed")
            .group_by(PreOrder.menu_item_id).all())
    return {i: int(q) for i, q in rows}


def _retry_on_duplicate(fn):
    """Two cooks can add the first portions of an undecided item at the same moment: both accept it automatically and
    the second insert fails on the unique (item, date) plan key. Roll the whole entry back and run it again on a fresh
    snapshot, where the other request's plan exists, so the portions are recorded exactly once and no plan is lost."""
    import functools

    from sqlalchemy.exc import IntegrityError

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        for attempt in range(3):
            try:
                return fn(*args, **kwargs)
            except IntegrityError:
                db.session.rollback()
                if attempt == 2:
                    raise
    return wrapper


@inv._retry_on_conflict
@_retry_on_duplicate
def record_prepared(outlet_id: int, data: dict, actor_id: int | None = None, decide_first=None) -> dict:
    """K5: several entries per item and day are summed (each entry is added to the total, never replaces it).
    decide_first(outlet_id, item, day, actor_id), when given, is called for an item without a plan and may add one in
    this transaction (the API passes recommendation_service.accept_on_first_prepared; the kitchen service does not call
    the recommendation service itself, see test_architecture)."""
    f = Fields(data)
    item_id = f.integer("menu_item_id", gt=0)
    day = f.date("date", not_future=True)
    qty = f.portions("quantity", gt=0)
    f.check()
    item = dm.get_menu_item(outlet_id, item_id)
    db.session.add(PreparationRecord(outlet_id=outlet_id, menu_item_id=item.id, prep_date=day, quantity=qty,
                                     prepared_at=utcnow(), created_by=actor_id))
    # K4: the first prepared quantity starts a planned item; a finished item stays done (the extra entry is a correction).
    # An undecided item (today, active, with a forecast) is accepted at the current recommendation by decide_first.
    plan = Recommendation.query.filter_by(outlet_id=outlet_id, menu_item_id=item.id, target_date=day).first()
    auto = None
    if plan is None:
        if decide_first is not None:
            auto = decide_first(outlet_id, item, day, actor_id)
    elif plan.prep_status == "planned":
        plan.prep_status, plan.prep_started_at = "in_progress", utcnow()
    audit.record(outlet_id, actor_id, "prepared.record", "menu_item", item.id,
                 {"item": item.name, "date": day.isoformat(), "quantity": qty})
    db.session.commit()
    return {"menu_item_id": item.id, "date": day.isoformat(), "added": qty,
            "total_prepared": _prepared_total(outlet_id, item.id, day),
            "auto_accepted": {"final_qty": auto.final_qty} if auto is not None else None}


def record_served(outlet_id: int, data: dict, actor_id: int | None = None) -> dict:
    """K6: end-of-day served quantities. One sales record per item per day (C4); overwriting needs confirmation."""
    f = Fields(data)
    day = f.date("date", not_future=True)
    f.check()
    lines = data.get("lines")
    if not isinstance(lines, list) or not lines:
        raise ValidationError("Please fix the highlighted fields.", {"lines": "add at least one item"})
    confirm = bool(data.get("confirm_overwrite"))
    clean, errors, seen = [], {}, set()
    for i, raw in enumerate(lines):
        lf = Fields(raw if isinstance(raw, dict) else {})
        item_id = lf.integer("menu_item_id", gt=0)
        qty = lf.portions("quantity", min=0)
        if lf.errors:
            errors[f"lines[{i}]"] = "; ".join(f"{k} {m}" for k, m in lf.errors.items())
            continue
        if item_id in seen:
            errors[f"lines[{i}]"] = "item appears twice"
            continue
        seen.add(item_id)
        clean.append((dm.get_menu_item(outlet_id, item_id), qty))
    if errors:
        raise ValidationError("Please fix the highlighted fields.", errors)

    existing = {s.menu_item_id: s for s in SalesRecord.query.filter(
        SalesRecord.outlet_id == outlet_id, SalesRecord.sale_date == day)}
    conflicts = [{"menu_item_id": item.id, "item": item.name, "existing": existing[item.id].quantity_sold}
                 for item, qty in clean if item.id in existing and existing[item.id].quantity_sold != qty]
    if conflicts and not confirm:
        raise ConflictError("A different quantity is already recorded for some items on this date.",
                            code="duplicate_record", extra={"conflicts": conflicts})
    warnings, saved = [], 0
    collected = collected_pre_orders(outlet_id, day)
    for item, qty in clean:
        cur = existing.get(item.id)
        if cur is None:
            db.session.add(SalesRecord(outlet_id=outlet_id, menu_item_id=item.id, sale_date=day, quantity_sold=qty,
                                       unit_price=item.price, source="kitchen", created_by=actor_id))
            saved += 1
        elif cur.quantity_sold != qty:
            cur.quantity_sold, cur.source, cur.created_by = qty, "kitchen", actor_id
            saved += 1
        prepared = _prepared_total(outlet_id, item.id, day)
        if qty > prepared:
            warnings.append(f"{item.name}: served ({qty}) is higher than prepared ({prepared}). Saved, and flagged for review.")
        if qty < collected.get(item.id, 0):     # a warning only: the figure is saved as entered, nothing is added to it
            warnings.append(f"{item.name}: served ({qty}) is lower than the {collected[item.id]} pre-ordered portions "
                            f"collected today. Served must include collected pre-orders. Saved; please check.")
    audit.record(outlet_id, actor_id, "sales.served", "sales_records", None, {"date": day.isoformat(), "lines": saved})
    db.session.commit()
    return {"date": day.isoformat(), "saved": saved, "warnings": warnings}


def record_waste(outlet_id: int, data: dict, actor_id: int | None = None) -> dict:
    """K7: prepared-food waste. Waste above the prepared total is allowed with a warning."""
    f = Fields(data)
    item_id = f.integer("menu_item_id", gt=0)
    day = f.date("date", not_future=True)
    qty = f.portions("quantity", gt=0)
    reason = f.choice("reason", WASTE_REASONS)
    note = f.text("note", required=False, max_len=255)
    f.check()
    item = dm.get_menu_item(outlet_id, item_id)
    db.session.add(FoodWaste(outlet_id=outlet_id, menu_item_id=item.id, waste_date=day, quantity=qty, reason=reason,
                             unit_price=item.price, note=note, created_by=actor_id))
    audit.record(outlet_id, actor_id, "waste.record", "menu_item", item.id,
                 {"item": item.name, "date": day.isoformat(), "quantity": qty, "reason": reason})
    db.session.commit()
    total, prepared = _waste_total(outlet_id, item.id, day), _prepared_total(outlet_id, item.id, day)
    warnings = []
    if total > prepared:
        warnings.append(f"Waste for {item.name} today ({total}) is higher than prepared ({prepared}).")
    return {"menu_item_id": item.id, "date": day.isoformat(), "added": qty, "total_waste": total, "warnings": warnings}


# ---- pre-orders (K10, Preorder Management) -----------------------------------------------------------
# A customer orders ahead for a given day and pickup time. Status flow:
#   pending -> confirmed -> completed (handed over)      pending or confirmed -> cancelled
#   confirmed -> pending (back on hold)                   completed and cancelled are final
# Confirmed and completed pre-orders are committed demand for their day, so the prep plan counts both
# (recommendation_service._preorder_totals); pending and cancelled ones are ignored. Completing a pre-order records no
# sale: the kitchen's served total for the day already includes the portions handed over, so it is never counted twice.
PREORDER_TRANSITIONS = {"pending": ("confirmed", "cancelled"), "confirmed": ("pending", "completed", "cancelled"),
                        "completed": (), "cancelled": ()}


def pre_order_dict(p: PreOrder, item_name: str) -> dict:
    return {"id": p.id, "menu_item_id": p.menu_item_id, "item": item_name, "target_date": p.target_date.isoformat(),
            "pickup_time": p.pickup_time.strftime("%H:%M") if p.pickup_time else None, "quantity": p.quantity,
            "status": p.status, "customer_name": p.customer_name, "customer_contact": p.customer_contact,
            "customer_note": p.customer_note, "created_at": p.created_at.isoformat() + "Z" if p.created_at else None,
            "completed_at": p.completed_at.isoformat() + "Z" if p.completed_at else None,
            "counts_in_plan": p.status in PLAN_STATUSES}


PLAN_STATUSES = ("confirmed", "completed")


def _decision_warning(outlet_id: int, item_id: int, day) -> list[str]:
    """Editing a pre-order after the manager has already accepted or overridden the plan needs a second look (K10)."""
    if Recommendation.query.filter_by(outlet_id=outlet_id, menu_item_id=item_id, target_date=day).first():
        return ["A decision was already made for this item and date. Open the Prep plan to check the recommendation."]
    return []


def get_pre_order(outlet_id: int, pre_order_id: int) -> PreOrder:
    p = PreOrder.query.filter_by(id=pre_order_id, outlet_id=outlet_id).first()
    if not p:
        raise NotFoundError("Pre-order not found.")
    return p


def pre_order_detail(outlet_id: int, pre_order_id: int) -> dict:
    """One pre-order with who created it, when it was last changed and which status changes are allowed next."""
    p = get_pre_order(outlet_id, pre_order_id)
    item = db.session.get(MenuItem, p.menu_item_id)
    creator = db.session.get(User, p.created_by) if p.created_by else None
    return {**pre_order_dict(p, item.name), "created_by": (creator.full_name or creator.username) if creator else None,
            "updated_at": p.updated_at.isoformat() + "Z" if p.updated_at else None,
            "allowed_status": list(PREORDER_TRANSITIONS[p.status])}


def list_pre_orders(outlet_id: int, start=None, end=None, status: str | None = None, item_id: int | None = None) -> list[dict]:
    q = db.session.query(PreOrder, MenuItem.name).join(MenuItem, MenuItem.id == PreOrder.menu_item_id).filter(
        PreOrder.outlet_id == outlet_id)
    if start:
        q = q.filter(PreOrder.target_date >= start)
    if end:
        q = q.filter(PreOrder.target_date <= end)
    if status:
        if status not in PREORDER_STATUSES:
            raise ValidationError("Please fix the highlighted fields.", {"status": "unknown status"})
        q = q.filter(PreOrder.status == status)
    if item_id:
        q = q.filter(PreOrder.menu_item_id == item_id)
    return [pre_order_dict(p, name) for p, name in
            q.order_by(PreOrder.target_date, PreOrder.pickup_time, PreOrder.id).all()]


def upcoming_pre_orders(outlet_id: int, days: int = 7) -> dict:
    """Confirmed pre-orders from today for `days` days (the admin dashboard card), with portions per item."""
    rows = list_pre_orders(outlet_id, today(), today() + timedelta(days=days - 1), "confirmed")
    by_item: dict = {}
    for r in rows:
        by_item[r["item"]] = by_item.get(r["item"], 0) + r["quantity"]
    return {"from": today().isoformat(), "days": days, "rows": rows, "count": len(rows),
            "portions": sum(r["quantity"] for r in rows),
            "by_item": [{"item": k, "quantity": v} for k, v in sorted(by_item.items(), key=lambda kv: -kv[1])]}


def _customer_fields(f: Fields):
    name = f.text("customer_name", max_len=100)
    contact = f.text("customer_contact", required=False, max_len=60)
    pickup = f.time("pickup_time")
    note = f.text("customer_note", required=False, max_len=255)
    return name, contact, pickup, note


def create_pre_order(outlet_id: int, data: dict, actor_id: int | None = None) -> dict:
    f = Fields(data)
    item_id = f.integer("menu_item_id", gt=0)
    day = f.date("target_date")
    qty = f.portions("quantity", gt=0)
    name, contact, pickup, note = _customer_fields(f)
    status = f.choice("status", ("pending", "confirmed"), default="pending")
    if day and day < today():
        f.error("target_date", "cannot be in the past")
    f.check()
    item = dm.get_menu_item(outlet_id, item_id)
    if not item.is_active:
        raise ValidationError("That menu item is not active.", {"menu_item_id": "is not active"})
    p = PreOrder(outlet_id=outlet_id, menu_item_id=item.id, target_date=day, quantity=qty, status=status,
                 customer_name=name, customer_contact=contact, pickup_time=pickup, customer_note=note, created_by=actor_id)
    db.session.add(p)
    db.session.flush()
    audit.record(outlet_id, actor_id, "preorder.create", "pre_order", p.id,
                 {"item": item.name, "date": day.isoformat(), "quantity": qty, "status": status})
    db.session.commit()
    return {**pre_order_dict(p, item.name), "warnings": _decision_warning(outlet_id, item.id, day) if status == "confirmed" else []}


def update_pre_order(outlet_id: int, pre_order_id: int, data: dict, actor_id: int | None = None) -> dict:
    """Edit the details, or move the status along PREORDER_TRANSITIONS. Completed and cancelled pre-orders are history.
    A pre-order for a past date can only be completed (handed over, recorded late)."""
    p = get_pre_order(outlet_id, pre_order_id)
    if p.status in ("cancelled", "completed"):
        raise ConflictError(f"A {p.status} pre-order cannot be changed.")
    new_status = data.get("status", p.status)
    if new_status != p.status and new_status in PREORDER_STATUSES and new_status not in PREORDER_TRANSITIONS[p.status]:
        raise ConflictError(f"A {p.status} pre-order cannot be marked {new_status}.", code="invalid_transition")
    detail_keys = ("quantity", "target_date", "pickup_time", "customer_name", "customer_contact", "customer_note")
    if p.target_date < today() and not (new_status == "completed" and not any(k in data for k in detail_keys)):
        raise ConflictError("A pre-order for a past date cannot be changed.")
    merged = {"quantity": p.quantity, "target_date": p.target_date, "customer_note": p.customer_note, "status": p.status,
              "customer_name": p.customer_name, "customer_contact": p.customer_contact, "pickup_time": p.pickup_time}
    merged.update({k: data[k] for k in merged if k in data})
    f = Fields(merged)
    qty = f.portions("quantity", gt=0)
    day = f.date("target_date")
    # pre-orders recorded before 13 Oct 2026 have no name or pickup time; they stay editable without one
    name = f.text("customer_name", required=p.customer_name is not None or "customer_name" in data, max_len=100)
    contact = f.text("customer_contact", required=False, max_len=60)
    pickup = f.time("pickup_time", required=p.pickup_time is not None or "pickup_time" in data)
    note = f.text("customer_note", required=False, max_len=255)
    status = f.choice("status", PREORDER_STATUSES)
    if day and day < today() and status != "completed":
        f.error("target_date", "cannot be in the past")
    if status == "completed" and day and day > today():
        f.error("status", "a pre-order can be completed on or after its date")
    f.check()
    before = (p.quantity, p.target_date, p.status)
    old_day, old_status = p.target_date, p.status
    p.quantity, p.target_date, p.customer_note, p.status = qty, day, note, status
    p.customer_name, p.customer_contact, p.pickup_time = name, contact, pickup
    if status == "completed" and old_status != "completed":
        p.completed_at = utcnow()
    action = {"confirmed": "confirm", "cancelled": "cancel", "completed": "complete", "pending": "hold"}.get(status)
    audit.record(outlet_id, actor_id, f"preorder.{action}" if status != old_status else "preorder.update", "pre_order", p.id,
                 {"item": db.session.get(MenuItem, p.menu_item_id).name, "quantity": qty, "date": day.isoformat(),
                  "from": [before[0], before[1].isoformat(), before[2]], "to": [qty, day.isoformat(), status]})
    warnings = []
    # the plan changes when the pre-order starts or stops counting, or when a counted one moves or changes size
    plan_changed = (old_status in PLAN_STATUSES) != (status in PLAN_STATUSES) or (
        status in PLAN_STATUSES and (old_day != day or before[0] != qty))
    if plan_changed:
        warnings = _decision_warning(outlet_id, p.menu_item_id, day)
        if old_day != day:
            warnings += _decision_warning(outlet_id, p.menu_item_id, old_day)
    db.session.commit()
    return {**pre_order_dict(p, db.session.get(MenuItem, p.menu_item_id).name), "warnings": warnings}


# ---- daily orders (K10) -------------------------------------------------------------------------------
# An internal record of the day's food orders: item, quantity, note, status. No prices or payments, and nothing here feeds
# a forecast or a calculation. Only an open order can change; fulfilled and cancelled orders are history.
def order_dict(o: Order, item_name: str) -> dict:
    return {"id": o.id, "menu_item_id": o.menu_item_id, "item": item_name, "order_date": o.order_date.isoformat(),
            "quantity": o.quantity, "status": o.status, "customer_note": o.customer_note}


def get_order(outlet_id: int, order_id: int) -> Order:
    o = Order.query.filter_by(id=order_id, outlet_id=outlet_id).first()
    if not o:
        raise NotFoundError("Order not found.")
    return o


def list_orders(outlet_id: int, start=None, end=None, status: str | None = None, item_id: int | None = None) -> list[dict]:
    q = db.session.query(Order, MenuItem.name).join(MenuItem, MenuItem.id == Order.menu_item_id).filter(Order.outlet_id == outlet_id)
    if start:
        q = q.filter(Order.order_date >= start)
    if end:
        q = q.filter(Order.order_date <= end)
    if status:
        if status not in ORDER_STATUSES:
            raise ValidationError("Please fix the highlighted fields.", {"status": "unknown status"})
        q = q.filter(Order.status == status)
    if item_id:
        q = q.filter(Order.menu_item_id == item_id)
    return [order_dict(o, name) for o, name in q.order_by(Order.order_date.desc(), Order.id.desc()).all()]


def create_order(outlet_id: int, data: dict, actor_id: int | None = None) -> dict:
    f = Fields(data)
    item_id = f.integer("menu_item_id", gt=0)
    day = f.date("order_date", not_future=True, default=today())
    qty = f.portions("quantity", gt=0)
    note = f.text("customer_note", required=False, max_len=255)
    f.check()
    item = dm.get_menu_item(outlet_id, item_id)
    if not item.is_active:
        raise ValidationError("That menu item is not active.", {"menu_item_id": "is not active"})
    o = Order(outlet_id=outlet_id, menu_item_id=item.id, order_date=day, quantity=qty, status="open",
              customer_note=note, created_by=actor_id)
    db.session.add(o)
    db.session.flush()
    audit.record(outlet_id, actor_id, "order.create", "order", o.id, {"item": item.name, "date": day.isoformat(), "quantity": qty})
    db.session.commit()
    return order_dict(o, item.name)


def update_order(outlet_id: int, order_id: int, data: dict, actor_id: int | None = None) -> dict:
    """Edit quantity, date or note of an open order, or mark it fulfilled or cancelled."""
    o = get_order(outlet_id, order_id)
    if o.status != "open":
        raise ConflictError(f"A {o.status} order cannot be changed.")
    merged = {"quantity": o.quantity, "order_date": o.order_date, "customer_note": o.customer_note, "status": o.status}
    merged.update({k: data[k] for k in merged if k in data})
    f = Fields(merged)
    qty = f.portions("quantity", gt=0)
    day = f.date("order_date", not_future=True)
    note = f.text("customer_note", required=False, max_len=255)
    status = f.choice("status", ORDER_STATUSES)
    f.check()
    before = (o.quantity, o.order_date, o.status)
    o.quantity, o.order_date, o.customer_note, o.status = qty, day, note, status
    audit.record(outlet_id, actor_id, "order.update", "order", o.id,
                 {"from": [before[0], before[1].isoformat(), before[2]], "to": [qty, day.isoformat(), status]})
    db.session.commit()
    return order_dict(o, db.session.get(MenuItem, o.menu_item_id).name)


# ---- ingredient usage (K8) ---------------------------------------------------------------------------------
# Expected use = what was prepared x the recipe. The kitchen may record the actual amount for an ingredient and day (one
# figure per ingredient and day; recording again replaces it). Recording never changes stock: stock only falls through
# the inventory manager's movements (DATABASE.md DB8).
_Q3 = Decimal("0.001")


def ingredient_usage_for(outlet_id: int, day) -> dict:
    prepared = dict(db.session.query(PreparationRecord.menu_item_id, db.func.sum(PreparationRecord.quantity)).filter(
        PreparationRecord.outlet_id == outlet_id, PreparationRecord.prep_date == day).group_by(PreparationRecord.menu_item_id).all())
    recipes: dict = {}
    if prepared:
        for line in RecipeLine.query.filter(RecipeLine.menu_item_id.in_(list(prepared))):
            recipes.setdefault(line.menu_item_id, []).append(line)
    names = {m.id: m.name for m in MenuItem.query.filter(MenuItem.id.in_(list(prepared)))} if prepared else {}
    expected: dict = {}
    sources: dict = {}      # where each expected figure comes from: item, portions prepared x recipe quantity (display only)
    for item_id, qty in prepared.items():
        for line in recipes.get(item_id, []):
            expected[line.ingredient_id] = expected.get(line.ingredient_id, Decimal(0)) + Decimal(int(qty)) * line.quantity_per_portion
            sources.setdefault(line.ingredient_id, []).append(
                {"menu_item_id": item_id, "item": names.get(item_id, ""), "prepared": int(qty),
                 "per_portion": float(line.quantity_per_portion),
                 "quantity": float((Decimal(int(qty)) * line.quantity_per_portion).quantize(_Q3))})
    no_recipe = [name for item_id, name in names.items() if item_id not in recipes]
    recorded = {u.ingredient_id: u for u in IngredientUsage.query.filter_by(outlet_id=outlet_id, usage_date=day)}
    ids = set(expected) | set(recorded)
    ings = {i.id: i for i in Ingredient.query.filter(Ingredient.id.in_(ids))} if ids else {}
    rows = []
    for ing_id in sorted(ids, key=lambda i: ings[i].name):
        exp, rec = expected.get(ing_id), recorded.get(ing_id)
        exp_q = exp.quantize(_Q3) if exp is not None else Decimal(0)
        rows.append({"ingredient_id": ing_id, "ingredient": ings[ing_id].name, "unit": ings[ing_id].unit,
                     "expected": float(exp_q), "recorded": float(rec.quantity) if rec else None,
                     "variance": float(rec.quantity - exp_q) if rec else None, "note": rec.note if rec else None,
                     "usage_id": rec.id if rec else None,
                     "sources": sorted(sources.get(ing_id, []), key=lambda s: s["item"])})
    return {"date": day.isoformat(), "rows": rows, "items_without_recipe": sorted(no_recipe),
            "prepared_items": len(prepared)}


def record_ingredient_usage(outlet_id: int, data: dict, actor_id: int | None = None) -> dict:
    f = Fields(data)
    day = f.date("date", not_future=True, default=today())
    ing_id = f.integer("ingredient_id", gt=0)
    qty = f.stock_qty("quantity", min=0)
    note = f.text("note", required=False, max_len=255)
    f.check()
    ing = Ingredient.query.filter_by(id=ing_id, outlet_id=outlet_id, is_active=True).first()
    if not ing:
        raise ValidationError("Please fix the highlighted fields.", {"ingredient_id": "unknown or inactive ingredient"})
    qty = qty.quantize(_Q3)
    u = IngredientUsage.query.filter_by(outlet_id=outlet_id, ingredient_id=ing.id, usage_date=day).first()
    created = u is None
    if created:
        u = IngredientUsage(outlet_id=outlet_id, ingredient_id=ing.id, usage_date=day)
        db.session.add(u)
    u.quantity, u.note, u.created_by = qty, note, actor_id
    db.session.flush()
    audit.record(outlet_id, actor_id, "usage.record", "ingredient", ing.id,
                 {"date": day.isoformat(), "quantity": float(qty), "replaced": not created})
    db.session.commit()
    return {"usage_id": u.id, "ingredient_id": ing.id, "ingredient": ing.name, "unit": ing.unit, "date": day.isoformat(),
            "quantity": float(qty), "note": note, "created": created}


def clear_ingredient_usage(outlet_id: int, usage_id: int, actor_id: int | None = None) -> dict:
    """Remove a recorded figure, so the row falls back to the expected usage."""
    u = IngredientUsage.query.filter_by(id=usage_id, outlet_id=outlet_id).first()
    if not u:
        raise NotFoundError("Usage record not found.")
    audit.record(outlet_id, actor_id, "usage.clear", "ingredient", u.ingredient_id,
                 {"date": u.usage_date.isoformat(), "quantity": float(u.quantity)})
    db.session.delete(u)
    db.session.commit()
    return {"cleared": usage_id}


# ---- K14: Actual Food Usage (staff meals, complimentary portions, samples, other) --------------------------
def _other_use(outlet_id: int, day) -> dict:
    """{menu_item_id: {usage_type: quantity}} for one day."""
    out: dict = {}
    for u in FoodUsage.query.filter_by(outlet_id=outlet_id, usage_date=day):
        out.setdefault(u.menu_item_id, {})[u.usage_type] = u.quantity
    return out


def _balance_row(item: MenuItem, prepared: int, served: int | None, wasted: int, other: dict) -> dict:
    """prepared = served + wasted + other use + unaccounted; unaccounted stays unknown until served is recorded."""
    other_use = {t: int(other.get(t, 0)) for t in FOOD_USAGE_TYPES}
    other_total = sum(other_use.values())
    used = (served or 0) + wasted + other_total
    return {"menu_item_id": item.id, "name": item.name, "prepared": prepared, "served": served, "wasted": wasted,
            "other_use": other_use, "other_total": other_total,
            "unaccounted": None if served is None else prepared - used,
            "flags": ["used_more_than_prepared"] if used > prepared else []}


def _balance_for(outlet_id: int, item: MenuItem, day) -> dict:
    sale = SalesRecord.query.filter_by(outlet_id=outlet_id, menu_item_id=item.id, sale_date=day).first()
    return _balance_row(item, _prepared_total(outlet_id, item.id, day), sale.quantity_sold if sale else None,
                        _waste_total(outlet_id, item.id, day), _other_use(outlet_id, day).get(item.id, {}))


def food_usage_for(outlet_id: int, day) -> dict:
    """The day's recorded other use and, per active item, the balance against prepared, served and wasted."""
    entries = (db.session.query(FoodUsage, MenuItem.name).join(MenuItem, MenuItem.id == FoodUsage.menu_item_id)
               .filter(FoodUsage.outlet_id == outlet_id, FoodUsage.usage_date == day)
               .order_by(MenuItem.name, FoodUsage.usage_type))
    return {"date": day.isoformat(), "usage_types": list(FOOD_USAGE_TYPES),
            "entries": [{"usage_id": u.id, "menu_item_id": u.menu_item_id, "item": name, "usage_type": u.usage_type,
                         "quantity": u.quantity, "note": u.note} for u, name in entries],
            "balance": [_balance_for(outlet_id, item, day) for item in dm.list_menu_items(outlet_id, active_only=True)]}


def record_food_usage(outlet_id: int, data: dict, actor_id: int | None = None) -> dict:
    """One figure per item, day and type; recording again replaces it. Saved with a warning when the day's use adds
    up to more than was prepared, as served above prepared is (K6)."""
    f = Fields(data)
    day = f.date("date", not_future=True, default=today())
    item_id = f.integer("menu_item_id", gt=0)
    usage_type = f.choice("usage_type", FOOD_USAGE_TYPES)
    qty = f.portions("quantity", gt=0)
    note = f.text("note", required=False, max_len=255)
    f.check()
    item = dm.get_menu_item(outlet_id, item_id)
    u = FoodUsage.query.filter_by(outlet_id=outlet_id, menu_item_id=item.id, usage_date=day, usage_type=usage_type).first()
    created = u is None
    if created:
        u = FoodUsage(outlet_id=outlet_id, menu_item_id=item.id, usage_date=day, usage_type=usage_type)
        db.session.add(u)
    u.quantity, u.note, u.created_by = qty, note, actor_id
    db.session.flush()
    audit.record(outlet_id, actor_id, "food_usage.record", "menu_item", item.id,
                 {"date": day.isoformat(), "type": usage_type, "quantity": qty, "replaced": not created})
    b = _balance_for(outlet_id, item, day)
    warnings = []
    if b["flags"]:
        parts = ([f"served ({b['served']})"] if b["served"] is not None else []) + [f"waste ({b['wasted']})"]
        used = (b["served"] or 0) + b["wasted"] + b["other_total"]
        warnings.append(f"{item.name}: {', '.join(parts)} and other use ({b['other_total']}) add up to {used}, "
                        f"more than the {b['prepared']} prepared.")
    db.session.commit()
    return {"usage_id": u.id, "menu_item_id": item.id, "item": item.name, "date": day.isoformat(),
            "usage_type": usage_type, "quantity": qty, "note": note, "created": created, "warnings": warnings}


def clear_food_usage(outlet_id: int, usage_id: int, actor_id: int | None = None) -> dict:
    u = FoodUsage.query.filter_by(id=usage_id, outlet_id=outlet_id).first()
    if not u:
        raise NotFoundError("Food usage record not found.")
    audit.record(outlet_id, actor_id, "food_usage.clear", "menu_item", u.menu_item_id,
                 {"date": u.usage_date.isoformat(), "type": u.usage_type, "quantity": u.quantity})
    db.session.delete(u)
    db.session.commit()
    return {"cleared": usage_id}
