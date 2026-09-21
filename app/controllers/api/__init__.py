from flask import Blueprint

bp = Blueprint("api", __name__, url_prefix="/api/v1")

from app.controllers.api import alerts, data, forecasts, inventory, kitchen, recommendations, session, users  # noqa: E402,F401
