from app.extensions import db
from app.models.base import BigInt, OutletScopedMixin, TimestampMixin, check, in_list, utcnow

ROLES = ("admin", "kitchen", "inventory")


class Outlet(TimestampMixin, db.Model):
    __tablename__ = "outlets"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    address = db.Column(db.String(255))
    contact = db.Column(db.String(120))
    opening_days = db.Column(db.String(60))
    opening_hours = db.Column(db.String(60))
    timezone = db.Column(db.String(40), nullable=False, default="Asia/Colombo")
    is_active = db.Column(db.Boolean, nullable=False, default=True)


class User(OutletScopedMixin, TimestampMixin, db.Model):
    __tablename__ = "users"
    __table_args__ = (check("role", in_list("role", ROLES)),)
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), nullable=False, unique=True)
    full_name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(160))
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    last_login_at = db.Column(db.DateTime)
    # Part of the session id. Raising it ends every session of this user at once (logout, password reset,
    # deactivation), which a signed cookie alone cannot do (C3).
    session_version = db.Column(db.Integer, nullable=False, default=0, server_default="0")

    # Flask-Login protocol (implemented here so models stay free of framework imports).
    @property
    def is_authenticated(self) -> bool:
        return True

    @property
    def is_anonymous(self) -> bool:
        return False

    def get_id(self) -> str:
        return f"{self.id}:{self.session_version}"


class LoginAttempt(db.Model):
    __tablename__ = "login_attempts"
    __table_args__ = (db.Index("ix_login_attempts_username_attempted_at", "username", "attempted_at"),)
    id = db.Column(BigInt, primary_key=True)
    username = db.Column(db.String(80), nullable=False)
    attempted_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    success = db.Column(db.Boolean, nullable=False, default=False)
    ip_address = db.Column(db.String(45))


class AuditLog(OutletScopedMixin, db.Model):
    __tablename__ = "audit_logs"
    __table_args__ = (db.Index("ix_audit_logs_outlet_created", "outlet_id", "created_at"),)
    id = db.Column(BigInt, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    action = db.Column(db.String(60), nullable=False)
    entity_type = db.Column(db.String(40))
    entity_id = db.Column(db.String(40))
    detail = db.Column(db.JSON)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
