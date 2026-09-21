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
