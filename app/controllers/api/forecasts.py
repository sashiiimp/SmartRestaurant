from datetime import timedelta

from flask import current_app
from flask_login import current_user

from app.controllers.api import bp
from app.services import forecasting_service as fs
from app.utils.dates import today
from app.utils.responses import date_arg, int_arg, json_body, ok
from app.utils.security import current_outlet_id, roles_required


@bp.route("/forecasts")
@roles_required("admin", "kitchen", "inventory")
def get_forecasts():
    start = date_arg("from", today())
    end = date_arg("to", start + timedelta(days=6))
    out = fs.get_forecasts(current_outlet_id(), start, end, int_arg("item_id"))
    return ok(out["rows"], {"total": len(out["rows"]), **out["meta"]})


@bp.route("/forecast-runs")
@roles_required("admin")
def list_runs():
    rows = fs.list_runs(current_outlet_id(), int_arg("limit", 30))
    return ok(rows, {"total": len(rows)})


@bp.route("/forecast-runs", methods=["POST"])
@roles_required("admin")
def create_run():
    b = json_body()
    as_of = date_arg("as_of")
    result = fs.run_forecast(current_outlet_id(), as_of, b.get("horizon_days"), trigger="admin",
                             actor_id=current_user.id)
    return ok(result, status=201)


@bp.route("/model-versions")
@roles_required("admin")
def list_models():
    rows = fs.list_model_versions(current_outlet_id())
    return ok([fs.model_version_dict(m) for m in rows], {"total": len(rows)})


@bp.route("/model-versions", methods=["POST"])
@roles_required("admin")
def train():
    result = fs.train_model(current_outlet_id(), current_app.config["MODEL_DIR"], actor_id=current_user.id)
    return ok(result, status=201)


@bp.route("/model-versions/<int:version_id>/activate", methods=["POST"])
@roles_required("admin")
def activate(version_id):
    mv = fs.activate_model(current_outlet_id(), version_id, current_user.id)
    return ok(fs.model_version_dict(mv))


@bp.route("/forecasts/accuracy")
@roles_required("admin")
def accuracy():
    end = date_arg("to", today() - timedelta(days=1))
    return ok(fs.accuracy(current_outlet_id(), date_arg("from", end - timedelta(days=27)), end, int_arg("item_id")))
