from flask_login import current_user

from app.controllers.api import bp
from app.services import settings
from app.utils.responses import json_body, ok
from app.utils.security import current_outlet_id, roles_required


@bp.route("/settings")
@roles_required("admin")
def get_settings():
    return ok(settings.list_editable(current_outlet_id()))


@bp.route("/settings", methods=["PUT"])
@roles_required("admin")
def put_settings():
    return ok(settings.update_editable(current_outlet_id(), json_body(), current_user.id))
