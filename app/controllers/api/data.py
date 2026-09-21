from flask import request
from flask_login import current_user

from app.controllers.api import bp
from app.services import data_management_service as dm
from app.services.errors import ValidationError
from app.utils.responses import bool_arg, date_arg, json_body, ok
from app.utils.security import current_outlet_id, roles_required

ALL = ("admin", "kitchen", "inventory")


# ---- menu and recipes (A4, A5) ---------------------------------------------------------------
@bp.route("/menu-items")
@roles_required(*ALL)
def list_menu_items():
    items = dm.list_menu_items(current_outlet_id(), active_only=bool_arg("active"))
    return ok([dm.menu_item_dict(m) for m in items], {"total": len(items)})


@bp.route("/menu-items", methods=["POST"])
@roles_required("admin")
def create_menu_item():
    return ok(dm.menu_item_dict(dm.create_menu_item(current_outlet_id(), json_body(), current_user.id)), status=201)


@bp.route("/menu-items/<int:item_id>", methods=["PATCH"])
@roles_required("admin")
def update_menu_item(item_id):
    return ok(dm.menu_item_dict(dm.update_menu_item(current_outlet_id(), item_id, json_body(), current_user.id)))


@bp.route("/menu-items/<int:item_id>/availability", methods=["PATCH"])
@roles_required("kitchen")
def set_availability(item_id):
    flag = json_body().get("is_available")
    if not isinstance(flag, bool):
        raise ValidationError("Please fix the highlighted fields.", {"is_available": "must be true or false"})
    return ok(dm.menu_item_dict(dm.set_availability(current_outlet_id(), item_id, flag, current_user.id)))


@bp.route("/menu-items/<int:item_id>/recipe")
@roles_required(*ALL)
def get_recipe(item_id):
    return ok(dm.recipe_dict(dm.get_recipe(current_outlet_id(), item_id)))


@bp.route("/menu-items/<int:item_id>/recipe", methods=["PUT"])
@roles_required("admin")
def put_recipe(item_id):
    lines = dm.set_recipe(current_outlet_id(), item_id, json_body().get("lines"), current_user.id)
    return ok(dm.recipe_dict(lines))


# ---- imports (A14, A15) ----------------------------------------------------------------------
def _upload():
    f = request.files.get("file")
    if f is None:
        raise ValidationError("Choose a CSV file to upload.", {"file": "is required"}, code="bad_file")
    return f.read()


def _dry_run() -> bool:
    return request.form.get("dry_run", "true").lower() not in ("0", "false", "no")


@bp.route("/sales/import", methods=["POST"])
@roles_required("admin")
def import_sales():
    return ok(dm.import_sales_csv(current_outlet_id(), _upload(), _dry_run(), request.form.get("on_conflict", "skip"),
                                  actor_id=current_user.id))


@bp.route("/holidays/import", methods=["POST"])
@roles_required("admin")
def import_holidays():
    return ok(dm.import_holidays_csv(current_outlet_id(), _upload(), _dry_run(), actor_id=current_user.id))


@bp.route("/weather/import", methods=["POST"])
@roles_required("admin")
def import_weather():
    return ok(dm.import_weather_csv(current_outlet_id(), _upload(), _dry_run(),
                                    on_conflict=request.form.get("on_conflict", "skip"), actor_id=current_user.id))


@bp.route("/holidays")
@roles_required("admin")
def list_holidays():
    rows = dm.list_holidays(current_outlet_id(), date_arg("from"), date_arg("to"))
    return ok([dm.holiday_dict(h) for h in rows], {"total": len(rows)})


@bp.route("/weather")
@roles_required("admin")
def list_weather():
    rows = dm.list_weather(current_outlet_id(), date_arg("from"), date_arg("to"))
    return ok([dm.weather_dict(w) for w in rows], {"total": len(rows)})


@bp.route("/promotions")
@roles_required("admin")
def list_promotions():
    rows = dm.list_promotions(current_outlet_id())
    return ok([dm.promotion_dict(p) for p in rows], {"total": len(rows)})


@bp.route("/promotions", methods=["POST"])
@roles_required("admin")
def create_promotion():
    return ok(dm.promotion_dict(dm.create_promotion(current_outlet_id(), json_body(), current_user.id)), status=201)


@bp.route("/promotions/<int:promotion_id>", methods=["PATCH"])
@roles_required("admin")
def patch_promotion(promotion_id):
    flag = json_body().get("is_active")
    if not isinstance(flag, bool):
        raise ValidationError("Please fix the highlighted fields.", {"is_active": "must be true or false"})
    return ok(dm.promotion_dict(dm.set_promotion_active(current_outlet_id(), promotion_id, flag)))
