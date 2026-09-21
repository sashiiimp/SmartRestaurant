"""SEC-1: every route x every role (C2). A route with no declared role rule fails the test."""
import re

import pytest

from tests.conftest import login

ROLES = ("admin", "kitchen", "inventory")
PUBLIC = {"static", "auth.login", "index"}
SKIP_IN_ROLE_LOOP = {"auth.logout"}  # tested separately: it ends the session


def declared_roles(app, rule):
    view = app.view_functions[rule.endpoint]
    roles = getattr(view, "allowed_roles", None)
    if roles is None and "." in rule.endpoint:
        roles = getattr(app.blueprints.get(rule.endpoint.split(".")[0]), "allowed_roles", None)
    return roles


def url_for_rule(rule):
    return re.sub(r"<[^>]+>", "1", rule.rule)


def all_routes(app):
    for rule in app.url_map.iter_rules():
        if rule.endpoint in PUBLIC:
            continue
        for method in sorted(rule.methods - {"HEAD", "OPTIONS"}):
            yield rule, method


def test_every_route_declares_roles(app):
    missing = [r.rule for r, _ in all_routes(app) if not declared_roles(app, r)]
    assert not missing, f"routes without a role rule: {missing}"


def request_as(client, method, url):
    kwargs = {"json": {}} if url.startswith("/api/") and method in ("POST", "PUT", "PATCH") else {}
    return client.open(url, method=method, **kwargs)


def test_anonymous_is_refused_everywhere(app, client):
    for rule, method in all_routes(app):
        url = url_for_rule(rule)
        resp = request_as(client, method, url)
        if url.startswith("/api/"):
            assert resp.status_code == 401, (method, url, resp.status_code)
            assert resp.get_json()["error"]["code"] == "unauthenticated"
        else:
            assert resp.status_code == 302 and "/login" in resp.headers["Location"], (method, url, resp.status_code)


@pytest.mark.parametrize("role", ROLES)
def test_route_by_role_matrix(app, users, role):
    client = app.test_client()
    assert login(client, users[role].username).status_code == 302
    for rule, method in all_routes(app):
        if rule.endpoint in SKIP_IN_ROLE_LOOP:
            continue
        url = url_for_rule(rule)
        allowed = role in declared_roles(app, rule)
        resp = request_as(client, method, url)
        if allowed:
            assert resp.status_code not in (401, 403, 500), (role, method, url, resp.status_code)
        else:
            assert resp.status_code == 403, (role, method, url, resp.status_code)
            if url.startswith("/api/"):
                assert resp.get_json()["error"]["code"] == "forbidden"
