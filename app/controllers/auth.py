from flask import Blueprint, redirect, render_template, request, session, url_for
from flask_login import current_user, login_user, logout_user

from app.services import auth_service
from app.services.errors import AccountLocked, AuthenticationError
from app.utils.security import roles_required

bp = Blueprint("auth", __name__)


@bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(auth_service.home_url_for(current_user.role))
    error = None
    status = 200
    if request.method == "POST":
        username = request.form.get("username", "")
        try:
            user = auth_service.login(username, request.form.get("password", ""), request.remote_addr)
        except AccountLocked as e:
            error, status = e.message, 429
        except AuthenticationError as e:
            error, status = e.message, 401
        else:
            login_user(user)
            session.permanent = True
            return redirect(auth_service.home_url_for(user.role))
    return render_template("auth/login.html", error=error, username=request.form.get("username", "")), status


@bp.route("/logout", methods=["POST"])
@roles_required("admin", "kitchen", "inventory")
def logout():
    auth_service.logout(current_user.id)
    logout_user()
    session.clear()
    return redirect(url_for("auth.login"))
