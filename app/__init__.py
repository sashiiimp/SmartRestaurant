import logging
import os
from logging.handlers import RotatingFileHandler

from flask import Flask, redirect, url_for
from flask_login import current_user

from app.config import get_config
from app.extensions import csrf, db, login_manager, migrate


CSP = ("default-src 'self'; script-src 'self' 'unsafe-eval'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
       "font-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'self'; form-action 'self'; "
       "frame-ancestors 'none'")


def create_app(config_name: str | None = None, overrides: dict | None = None) -> Flask:
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(get_config(config_name))
    app.config.update(overrides or {})
    os.makedirs(app.instance_path, exist_ok=True)
    if app.config.get("SECRET_KEY") == "dev-only-change-me" and os.environ.get("APP_ENV") == "prod":
        raise RuntimeError("Set SECRET_KEY in the environment before running with APP_ENV=prod.")
    from app.utils.db_check import check_server, check_url
    check_url(app.config)   # DATABASE_URL set, and MySQL where it is required

    if app.config.get("TRUST_PROXY"):
        from werkzeug.middleware.proxy_fix import ProxyFix
        n = app.config["TRUST_PROXY"]
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=n, x_proto=n, x_host=n)

    db.init_app(app)
    app.config["DATABASE_SERVER"] = check_server(app, db)   # MySQL 8.4 or later where required (not MariaDB)
    migrate.init_app(app, db)
    csrf.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"

    from app import models  # noqa: F401  (register tables with the metadata)
    from app.services import auth_service, settings
    from app.utils.dates import today
    from app.utils.responses import register_error_handlers

    @login_manager.user_loader
    def _load_user(user_id):
        return auth_service.get_user(user_id)

    @login_manager.unauthorized_handler
    def _unauthorized():
        from app.utils.security import is_api_request
        from app.utils.responses import api_error
        if is_api_request():
            return api_error("unauthenticated", "Please log in.", 401)
        return redirect(url_for("auth.login"))

    register_error_handlers(app)

    from app.controllers import admin, auth, inventory, kitchen
    from app.controllers.api import bp as api_bp

    app.register_blueprint(auth.bp)
    app.register_blueprint(admin.bp)
    app.register_blueprint(kitchen.bp)
    app.register_blueprint(inventory.bp)
    app.register_blueprint(api_bp)

    @app.route("/")
    def index():
        if current_user.is_authenticated:
            return redirect(auth_service.home_url_for(current_user.role))
        return redirect(url_for("auth.login"))

    @app.context_processor
    def _template_globals():
        label = None
        if current_user.is_authenticated:
            label = settings.get(current_user.outlet_id, "data_source_label")
        from app.services import auth_service as _a
        from app.utils.navigation import nav_groups, nav_links
        home = _a.home_url_for(current_user.role) if current_user.is_authenticated else "/"
        restaurant = None
        if current_user.is_authenticated:
            from app.models import Outlet
            outlet = db.session.get(Outlet, current_user.outlet_id)
            restaurant = outlet.name if outlet else None
        return {"data_source_label": label, "business_today": today(), "nav_links": nav_links, "nav_groups": nav_groups, "home_href": home,
                "restaurant_name": restaurant}

    @app.after_request
    def _no_store(resp):
        # Back button must not reveal protected pages after logout (C3).
        if current_user.is_authenticated:
            resp.headers.setdefault("Cache-Control", "no-store")
        return resp

    @app.after_request
    def _security_headers(resp):
        # Everything is served from this origin (vendored libraries, no CDN). 'unsafe-eval' is needed because Vue
        # compiles the in-page templates at run time; there is no inline script, and pages cannot be framed.
        resp.headers.setdefault("Content-Security-Policy", CSP)
        resp.headers.setdefault("X-Frame-Options", "DENY")
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("Referrer-Policy", "same-origin")
        return resp

    if not app.testing:
        handler = RotatingFileHandler(os.path.join(app.instance_path, "smartrest.log"), maxBytes=1_000_000, backupCount=3)
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        logging.getLogger("smartrest").addHandler(handler)
        logging.getLogger("smartrest").setLevel(logging.INFO)

    from app.cli import register_cli
    register_cli(app)
    return app
