from flask_login import current_user

from app.controllers.api import bp
from app.services import auth_service
from app.utils.responses import json_body, ok
from app.utils.security import current_outlet_id, roles_required


@bp.route("/users")
@roles_required("admin")
def list_users():
    users = auth_service.list_users(current_outlet_id())
    return ok([auth_service.user_dict(u) for u in users], {"total": len(users)})


@bp.route("/users", methods=["POST"])
@roles_required("admin")
def create_user():
    b = json_body()
    u = auth_service.create_user(current_outlet_id(), b.get("full_name"), b.get("username"), b.get("role"),
                                 b.get("password"), b.get("email"), current_user.id)
    return ok(auth_service.user_dict(u), status=201)


@bp.route("/users/<int:user_id>", methods=["PATCH"])
@roles_required("admin")
def update_user(user_id):
    b = json_body()
    changes = {k: b[k] for k in ("full_name", "email", "role", "is_active") if k in b}
    u = auth_service.update_user(current_outlet_id(), user_id, actor_id=current_user.id, **changes)
    return ok(auth_service.user_dict(u))


@bp.route("/users/<int:user_id>/password", methods=["POST"])
@roles_required("admin")
def reset_password(user_id):
    auth_service.reset_password(current_outlet_id(), user_id, json_body().get("password"), current_user.id)
    return ok({"reset": True})
