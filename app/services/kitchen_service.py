"""Prepared / served / waste recording (Kitchen Operations service, ARCH section 3)."""
from datetime import datetime
from decimal import Decimal

from app.extensions import db
from app.models import (FoodWaste, Ingredient, IngredientUsage, MenuItem, Order, PreOrder, PreparationRecord,
                        RecipeLine, Recommendation, SalesRecord)
from app.models.base import utcnow
from app.models.kitchen import WASTE_REASONS
from app.models.sales import ORDER_STATUSES, PREORDER_STATUSES
from app.services import audit
from app.services import data_management_service as dm
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


def record_prepared(outlet_id: int, data: dict, actor_id: int | None = None) -> dict:
    """K5: several entries per item and day are summed."""
    f = Fields(data)
    item_id = f.integer("menu_item_id", gt=0)
    day = f.date("date", not_future=True)
    qty = f.integer("quantity", gt=0)
    f.check()
    item = dm.get_menu_item(outlet_id, item_id)
    db.session.add(PreparationRecord(outlet_id=outlet_id, menu_item_id=item.id, prep_date=day, quantity=qty,
                                     prepared_at=utcnow(), created_by=actor_id))
    db.session.commit()
    return {"menu_item_id": item.id, "date": day.isoformat(), "added": qty,
            "total_prepared": _prepared_total(outlet_id, item.id, day)}


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
        qty = lf.integer("quantity", min=0)
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
    audit.record(outlet_id, actor_id, "sales.served", "sales_records", None, {"date": day.isoformat(), "lines": saved})
    db.session.commit()
    return {"date": day.isoformat(), "saved": saved, "warnings": warnings}


def record_waste(outlet_id: int, data: dict, actor_id: int | None = None) -> dict:
    """K7: prepared-food waste. Waste above the prepared total is allowed with a warning."""
    f = Fields(data)
    item_id = f.integer("menu_item_id", gt=0)
    day = f.date("date", not_future=True)
    qty = f.integer("quantity", gt=0)
    reason = f.choice("reason", WASTE_REASONS)
    note = f.text("note", required=False, max_len=255)
    f.check()
    item = dm.get_menu_item(outlet_id, item_id)
    db.session.add(FoodWaste(outlet_id=outlet_id, menu_item_id=item.id, waste_date=day, quantity=qty, reason=reason,
                             unit_price=item.price, note=note, created_by=actor_id))
    db.session.commit()
    total, prepared = _waste_total(outlet_id, item.id, day), _prepared_total(outlet_id, item.id, day)
    warnings = []
    if total > prepared:
        warnings.append(f"Waste for {item.name} today ({total}) is higher than prepared ({prepared}).")
    return {"menu_item_id": item.id, "date": day.isoformat(), "added": qty, "total_waste": total, "warnings": warnings}


# ---- pre-orders (K10) ---------------------------------------------------------------------------
# Only confirmed pre-orders count in the preparation quantity (recommendation_service reads them). "Cancelled" is final.
def pre_order_dict(p: PreOrder, item_name: str) -> dict:
    return {"id": p.id, "menu_item_id": p.menu_item_id, "item": item_name, "target_date": p.target_date.isoformat(),
            "quantity": p.quantity, "status": p.status, "customer_note": p.customer_note}


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
    return [pre_order_dict(p, name) for p, name in q.order_by(PreOrder.target_date, PreOrder.id).all()]


def create_pre_order(outlet_id: int, data: dict, actor_id: int | None = None) -> dict:
    f = Fields(data)
    item_id = f.integer("menu_item_id", gt=0)
    day = f.date("target_date")
    qty = f.integer("quantity", gt=0)
    note = f.text("customer_note", required=False, max_len=255)
    status = f.choice("status", ("pending", "confirmed"), default="pending")
    if day and day < today():
        f.error("target_date", "cannot be in the past")
    f.check()
    item = dm.get_menu_item(outlet_id, item_id)
    if not item.is_active:
        raise ValidationError("That menu item is not active.", {"menu_item_id": "is not active"})
    p = PreOrder(outlet_id=outlet_id, menu_item_id=item.id, target_date=day, quantity=qty, status=status,
                 customer_note=note, created_by=actor_id)
    db.session.add(p)
    db.session.flush()
    audit.record(outlet_id, actor_id, "preorder.create", "pre_order", p.id,
                 {"item": item.name, "date": day.isoformat(), "quantity": qty, "status": status})
    db.session.commit()
    return {**pre_order_dict(p, item.name), "warnings": _decision_warning(outlet_id, item.id, day) if status == "confirmed" else []}


def update_pre_order(outlet_id: int, pre_order_id: int, data: dict, actor_id: int | None = None) -> dict:
    """Edit quantity, date or note, or confirm / cancel. Past-dated and cancelled pre-orders are history."""
    p = get_pre_order(outlet_id, pre_order_id)
    if p.status == "cancelled":
        raise ConflictError("A cancelled pre-order cannot be changed.")
    if p.target_date < today():
        raise ConflictError("A pre-order for a past date cannot be changed.")
    merged = {"quantity": p.quantity, "target_date": p.target_date, "customer_note": p.customer_note, "status": p.status}
    merged.update({k: data[k] for k in merged if k in data})
    f = Fields(merged)
    qty = f.integer("quantity", gt=0)
    day = f.date("target_date")
    note = f.text("customer_note", required=False, max_len=255)
    status = f.choice("status", PREORDER_STATUSES)
    if day and day < today():
        f.error("target_date", "cannot be in the past")
    f.check()
    before = (p.quantity, p.target_date, p.status)
    old_day, old_status = p.target_date, p.status
    p.quantity, p.target_date, p.customer_note, p.status = qty, day, note, status
    audit.record(outlet_id, actor_id, "preorder.update", "pre_order", p.id,
                 {"from": [before[0], before[1].isoformat(), before[2]], "to": [qty, day.isoformat(), status]})
    warnings = []
    if "confirmed" in (old_status, status):     # only confirmed pre-orders change the plan
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
    qty = f.integer("quantity", gt=0)
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
    qty = f.integer("quantity", gt=0)
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
    expected: dict = {}
    for item_id, qty in prepared.items():
        for line in recipes.get(item_id, []):
            expected[line.ingredient_id] = expected.get(line.ingredient_id, Decimal(0)) + Decimal(int(qty)) * line.quantity_per_portion
    no_recipe = [m.name for m in MenuItem.query.filter(MenuItem.id.in_(list(prepared))) if m.id not in recipes] if prepared else []
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
                     "usage_id": rec.id if rec else None})
    return {"date": day.isoformat(), "rows": rows, "items_without_recipe": sorted(no_recipe),
            "prepared_items": len(prepared)}


def record_ingredient_usage(outlet_id: int, data: dict, actor_id: int | None = None) -> dict:
    f = Fields(data)
    day = f.date("date", not_future=True, default=today())
    ing_id = f.integer("ingredient_id", gt=0)
    qty = f.decimal("quantity", min=0)
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
