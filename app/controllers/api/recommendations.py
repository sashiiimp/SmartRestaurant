from flask_login import current_user

from app.controllers.api import bp
from app.services import recommendation_service as rec
from app.utils.dates import today
from app.utils.responses import date_arg, int_arg, json_body, ok
from app.utils.security import current_outlet_id, roles_required


@bp.route("/recommendations/prep")
@roles_required("admin", "kitchen")
def prep_plan():
    return ok(rec.get_prep_plan(current_outlet_id(), date_arg("date", today())))


@bp.route("/recommendations/prep/decisions", methods=["POST"])
@roles_required("kitchen")
def prep_decision():
    return ok(rec.decide(current_outlet_id(), json_body(), current_user.id), status=201)


@bp.route("/recommendations/requirements")
@roles_required("admin", "kitchen", "inventory")
def requirements():
    return ok(rec.get_requirements(current_outlet_id(), date_arg("date", today())))


@bp.route("/recommendations/ingredient-forecast")
@roles_required("admin", "inventory")
def ingredient_forecast():
    return ok(rec.get_ingredient_forecast(current_outlet_id(), date_arg("from", today()), int_arg("days", 7)))


@bp.route("/recommendations/reorder")
@roles_required("admin", "inventory")
def reorder():
    rows = rec.get_reorder_suggestions(current_outlet_id())
    return ok(rows, {"total": len(rows)})
