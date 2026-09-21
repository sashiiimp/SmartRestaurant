"""Users, roles and login checks (C1, C2, A2, A3)."""
import os
from datetime import timedelta

from werkzeug.security import check_password_hash, generate_password_hash

from app.extensions import db
from app.models import LoginAttempt, User
from app.models.base import utcnow
from app.models.user import ROLES
from app.services import audit
from app.services.errors import AccountLocked, AuthenticationError, ConflictError, NotFoundError, ValidationError

MAX_FAILURES = 5
FAILURE_WINDOW = timedelta(minutes=10)
LOCK_TIME = timedelta(minutes=5)
MIN_PASSWORD_LEN = 8

HOME_URLS = {"admin": "/admin", "kitchen": "/kitchen", "inventory": "/inventory"}


def home_url_for(role: str) -> str:
    return HOME_URLS[role]


def hash_password(password: str) -> str:
    if os.environ.get("SMARTREST_FAST_HASH"):  # tests only: scrypt is deliberately slow
        return generate_password_hash(password, method="pbkdf2:sha256:1000")
    return generate_password_hash(password)


def _is_locked(username: str) -> bool:
    now = utcnow()
    start = now - FAILURE_WINDOW
    last_success = (db.session.query(db.func.max(LoginAttempt.attempted_at))
                    .filter(LoginAttempt.username == username, LoginAttempt.success.is_(True)).scalar())
    if last_success and last_success > start:
        start = last_success
    q = db.session.query(db.func.count(LoginAttempt.id), db.func.max(LoginAttempt.attempted_at)).filter(
        LoginAttempt.username == username, LoginAttempt.success.is_(False), LoginAttempt.attempted_at > start)
    count, last_failure = q.one()
    return bool(count >= MAX_FAILURES and last_failure and now < last_failure + LOCK_TIME)


def login(username: str, password: str, ip: str | None = None) -> User:
    """Return the user or raise. The error never says whether the username exists (C1)."""
    username = (username or "").strip().lower()
    if _is_locked(username):
        raise AccountLocked("Too many attempts. Try again in a few minutes.")
    user = User.query.filter_by(username=username).first() if username else None
    ok = bool(user and user.is_active and check_password_hash(user.password_hash, password or ""))
    if not user:  # keep timing similar for unknown usernames
        check_password_hash(generate_password_hash("x"), password or "")
    db.session.add(LoginAttempt(username=username, success=ok, ip_address=ip))
    if not ok:
        db.session.commit()
        raise AuthenticationError("Incorrect username or password.")
    user.last_login_at = utcnow()
    db.session.commit()
    return user


def username_exists(username: str) -> bool:
    return User.query.filter_by(username=username.strip().lower()).first() is not None


def get_user(user_id) -> User | None:
    """Loader for sessions: a deactivated user's session stops working at once."""
    user = db.session.get(User, int(user_id))
    return user if user and user.is_active else None


def _validate_user_fields(full_name, username, role, email=None):
    errors = {}
    if not (full_name or "").strip():
        errors["full_name"] = "is required"
    elif len(full_name) > 120:
        errors["full_name"] = "is too long"
    if not (username or "").strip():
        errors["username"] = "is required"
    elif len(username) > 80:
        errors["username"] = "is too long"
    if role not in ROLES:
        errors["role"] = "must be one of: " + ", ".join(ROLES)
    if email and len(email) > 160:
        errors["email"] = "is too long"
    if errors:
        raise ValidationError("Please fix the highlighted fields.", errors)


def create_user(outlet_id: int, full_name: str, username: str, role: str, password: str,
                email: str | None = None, actor_id: int | None = None) -> User:
    _validate_user_fields(full_name, username, role, email)
    if len(password or "") < MIN_PASSWORD_LEN:
        raise ValidationError("Please fix the highlighted fields.",
                              {"password": f"must be at least {MIN_PASSWORD_LEN} characters"})
    username = username.strip().lower()
    if User.query.filter_by(username=username).first():
        raise ConflictError("That username is already taken.", code="duplicate_record")
    user = User(outlet_id=outlet_id, full_name=full_name.strip(), username=username, email=email,
                role=role, password_hash=hash_password(password))
    db.session.add(user)
    db.session.flush()
    audit.record(outlet_id, actor_id, "user.create", "user", user.id, {"role": role})
    db.session.commit()
    return user


def list_users(outlet_id: int) -> list[User]:
    return User.query.filter_by(outlet_id=outlet_id).order_by(User.username).all()


def update_user(outlet_id: int, user_id: int, actor_id: int | None = None, **changes) -> User:
    user = User.query.filter_by(id=user_id, outlet_id=outlet_id).first()
    if not user:
        raise NotFoundError("User not found.")
    new_role = changes.get("role", user.role)
    new_active = changes.get("is_active", user.is_active)
    _validate_user_fields(changes.get("full_name", user.full_name), user.username, new_role,
                          changes.get("email", user.email))
    removes_admin = user.role == "admin" and user.is_active and (new_role != "admin" or not new_active)
    if removes_admin:
        other_admins = User.query.filter(User.outlet_id == outlet_id, User.role == "admin",
                                         User.is_active.is_(True), User.id != user.id).count()
        if other_admins == 0:
            raise ValidationError("The last active administrator cannot be deactivated or changed.",
                                  code="last_admin")
    if new_role != user.role:
        audit.record(outlet_id, actor_id, "user.role_change", "user", user.id,
                     {"from": user.role, "to": new_role})
    if new_active != user.is_active:
        audit.record(outlet_id, actor_id, "user.activate" if new_active else "user.deactivate", "user", user.id)
    for field in ("full_name", "email", "role", "is_active"):
        if field in changes:
            setattr(user, field, changes[field])
    db.session.commit()
    return user


def reset_password(outlet_id: int, user_id: int, new_password: str, actor_id: int | None = None) -> None:
    user = User.query.filter_by(id=user_id, outlet_id=outlet_id).first()
    if not user:
        raise NotFoundError("User not found.")
    if len(new_password or "") < MIN_PASSWORD_LEN:
        raise ValidationError("Please fix the highlighted fields.",
                              {"password": f"must be at least {MIN_PASSWORD_LEN} characters"})
    user.password_hash = hash_password(new_password)
    audit.record(outlet_id, actor_id, "user.password_reset", "user", user.id)
    db.session.commit()


def user_dict(u: User) -> dict:
    return {"id": u.id, "username": u.username, "full_name": u.full_name, "email": u.email, "role": u.role,
            "is_active": u.is_active, "last_login_at": u.last_login_at.isoformat() + "Z" if u.last_login_at else None}
