from flask import Blueprint, render_template

from app.utils.security import role_guard

bp = Blueprint("inventory", __name__, url_prefix="/inventory")
bp.allowed_roles = frozenset({"inventory"})
bp.before_request(role_guard("inventory"))


@bp.route("")
def dashboard():
    return render_template("inventory/dashboard.html")


@bp.route("/stock")
def stock():
    return render_template("inventory/stock.html")


@bp.route("/movements")
def movements():
    return render_template("inventory/movements.html")


@bp.route("/forecast")
def forecast():
    return render_template("inventory/forecast.html")


@bp.route("/reorder")
def reorder():
    return render_template("inventory/reorder.html")


@bp.route("/suppliers")
def suppliers():
    return render_template("inventory/suppliers.html")


@bp.route("/purchase-orders")
def purchase_orders():
    return render_template("inventory/purchase_orders.html")


@bp.route("/requests")
def requests():
    return render_template("inventory/requests.html")
