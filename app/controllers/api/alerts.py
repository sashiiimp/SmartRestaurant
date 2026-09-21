from flask import request
from flask_login import current_user

from app.controllers.api import bp
from app.services import alert_service
from app.utils.responses import bool_arg, ok
from app.utils.security import current_outlet_id, roles_required


@bp.route("/alerts")
@roles_required("admin", "kitchen", "inventory")
def list_alerts():
    out = alert_service.list_alerts(current_outlet_id(), current_user.role, request.args.get("status", "open"),
                                    request.args.get("type"), bool_arg("refresh"))
    return ok(out["rows"], {"total": len(out["rows"]), "counts": out["counts"]})


@bp.route("/alerts/<int:alert_id>/acknowledge", methods=["POST"])
@roles_required("admin", "kitchen", "inventory")
def acknowledge(alert_id):
    return ok(alert_service.acknowledge(current_outlet_id(), alert_id, current_user.role, current_user.id))


@bp.route("/alerts/run", methods=["POST"])
@roles_required("admin")
def run_alerts():
    return ok(alert_service.evaluate(current_outlet_id()))
