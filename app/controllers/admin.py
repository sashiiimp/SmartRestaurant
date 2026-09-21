from flask import Blueprint, render_template

from app.utils.security import role_guard

bp = Blueprint("admin", __name__, url_prefix="/admin")
bp.allowed_roles = frozenset({"admin"})
bp.before_request(role_guard("admin"))


@bp.route("")
def dashboard():
    return render_template("admin/dashboard.html")
