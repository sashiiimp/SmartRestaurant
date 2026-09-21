from datetime import datetime, timezone

from sqlalchemy import CheckConstraint

from app.extensions import db

# BIGINT on MariaDB, plain INTEGER on SQLite (which only auto-increments INTEGER keys).
BigInt = db.BigInteger().with_variant(db.Integer(), "sqlite")


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def check(name: str, expr: str) -> CheckConstraint:
    return CheckConstraint(expr, name=name)


def in_list(column: str, values) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


class TimestampMixin:
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=utcnow, onupdate=utcnow)


class OutletScopedMixin:
    """Every operational table carries outlet_id (NFR7)."""

    outlet_id = db.Column(db.Integer, db.ForeignKey("outlets.id"), nullable=False, default=1, index=True)
