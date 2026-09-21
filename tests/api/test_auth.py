"""SEC-2 .. SEC-7, C1, C3."""
from app import create_app
from app.extensions import db
from app.models import LoginAttempt, User
from app.models.base import utcnow
from tests.conftest import login
from tests.factories import make_user


def test_each_role_lands_on_own_home(app, users):
    for role, home in (("admin", "/admin"), ("kitchen", "/kitchen"), ("inventory", "/inventory")):
        client = app.test_client()
        resp = login(client, users[role].username)
        assert resp.status_code == 302 and resp.headers["Location"].endswith(home)
        assert client.get(home).status_code == 200


def test_wrong_password_and_unknown_user_look_identical(app, users, client):
    a = login(client, users["admin"].username, "wrong-password")
    b = login(client, "no-such-user", "whatever1")
    assert a.status_code == b.status_code == 401
    strip = lambda r: r.get_data(as_text=True).split('name="csrf_token"')[0].split('<div class="alert')[1][:90]
    assert strip(a) == strip(b)
    assert b"Incorrect username or password." in a.get_data()


def test_deactivated_user_cannot_log_in(app, client):
    user = make_user("kitchen", active=False)
    resp = login(client, user.username)
    assert resp.status_code == 401 and b"Incorrect username or password." in resp.get_data()


def test_lockout_after_five_failures_including_unknown_user(app, users, client):
    for _ in range(5):
        assert login(client, "ghost", "bad-password").status_code == 401
    resp = login(client, "ghost", "bad-password")
    assert resp.status_code == 429
    # the real account is unaffected, and a locked real account refuses even the right password
    assert login(app.test_client(), users["admin"].username).status_code == 302
    for _ in range(5):
        login(client, users["kitchen"].username, "bad-password")
    assert login(client, users["kitchen"].username).status_code == 429


def test_lockout_expires(app, users, client):
    for _ in range(5):
        login(client, users["kitchen"].username, "bad-password")
    assert login(client, users["kitchen"].username).status_code == 429
    from datetime import timedelta
    for row in LoginAttempt.query.all():
        row.attempted_at = utcnow() - timedelta(minutes=6)
    db.session.commit()
    # failures are older than the 5 minute lock but still inside the 10 minute window: allowed again
    assert login(client, users["kitchen"].username).status_code == 302


def test_password_is_hashed_and_never_returned(app, users, client):
    user = User.query.filter_by(username=users["admin"].username).one()
    assert "password1" not in user.password_hash and user.password_hash.startswith(("scrypt", "pbkdf2"))
    login(client, user.username)
    body = client.get("/api/v1/me").get_data(as_text=True)
    assert "password" not in body


def test_logout_and_back_button(app, users, client):
    login(client, users["admin"].username)
    resp = client.get("/admin")
    assert resp.headers["Cache-Control"] == "no-store"
    assert client.post("/logout").status_code == 302
    assert client.get("/admin").status_code == 302


def test_me_endpoint(app, users, as_role):
    client = as_role("kitchen")
    data = client.get("/api/v1/me").get_json()["data"]
    assert data["role"] == "kitchen" and data["home_url"] == "/kitchen"


def test_csrf_required_on_writes():
    application = create_app("test")
    application.config["WTF_CSRF_ENABLED"] = True
    with application.app_context():
        db.create_all()
        from app.models import Outlet
        db.session.add(Outlet(id=1, name="x"))
        db.session.commit()
        make_user("admin", username="csrfadmin")
        client = application.test_client()
        page = client.get("/login").get_data(as_text=True)
        token = page.split('name="csrf_token" value="')[1].split('"')[0]
        client.post("/login", data={"username": "csrfadmin", "password": "password1", "csrf_token": token})
        assert client.post("/logout").status_code == 400  # POST without token
        resp = client.post("/logout", data={"csrf_token": token})
        assert resp.status_code == 302
        db.drop_all()


def test_last_admin_cannot_be_deactivated(app, users):
    from app.services import auth_service
    from app.services.errors import ValidationError
    import pytest
    with pytest.raises(ValidationError) as e:
        auth_service.update_user(1, users["admin"].id, is_active=False)
    assert e.value.code == "last_admin"
    second = make_user("admin")
    auth_service.update_user(1, second.id, is_active=False)  # fine: another active admin remains
