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
