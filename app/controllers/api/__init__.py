from flask import Blueprint

bp = Blueprint("api", __name__, url_prefix="/api/v1")

from app.controllers.api import session  # noqa: E402,F401  (registers routes on bp)
