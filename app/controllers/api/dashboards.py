from flask_login import current_user

from app.controllers.api import bp
from app.services import dashboard_service as dash
from app.utils.dates import today
from app.utils.responses import date_arg, ok
from app.utils.security import current_outlet_id, roles_required


@bp.route("/dashboards/kitchen")
@roles_required("kitchen", "admin")
def kitchen_dashboard():
    return ok(dash.kitchen_dashboard(current_outlet_id(), date_arg("date", today()), current_user.role))


@bp.route("/dashboards/inventory")
@roles_required("inventory", "admin")
def inventory_dashboard():
    return ok(dash.inventory_dashboard(current_outlet_id(), current_user.role))
