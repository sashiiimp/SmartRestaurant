"""Typed access to the per-outlet settings table (DATABASE.md 2.1)."""
from decimal import Decimal

from app.extensions import db
from app.models import Setting
from app.models.forecast import ALERT_TYPES

DEFAULTS = {
    "safety_buffer_pct": "10",
    "forecast_horizon_days": "7",
    "min_history_days": "35",
    "currency_label": "LKR",
    "data_source_label": "Synthetic demo data",
    "expiry_warning_days": "3",
    "waste_risk_threshold_pct": "15",
    "stockout_lookahead_days": "7",
    "default_lead_time_days": "2",
    **{f"alert.{t}.enabled": "1" for t in ALERT_TYPES},
}


def get(outlet_id: int, key: str) -> str | None:
    row = Setting.query.filter_by(outlet_id=outlet_id, setting_key=key).first()
    if row is not None and row.value is not None:
        return row.value
    return DEFAULTS.get(key)


def get_int(outlet_id: int, key: str) -> int:
    return int(Decimal(get(outlet_id, key)))


def get_decimal(outlet_id: int, key: str) -> Decimal:
    return Decimal(get(outlet_id, key))


def get_bool(outlet_id: int, key: str) -> bool:
    return get(outlet_id, key) in ("1", "true", "True")


def set_value(outlet_id: int, key: str, value, user_id: int | None = None) -> None:
    row = Setting.query.filter_by(outlet_id=outlet_id, setting_key=key).first()
    if row is None:
        row = Setting(outlet_id=outlet_id, setting_key=key)
        db.session.add(row)
    row.value = None if value is None else str(value)
    row.updated_by = user_id
    db.session.commit()


def seed_defaults(outlet_id: int) -> None:
    existing = {s.setting_key for s in Setting.query.filter_by(outlet_id=outlet_id)}
    for key, value in DEFAULTS.items():
        if key not in existing:
            db.session.add(Setting(outlet_id=outlet_id, setting_key=key, value=value))
    db.session.commit()


# ---- admin-editable subset (A6, A7) -----------------------------------------------------------------
EDITABLE = {  # key: (label, min, max)
    "safety_buffer_pct": ("Safety buffer for preparation (%)", 0, 100),
    "expiry_warning_days": ("Warn about expiry this many days ahead", 0, 30),
    "waste_risk_threshold_pct": ("Waste-risk alert above (% of prepared)", 0, 100),
    "stockout_lookahead_days": ("Projected stock-out look-ahead (days)", 1, 7),
    "default_lead_time_days": ("Default supplier lead time (days)", 0, 30),
    "min_history_days": ("Minimum days of history for a model forecast", 14, 120),
}


def list_editable(outlet_id: int) -> dict:
    values = [{"key": k, "label": lab, "min": lo, "max": hi, "value": float(get_decimal(outlet_id, k))}
              for k, (lab, lo, hi) in EDITABLE.items()]
    alerts = [{"key": f"alert.{t}.enabled", "type": t, "enabled": get_bool(outlet_id, f"alert.{t}.enabled")}
              for t in ALERT_TYPES if t != "manual_shortage"]
    return {"values": values, "alerts": alerts, "data_source_label": get(outlet_id, "data_source_label") or ""}


def update_editable(outlet_id: int, data: dict, user_id: int | None = None) -> dict:
    from app.services import audit
    from app.services.validation import Fields

    f = Fields(data)
    for key, (_lab, lo, hi) in EDITABLE.items():
        if key in data:
            f.decimal(key, min=lo, max=hi)
    f.text("data_source_label", required=False, max_len=60)
    if not isinstance(data.get("alerts") or {}, dict):
        f.error("alerts", "must be an object of alert switches")
    f.check()
    for key in EDITABLE:
        if key in f.values and f.values[key] is not None:
            set_value(outlet_id, key, f.values[key].normalize() if f.values[key] == f.values[key].to_integral_value() else f.values[key], user_id)
    if "data_source_label" in data:
        set_value(outlet_id, "data_source_label", (data.get("data_source_label") or "").strip(), user_id)
    for key, val in (data.get("alerts") or {}).items():
        if key in {f"alert.{t}.enabled" for t in ALERT_TYPES}:
            set_value(outlet_id, key, 1 if val else 0, user_id)
    audit.record(outlet_id, user_id, "settings.update", "settings", None, {"keys": sorted(data)})
    from app.extensions import db
    db.session.commit()
    return list_editable(outlet_id)
