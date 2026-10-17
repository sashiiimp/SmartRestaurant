"""Ingredients, suppliers, stock (Inventory service). Master data first; movements are added in the stock slice."""
from datetime import date as _date, timedelta
from decimal import Decimal as _D

from app.extensions import db
from app.models import (Ingredient, PurchaseOrder, PurchaseOrderLine, StockBatch, StockMovement, StockRequest,
                        StockRequestLine, Supplier, User)
from app.models.inventory import MOVEMENT_TYPES, PO_STATUSES, STOCK_REQUEST_STATUSES
from app.models.base import utcnow
from app.services import audit
from app.services.errors import ConflictError, NotFoundError, ValidationError
from app.services.validation import MAX_INT, Fields
from app.utils.dates import today


# ---- suppliers (I10) -------------------------------------------------------------------------
def _supplier_fields(data: dict) -> dict:
    f = Fields(data)
    f.text("name", max_len=120)
    f.text("contact_person", required=False, max_len=120)
    f.text("phone", required=False, max_len=40)
    f.text("email", required=False, max_len=160)
    f.integer("lead_time_days", min=0, max=365, default=2)
    f.text("notes", required=False)
    return f.check()


def get_supplier(outlet_id: int, supplier_id: int) -> Supplier:
    supplier = Supplier.query.filter_by(id=supplier_id, outlet_id=outlet_id).first()
    if not supplier:
        raise NotFoundError("Supplier not found.")
    return supplier


def _supplier_name_taken(outlet_id: int, name: str, exclude_id: int | None = None) -> bool:
    q = Supplier.query.filter(Supplier.outlet_id == outlet_id, Supplier.name == name)
    if exclude_id:
        q = q.filter(Supplier.id != exclude_id)
    return q.first() is not None


def create_supplier(outlet_id: int, data: dict, actor_id: int | None = None) -> Supplier:
    v = _supplier_fields(data)
    if _supplier_name_taken(outlet_id, v["name"]):
        raise ValidationError("Please fix the highlighted fields.", {"name": "already exists"})
    supplier = Supplier(outlet_id=outlet_id, **v)
    db.session.add(supplier)
    db.session.flush()
    audit.record(outlet_id, actor_id, "supplier.create", "supplier", supplier.id)
    db.session.commit()
    return supplier


def update_supplier(outlet_id: int, supplier_id: int, data: dict, actor_id: int | None = None) -> Supplier:
    """Edit details or (de)activate. Deactivating keeps every existing reference (ingredients, orders, batches)."""
    supplier = get_supplier(outlet_id, supplier_id)
    keys = ("name", "contact_person", "phone", "email", "lead_time_days", "notes")
    merged = {k: getattr(supplier, k) for k in keys}
    merged.update({k: data[k] for k in keys if k in data})
    v = _supplier_fields(merged)
    if _supplier_name_taken(outlet_id, v["name"], exclude_id=supplier.id):
        raise ValidationError("Please fix the highlighted fields.", {"name": "already exists"})
    for k, val in v.items():
        setattr(supplier, k, val)
    if "is_active" in data:
        flag = Fields(data).boolean("is_active")
        if flag is None:
            raise ValidationError("Please fix the highlighted fields.", {"is_active": "must be true or false"})
        supplier.is_active = flag
    audit.record(outlet_id, actor_id, "supplier.update", "supplier", supplier.id,
                 {"is_active": supplier.is_active})
    db.session.commit()
    return supplier


def list_suppliers(outlet_id: int, active_only: bool = False) -> list[Supplier]:
    q = Supplier.query.filter_by(outlet_id=outlet_id)
    if active_only:
        q = q.filter_by(is_active=True)
    return q.order_by(Supplier.name).all()


def usable_supplier(outlet_id: int, supplier_id, field: str, current_id=None) -> None:
    """A supplier must exist, and be active unless it is the one already on the record (existing links are kept)."""
    if not supplier_id:
        return
    s = Supplier.query.filter_by(id=supplier_id, outlet_id=outlet_id).first()
    if not s:
        raise ValidationError("Please fix the highlighted fields.", {field: "unknown supplier"})
    if not s.is_active and supplier_id != current_id:
        raise ValidationError("Please fix the highlighted fields.", {field: "supplier is inactive"})


# ---- ingredients (I2, I4) --------------------------------------------------------------------
def _ingredient_fields(data: dict) -> dict:
    f = Fields(data)
    f.text("name", max_len=120)
    f.text("unit", max_len=20)
    f.text("category", required=False, max_len=60)
    f.integer("shelf_life_days", required=False, min=0, max=3650)
    f.integer("default_supplier_id", required=False, min=1)
    f.stock_qty("min_stock", min=0, default=0)
    f.stock_qty("reorder_level", min=0, default=0)
    f.stock_qty("pack_size", gt=0, default=1)
    f.stock_qty("reorder_qty", min=0, default=0)
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


def _check_supplier(outlet_id: int, supplier_id, current_id=None):
    usable_supplier(outlet_id, supplier_id, "default_supplier_id", current_id)


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
    _check_supplier(outlet_id, v.get("default_supplier_id"), ing.default_supplier_id)
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


def open_orders_by_ingredient(outlet_id: int) -> dict:
    """The open purchase orders behind on_order_map, per ingredient: {id: [{"id", "status", "qty"}]} (same statuses).
    A draft counts as on order, so the same stock is not suggested twice, but it has not been sent to the supplier."""
    rows = (db.session.query(PurchaseOrderLine.ingredient_id, PurchaseOrder.id, PurchaseOrder.status,
                             PurchaseOrderLine.qty_ordered - PurchaseOrderLine.qty_received)
            .join(PurchaseOrder, PurchaseOrder.id == PurchaseOrderLine.purchase_order_id)
            .filter(PurchaseOrder.outlet_id == outlet_id, PurchaseOrder.status.in_(("draft", "sent", "partially_received")))
            .order_by(PurchaseOrder.id).all())
    out = {}
    for ing_id, po_id, status, left in rows:
        if left and left > 0:
            out.setdefault(ing_id, []).append({"id": po_id, "status": status, "qty": float(left)})
    return out


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
        h = on_hand.get(ing.id, ZERO)
        out.append({**ingredient_dict(ing), "on_hand": float(h), "usable": float(u),
                    "expired": float(max(h - u, ZERO)),   # on hand but not usable: expired, awaiting a wastage record
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


def _add_stock_batch(outlet_id, ing, qty, received, expiry, batch_no, cost, supplier_id, actor_id,
                     purchase_order_id=None) -> StockBatch:
    """One batch plus its stock_in movement (the caller commits). A purchase-order receipt links both to the order."""
    batch = StockBatch(outlet_id=outlet_id, ingredient_id=ing.id, batch_no=batch_no or f"{received:%Y%m%d}-{ing.id}",
                       received_date=received, expiry_date=expiry, qty_received=qty, qty_remaining=qty,
                       unit_cost=cost, supplier_id=supplier_id or ing.default_supplier_id,
                       purchase_order_id=purchase_order_id)
    db.session.add(batch)
    db.session.flush()
    db.session.add(StockMovement(outlet_id=outlet_id, ingredient_id=ing.id, batch_id=batch.id, movement_type="stock_in",
                                 quantity=qty, movement_date=received, reason=None, created_by=actor_id,
                                 reference_type="purchase_order" if purchase_order_id else None,
                                 reference_id=purchase_order_id))
    return batch


def record_stock_in(outlet_id: int, data: dict, actor_id: int | None = None) -> dict:
    f = Fields(data)
    ing_id = f.integer("ingredient_id", gt=0)
    qty = f.stock_qty("quantity", gt=0)
    received = f.date("received_date", not_future=True, default=today())
    expiry = f.date("expiry_date", required=False)
    batch_no = f.text("batch_no", required=False, max_len=60)
    cost = f.money("unit_cost", required=False)
    supplier_id = f.integer("supplier_id", required=False, gt=0)
    f.check()
    if expiry and received and expiry < received:
        raise ValidationError("Please fix the highlighted fields.", {"expiry_date": "cannot be before the received date"})
    ing = get_ingredient(outlet_id, ing_id)
    usable_supplier(outlet_id, supplier_id, "supplier_id")
    batch = _add_stock_batch(outlet_id, ing, qty, received, expiry, batch_no, cost, supplier_id, actor_id)
    db.session.commit()
    return {"ingredient_id": ing.id, "batch_id": batch.id, "quantity": float(qty), "unit": ing.unit,
            "usable": float(usable_map(outlet_id).get(ing.id, ZERO))}


def _draw_down(outlet_id, ing, batches, qty: _D, mtype: str, day: _date, reason, note, actor_id,
               reference_type=None, reference_id=None) -> list[dict]:
    """Deduct qty from batches in the order given; one movement (negative) per batch touched."""
    left, used = qty, []
    for b in batches:
        if left <= 0:
            break
        take = min(b.qty_remaining, left)
        b.qty_remaining -= take
        left -= take
        db.session.add(StockMovement(outlet_id=outlet_id, ingredient_id=ing.id, batch_id=b.id, movement_type=mtype,
                                     quantity=-take, movement_date=day, reason=reason, note=note, created_by=actor_id,
                                     reference_type=reference_type, reference_id=reference_id))
        used.append({"batch_id": b.id, "quantity": float(take)})
    return used


@_retry_on_conflict
def record_stock_out(outlet_id: int, data: dict, actor_id: int | None = None) -> dict:
    """FEFO over usable (non-expired) batches. Rejected as a whole if usable stock is insufficient (I6)."""
    f = Fields(data)
    ing_id = f.integer("ingredient_id", gt=0)
    qty = f.stock_qty("quantity", gt=0)
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
    qty = f.stock_qty("quantity", gt=0)
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


@_retry_on_conflict
def record_adjustment(outlet_id: int, data: dict, actor_id: int | None = None) -> dict:
    """I14: the manager enters the counted quantity; the signed difference to the on-hand stock is posted.

    On-hand includes expired stock, because the count is of what is physically there. A shortfall is drawn from the
    earliest-expiry batches first (expired ones first); a surplus becomes a new batch with no expiry. The movement is
    immutable like every other, and a note is mandatory."""
    f = Fields(data)
    ing_id = f.integer("ingredient_id", gt=0)
    counted = f.stock_qty("counted_quantity", min=0)
    day = f.date("movement_date", not_future=True, default=today())
    note = f.text("note", max_len=255)
    f.check()
    counted = counted.quantize(_D("0.001"))
    ing = get_ingredient(outlet_id, ing_id)
    batches = _lock_batches(outlet_id, ing.id, None, usable_only=False)
    on_hand = sum((b.qty_remaining for b in batches), ZERO)
    diff = counted - on_hand
    if diff == 0:
        db.session.rollback()
        raise ValidationError("Please fix the highlighted fields.",
                              {"counted_quantity": "is the same as the system quantity, so there is nothing to adjust"})
    if diff < 0:
        used = _draw_down(outlet_id, ing, batches, -diff, "adjustment", day, None, note, actor_id)
    else:
        batch = StockBatch(outlet_id=outlet_id, ingredient_id=ing.id, batch_no=f"ADJ-{day:%Y%m%d}",
                           received_date=day, expiry_date=None, qty_received=diff, qty_remaining=diff)
        db.session.add(batch)
        db.session.flush()
        db.session.add(StockMovement(outlet_id=outlet_id, ingredient_id=ing.id, batch_id=batch.id,
                                     movement_type="adjustment", quantity=diff, movement_date=day, note=note,
                                     created_by=actor_id))
        used = [{"batch_id": batch.id, "quantity": float(diff)}]
    audit.record(outlet_id, actor_id, "stock.adjust", "ingredient", ing.id,
                 {"on_hand": float(on_hand), "counted": float(counted), "difference": float(diff)})
    db.session.commit()
    return {"ingredient_id": ing.id, "unit": ing.unit, "on_hand_before": float(on_hand), "counted": float(counted),
            "difference": float(diff), "batches": used, "usable": float(usable_map(outlet_id).get(ing.id, ZERO))}


# ---- purchase orders (I11) ---------------------------------------------------------------------
# An internal record only: "sent" is marked by hand, nothing is transmitted to a supplier.
RECEIVABLE = ("draft", "sent", "partially_received")
_Q3 = _D("0.001")


def _next_po_number(outlet_id: int) -> str:
    prefix = f"PO-{today():%Y%m%d}-"
    n = PurchaseOrder.query.filter(PurchaseOrder.outlet_id == outlet_id,
                                   PurchaseOrder.po_number.like(prefix + "%")).count()
    return f"{prefix}{n + 1:02d}"


def get_purchase_order(outlet_id: int, po_id: int, lock: bool = False) -> PurchaseOrder:
    q = PurchaseOrder.query.filter_by(id=po_id, outlet_id=outlet_id)
    po = (q.with_for_update() if lock else q).first()
    if not po:
        raise NotFoundError("Purchase order not found.")
    return po


def purchase_order_dict(po: PurchaseOrder, detail: bool = True) -> dict:
    supplier = db.session.get(Supplier, po.supplier_id)
    ings = {i.id: i for i in Ingredient.query.filter(Ingredient.id.in_([l.ingredient_id for l in po.lines]))} if po.lines else {}
    lines = [{"id": l.id, "ingredient_id": l.ingredient_id, "ingredient": ings[l.ingredient_id].name,
              "unit": ings[l.ingredient_id].unit, "qty_ordered": float(l.qty_ordered), "qty_received": float(l.qty_received),
              "qty_outstanding": float(l.qty_ordered - l.qty_received),
              "unit_cost": float(l.unit_cost) if l.unit_cost is not None else None} for l in po.lines]
    out = {"id": po.id, "po_number": po.po_number, "supplier_id": po.supplier_id,
           "supplier": supplier.name if supplier else None, "status": po.status,
           "order_date": po.order_date.isoformat() if po.order_date else None,
           "expected_date": po.expected_date.isoformat() if po.expected_date else None, "notes": po.notes,
           "line_count": len(lines), "outstanding_lines": sum(1 for l in lines if l["qty_outstanding"] > 0)}
    if detail:
        out["lines"] = lines
    return out


def list_purchase_orders(outlet_id: int, status: str | None = None) -> list[dict]:
    q = PurchaseOrder.query.filter_by(outlet_id=outlet_id)
    if status:
        if status not in PO_STATUSES:
            raise ValidationError("Please fix the highlighted fields.", {"status": "unknown status"})
        q = q.filter_by(status=status)
    return [purchase_order_dict(po, detail=False) for po in q.order_by(PurchaseOrder.id.desc()).all()]


def create_purchase_order(outlet_id: int, data: dict, actor_id: int | None = None) -> dict:
    f = Fields(data)
    supplier_id = f.integer("supplier_id", gt=0)
    expected = f.date("expected_date", required=False)
    notes = f.text("notes", required=False, max_len=255)
    f.check()
    if expected and expected < today():
        raise ValidationError("Please fix the highlighted fields.", {"expected_date": "cannot be in the past"})
    usable_supplier(outlet_id, supplier_id, "supplier_id")
    raw_lines = data.get("lines")
    if not isinstance(raw_lines, list) or not raw_lines:
        raise ValidationError("Please fix the highlighted fields.", {"lines": "add at least one ingredient"})
    lines, errors, seen = [], {}, set()
    for i, raw in enumerate(raw_lines):
        lf = Fields(raw if isinstance(raw, dict) else {})
        ing_id = lf.integer("ingredient_id", gt=0)
        qty = lf.stock_qty("qty_ordered", gt=0)
        cost = lf.money("unit_cost", required=False)
        if lf.errors:
            errors[f"lines[{i}]"] = "; ".join(f"{k} {m}" for k, m in lf.errors.items())
            continue
        ing = Ingredient.query.filter_by(id=ing_id, outlet_id=outlet_id, is_active=True).first()
        if not ing:
            errors[f"lines[{i}]"] = "unknown or inactive ingredient"
        elif ing_id in seen:
            errors[f"lines[{i}]"] = "ingredient appears twice"
        else:
            seen.add(ing_id)
            lines.append(PurchaseOrderLine(ingredient_id=ing_id, qty_ordered=qty.quantize(_Q3), qty_received=ZERO,
                                           unit_cost=cost))
    if errors:
        raise ValidationError("Please fix the highlighted fields.", errors)
    po = PurchaseOrder(outlet_id=outlet_id, supplier_id=supplier_id, po_number=_next_po_number(outlet_id),
                       status="draft", order_date=today(), expected_date=expected, notes=notes, created_by=actor_id)
    po.lines = lines
    db.session.add(po)
    db.session.flush()
    audit.record(outlet_id, actor_id, "purchase_order.create", "purchase_order", po.id, {"po_number": po.po_number})
    db.session.commit()
    return purchase_order_dict(po)


def send_purchase_order(outlet_id: int, po_id: int, actor_id: int | None = None) -> dict:
    """Marks the order as sent by hand (I11). Nothing is transmitted to the supplier."""
    po = get_purchase_order(outlet_id, po_id, lock=True)
    if po.status != "draft":
        db.session.rollback()
        raise ConflictError("Only a draft order can be marked as sent.")
    po.status, po.order_date = "sent", today()
    audit.record(outlet_id, actor_id, "purchase_order.send", "purchase_order", po.id)
    db.session.commit()
    return purchase_order_dict(po)


def cancel_purchase_order(outlet_id: int, po_id: int, actor_id: int | None = None) -> dict:
    po = get_purchase_order(outlet_id, po_id, lock=True)
    if po.status not in ("draft", "sent") or any(l.qty_received > 0 for l in po.lines):
        db.session.rollback()
        raise ConflictError("Only an order with nothing received can be cancelled.")
    po.status = "cancelled"
    audit.record(outlet_id, actor_id, "purchase_order.cancel", "purchase_order", po.id)
    db.session.commit()
    return purchase_order_dict(po)


@_retry_on_conflict
def receive_purchase_order(outlet_id: int, po_id: int, data: dict, actor_id: int | None = None) -> dict:
    """I11: receive all or part of an order. Each received line becomes a batch and a stock_in movement linked to the
    order; a line can never receive more than is still outstanding."""
    po = get_purchase_order(outlet_id, po_id, lock=True)
    if po.status not in RECEIVABLE:
        db.session.rollback()
        raise ConflictError(f"A {po.status.replace('_', ' ')} order cannot receive stock.")
    f = Fields(data)
    received = f.date("received_date", not_future=True, default=today())
    f.check()
    raw_lines = data.get("lines")
    if not isinstance(raw_lines, list) or not raw_lines:
        db.session.rollback()
        raise ValidationError("Please fix the highlighted fields.", {"lines": "enter a quantity for at least one line"})
    by_id = {l.id: l for l in po.lines}
    plan, errors, seen = [], {}, set()
    for i, raw in enumerate(raw_lines):
        lf = Fields(raw if isinstance(raw, dict) else {})
        line_id = lf.integer("line_id", gt=0)
        qty = lf.stock_qty("quantity", gt=0)
        expiry = lf.date("expiry_date", required=False)
        batch_no = lf.text("batch_no", required=False, max_len=60)
        cost = lf.money("unit_cost", required=False)
        key = f"lines[{i}]"
        if lf.errors:
            errors[key] = "; ".join(f"{k} {m}" for k, m in lf.errors.items())
            continue
        line = by_id.get(line_id)
        qty = qty.quantize(_Q3)
        if line is None:
            errors[key] = "not a line of this order"
        elif line_id in seen:
            errors[key] = "line appears twice"
        elif qty > line.qty_ordered - line.qty_received:
            errors[key] = f"only {(line.qty_ordered - line.qty_received).normalize():f} can still be received"
        elif expiry and expiry < received:
            errors[key] = "expiry date cannot be before the received date"
        else:
            seen.add(line_id)
            plan.append((line, qty, expiry, batch_no, cost))
    if errors:
        db.session.rollback()
        raise ValidationError("Please fix the highlighted fields.", errors)
    got = []
    for line, qty, expiry, batch_no, cost in plan:
        ing = db.session.get(Ingredient, line.ingredient_id)
        batch = _add_stock_batch(outlet_id, ing, qty, received, expiry, batch_no or po.po_number,
                                 cost if cost is not None else line.unit_cost, po.supplier_id, actor_id, po.id)
        line.qty_received = line.qty_received + qty
        if cost is not None:
            line.unit_cost = cost
        got.append({"ingredient_id": ing.id, "ingredient": ing.name, "quantity": float(qty), "unit": ing.unit,
                    "batch_id": batch.id})
    po.status = "received" if all(l.qty_received >= l.qty_ordered for l in po.lines) else "partially_received"
    audit.record(outlet_id, actor_id, "purchase_order.receive", "purchase_order", po.id,
                 {"lines": len(got), "status": po.status})
    db.session.commit()
    return {"purchase_order": purchase_order_dict(po), "received": got}


# ---- kitchen stock requests (K11 / I15) -----------------------------------------------------------
# The kitchen asks for ingredients; the inventory manager approves, rejects (reason) or issues. Issuing posts the
# stock-out through the same FEFO path as a manual stock-out, linked to the request. Logic lives here (Inventory service).
OPEN_REQUEST = ("pending", "approved")


def _person(user_id) -> str | None:
    u = db.session.get(User, user_id) if user_id else None
    return (u.full_name or u.username) if u else None


def stock_request_dict(req: StockRequest, detail: bool = True) -> dict:
    ings = {i.id: i for i in Ingredient.query.filter(Ingredient.id.in_([l.ingredient_id for l in req.lines]))} if req.lines else {}
    show_usable = detail and req.status in OPEN_REQUEST          # stock is only relevant while something can still be issued
    usable = usable_map(req.outlet_id) if show_usable else {}
    lines = [{"id": l.id, "ingredient_id": l.ingredient_id, "ingredient": ings[l.ingredient_id].name,
              "unit": ings[l.ingredient_id].unit, "qty_requested": float(l.qty_requested),
              "qty_issued": float(l.qty_issued), "qty_outstanding": float(l.qty_requested - l.qty_issued),
              "usable_stock": float(usable.get(l.ingredient_id, ZERO)) if show_usable else None} for l in req.lines]
    out = {"id": req.id, "status": req.status, "needed_date": req.needed_date.isoformat() if req.needed_date else None,
           "note": req.note, "reject_reason": req.reject_reason, "requested_by": _person(req.requested_by),
           "created_at": req.created_at.isoformat() + "Z", "decided_by": _person(req.decided_by),
           "decided_at": req.decided_at.isoformat() + "Z" if req.decided_at else None,
           # still open after the day it was needed: shown as overdue on the lists and the dashboard
           "overdue": bool(req.needed_date and req.status in OPEN_REQUEST and req.needed_date < today()),
           "line_count": len(lines), "summary": ", ".join(f"{l['ingredient']} {l['qty_requested']:g} {l['unit']}" for l in lines)}
    if detail:
        out["lines"] = lines
    return out


def get_stock_request(outlet_id: int, request_id: int, lock: bool = False) -> StockRequest:
    q = StockRequest.query.filter_by(id=request_id, outlet_id=outlet_id)
    req = (q.with_for_update() if lock else q).first()
    if not req:
        raise NotFoundError("Stock request not found.")
    return req


def list_stock_requests(outlet_id: int, status: str | None = None, detail: bool = False) -> list[dict]:
    q = StockRequest.query.filter_by(outlet_id=outlet_id)
    if status:
        if status not in STOCK_REQUEST_STATUSES:
            raise ValidationError("Please fix the highlighted fields.", {"status": "unknown status"})
        q = q.filter_by(status=status)
    # open requests first (oldest first, so nothing waits unseen), then history newest first
    rows = q.order_by(StockRequest.id.desc()).all()
    rows.sort(key=lambda r: (0, r.id) if r.status == "pending" else (1, r.id) if r.status == "approved" else (2, -r.id))
    return [stock_request_dict(r, detail=detail) for r in rows]


def pending_request_count(outlet_id: int) -> int:
    return StockRequest.query.filter_by(outlet_id=outlet_id, status="pending").count()


def create_stock_request(outlet_id: int, data: dict, actor_id: int | None = None) -> dict:
    f = Fields(data)
    needed = f.date("needed_date", required=False)
    note = f.text("note", required=False, max_len=255)
    if needed and needed < today():
        f.error("needed_date", "cannot be in the past")
    f.check()
    raw_lines = data.get("lines")
    if not isinstance(raw_lines, list) or not raw_lines:
        raise ValidationError("Please fix the highlighted fields.", {"lines": "add at least one ingredient"})
    lines, errors, seen = [], {}, set()
    for i, raw in enumerate(raw_lines):
        lf = Fields(raw if isinstance(raw, dict) else {})
        ing_id = lf.integer("ingredient_id", gt=0)
        qty = lf.stock_qty("quantity", gt=0)
        if lf.errors:
            errors[f"lines[{i}]"] = "; ".join(f"{k} {m}" for k, m in lf.errors.items())
            continue
        ing = Ingredient.query.filter_by(id=ing_id, outlet_id=outlet_id, is_active=True).first()
        if not ing:
            errors[f"lines[{i}]"] = "unknown or inactive ingredient"
        elif ing_id in seen:
            errors[f"lines[{i}]"] = "ingredient appears twice"
        else:
            seen.add(ing_id)
            lines.append(StockRequestLine(ingredient_id=ing_id, qty_requested=qty.quantize(_Q3), qty_issued=ZERO))
    if errors:
        raise ValidationError("Please fix the highlighted fields.", errors)
    req = StockRequest(outlet_id=outlet_id, requested_by=actor_id, needed_date=needed, note=note, status="pending")
    req.lines = lines
    db.session.add(req)
    db.session.flush()
    audit.record(outlet_id, actor_id, "stock_request.create", "stock_request", req.id, {"lines": len(lines)})
    db.session.commit()
    return stock_request_dict(req)


def cancel_stock_request(outlet_id: int, request_id: int, actor_id: int | None = None) -> dict:
    """The kitchen may withdraw a request only while it is still pending."""
    req = get_stock_request(outlet_id, request_id, lock=True)
    if req.status != "pending":
        db.session.rollback()
        raise ConflictError("Only a pending request can be cancelled.")
    req.status = "cancelled"
    audit.record(outlet_id, actor_id, "stock_request.cancel", "stock_request", req.id)
    db.session.commit()
    return stock_request_dict(req)


def approve_stock_request(outlet_id: int, request_id: int, actor_id: int | None = None) -> dict:
    req = get_stock_request(outlet_id, request_id, lock=True)
    if req.status != "pending":
        db.session.rollback()
        raise ConflictError("Only a pending request can be approved.")
    req.status, req.decided_by, req.decided_at = "approved", actor_id, utcnow()
    audit.record(outlet_id, actor_id, "stock_request.approve", "stock_request", req.id)
    db.session.commit()
    return stock_request_dict(req)


def reject_stock_request(outlet_id: int, request_id: int, data: dict, actor_id: int | None = None) -> dict:
    f = Fields(data)
    reason = f.text("reason", max_len=255)
    f.check()
    req = get_stock_request(outlet_id, request_id, lock=True)
    if req.status != "pending":
        db.session.rollback()
        raise ConflictError("Only a pending request can be rejected.")
    req.status, req.reject_reason, req.decided_by, req.decided_at = "rejected", reason, actor_id, utcnow()
    audit.record(outlet_id, actor_id, "stock_request.reject", "stock_request", req.id, {"reason": reason})
    db.session.commit()
    return stock_request_dict(req)


@_retry_on_conflict
def issue_stock_request(outlet_id: int, request_id: int, data: dict, actor_id: int | None = None) -> dict:
    """Issue all or part of a request (I15). Nothing is issued unless every entered line can be covered by usable stock.

    The request becomes `issued` when every line is complete, or when the manager closes it (`close: true`) with some
    lines only part issued; otherwise it stays `approved` and can be issued again."""
    req = get_stock_request(outlet_id, request_id, lock=True)
    if req.status not in OPEN_REQUEST:
        db.session.rollback()
        raise ConflictError(f"A {req.status} request cannot be issued.")
    raw_lines = data.get("lines")
    if not isinstance(raw_lines, list) or not raw_lines:
        db.session.rollback()
        raise ValidationError("Please fix the highlighted fields.", {"lines": "enter a quantity for at least one line"})
    close = bool(data.get("close"))
    by_id = {l.id: l for l in req.lines}
    plan, errors, seen, per_ing = [], {}, set(), {}
    for i, raw in enumerate(raw_lines):
        lf = Fields(raw if isinstance(raw, dict) else {})
        line_id = lf.integer("line_id", gt=0)
        qty = lf.stock_qty("quantity", gt=0)
        key = f"lines[{i}]"
        if lf.errors:
            errors[key] = "; ".join(f"{k} {m}" for k, m in lf.errors.items())
            continue
        line, qty = by_id.get(line_id), qty.quantize(_Q3)
        if line is None:
            errors[key] = "not a line of this request"
        elif line_id in seen:
            errors[key] = "line appears twice"
        elif qty > line.qty_requested - line.qty_issued:
            errors[key] = f"only {(line.qty_requested - line.qty_issued).normalize():f} is still to be issued"
        else:
            seen.add(line_id)
            plan.append((line, qty))
            per_ing[line.ingredient_id] = per_ing.get(line.ingredient_id, ZERO) + qty
    if errors:
        db.session.rollback()
        raise ValidationError("Please fix the highlighted fields.", errors)
    # lock ingredient by ingredient in id order so two issues can never wait on each other
    locked = {}
    for ing_id in sorted(per_ing):
        locked[ing_id] = _lock_batches(outlet_id, ing_id, today(), usable_only=True)
        available = sum((b.qty_remaining for b in locked[ing_id]), ZERO)
        if per_ing[ing_id] > available:
            ing = db.session.get(Ingredient, ing_id)
            db.session.rollback()
            raise ValidationError(f"Only {available.normalize():f} {ing.unit} of {ing.name} is usable.",
                                  {"lines": f"{ing.name}: only {available.normalize():f} {ing.unit} usable stock"},
                                  code="insufficient_stock", extra={"available": float(available), "ingredient_id": ing_id})
    issued = []
    for line, qty in plan:
        ing = db.session.get(Ingredient, line.ingredient_id)
        _draw_down(outlet_id, ing, locked[ing.id], qty, "stock_out", today(), "issued_to_kitchen",
                   f"Kitchen request #{req.id}", actor_id, reference_type="stock_request", reference_id=req.id)
        line.qty_issued = line.qty_issued + qty
        issued.append({"ingredient": ing.name, "quantity": float(qty), "unit": ing.unit})
    complete = all(l.qty_issued >= l.qty_requested for l in req.lines)
    req.status = "issued" if complete or close else "approved"
    if req.decided_by is None:
        req.decided_by, req.decided_at = actor_id, utcnow()
    audit.record(outlet_id, actor_id, "stock_request.issue", "stock_request", req.id,
                 {"lines": len(issued), "status": req.status})
    db.session.commit()
    return {"stock_request": stock_request_dict(req), "issued": issued}


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
    rows = q.order_by(StockMovement.movement_date.desc(), StockMovement.id.desc()).limit(min(max(limit, 1), 200)).offset(min(max(offset, 0), MAX_INT)).all()
    return {"total": total, "rows": [{"id": m.id, "ingredient_id": m.ingredient_id, "ingredient": i.name, "unit": i.unit,
                                      "type": m.movement_type, "quantity": float(m.quantity), "reason": m.reason,
                                      "note": m.note, "date": m.movement_date.isoformat(), "batch_id": m.batch_id}
                                     for m, i in rows]}


def consistency_check(outlet_id: int) -> dict:
    """I16: checks stored stock against the movement history. Read-only; every list should be empty.

    1. movements vs batches: for each ingredient the sum of all movements must equal the sum of batch quantities left;
    2. batches with more left than was ever received;
    3. expired batches that still hold stock (they need a wastage record, they are not an error in the data)."""
    names = {i.id: i for i in Ingredient.query.filter_by(outlet_id=outlet_id)}
    mismatches = []
    for v in stock_invariant_violations(outlet_id):
        ing = names.get(v["ingredient_id"])
        mismatches.append({**v, "ingredient": ing.name if ing else str(v["ingredient_id"]), "unit": ing.unit if ing else None,
                           "difference": round(v["batches"] - v["movements"], 3)})
    over = [{"batch_id": b.id, "ingredient": b.ingredient.name, "batch_no": b.batch_no,
             "qty_received": float(b.qty_received), "qty_remaining": float(b.qty_remaining)}
            for b in StockBatch.query.filter(StockBatch.outlet_id == outlet_id, StockBatch.qty_remaining > StockBatch.qty_received)]
    expired = [b for b in list_batches(outlet_id) if b["expired"]]
    return {"checked_on": today().isoformat(), "batches_checked": StockBatch.query.filter_by(outlet_id=outlet_id).count(),
            "ingredients_checked": len(names), "mismatches": mismatches, "batches_over_received": over,
            "expired_with_stock": expired, "consistent": not mismatches and not over}


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
