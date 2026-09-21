from flask_login import current_user

from app.controllers.api import bp
from app.services import inventory_service as inv
from app.utils.dates import today
from app.utils.responses import bool_arg, date_arg, int_arg, json_body, ok
from app.utils.security import current_outlet_id, roles_required
from flask import request

ALL = ("admin", "kitchen", "inventory")


@bp.route("/ingredients")
@roles_required(*ALL)
def list_ingredients():
    rows = inv.list_ingredients(current_outlet_id(), active_only=bool_arg("active"))
    return ok([inv.ingredient_dict(i) for i in rows], {"total": len(rows)})


@bp.route("/ingredients", methods=["POST"])
@roles_required("inventory")
def create_ingredient():
    return ok(inv.ingredient_dict(inv.create_ingredient(current_outlet_id(), json_body(), current_user.id)), status=201)


@bp.route("/ingredients/<int:ingredient_id>", methods=["PATCH"])
@roles_required("inventory")
def update_ingredient(ingredient_id):
    return ok(inv.ingredient_dict(inv.update_ingredient(current_outlet_id(), ingredient_id, json_body(), current_user.id)))


@bp.route("/suppliers")
@roles_required("admin", "inventory")
def list_suppliers():
    rows = inv.list_suppliers(current_outlet_id(), active_only=bool_arg("active"))
    return ok([inv.supplier_dict(s) for s in rows], {"total": len(rows)})


@bp.route("/suppliers", methods=["POST"])
@roles_required("inventory")
def create_supplier():
    return ok(inv.supplier_dict(inv.create_supplier(current_outlet_id(), json_body(), current_user.id)), status=201)


@bp.route("/suppliers/<int:supplier_id>", methods=["PATCH"])
@roles_required("inventory")
def update_supplier(supplier_id):
    return ok(inv.supplier_dict(inv.update_supplier(current_outlet_id(), supplier_id, json_body(), current_user.id)))


@bp.route("/stock/levels")
@roles_required("admin", "kitchen", "inventory")
def stock_levels():
    rows = inv.stock_levels(current_outlet_id())
    counts = {"ok": 0, "low": 0, "out": 0}
    for r in rows:
        counts[r["status"]] += 1
    return ok(rows, {"total": len(rows), "counts": counts})


@bp.route("/stock/batches")
@roles_required("admin", "inventory")
def stock_batches():
    rows = inv.list_batches(current_outlet_id(), int_arg("ingredient_id"), int_arg("expiring_within_days"))
    return ok(rows, {"total": len(rows)})


@bp.route("/stock/movements")
@roles_required("admin", "inventory")
def stock_movements():
    out = inv.list_movements(current_outlet_id(), int_arg("ingredient_id"), request.args.get("type"),
                             date_arg("from"), date_arg("to"), int_arg("limit", 50), int_arg("offset", 0))
    return ok(out["rows"], {"total": out["total"], "limit": int_arg("limit", 50), "offset": int_arg("offset", 0)})


@bp.route("/stock/in", methods=["POST"])
@roles_required("inventory")
def stock_in():
    return ok(inv.record_stock_in(current_outlet_id(), json_body(), current_user.id), status=201)


@bp.route("/stock/out", methods=["POST"])
@roles_required("inventory")
def stock_out():
    return ok(inv.record_stock_out(current_outlet_id(), json_body(), current_user.id), status=201)


@bp.route("/stock/wastage", methods=["POST"])
@roles_required("inventory")
def stock_wastage():
    return ok(inv.record_wastage(current_outlet_id(), json_body(), current_user.id), status=201)


@bp.route("/stock/adjustments", methods=["POST"])
@roles_required("inventory")
def stock_adjustment():
    return ok(inv.record_adjustment(current_outlet_id(), json_body(), current_user.id), status=201)


@bp.route("/purchase-orders")
@roles_required("admin", "inventory")
def list_purchase_orders():
    rows = inv.list_purchase_orders(current_outlet_id(), request.args.get("status"))
    return ok(rows, {"total": len(rows)})


@bp.route("/purchase-orders", methods=["POST"])
@roles_required("inventory")
def create_purchase_order():
    return ok(inv.create_purchase_order(current_outlet_id(), json_body(), current_user.id), status=201)


@bp.route("/purchase-orders/<int:po_id>")
@roles_required("admin", "inventory")
def get_purchase_order(po_id):
    return ok(inv.purchase_order_dict(inv.get_purchase_order(current_outlet_id(), po_id)))


@bp.route("/purchase-orders/<int:po_id>/send", methods=["POST"])
@roles_required("inventory")
def send_purchase_order(po_id):
    return ok(inv.send_purchase_order(current_outlet_id(), po_id, current_user.id))


@bp.route("/purchase-orders/<int:po_id>/receive", methods=["POST"])
@roles_required("inventory")
def receive_purchase_order(po_id):
    return ok(inv.receive_purchase_order(current_outlet_id(), po_id, json_body(), current_user.id))


@bp.route("/purchase-orders/<int:po_id>/cancel", methods=["POST"])
@roles_required("inventory")
def cancel_purchase_order(po_id):
    return ok(inv.cancel_purchase_order(current_outlet_id(), po_id, current_user.id))


@bp.route("/stock-requests")
@roles_required("admin", "inventory")
def list_stock_requests():
    rows = inv.list_stock_requests(current_outlet_id(), request.args.get("status"), detail=bool_arg("detail"))
    return ok(rows, {"total": len(rows), "pending": inv.pending_request_count(current_outlet_id())})


@bp.route("/stock-requests/<int:request_id>")
@roles_required("admin", "inventory")
def get_stock_request(request_id):
    return ok(inv.stock_request_dict(inv.get_stock_request(current_outlet_id(), request_id)))


@bp.route("/stock-requests/<int:request_id>/approve", methods=["POST"])
@roles_required("inventory")
def approve_stock_request(request_id):
    return ok(inv.approve_stock_request(current_outlet_id(), request_id, current_user.id))


@bp.route("/stock-requests/<int:request_id>/reject", methods=["POST"])
@roles_required("inventory")
def reject_stock_request(request_id):
    return ok(inv.reject_stock_request(current_outlet_id(), request_id, json_body(), current_user.id))


@bp.route("/stock-requests/<int:request_id>/issue", methods=["POST"])
@roles_required("inventory")
def issue_stock_request(request_id):
    return ok(inv.issue_stock_request(current_outlet_id(), request_id, json_body(), current_user.id))


@bp.route("/stock/consistency")
@roles_required("admin", "inventory")
def stock_consistency():
    return ok(inv.consistency_check(current_outlet_id()))
