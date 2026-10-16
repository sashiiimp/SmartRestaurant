from flask import Blueprint, render_template

from app.services import alert_service
from app.utils.navigation import redirect_to_tab, render_hub, role_access
from app.utils.security import role_guard

bp = Blueprint("admin", __name__, url_prefix="/admin")
bp.allowed_roles = frozenset({"admin"})
bp.before_request(role_guard("admin"))


@bp.route("")
def dashboard():
    return render_template("admin/dashboard.html")


@bp.route("/users")
def users():
    """Administration: Users (with the Role access section) and Settings & alerts."""
    return render_hub("/admin/users", role_access=role_access(), alert_access=alert_service.visibility())


@bp.route("/catalog")
def catalog():
    """Menu & Recipes (BOM): Menu items (with each item's recipe), BOM overview, Ingredients."""
    return render_hub("/admin/catalog")


@bp.route("/models")
def models():
    """Forecasting: Models & runs, Import data."""
    return render_hub("/admin/models")


@bp.route("/monitor")
def monitor():
    return render_template("admin/monitor.html")


@bp.route("/data")
def data():
    return redirect_to_tab("/admin/data")


@bp.route("/settings")
def settings():
    return redirect_to_tab("/admin/settings")


@bp.route("/inventory")
def inventory():
    return redirect_to_tab("/admin/inventory")
