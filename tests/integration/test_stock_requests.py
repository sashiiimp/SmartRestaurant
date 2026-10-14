"""K11 / I15: kitchen stock requests. Batches as in test_stock_service: usable chicken is 17 kg (B4 is expired)."""
import threading
from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.extensions import db
from app.models import AuditLog, StockBatch, StockMovement
from app.services import inventory_service as inv
from app.services.errors import ConflictError, NotFoundError, ValidationError
from tests.factories import add_batch, make_ingredient, make_user

TODAY = date(2026, 9, 25)


@pytest.fixture()
def world(app):
    chicken = make_ingredient(name="Chicken", unit="kg")
    rice = make_ingredient(name="Rice", unit="kg")
    b = {"B1": add_batch(chicken, 3, received=date(2026, 9, 20), expiry=date(2026, 10, 10), batch_no="B1"),
         "B2": add_batch(chicken, 4, received=date(2026, 9, 21), expiry=date(2026, 10, 5), batch_no="B2"),
         "B3": add_batch(chicken, 10, received=date(2026, 9, 22), expiry=None, batch_no="B3"),
         "B4": add_batch(chicken, 6, received=date(2026, 9, 10), expiry=date(2026, 9, 20), batch_no="B4")}   # expired
    add_batch(rice, 50)
    return {"chicken": chicken, "rice": rice, "b": b, "kitchen": make_user("kitchen")}


def ask(w, chicken=12, rice=None, **extra):
    lines = [{"ingredient_id": w["chicken"].id, "quantity": chicken}]
    if rice:
        lines.append({"ingredient_id": w["rice"].id, "quantity": rice})
    return inv.create_stock_request(1, {"lines": lines, **extra}, w["kitchen"].id)


def line(req, name):
    return next(l["id"] for l in req["lines"] if l["ingredient"] == name)


def remaining(w):
    return {k: b.qty_remaining for k, b in w["b"].items()}


# ---- create -----------------------------------------------------------------------------------------
def test_create_starts_pending_with_lines_and_requester(world):
    r = ask(world, rice=5, note="lunch rush", needed_date=TODAY.isoformat())
    assert (r["status"], r["note"], r["needed_date"], r["line_count"]) == ("pending", "lunch rush", "2026-09-25", 2)
    assert r["requested_by"] and r["summary"] == "Chicken 12 kg, Rice 5 kg"
    assert [(l["ingredient"], l["qty_requested"], l["qty_issued"], l["usable_stock"]) for l in r["lines"]] == [
        ("Chicken", 12.0, 0.0, 17.0), ("Rice", 5.0, 0.0, 50.0)]
    assert AuditLog.query.filter_by(action="stock_request.create").count() == 1
    assert inv.pending_request_count(1) == 1


def test_create_validation(world):
    w = world
    ok = {"ingredient_id": w["chicken"].id, "quantity": 5}
    def fail(**data):
        with pytest.raises(ValidationError) as e:
            inv.create_stock_request(1, {"lines": [ok], **data})
        return e.value.fields
    assert "lines" in fail(lines=[])
    assert "lines[0]" in fail(lines=[{"ingredient_id": w["chicken"].id, "quantity": 0}])
    assert "lines[1]" in fail(lines=[ok, ok])
    assert "lines[0]" in fail(lines=[{"ingredient_id": 999, "quantity": 1}])
    assert "needed_date" in fail(needed_date="2026-09-01")
    assert "note" in fail(note="x" * 256)
    w["rice"].is_active = False; db.session.commit()
    assert "lines[0]" in fail(lines=[{"ingredient_id": w["rice"].id, "quantity": 1}])


# ---- approve / reject / cancel -----------------------------------------------------------------------
def test_approve_reject_cancel_rules(world):
    a, b, c = ask(world), ask(world), ask(world)
    assert inv.approve_stock_request(1, a["id"])["status"] == "approved"
    with pytest.raises(ConflictError):
        inv.approve_stock_request(1, a["id"])                                  # only pending can be approved
    with pytest.raises(ConflictError):
        inv.reject_stock_request(1, a["id"], {"reason": "no"})                # ... or rejected
    with pytest.raises(ValidationError) as e:
        inv.reject_stock_request(1, b["id"], {})
    assert "reason" in e.value.fields
    r = inv.reject_stock_request(1, b["id"], {"reason": "Out of stock until Friday"})
    assert (r["status"], r["reject_reason"]) == ("rejected", "Out of stock until Friday")
    assert inv.cancel_stock_request(1, c["id"])["status"] == "cancelled"
    for rid in (a["id"], b["id"], c["id"]):
        with pytest.raises(ConflictError):
            inv.cancel_stock_request(1, rid)                                   # approved, rejected, cancelled: too late
    with pytest.raises(NotFoundError):
        inv.approve_stock_request(1, 999)


# ---- issue ----------------------------------------------------------------------------------------------
def test_issue_draws_fefo_and_links_the_movements(world):
    w = world
    r = ask(w, chicken=12, rice=5)
    out = inv.issue_stock_request(1, r["id"], {"lines": [{"line_id": line(r, "Chicken"), "quantity": 12},
                                                          {"line_id": line(r, "Rice"), "quantity": 5}]})
    assert out["stock_request"]["status"] == "issued"
    # 12 kg: B2 (expires 5 Oct) 4, B1 (10 Oct) 3, then B3 (no expiry) 5; the expired B4 is never used
    assert remaining(w) == {"B1": 0, "B2": 0, "B3": 5, "B4": 6}
    moves = StockMovement.query.filter_by(reference_type="stock_request").all()
    assert {(m.movement_type, m.reason, m.reference_id) for m in moves} == {("stock_out", "issued_to_kitchen", r["id"])}
    assert sorted(float(m.quantity) for m in moves) == [-5.0, -5.0, -4.0, -3.0]      # 3 chicken batches + 1 rice
    assert inv.usable_map(1)[w["chicken"].id] == Decimal("5")
    assert inv.stock_invariant_violations(1) == []
    assert AuditLog.query.filter_by(action="stock_request.issue").count() == 1


def test_partial_issue_then_complete(world):
    w = world
    r = ask(w, chicken=10)
    lid = r["lines"][0]["id"]
    first = inv.issue_stock_request(1, r["id"], {"lines": [{"line_id": lid, "quantity": 6}]})["stock_request"]
    assert first["status"] == "approved" and first["lines"][0]["qty_outstanding"] == 4.0
    second = inv.issue_stock_request(1, r["id"], {"lines": [{"line_id": lid, "quantity": 4}]})["stock_request"]
    assert second["status"] == "issued" and second["lines"][0]["usable_stock"] is None
    with pytest.raises(ConflictError):
        inv.issue_stock_request(1, r["id"], {"lines": [{"line_id": lid, "quantity": 1}]})   # nothing left, and closed
    assert inv.stock_invariant_violations(1) == []


def test_close_marks_a_part_issued_request_as_issued(world):
    r = ask(world, chicken=10)
    out = inv.issue_stock_request(1, r["id"], {"lines": [{"line_id": r["lines"][0]["id"], "quantity": 6}], "close": True})
    assert out["stock_request"]["status"] == "issued" and out["stock_request"]["lines"][0]["qty_outstanding"] == 4.0


def test_issue_more_than_usable_stock_writes_nothing(world):
    w = world
    r = ask(w, chicken=20, rice=5)                                             # only 17 kg chicken is usable
    lines = [{"line_id": line(r, "Rice"), "quantity": 5}, {"line_id": line(r, "Chicken"), "quantity": 20}]
    with pytest.raises(ValidationError) as e:
        inv.issue_stock_request(1, r["id"], lines and {"lines": lines})
    assert e.value.code == "insufficient_stock" and e.value.extra["available"] == 17.0
    assert StockMovement.query.filter_by(reference_type="stock_request").count() == 0     # rice was not issued either
    assert inv.get_stock_request(1, r["id"]).status == "pending"
    out = inv.issue_stock_request(1, r["id"], {"lines": [{"line_id": line(r, "Chicken"), "quantity": 17}]})
    assert out["stock_request"]["status"] == "approved"


def test_issue_validation(world):
    r = ask(world, chicken=10)
    lid = r["lines"][0]["id"]
    def fail(lines):
        with pytest.raises(ValidationError) as e:
            inv.issue_stock_request(1, r["id"], {"lines": lines})
        return e.value.fields
    assert fail([{"line_id": lid, "quantity": 11}]) == {"lines[0]": "only 10 is still to be issued"}
    assert "lines[1]" in fail([{"line_id": lid, "quantity": 1}, {"line_id": 999, "quantity": 1}])
    assert "lines[1]" in fail([{"line_id": lid, "quantity": 1}, {"line_id": lid, "quantity": 1}])
    assert "lines[0]" in fail([{"line_id": lid, "quantity": 0}])
    assert "lines" in fail([])
    rej = ask(world)
    inv.reject_stock_request(1, rej["id"], {"reason": "no"})
    with pytest.raises(ConflictError):
        inv.issue_stock_request(1, rej["id"], {"lines": [{"line_id": rej["lines"][0]["id"], "quantity": 1}]})


def test_list_puts_open_requests_first_and_filters(world):
    a, b, c, d = ask(world), ask(world), ask(world), ask(world)
    inv.approve_stock_request(1, b["id"])
    inv.cancel_stock_request(1, c["id"])
    inv.reject_stock_request(1, d["id"], {"reason": "no"})
    assert [r["id"] for r in inv.list_stock_requests(1)] == [a["id"], b["id"], d["id"], c["id"]]
    assert [r["id"] for r in inv.list_stock_requests(1, "approved")] == [b["id"]]
    assert "lines" not in inv.list_stock_requests(1)[0]
    with pytest.raises(ValidationError):
        inv.list_stock_requests(1, "bogus")
    assert inv.pending_request_count(1) == 1


@pytest.mark.mysql
def test_concurrent_issues_never_exceed_usable_stock(app):
    """Two parallel issues of 10 kg against 12 kg usable: exactly one succeeds."""
    kitchen = make_user("kitchen")
    ing = make_ingredient(name="Chicken", unit="kg")
    add_batch(ing, 12, received=date(2026, 9, 20), expiry=date(2026, 12, 1))
    ids = []
    for _ in range(2):
        r = inv.create_stock_request(1, {"lines": [{"ingredient_id": ing.id, "quantity": 10}]}, kitchen.id)
        ids.append((r["id"], r["lines"][0]["id"]))
    barrier, results = threading.Barrier(2), []

    def worker(rid, lid):
        with app.app_context():
            barrier.wait()
            try:
                inv.issue_stock_request(1, rid, {"lines": [{"line_id": lid, "quantity": 10}]})
                results.append("ok")
            except ValidationError:
                results.append("rejected")
            except Exception as exc:
                results.append(f"error: {type(exc).__name__}: {exc}")
            finally:
                db.session.remove()

    threads = [threading.Thread(target=worker, args=a) for a in ids]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert sorted(results) == ["ok", "rejected"]
    db.session.rollback()
    assert db.session.query(StockBatch).one().qty_remaining == Decimal("2.000")
    assert inv.stock_invariant_violations(1) == []


# ---- final checks (Oct 2026): approval never moves stock; issuing needs usable stock --------------------------
def test_approve_with_no_usable_stock_is_allowed_and_moves_nothing(world):
    tofu = make_ingredient(name="Tofu", unit="kg")                            # no batches at all
    r = inv.create_stock_request(1, {"lines": [{"ingredient_id": tofu.id, "quantity": 3}]}, world["kitchen"].id)
    before = StockMovement.query.count()
    assert inv.approve_stock_request(1, r["id"])["status"] == "approved"
    assert StockMovement.query.count() == before


def test_issue_with_zero_usable_stock_is_refused_and_writes_nothing(world):
    tofu = make_ingredient(name="Tofu", unit="kg")
    r = inv.create_stock_request(1, {"lines": [{"ingredient_id": tofu.id, "quantity": 3}]}, world["kitchen"].id)
    inv.approve_stock_request(1, r["id"])
    before = StockMovement.query.count()
    with pytest.raises(ValidationError) as e:
        inv.issue_stock_request(1, r["id"], {"lines": [{"line_id": r["lines"][0]["id"], "quantity": 1}]})
    assert e.value.code == "insufficient_stock" and e.value.extra["available"] == 0.0
    assert StockMovement.query.count() == before and inv.get_stock_request(1, r["id"]).status == "approved"


def test_only_expired_stock_counts_as_zero_usable(world):
    milk = make_ingredient(name="Milk", unit="l")
    add_batch(milk, 8, received=date(2026, 9, 10), expiry=date(2026, 9, 20), batch_no="M-OLD")   # expired before today
    r = inv.create_stock_request(1, {"lines": [{"ingredient_id": milk.id, "quantity": 2}]}, world["kitchen"].id)
    assert inv.get_stock_request(1, r["id"]).status == "pending"
    detail = inv.stock_request_dict(inv.get_stock_request(1, r["id"]))
    assert detail["lines"][0]["usable_stock"] == 0.0                          # what the issue form shows
    with pytest.raises(ValidationError) as e:
        inv.issue_stock_request(1, r["id"], {"lines": [{"line_id": r["lines"][0]["id"], "quantity": 2}]})
    assert e.value.code == "insufficient_stock" and e.value.extra["available"] == 0.0
