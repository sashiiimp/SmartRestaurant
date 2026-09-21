import logging
import os
from logging.handlers import RotatingFileHandler

from flask import Flask, redirect, url_for
from flask_login import current_user

from app.config import get_config
from app.extensions import csrf, db, login_manager, migrate


def create_app(config_name: str | None = None, overrides: dict | None = None) -> Flask:
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(get_config(config_name))
    app.config.update(overrides or {})
    os.makedirs(app.instance_path, exist_ok=True)

    db.init_app(app)
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
        from app.utils.navigation import nav_links
        home = _a.home_url_for(current_user.role) if current_user.is_authenticated else "/"
        return {"data_source_label": label, "business_today": today(), "nav_links": nav_links, "home_href": home}

    @app.after_request
    def _no_store(resp):
        # Back button must not reveal protected pages after logout (C3).
        if current_user.is_authenticated:
            resp.headers.setdefault("Cache-Control", "no-store")
        return resp

    if not app.testing:
        handler = RotatingFileHandler(os.path.join(app.instance_path, "smartrest.log"), maxBytes=1_000_000, backupCount=3)
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        logging.getLogger("smartrest").addHandler(handler)
        logging.getLogger("smartrest").setLevel(logging.INFO)

    from app.cli import register_cli
    register_cli(app)
    return app
