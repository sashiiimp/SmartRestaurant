"""B7 (review 7 Oct 2026): the administrator can have its own seed password."""
from werkzeug.security import check_password_hash

from app.models import User


def _ok(username, password):
    return check_password_hash(User.query.filter_by(username=username).one().password_hash, password)


def test_per_account_seed_password_overrides_the_shared_one(app, monkeypatch):
    from app.seed.seeder import seed_base
    monkeypatch.setenv("SEED_PASSWORD", "shared-pass-1")
    monkeypatch.setenv("SEED_PASSWORD_ADMIN", "boss-own-pass-2")
    seed_base()
    assert _ok("admin", "boss-own-pass-2") and not _ok("admin", "shared-pass-1")
    assert _ok("kitchen1", "shared-pass-1") and _ok("inventory1", "shared-pass-1")


def test_seed_command_never_prints_a_password_from_the_environment(app, monkeypatch):
    monkeypatch.delenv("SEED_PASSWORD", raising=False)
    monkeypatch.setenv("SEED_PASSWORD_ADMIN", "boss-own-pass-3")
    out = app.test_cli_runner().invoke(args=["smartrest", "seed"]).output
    assert "boss-own-pass-3" not in out
    assert "Generated password for the accounts without their own" in out   # kitchen1 and inventory1 share one
    line = next(l for l in out.splitlines() if l.startswith("Generated password"))
    generated = line.rsplit(": ", 1)[1].strip()
    assert _ok("kitchen1", generated) and _ok("admin", "boss-own-pass-3")
