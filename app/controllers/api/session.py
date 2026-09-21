from flask_login import current_user

from app.controllers.api import bp
from app.services import auth_service
from app.utils.responses import ok
from app.utils.security import roles_required


@bp.route("/me")
@roles_required("admin", "kitchen", "inventory")
def me():
    return ok({"id": current_user.id, "username": current_user.username, "full_name": current_user.full_name,
               "role": current_user.role, "home_url": auth_service.home_url_for(current_user.role)})
