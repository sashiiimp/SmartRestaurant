"""PREP-AUTO-1 .. 14: the first prepared portions of an undecided item accept today's recommendation automatically.

Hand-worked values: Chicken Burger, forecast 47.3, buffer 10%, batch 6 -> 52.03 -> recommended 54 (TESTING.md 4.1, P1).
With 70 confirmed pre-orders the plan never goes below them: max(52.03, 70) = 70 -> 72 (12 batches of 6).
"""
import threading
from datetime import date, timedelta

import pytest
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import AuditLog, PreOrder, PreparationRecord, RecipeLine, Recommendation
from app.services import kitchen_service as kit
from app.services import recommendation_service as rec
from app.services.errors import ConflictError
from tests.factories import make_ingredient, make_item, make_user
from tests.integration.test_kitchen_recommendation import add_forecast

TODAY = date(2026, 9, 25)


@pytest.fixture()
def burger(app):
    item = make_item(name="Chicken Burger", batch_size=6)
    add_forecast(item, TODAY, "47.3")
    add_forecast(item, TODAY - timedelta(days=1), "47.3")
    return item


def plan_row(item, day=TODAY):
    return next(r for r in rec.get_prep_plan(1, day)["items"] if r["menu_item_id"] == item.id)


def prepare(item, qty, day=TODAY, actor=None):
    """As the kitchen API records it: with the automatic acceptance of an undecided item."""
    return kit.record_prepared(1, {"menu_item_id": item.id, "date": day.isoformat(), "quantity": qty}, actor_id=actor,
                               decide_first=rec.accept_on_first_prepared)


def plans(item, day=TODAY):
    return Recommendation.query.filter_by(menu_item_id=item.id, target_date=day).all()


def decisions_audited(item):
    return [a for a in AuditLog.query.order_by(AuditLog.id) if a.action.startswith("recommendation.") and a.entity_id == str(item.id)]


def test_first_prepared_entry_accepts_the_current_recommendation(burger):
    """PREP-AUTO-1: same snapshot as Accept, preparation started, the response says so."""
    cook = make_user("kitchen")
    out = prepare(burger, 24, actor=cook.id)
    assert out["auto_accepted"] == {"final_qty": 54} and out["total_prepared"] == 24
    [p] = plans(burger)
    assert (p.status, p.recommended_qty, p.final_qty, p.prep_status) == ("accepted", 54, 54, "in_progress")
    assert (float(p.forecast_qty), float(p.buffer_pct), p.preorder_qty, p.batch_size) == (47.3, 10.0, 0, 6)
    assert p.forecast_id is not None and p.decided_by == cook.id and p.prep_started_at is not None and p.override_reason is None
    r = plan_row(burger)
    assert (r["status"], r["final_qty"], r["prep_status"], r["prepared_so_far"], r["decision_source"]) == ("accepted", 54, "in_progress", 24, "auto")


def test_automatic_acceptance_is_audited_apart_from_a_manual_one(burger):
    """PREP-AUTO-2: one accept entry marked auto, plus the prepared entry; the manual accept carries no auto flag."""
    prepare(burger, 24)
    [a] = decisions_audited(burger)
    assert a.action == "recommendation.accept"
    assert a.detail == {"date": "2026-09-25", "recommended": 54, "final": 54, "auto": True, "trigger": "first_prepared"}
    assert AuditLog.query.filter_by(action="prepared.record").count() == 1
    other = make_item(name="Beef Burger", batch_size=6)
    add_forecast(other, TODAY, "47.3")
    rec.decide(1, {"menu_item_id": other.id, "date": "2026-09-25", "action": "accept"})
    [m] = decisions_audited(other)
    assert "auto" not in m.detail and plan_row(other)["decision_source"] == "manual"


def test_later_entries_add_up_and_do_not_decide_again(burger):
    """PREP-AUTO-3: 24 + 30 = 54; still one plan and one decision entry."""
    prepare(burger, 24)
    out = prepare(burger, 30)
    assert out["auto_accepted"] is None and out["total_prepared"] == 54
    assert len(plans(burger)) == 1 and len(decisions_audited(burger)) == 1
    assert PreparationRecord.query.count() == 2


def test_an_existing_manual_accept_is_kept(burger):
    """PREP-AUTO-4"""
    rec.decide(1, {"menu_item_id": burger.id, "date": "2026-09-25", "action": "accept"})
    out = prepare(burger, 10)
    assert out["auto_accepted"] is None
    r = plan_row(burger)
    assert (r["status"], r["final_qty"], r["prep_status"], r["decision_source"]) == ("accepted", 54, "in_progress", "manual")
    assert len(decisions_audited(burger)) == 1


def test_a_changed_plan_is_never_replaced(burger):
    """PREP-AUTO-5: the change (override) and its reason stay."""
    rec.decide(1, {"menu_item_id": burger.id, "date": "2026-09-25", "action": "override", "final_qty": 40, "reason": "rain"})
    prepare(burger, 10)
    r = plan_row(burger)
    assert (r["status"], r["final_qty"], r["override_reason"], r["prep_status"]) == ("overridden", 40, "rain", "in_progress")
    assert [a.action for a in decisions_audited(burger)] == ["recommendation.override"]


def test_no_forecast_records_the_portions_without_a_plan(app):
    """PREP-AUTO-6"""
    item = make_item(name="Veg Kottu")
    out = prepare(item, 5)
    assert out["auto_accepted"] is None and out["total_prepared"] == 5 and plans(item) == []
    assert plan_row(item)["status"] == "no_forecast"


def test_a_past_date_is_never_accepted_automatically(burger):
    """PREP-AUTO-7: a late entry for yesterday is recorded; plans for past dates are not decided (same rule as Accept)."""
    yesterday = TODAY - timedelta(days=1)
    out = prepare(burger, 12, day=yesterday)
    assert out["auto_accepted"] is None and plans(burger, yesterday) == []
    assert plan_row(burger, yesterday)["status"] == "suggested"


def test_an_inactive_item_is_not_accepted(app):
    """PREP-AUTO-8"""
    item = make_item(name="Old Special", batch_size=6, active=False)
    add_forecast(item, TODAY, "10")
    out = prepare(item, 3)
    assert out["auto_accepted"] is None and plans(item) == []


def test_an_unavailable_but_active_item_is_accepted_like_accept_would(burger):
    """PREP-AUTO-9: availability is a menu flag, not a planning rule (Accept allows it too)."""
    burger.is_available = False
    db.session.commit()
    assert prepare(burger, 6)["auto_accepted"] == {"final_qty": 54}


def test_confirmed_pre_orders_are_part_of_the_accepted_snapshot(burger):
    """PREP-AUTO-10: 70 confirmed pre-orders lift the plan to 72; pending ones do not count."""
    db.session.add_all([PreOrder(outlet_id=1, menu_item_id=burger.id, target_date=TODAY, quantity=70, status="confirmed"),
                        PreOrder(outlet_id=1, menu_item_id=burger.id, target_date=TODAY, quantity=50, status="pending")])
    db.session.commit()
    assert prepare(burger, 12)["auto_accepted"] == {"final_qty": 72}
    [p] = plans(burger)
    assert (p.preorder_qty, p.recommended_qty, p.final_qty) == (70, 72, 72)


def test_a_later_change_to_the_recommendation_keeps_the_plan_and_shows_the_new_figure(burger):
    """PREP-AUTO-11: after acceptance the plan is fixed; a new forecast moves only the recommendation, and an explicit
    Accept (manual) takes the new figure."""
    prepare(burger, 12)
    add_forecast(burger, TODAY, "60")                      # re-run: 60 x 1.1 = 66 -> 66
    r = plan_row(burger)
    assert (r["final_qty"], r["recommended_qty"], r["decision_source"]) == (54, 66, "auto")
    out = rec.decide(1, {"menu_item_id": burger.id, "date": "2026-09-25", "action": "accept"})
    assert out["final_qty"] == 66 and any("already started" in w for w in out["warnings"])
    assert plan_row(burger)["decision_source"] == "manual"


def test_finishing_below_the_plan_still_works_after_automatic_acceptance(burger):
    """PREP-AUTO-12: Finish preparation (done) with 40 of 54 warns and keeps the figures; Reopen still works."""
    prepare(burger, 40)
    out = rec.set_prep_status(1, {"menu_item_id": burger.id, "date": "2026-09-25", "action": "done"})
    assert out["prep_status"] == "done" and out["warnings"] == ["Prepared (40) is 14 below the plan (54)."]
    with pytest.raises(ConflictError):
        rec.decide(1, {"menu_item_id": burger.id, "date": "2026-09-25", "action": "accept"})
    assert rec.set_prep_status(1, {"menu_item_id": burger.id, "date": "2026-09-25", "action": "reopen"})["prep_status"] == "in_progress"


def test_ingredient_requirements_are_the_same_before_and_after(burger):
    """PREP-AUTO-13: requirements use the suggestion until a decision exists, then the decision: both are 54 x recipe."""
    ing = make_ingredient(name="Chicken", unit="kg")
    db.session.add(RecipeLine(menu_item_id=burger.id, ingredient_id=ing.id, quantity_per_portion=0.12))
    db.session.commit()
    before = rec.get_requirements(1, TODAY)["ingredients"]
    prepare(burger, 6)
    after = rec.get_requirements(1, TODAY)["ingredients"]
    assert before == after and abs(after[0]["required"] - 6.48) < 1e-9


def test_without_decide_first_the_kitchen_service_only_records(burger):
    """PREP-AUTO-0: kitchen_service on its own (e.g. history loading) never decides a plan."""
    out = kit.record_prepared(1, {"menu_item_id": burger.id, "date": "2026-09-25", "quantity": 5})
    assert out["auto_accepted"] is None and plans(burger) == [] and plan_row(burger)["status"] == "suggested"


def test_a_duplicate_plan_from_a_simultaneous_entry_is_retried_and_counted_once(burger, monkeypatch):
    """PREP-AUTO-14: the other cook's plan wins the unique (item, date) key; this entry is rolled back and recorded
    again on the fresh snapshot: portions counted once, one plan, one automatic acceptance."""
    real, calls = rec.accept_on_first_prepared, []

    def racing(outlet_id, item, day, actor_id=None):
        calls.append(1)
        if len(calls) == 1:
            raise IntegrityError("INSERT INTO recommendations", {}, Exception("1062 Duplicate entry"))
        return real(outlet_id, item, day, actor_id)

    monkeypatch.setattr(rec, "accept_on_first_prepared", racing)
    out = prepare(burger, 24)
    assert len(calls) == 2 and out["total_prepared"] == 24
    assert PreparationRecord.query.count() == 1 and len(plans(burger)) == 1
    assert AuditLog.query.filter_by(action="prepared.record").count() == 1


@pytest.mark.mysql
def test_two_cooks_adding_the_first_portions_at_once(app):
    """PREP-AUTO-15 (MySQL/MariaDB): two simultaneous first entries: both portions recorded, exactly one plan, exactly
    one automatic acceptance."""
    item = make_item(name="Chicken Burger", batch_size=6)
    add_forecast(item, TODAY, "47.3")
    item_id, barrier, results = item.id, threading.Barrier(2), []

    def worker(qty):
        with app.app_context():
            barrier.wait()
            try:
                results.append(kit.record_prepared(1, {"menu_item_id": item_id, "date": "2026-09-25", "quantity": qty},
                                                   decide_first=rec.accept_on_first_prepared))
            except Exception as exc:  # surface anything unexpected instead of hiding it in the thread
                results.append(f"error: {type(exc).__name__}: {exc}")
            finally:
                db.session.remove()

    threads = [threading.Thread(target=worker, args=(q,)) for q in (20, 30)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    db.session.rollback()   # end this session's old REPEATABLE READ snapshot before re-reading
    assert all(isinstance(r, dict) for r in results), results
    assert sorted(r["added"] for r in results) == [20, 30]
    assert sum(1 for r in results if r["auto_accepted"]) == 1
    p = Recommendation.query.filter_by(menu_item_id=item_id, target_date=TODAY).all()
    assert len(p) == 1 and (p[0].status, p[0].final_qty, p[0].prep_status) == ("accepted", 54, "in_progress")
    assert rec._prepared(1, item_id, TODAY) == 50
    assert AuditLog.query.filter_by(action="recommendation.accept").count() == 1
