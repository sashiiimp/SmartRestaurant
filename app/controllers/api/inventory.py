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
    rows = inv.list_suppliers(current_outlet_id())
    return ok([inv.supplier_dict(s) for s in rows], {"total": len(rows)})


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
