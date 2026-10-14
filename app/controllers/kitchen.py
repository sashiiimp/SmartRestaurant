from flask import Blueprint, render_template

from app.utils.navigation import redirect_to_tab, render_hub
from app.utils.security import role_guard

bp = Blueprint("kitchen", __name__, url_prefix="/kitchen")
bp.allowed_roles = frozenset({"kitchen"})
bp.before_request(role_guard("kitchen"))


@bp.route("")
def dashboard():
    return render_template("kitchen/dashboard.html")


@bp.route("/prep")
def prep():
    """Plan & prepare: Prep plan, 7-day forecast."""
    return render_hub("/kitchen/prep")


@bp.route("/record")
def record():
    return render_template("kitchen/record.html")


@bp.route("/requirements")
def requirements():
    """Ingredients: Needs & shortages, Stock requests."""
    return render_hub("/kitchen/requirements")


@bp.route("/orders")
def orders():
    return render_template("kitchen/orders.html")


@bp.route("/forecast")
def forecast():
    return redirect_to_tab("/kitchen/forecast")


@bp.route("/stock-requests")
def stock_requests():
    return redirect_to_tab("/kitchen/stock-requests")
