from flask import request
from flask_login import current_user

from app.controllers.api import bp
from app.services import dashboard_service as dash
from app.services import kitchen_service as kit
from app.utils.dates import today
from app.utils.responses import date_arg, int_arg, json_body, ok
from app.utils.security import current_outlet_id, roles_required


@bp.route("/kitchen/prepared", methods=["POST"])
@roles_required("kitchen")
def prepared():
    return ok(kit.record_prepared(current_outlet_id(), json_body(), current_user.id), status=201)


@bp.route("/kitchen/waste", methods=["POST"])
@roles_required("kitchen")
def waste():
    result = kit.record_waste(current_outlet_id(), json_body(), current_user.id)
    return ok(result, {"warnings": result["warnings"]}, status=201)


@bp.route("/sales/served", methods=["POST"])
@roles_required("kitchen")
def served():
    result = kit.record_served(current_outlet_id(), json_body(), current_user.id)
    return ok(result, {"warnings": result["warnings"]}, status=201)


@bp.route("/kitchen/daily-summary")
@roles_required("admin", "kitchen")
def daily_summary():
    return ok(dash.kitchen_daily_summary(current_outlet_id(), date_arg("date", today())))


@bp.route("/kitchen/pre-orders")
@roles_required("admin", "kitchen")
def list_pre_orders():
    rows = kit.list_pre_orders(current_outlet_id(), date_arg("from", today()), date_arg("to"),
                               request.args.get("status"), int_arg("menu_item_id"))
    return ok(rows, {"total": len(rows)})


@bp.route("/kitchen/pre-orders", methods=["POST"])
@roles_required("kitchen")
def create_pre_order():
    result = kit.create_pre_order(current_outlet_id(), json_body(), current_user.id)
    return ok(result, {"warnings": result["warnings"]}, status=201)


@bp.route("/kitchen/pre-orders/<int:pre_order_id>", methods=["PATCH"])
@roles_required("kitchen")
def update_pre_order(pre_order_id):
    result = kit.update_pre_order(current_outlet_id(), pre_order_id, json_body(), current_user.id)
    return ok(result, {"warnings": result["warnings"]})
