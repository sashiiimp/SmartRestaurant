"""Prepared / served / waste recording (Kitchen Operations service, ARCH section 3)."""
from datetime import datetime

from app.extensions import db
from app.models import FoodWaste, PreparationRecord, SalesRecord
from app.models.base import utcnow
from app.models.kitchen import WASTE_REASONS
from app.services import audit
from app.services import data_management_service as dm
from app.services.errors import ConflictError, ValidationError
from app.services.validation import Fields


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
