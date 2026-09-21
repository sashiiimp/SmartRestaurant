from functools import wraps

from flask import request
from flask_login import current_user

from app.utils.responses import api_error


def is_api_request() -> bool:
    return request.path.startswith("/api/")


def _check(roles):
    """Return None if allowed, else a response (JSON for /api, redirect/403 for pages)."""
    from flask import redirect, render_template, url_for

    if not current_user.is_authenticated:
        if is_api_request():
            return api_error("unauthenticated", "Please log in.", 401)
        return redirect(url_for("auth.login"))
    if current_user.role not in roles:
        if is_api_request():
            return api_error("forbidden", "You do not have access to this resource.", 403)
        return render_template("errors/403.html"), 403
    return None


def roles_required(*roles):
    """Decorator for a single route. The roles are also stored on the function for the RBAC test."""

    def decorator(view):
        @wraps(view)
        def wrapper(*args, **kwargs):
            denied = _check(roles)
            return denied if denied is not None else view(*args, **kwargs)

        wrapper.allowed_roles = frozenset(roles)
        return wrapper

    return decorator


def role_guard(*roles):
    """before_request function for a whole role blueprint (ARCH 7.1)."""

    def guard():
        return _check(roles)

    guard.allowed_roles = frozenset(roles)
    return guard


def current_outlet_id() -> int:
    """Today always the user's outlet (1). Services never read a global (NFR7)."""
    return current_user.outlet_id if current_user.is_authenticated else 1
