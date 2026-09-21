"""Ingredients, suppliers, stock (Inventory service). Master data first; movements are added in the stock slice."""
from datetime import date as _date, timedelta
from decimal import Decimal as _D

from app.extensions import db
from app.models import Ingredient, PurchaseOrder, PurchaseOrderLine, StockBatch, StockMovement, Supplier
from app.models.inventory import MOVEMENT_TYPES
from app.services import audit
from app.services.errors import NotFoundError, ValidationError
from app.services.validation import Fields
from app.utils.dates import today


# ---- suppliers (I10) -------------------------------------------------------------------------
def create_supplier(outlet_id: int, data: dict, actor_id: int | None = None) -> Supplier:
    f = Fields(data)
    f.text("name", max_len=120)
    f.text("contact_person", required=False, max_len=120)
    f.text("phone", required=False, max_len=40)
    f.text("email", required=False, max_len=160)
    f.integer("lead_time_days", required=False, min=0, default=2)
    f.text("notes", required=False)
    v = f.check()
    if Supplier.query.filter_by(outlet_id=outlet_id, name=v["name"]).first():
        raise ValidationError("Please fix the highlighted fields.", {"name": "already exists"})
    supplier = Supplier(outlet_id=outlet_id, **v)
    db.session.add(supplier)
    db.session.commit()
    return supplier


def list_suppliers(outlet_id: int) -> list[Supplier]:
    return Supplier.query.filter_by(outlet_id=outlet_id).order_by(Supplier.name).all()


# ---- ingredients (I2, I4) --------------------------------------------------------------------
def _ingredient_fields(data: dict) -> dict:
    f = Fields(data)
    f.text("name", max_len=120)
    f.text("unit", max_len=20)
    f.text("category", required=False, max_len=60)
    f.integer("shelf_life_days", required=False, min=0)
    f.integer("default_supplier_id", required=False, min=1)
    f.decimal("min_stock", min=0, default=0)
    f.decimal("reorder_level", min=0, default=0)
    f.decimal("pack_size", gt=0, default=1)
    f.decimal("reorder_qty", min=0, default=0)
    v = f.check()
    if v["reorder_level"] < v["min_stock"]:
        raise ValidationError("Please fix the highlighted fields.",
                              {"reorder_level": "must be at least the minimum stock"})
    return v


def list_ingredients(outlet_id: int, active_only: bool = False) -> list[Ingredient]:
    q = Ingredient.query.filter_by(outlet_id=outlet_id)
    if active_only:
        q = q.filter_by(is_active=True)
    return q.order_by(Ingredient.name).all()


def get_ingredient(outlet_id: int, ingredient_id: int) -> Ingredient:
    ing = Ingredient.query.filter_by(id=ingredient_id, outlet_id=outlet_id).first()
    if not ing:
        raise NotFoundError("Ingredient not found.")
    return ing


def _check_supplier(outlet_id: int, supplier_id):
    if supplier_id and not Supplier.query.filter_by(id=supplier_id, outlet_id=outlet_id).first():
        raise ValidationError("Please fix the highlighted fields.", {"default_supplier_id": "unknown supplier"})


def create_ingredient(outlet_id: int, data: dict, actor_id: int | None = None) -> Ingredient:
    v = _ingredient_fields(data)
    if Ingredient.query.filter_by(outlet_id=outlet_id, name=v["name"]).first():
        raise ValidationError("Please fix the highlighted fields.", {"name": "already exists"})
    _check_supplier(outlet_id, v.get("default_supplier_id"))
    ing = Ingredient(outlet_id=outlet_id, **v)
    db.session.add(ing)
    db.session.flush()
    audit.record(outlet_id, actor_id, "ingredient.create", "ingredient", ing.id)
    db.session.commit()
    return ing


def update_ingredient(outlet_id: int, ingredient_id: int, data: dict, actor_id: int | None = None) -> Ingredient:
    ing = get_ingredient(outlet_id, ingredient_id)
    keys = ("name", "unit", "category", "shelf_life_days", "default_supplier_id", "min_stock",
            "reorder_level", "pack_size", "reorder_qty")
    merged = {k: getattr(ing, k) for k in keys}
    merged.update({k: data[k] for k in keys if k in data})
    v = _ingredient_fields(merged)
    if v["unit"] != ing.unit and db.session.query(StockMovement.id).filter_by(ingredient_id=ing.id).first():
        raise ValidationError("Please fix the highlighted fields.",
                              {"unit": "cannot change after stock has been recorded"})
    clash = Ingredient.query.filter(Ingredient.outlet_id == outlet_id, Ingredient.name == v["name"],
                                    Ingredient.id != ing.id).first()
    if clash:
        raise ValidationError("Please fix the highlighted fields.", {"name": "already exists"})
    _check_supplier(outlet_id, v.get("default_supplier_id"))
    for k, val in v.items():
        setattr(ing, k, val)
    if "is_active" in data:
        ing.is_active = bool(data["is_active"])
    audit.record(outlet_id, actor_id, "ingredient.update", "ingredient", ing.id)
    db.session.commit()
    return ing


# ---- stock: levels, batches, movements (I3, I5, I6, I13) ----------------------------------------
STOCK_OUT_REASONS = ("issued_to_kitchen", "other")
WASTAGE_REASONS = ("expired", "damaged", "spoiled", "other")
ZERO = _D("0")


def _usable_filter(day):
    return db.or_(StockBatch.expiry_date.is_(None), StockBatch.expiry_date >= day)


def usable_map(outlet_id: int, day: _date | None = None) -> dict:
    """{ingredient_id: usable quantity}: remaining stock in batches that are not expired (DB7)."""
    day = day or today()
    rows = (db.session.query(StockBatch.ingredient_id, db.func.sum(StockBatch.qty_remaining))
            .filter(StockBatch.outlet_id == outlet_id, StockBatch.qty_remaining > 0, _usable_filter(day))
            .group_by(StockBatch.ingredient_id).all())
    return {i: q for i, q in rows}


def on_hand_map(outlet_id: int) -> dict:
    rows = (db.session.query(StockBatch.ingredient_id, db.func.sum(StockBatch.qty_remaining))
            .filter(StockBatch.outlet_id == outlet_id).group_by(StockBatch.ingredient_id).all())
    return {i: q for i, q in rows}


def on_order_map(outlet_id: int) -> dict:
    """Open purchase order quantity not yet received. 0 until purchase orders exist (S tier)."""
    rows = (db.session.query(PurchaseOrderLine.ingredient_id,
                             db.func.sum(PurchaseOrderLine.qty_ordered - PurchaseOrderLine.qty_received))
            .join(PurchaseOrder, PurchaseOrder.id == PurchaseOrderLine.purchase_order_id)
            .filter(PurchaseOrder.outlet_id == outlet_id,
                    PurchaseOrder.status.in_(("draft", "sent", "partially_received")))
            .group_by(PurchaseOrderLine.ingredient_id).all())
    return {i: q for i, q in rows if q and q > 0}


def stock_status(usable: _D, ing: Ingredient) -> tuple[str, bool]:
    """('ok'|'low'|'out', is_critical) from usable stock (DATABASE DB7, ML_PLAN B4)."""
    critical = usable <= ing.min_stock
    if usable <= 0:
        return "out", True
    if usable <= ing.reorder_level:
        return "low", critical
    return "ok", critical


def stock_levels(outlet_id: int, day: _date | None = None, active_only: bool = True) -> list[dict]:
    day = day or today()
    usable, on_hand = usable_map(outlet_id, day), on_hand_map(outlet_id)
    last = dict(db.session.query(StockMovement.ingredient_id, db.func.max(StockMovement.movement_date))
                .filter(StockMovement.outlet_id == outlet_id).group_by(StockMovement.ingredient_id).all())
    out = []
    for ing in list_ingredients(outlet_id, active_only):
        u = usable.get(ing.id, ZERO)
        status, critical = stock_status(u, ing)
        out.append({**ingredient_dict(ing), "on_hand": float(on_hand.get(ing.id, ZERO)), "usable": float(u),
                    "status": status, "is_critical": critical,
                    "last_movement_date": last[ing.id].isoformat() if ing.id in last else None})
    return out


def ingredient_dict(i: Ingredient) -> dict:
    return {"id": i.id, "name": i.name, "unit": i.unit, "category": i.category, "shelf_life_days": i.shelf_life_days,
            "default_supplier_id": i.default_supplier_id,
            "default_supplier": i.default_supplier.name if i.default_supplier else None,
            "min_stock": float(i.min_stock), "reorder_level": float(i.reorder_level), "pack_size": float(i.pack_size),
            "reorder_qty": float(i.reorder_qty), "is_active": i.is_active}


def supplier_dict(s: Supplier) -> dict:
    return {"id": s.id, "name": s.name, "contact_person": s.contact_person, "phone": s.phone, "email": s.email,
            "lead_time_days": s.lead_time_days, "notes": s.notes, "is_active": s.is_active}


def _retry_on_conflict(fn):
    """MariaDB 11 (snapshot isolation) reports 1020 'record has changed since last read' when a locking read meets a
    row committed after this transaction's snapshot; deadlocks are 1213. Re-run the whole operation on a fresh snapshot."""
    import functools

    from sqlalchemy.exc import OperationalError

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        for attempt in range(4):
            try:
                return fn(*args, **kwargs)
            except OperationalError as exc:
                code = exc.orig.args[0] if getattr(exc, "orig", None) and exc.orig.args else None
                db.session.rollback()
                if code not in (1020, 1213, 1205) or attempt == 3:
                    raise
    return wrapper


def _lock_batches(outlet_id: int, ingredient_id: int, day: _date | None, usable_only: bool):
    """Batches in FEFO order (earliest expiry first, no-expiry last), locked for update (DB3, ARCH 7.3)."""
    q = StockBatch.query.filter(StockBatch.outlet_id == outlet_id, StockBatch.ingredient_id == ingredient_id,
                                StockBatch.qty_remaining > 0)
    if usable_only:
        q = q.filter(_usable_filter(day))
    return (q.order_by(StockBatch.expiry_date.is_(None), StockBatch.expiry_date, StockBatch.received_date,
                       StockBatch.id).with_for_update().all())


def record_stock_in(outlet_id: int, data: dict, actor_id: int | None = None) -> dict:
    f = Fields(data)
    ing_id = f.integer("ingredient_id", gt=0)
    qty = f.decimal("quantity", gt=0)
    received = f.date("received_date", not_future=True, default=today())
    expiry = f.date("expiry_date", required=False)
    batch_no = f.text("batch_no", required=False, max_len=60)
    cost = f.decimal("unit_cost", required=False, min=0)
    supplier_id = f.integer("supplier_id", required=False, gt=0)
    f.check()
    if expiry and received and expiry < received:
        raise ValidationError("Please fix the highlighted fields.", {"expiry_date": "cannot be before the received date"})
    ing = get_ingredient(outlet_id, ing_id)
    if supplier_id and not Supplier.query.filter_by(id=supplier_id, outlet_id=outlet_id).first():
        raise ValidationError("Please fix the highlighted fields.", {"supplier_id": "unknown supplier"})
    batch = StockBatch(outlet_id=outlet_id, ingredient_id=ing.id, batch_no=batch_no or f"{received:%Y%m%d}-{ing.id}",
                       received_date=received, expiry_date=expiry, qty_received=qty, qty_remaining=qty,
                       unit_cost=cost, supplier_id=supplier_id or ing.default_supplier_id)
    db.session.add(batch)
    db.session.flush()
    db.session.add(StockMovement(outlet_id=outlet_id, ingredient_id=ing.id, batch_id=batch.id, movement_type="stock_in",
                                 quantity=qty, movement_date=received, reason=None, created_by=actor_id))
    db.session.commit()
    return {"ingredient_id": ing.id, "batch_id": batch.id, "quantity": float(qty), "unit": ing.unit,
            "usable": float(usable_map(outlet_id).get(ing.id, ZERO))}


def _draw_down(outlet_id, ing, batches, qty: _D, mtype: str, day: _date, reason, note, actor_id) -> list[dict]:
    """Deduct qty from batches in the order given; one movement (negative) per batch touched."""
    left, used = qty, []
    for b in batches:
        if left <= 0:
            break
        take = min(b.qty_remaining, left)
        b.qty_remaining -= take
        left -= take
        db.session.add(StockMovement(outlet_id=outlet_id, ingredient_id=ing.id, batch_id=b.id, movement_type=mtype,
                                     quantity=-take, movement_date=day, reason=reason, note=note, created_by=actor_id))
        used.append({"batch_id": b.id, "quantity": float(take)})
    return used


@_retry_on_conflict
def record_stock_out(outlet_id: int, data: dict, actor_id: int | None = None) -> dict:
    """FEFO over usable (non-expired) batches. Rejected as a whole if usable stock is insufficient (I6)."""
    f = Fields(data)
    ing_id = f.integer("ingredient_id", gt=0)
    qty = f.decimal("quantity", gt=0)
    day = f.date("movement_date", not_future=True, default=today())
    reason = f.choice("reason", STOCK_OUT_REASONS, default="issued_to_kitchen")
    note = f.text("note", required=False)
    f.check()
    ing = get_ingredient(outlet_id, ing_id)
    batches = _lock_batches(outlet_id, ing.id, today(), usable_only=True)
    available = sum((b.qty_remaining for b in batches), ZERO)
    if qty > available:
        db.session.rollback()
        raise ValidationError(f"Only {available.normalize():f} {ing.unit} usable stock is available.",
                              {"quantity": f"only {available.normalize():f} {ing.unit} available"},
                              code="insufficient_stock", extra={"available": float(available)})
    used = _draw_down(outlet_id, ing, batches, qty, "stock_out", day, reason, note, actor_id)
    db.session.commit()
    return {"ingredient_id": ing.id, "quantity": float(qty), "unit": ing.unit, "batches": used,
            "usable": float(usable_map(outlet_id).get(ing.id, ZERO))}


@_retry_on_conflict
def record_wastage(outlet_id: int, data: dict, actor_id: int | None = None) -> dict:
    """Wastage may draw from any batch, expired ones first (that is its purpose) (I13)."""
    f = Fields(data)
    ing_id = f.integer("ingredient_id", gt=0)
    qty = f.decimal("quantity", gt=0)
    day = f.date("movement_date", not_future=True, default=today())
    reason = f.choice("reason", WASTAGE_REASONS)
    batch_id = f.integer("batch_id", required=False, gt=0)
    note = f.text("note", required=False)
    f.check()
    ing = get_ingredient(outlet_id, ing_id)
    batches = _lock_batches(outlet_id, ing.id, None, usable_only=False)
    if batch_id:
        batches = [b for b in batches if b.id == batch_id]
        if not batches:
            db.session.rollback()
            raise ValidationError("Please fix the highlighted fields.", {"batch_id": "batch not found or empty"})
    available = sum((b.qty_remaining for b in batches), ZERO)
    if qty > available:
        db.session.rollback()
        raise ValidationError(f"Only {available.normalize():f} {ing.unit} is on hand.",
                              {"quantity": f"only {available.normalize():f} {ing.unit} on hand"},
                              code="insufficient_stock", extra={"available": float(available)})
    used = _draw_down(outlet_id, ing, batches, qty, "wastage", day, reason, note, actor_id)
    db.session.commit()
    return {"ingredient_id": ing.id, "quantity": float(qty), "unit": ing.unit, "batches": used}


def list_batches(outlet_id: int, ingredient_id: int | None = None, expiring_within_days: int | None = None) -> list[dict]:
    q = (StockBatch.query.filter(StockBatch.outlet_id == outlet_id, StockBatch.qty_remaining > 0))
    if ingredient_id:
        q = q.filter(StockBatch.ingredient_id == ingredient_id)
    if expiring_within_days is not None:
        q = q.filter(StockBatch.expiry_date.isnot(None),
                     StockBatch.expiry_date <= today() + timedelta(days=expiring_within_days))
    day = today()
    return [{"id": b.id, "ingredient_id": b.ingredient_id, "ingredient": b.ingredient.name, "unit": b.ingredient.unit,
             "batch_no": b.batch_no, "received_date": b.received_date.isoformat(),
             "expiry_date": b.expiry_date.isoformat() if b.expiry_date else None,
             "qty_remaining": float(b.qty_remaining), "expired": bool(b.expiry_date and b.expiry_date < day),
             "days_to_expiry": (b.expiry_date - day).days if b.expiry_date else None}
            for b in q.order_by(StockBatch.expiry_date.is_(None), StockBatch.expiry_date, StockBatch.id).all()]


def list_movements(outlet_id: int, ingredient_id=None, mtype=None, start=None, end=None, limit=50, offset=0) -> dict:
    q = db.session.query(StockMovement, Ingredient).join(Ingredient, Ingredient.id == StockMovement.ingredient_id).filter(
        StockMovement.outlet_id == outlet_id)
    if ingredient_id:
        q = q.filter(StockMovement.ingredient_id == ingredient_id)
    if mtype:
        if mtype not in MOVEMENT_TYPES:
            raise ValidationError("Please fix the highlighted fields.", {"type": "unknown movement type"})
        q = q.filter(StockMovement.movement_type == mtype)
    if start:
        q = q.filter(StockMovement.movement_date >= start)
    if end:
        q = q.filter(StockMovement.movement_date <= end)
    total = q.count()
    rows = q.order_by(StockMovement.movement_date.desc(), StockMovement.id.desc()).limit(min(limit, 200)).offset(offset).all()
    return {"total": total, "rows": [{"id": m.id, "ingredient_id": m.ingredient_id, "ingredient": i.name, "unit": i.unit,
                                      "type": m.movement_type, "quantity": float(m.quantity), "reason": m.reason,
                                      "note": m.note, "date": m.movement_date.isoformat(), "batch_id": m.batch_id}
                                     for m, i in rows]}


def stock_invariant_violations(outlet_id: int) -> list[dict]:
    """Ingredients where SUM(movements) differs from SUM(batch remaining): must always be empty (DB6)."""
    moves = dict(db.session.query(StockMovement.ingredient_id, db.func.sum(StockMovement.quantity))
                 .filter(StockMovement.outlet_id == outlet_id).group_by(StockMovement.ingredient_id).all())
    remain = on_hand_map(outlet_id)
    bad = []
    for ing_id in set(moves) | set(remain):
        if moves.get(ing_id, ZERO) != remain.get(ing_id, ZERO):
            bad.append({"ingredient_id": ing_id, "movements": float(moves.get(ing_id, ZERO)),
                        "batches": float(remain.get(ing_id, ZERO))})
    return bad
