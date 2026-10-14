from flask import Blueprint, render_template

from app.utils.navigation import redirect_to_tab, render_hub
from app.utils.security import role_guard

bp = Blueprint("inventory", __name__, url_prefix="/inventory")
bp.allowed_roles = frozenset({"inventory"})
bp.before_request(role_guard("inventory"))


@bp.route("")
def dashboard():
    return render_template("inventory/dashboard.html")


@bp.route("/stock")
def stock():
    """Stock: Stock levels, Record stock."""
    return render_hub("/inventory/stock")


@bp.route("/reorder")
def reorder():
    """Purchasing: Reorder, Ingredient demand, Purchase orders, Suppliers."""
    return render_hub("/inventory/reorder")


@bp.route("/requests")
def requests():
    return render_template("inventory/requests.html")


@bp.route("/movements")
def movements():
    return redirect_to_tab("/inventory/movements")


@bp.route("/forecast")
def forecast():
    return redirect_to_tab("/inventory/forecast")


@bp.route("/suppliers")
def suppliers():
    return redirect_to_tab("/inventory/suppliers")


@bp.route("/purchase-orders")
def purchase_orders():
    return redirect_to_tab("/inventory/purchase-orders")
