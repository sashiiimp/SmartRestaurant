from flask import Blueprint, render_template

from app.utils.security import role_guard

bp = Blueprint("admin", __name__, url_prefix="/admin")
bp.allowed_roles = frozenset({"admin"})
bp.before_request(role_guard("admin"))


@bp.route("")
def dashboard():
    return render_template("admin/dashboard.html")


@bp.route("/users")
def users():
    return render_template("admin/users.html")


@bp.route("/catalog")
def catalog():
    return render_template("admin/catalog.html")


@bp.route("/data")
def data():
    return render_template("admin/data.html")


@bp.route("/models")
def models():
    return render_template("admin/models.html")


@bp.route("/monitor")
def monitor():
    return render_template("admin/monitor.html")
