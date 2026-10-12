"""Alert rules, de-duplication and auto-close (Alert service, ML_PLAN B4)."""
from datetime import timedelta

from app.extensions import db
from app.models import Alert, FoodWaste, ForecastRun, MenuItem, PreparationRecord, Setting, StockBatch, StockMovement
from app.models.base import utcnow
from app.models.forecast import ALERT_TYPES
from app.services import audit
from app.services import forecasting_service as fs
from app.services import inventory_service as inv
from app.services import recommendation_service as rec
from app.services import settings
from app.services.errors import NotFoundError, ValidationError
from app.services.validation import Fields
from app.utils.dates import today

REFRESH_SECONDS = 60
ZERO = inv.ZERO

# Who sees which alert type (API.md section 6).
VISIBLE_TO = {
    "low_stock": {"admin", "inventory"}, "critical_stock": {"admin", "inventory"},
    "projected_stockout": {"admin", "kitchen", "inventory"}, "expiry_warning": {"admin", "inventory"},
    "waste_risk": {"admin", "kitchen"}, "forecast_failed": {"admin"}, "manual_shortage": {"admin", "inventory"},
}
COMPUTED_TYPES = [t for t in ALERT_TYPES if t != "manual_shortage"]


def _fmt(x) -> str:
    return f"{x.normalize():f}"


def _desired(outlet_id: int) -> list[dict]:
    """The set of alert conditions that are true right now."""
    day = today()
    out = []
    ings = inv.list_ingredients(outlet_id, active_only=True)
    usable = inv.usable_map(outlet_id, day)
    look = min(settings.get_int(outlet_id, "stockout_lookahead_days"), 7)
    fc = rec.get_ingredient_forecast(outlet_id, day, 7)
    fc_by_id = {r["ingredient_id"]: r for r in fc["ingredients"]}
    for ing in ings:
        u = usable.get(ing.id, ZERO)
        status, critical = inv.stock_status(u, ing)
        base = {"entity_type": "ingredient", "entity_id": ing.id, "target_date": None}
        if critical:
            out.append({**base, "alert_type": "critical_stock", "severity": "critical",
                        "dedupe_key": f"critical_stock:ingredient:{ing.id}",
                        "message": f"{ing.name} is critically low: {_fmt(u)} {ing.unit} usable (minimum {_fmt(ing.min_stock)})",
                        "details": {"usable": float(u), "min_stock": float(ing.min_stock)}})
        elif status == "low":
            out.append({**base, "alert_type": "low_stock", "severity": "warning",
                        "dedupe_key": f"low_stock:ingredient:{ing.id}",
                        "message": f"{ing.name} is low: {_fmt(u)} {ing.unit} usable (reorder level {_fmt(ing.reorder_level)})",
                        "details": {"usable": float(u), "reorder_level": float(ing.reorder_level)}})
        row = fc_by_id.get(ing.id)
        if row and row["first_shortfall_date"]:
            d = row["first_shortfall_date"]
            days_away = (type(day).fromisoformat(d) - day).days
            if days_away < look:
                out.append({**base, "alert_type": "projected_stockout", "target_date": type(day).fromisoformat(d),
                            "severity": "critical" if days_away <= 1 else "warning",
                            "dedupe_key": f"projected_stockout:ingredient:{ing.id}",
                            "message": f"{ing.name} will run short on {d} (short by {row['short_by']:.2f} {ing.unit})",
                            "details": {"first_shortfall_date": d, "short_by": row["short_by"], "usable": row["usable_stock"]}})

    warn_days = settings.get_int(outlet_id, "expiry_warning_days")
    q = StockBatch.query.filter(StockBatch.outlet_id == outlet_id, StockBatch.qty_remaining > 0,
                                StockBatch.expiry_date.isnot(None), StockBatch.expiry_date <= day + timedelta(days=warn_days))
    for b in q:
        expired = b.expiry_date < day
        msg = (f"{b.ingredient.name}: batch {b.batch_no} EXPIRED on {b.expiry_date} ({_fmt(b.qty_remaining)} {b.ingredient.unit} "
               f"left). Record it as wastage." if expired else
               f"{b.ingredient.name}: batch {b.batch_no} expires on {b.expiry_date} ({_fmt(b.qty_remaining)} {b.ingredient.unit} left)")
        out.append({"alert_type": "expiry_warning", "severity": "critical" if expired else "warning",
                    "entity_type": "batch", "entity_id": b.id, "target_date": b.expiry_date,
                    "dedupe_key": f"expiry_warning:batch:{b.id}", "message": msg,
                    "details": {"ingredient_id": b.ingredient_id, "expired": expired}})

    threshold = settings.get_decimal(outlet_id, "waste_risk_threshold_pct")
    start = day - timedelta(days=7)
    prepared = dict(db.session.query(PreparationRecord.menu_item_id, db.func.sum(PreparationRecord.quantity)).filter(
        PreparationRecord.outlet_id == outlet_id, PreparationRecord.prep_date >= start,
        PreparationRecord.prep_date < day).group_by(PreparationRecord.menu_item_id).all())
    wasted = dict(db.session.query(FoodWaste.menu_item_id, db.func.sum(FoodWaste.quantity)).filter(
        FoodWaste.outlet_id == outlet_id, FoodWaste.waste_date >= start, FoodWaste.waste_date < day
    ).group_by(FoodWaste.menu_item_id).all())
    for item in MenuItem.query.filter_by(outlet_id=outlet_id, is_active=True):
        p, w = int(prepared.get(item.id, 0)), int(wasted.get(item.id, 0))
        if p >= 20 and w * 100 > p * threshold:
            pct = w * 100 / p
            out.append({"alert_type": "waste_risk", "severity": "warning", "entity_type": "menu_item",
                        "entity_id": item.id, "target_date": None, "dedupe_key": f"waste_risk:menu_item:{item.id}",
                        "message": f"{item.name}: {pct:.0f}% of prepared portions were wasted in the last 7 days "
                                   f"(limit {threshold.normalize():f}%). Consider preparing less.",
                        "details": {"prepared": p, "wasted": w, "waste_pct": round(pct, 1)}})

    last = ForecastRun.query.filter_by(outlet_id=outlet_id).order_by(ForecastRun.id.desc()).first()
    if last and last.status in ("failed", "skipped"):
        out.append({"alert_type": "forecast_failed", "severity": "critical" if last.status == "failed" else "warning",
                    "entity_type": "system", "entity_id": None, "target_date": last.as_of_date,
                    "dedupe_key": "forecast_failed:system",
                    "message": f"The last forecast run {last.status}: {last.reason or 'no reason recorded'}",
                    "details": {"run_id": last.id}})
    return out


def _retry_on_duplicate(fn):
    """The dashboard and the alert bell load together, so two requests can evaluate at once. Both see an alert missing
    and insert it, and the second insert fails on the unique open_key (1062). Evaluation is idempotent: roll back and
    run it again on a fresh snapshot, where the other request's alerts are already there."""
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


@inv._retry_on_conflict  # the dashboard and the alert bell both refresh lazily, so two requests can evaluate at once (1020)
@_retry_on_duplicate
def evaluate(outlet_id: int) -> dict:
    """Recompute the true conditions; open the missing ones and close those that no longer hold. Idempotent."""
    desired = {d["dedupe_key"]: d for d in _desired(outlet_id) if settings.get_bool(outlet_id, f"alert.{d['alert_type']}.enabled")}
    open_alerts = {a.dedupe_key: a for a in Alert.query.filter(Alert.outlet_id == outlet_id,
                                                                Alert.status.in_(("open", "acknowledged")))}
    opened = closed = updated = 0
    now = utcnow()
    for key, d in desired.items():
        cur = open_alerts.get(key)
        if cur is None:
            db.session.add(Alert(outlet_id=outlet_id, open_key=key, status="open", created_at=now, **d))
            opened += 1
        elif (cur.severity, cur.message, cur.target_date) != (d["severity"], d["message"], d["target_date"]):
            cur.severity, cur.message, cur.target_date, cur.details = d["severity"], d["message"], d["target_date"], d["details"]
            updated += 1
    for key, cur in open_alerts.items():
        if cur.alert_type == "manual_shortage":
            # a reported shortage clears itself once that ingredient has been restocked or corrected upwards
            if _restocked_since(outlet_id, cur):
                cur.status, cur.open_key, cur.closed_at, cur.closed_reason = "closed", None, now, "restocked"
                closed += 1
            continue
        if key in desired:
            continue
        if not settings.get_bool(outlet_id, f"alert.{cur.alert_type}.enabled"):
            continue  # disabled types are left alone (A7)
        cur.status, cur.open_key, cur.closed_at, cur.closed_reason = "closed", None, now, "cleared"
        closed += 1
    settings.set_value(outlet_id, "alerts_last_run_at", now.isoformat())
    return {"opened": opened, "closed": closed, "updated": updated, "open": len(desired)}


def _last_movement_id(outlet_id: int, ingredient_id) -> int:
    return int(db.session.query(db.func.coalesce(db.func.max(StockMovement.id), 0)).filter(
        StockMovement.outlet_id == outlet_id, StockMovement.ingredient_id == ingredient_id).scalar())


def _restocked_since(outlet_id: int, alert: Alert) -> bool:
    """A positive movement recorded after the report. Compared by movement id (always increasing), not by time:
    MySQL and MariaDB keep DATETIME in whole seconds, so a report and a stock-in in the same second carry the same
    timestamp. Alerts reported before 9 Oct 2026 have no stored id and fall back to the time comparison."""
    q = db.session.query(StockMovement.id).filter(
        StockMovement.outlet_id == outlet_id, StockMovement.ingredient_id == alert.entity_id, StockMovement.quantity > 0)
    last_id = (alert.details or {}).get("last_movement_id")
    q = q.filter(StockMovement.id > last_id) if isinstance(last_id, int) else q.filter(StockMovement.created_at > alert.created_at)
    return q.first() is not None


def report_shortage(outlet_id: int, data: dict, actor_id: int | None = None) -> dict:
    """K12: the kitchen reports an ingredient shortage (for example, less found than the system says). This opens a
    critical `manual_shortage` alert for Inventory and Admin. A second report for the same ingredient updates the open one."""
    f = Fields(data)
    ing_id = f.integer("ingredient_id", gt=0)
    note = f.text("note", required=False, max_len=150)
    f.check()
    ing = inv.get_ingredient(outlet_id, ing_id)
    key = f"manual_shortage:ingredient:{ing.id}"
    message = f"Kitchen reports a shortage of {ing.name}" + (f": {note}" if note else "")
    alert = Alert.query.filter_by(outlet_id=outlet_id, open_key=key).first()
    created = alert is None
    # the restock check starts from the stock movements that existed at the first report (kept on a repeat report)
    previous = (alert.details or {}).get("last_movement_id") if alert else None
    details = {"note": note, "reported_by": actor_id,
               "last_movement_id": previous if isinstance(previous, int) else _last_movement_id(outlet_id, ing.id)}
    if created:
        alert = Alert(outlet_id=outlet_id, alert_type="manual_shortage", severity="critical", entity_type="ingredient",
                      entity_id=ing.id, target_date=today(), message=message, details=details, status="open",
                      dedupe_key=key, open_key=key, created_at=utcnow())
        db.session.add(alert)
    else:
        alert.message, alert.details, alert.status = message, details, "open"
        alert.acknowledged_by = alert.acknowledged_at = None
    db.session.flush()
    audit.record(outlet_id, actor_id, "shortage.report", "ingredient", ing.id, {"note": note})
    db.session.commit()
    return {**alert_dict(alert), "created": created}


def _stale(outlet_id: int) -> bool:
    row = Setting.query.filter_by(outlet_id=outlet_id, setting_key="alerts_last_run_at").first()
    if not row or not row.value:
        return True
    from datetime import datetime
    return (utcnow() - datetime.fromisoformat(row.value)).total_seconds() > REFRESH_SECONDS


def alert_dict(a: Alert) -> dict:
    return {"id": a.id, "alert_type": a.alert_type, "severity": a.severity, "entity_type": a.entity_type,
            "entity_id": a.entity_id, "target_date": a.target_date.isoformat() if a.target_date else None,
            "message": a.message, "details": a.details, "status": a.status, "created_at": a.created_at.isoformat() + "Z"}


def list_alerts(outlet_id: int, role: str, status: str | None = "open", alert_type: str | None = None,
                refresh: bool = False) -> dict:
    """Role-filtered alerts. Evaluates first when the last evaluation is over 60 s old, or when refresh is set."""
    if refresh or _stale(outlet_id):
        evaluate(outlet_id)
    q = Alert.query.filter(Alert.outlet_id == outlet_id)
    if status == "open":
        q = q.filter(Alert.status.in_(("open", "acknowledged")))
    elif status:
        q = q.filter(Alert.status == status)
    if alert_type:
        q = q.filter(Alert.alert_type == alert_type)
    order = db.case((Alert.severity == "critical", 0), (Alert.severity == "warning", 1), else_=2)
    rows = [a for a in q.order_by(order, Alert.created_at.desc()).all() if role in VISIBLE_TO.get(a.alert_type, ())]
    counts = {"critical": 0, "warning": 0, "info": 0}
    for a in rows:
        if a.status == "open":
            counts[a.severity] += 1
    return {"rows": [alert_dict(a) for a in rows], "counts": counts}


def acknowledge(outlet_id: int, alert_id: int, role: str, user_id: int | None = None) -> dict:
    a = Alert.query.filter_by(id=alert_id, outlet_id=outlet_id).first()
    if not a or role not in VISIBLE_TO.get(a.alert_type, ()):
        raise NotFoundError("Alert not found.")
    if a.status == "closed":
        raise ValidationError("That alert is already closed.", code="conflict")
    a.status, a.acknowledged_by, a.acknowledged_at = "acknowledged", user_id, utcnow()
    db.session.commit()
    return alert_dict(a)
