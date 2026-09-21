import logging
import uuid

from flask import g, jsonify, render_template, request
from flask_wtf.csrf import CSRFError
from werkzeug.exceptions import HTTPException

from app.services.errors import (
    AccountLocked, AuthenticationError, ConflictError, NotFoundError, ServiceError, ValidationError,
)

log = logging.getLogger("smartrest")


def ok(data=None, meta=None, status: int = 200):
    body = {"data": data}
    if meta is not None:
        body["meta"] = meta
    return jsonify(body), status


def api_error(code: str, message: str, status: int, fields: dict | None = None, extra: dict | None = None):
    err = {"code": code, "message": message}
    if fields:
        err["fields"] = fields
    if extra:
        err.update(extra)
    return jsonify({"error": err}), status


def _is_api() -> bool:
    return request.path.startswith("/api/")


def _page_error(status: int, title: str, message: str):
    return render_template("errors/generic.html", status=status, title=title, message=message,
                           request_id=getattr(g, "request_id", "")), status


def register_error_handlers(app):
    @app.before_request
    def _request_id():
        g.request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:12]

    @app.after_request
    def _add_request_id(resp):
        resp.headers["X-Request-ID"] = getattr(g, "request_id", "")
        return resp

    @app.errorhandler(ServiceError)
    def _service_error(e: ServiceError):
        status = {ValidationError: 422, NotFoundError: 404, ConflictError: 409,
                  AuthenticationError: 401, AccountLocked: 429}.get(type(e), 400)
        if _is_api():
            return api_error(e.code, e.message, status, e.fields, e.extra)
        return _page_error(status, "Problem", e.message)

    @app.errorhandler(CSRFError)
    def _csrf(e):
        if _is_api():
            return api_error("csrf_failed", "Security token missing or expired. Reload the page.", 400)
        return _page_error(400, "Session expired", "Your form expired. Please go back, reload and try again.")

    @app.errorhandler(HTTPException)
    def _http(e: HTTPException):
        codes = {400: "bad_request", 401: "unauthenticated", 403: "forbidden", 404: "not_found",
                 405: "method_not_allowed", 413: "too_large"}
        if _is_api():
            return api_error(codes.get(e.code, "error"), e.description or e.name, e.code)
        if e.code == 403:
            return render_template("errors/403.html"), 403
        if e.code == 404:
            return render_template("errors/404.html"), 404
        return _page_error(e.code or 500, e.name, e.description or "")

    @app.errorhandler(Exception)
    def _unexpected(e: Exception):
        log.exception("Unhandled error [%s] %s %s", getattr(g, "request_id", ""), request.method, request.path)
        try:
            from app.extensions import db
            db.session.rollback()
        except Exception:  # pragma: no cover
            pass
        if _is_api():
            return api_error("server_error", f"Something went wrong (request {getattr(g, 'request_id', '')}).", 500)
        return render_template("errors/500.html", request_id=getattr(g, "request_id", "")), 500


def json_body() -> dict:
    """The JSON request body as a dict ({} when missing); other types are a validation error."""
    from flask import request as _r

    data = _r.get_json(silent=True)
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ValidationError("The request body must be a JSON object.", code="bad_request")
    return data


def date_arg(name: str, default=None):
    from datetime import date

    v = request.args.get(name)
    if not v:
        return default
    try:
        return date.fromisoformat(v)
    except ValueError:
        raise ValidationError("Please fix the highlighted fields.", {name: "must be a date (YYYY-MM-DD)"})


def int_arg(name: str, default=None):
    v = request.args.get(name)
    if v in (None, ""):
        return default
    try:
        return int(v)
    except ValueError:
        raise ValidationError("Please fix the highlighted fields.", {name: "must be a whole number"})


def bool_arg(name: str, default=False) -> bool:
    v = request.args.get(name)
    if v is None:
        return default
    return v.lower() in ("1", "true", "yes")


def csv_response(filename: str, header: list[str], rows: list[list]):
    """Download the same rows the screen shows (A13)."""
    import csv as _csv
    import io

    from flask import Response

    buf = io.StringIO()
    w = _csv.writer(buf)
    w.writerow(header)
    w.writerows(rows)
    return Response(buf.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})
