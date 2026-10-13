from flask import request
from flask_login import current_user

from app.controllers.api import bp
from app.services import alert_service as alerts
from app.services import dashboard_service as dash
from app.services import inventory_service as inv
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


@bp.route("/kitchen/pre-orders/<int:pre_order_id>")
@roles_required("admin", "kitchen")
def get_pre_order(pre_order_id):
    return ok(kit.pre_order_detail(current_outlet_id(), pre_order_id))


@bp.route("/kitchen/pre-orders/<int:pre_order_id>", methods=["PATCH"])
@roles_required("kitchen")
def update_pre_order(pre_order_id):
    result = kit.update_pre_order(current_outlet_id(), pre_order_id, json_body(), current_user.id)
    return ok(result, {"warnings": result["warnings"]})


@bp.route("/kitchen/stock-requests")
@roles_required("admin", "kitchen")
def list_kitchen_stock_requests():
    rows = inv.list_stock_requests(current_outlet_id(), request.args.get("status"), detail=True)
    return ok(rows, {"total": len(rows)})


@bp.route("/kitchen/stock-requests", methods=["POST"])
@roles_required("kitchen")
def create_stock_request():
    return ok(inv.create_stock_request(current_outlet_id(), json_body(), current_user.id), status=201)


@bp.route("/kitchen/stock-requests/<int:request_id>/cancel", methods=["POST"])
@roles_required("kitchen")
def cancel_stock_request(request_id):
    return ok(inv.cancel_stock_request(current_outlet_id(), request_id, current_user.id))


@bp.route("/kitchen/shortage-reports", methods=["POST"])
@roles_required("kitchen")
def report_shortage():
    result = alerts.report_shortage(current_outlet_id(), json_body(), current_user.id)
    return ok(result, status=201 if result["created"] else 200)


@bp.route("/kitchen/orders")
@roles_required("admin", "kitchen")
def list_orders():
    day = date_arg("date")
    rows = kit.list_orders(current_outlet_id(), day or date_arg("from"), day or date_arg("to"),
                           request.args.get("status"), int_arg("menu_item_id"))
    return ok(rows, {"total": len(rows)})


@bp.route("/kitchen/orders", methods=["POST"])
@roles_required("kitchen")
def create_order():
    return ok(kit.create_order(current_outlet_id(), json_body(), current_user.id), status=201)


@bp.route("/kitchen/orders/<int:order_id>", methods=["PATCH"])
@roles_required("kitchen")
def update_order(order_id):
    return ok(kit.update_order(current_outlet_id(), order_id, json_body(), current_user.id))


@bp.route("/kitchen/ingredient-usage")
@roles_required("admin", "kitchen")
def get_ingredient_usage():
    return ok(kit.ingredient_usage_for(current_outlet_id(), date_arg("date", today())))


@bp.route("/kitchen/ingredient-usage", methods=["POST"])
@roles_required("kitchen")
def record_ingredient_usage():
    result = kit.record_ingredient_usage(current_outlet_id(), json_body(), current_user.id)
    return ok(result, status=201 if result["created"] else 200)


@bp.route("/kitchen/ingredient-usage/<int:usage_id>", methods=["DELETE"])
@roles_required("kitchen")
def clear_ingredient_usage(usage_id):
    return ok(kit.clear_ingredient_usage(current_outlet_id(), usage_id, current_user.id))


@bp.route("/kitchen/food-usage")
@roles_required("admin", "kitchen")
def get_food_usage():
    return ok(kit.food_usage_for(current_outlet_id(), date_arg("date", today())))


@bp.route("/kitchen/food-usage", methods=["POST"])
@roles_required("kitchen")
def record_food_usage():
    result = kit.record_food_usage(current_outlet_id(), json_body(), current_user.id)
    return ok(result, {"warnings": result["warnings"]}, status=201 if result["created"] else 200)


@bp.route("/kitchen/food-usage/<int:usage_id>", methods=["DELETE"])
@roles_required("kitchen")
def clear_food_usage(usage_id):
    return ok(kit.clear_food_usage(current_outlet_id(), usage_id, current_user.id))
