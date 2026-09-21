from flask import Blueprint, render_template

from app.utils.security import role_guard

bp = Blueprint("kitchen", __name__, url_prefix="/kitchen")
bp.allowed_roles = frozenset({"kitchen"})
bp.before_request(role_guard("kitchen"))


@bp.route("")
def dashboard():
    return render_template("kitchen/dashboard.html")
