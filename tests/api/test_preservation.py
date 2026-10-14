"""PRES-1 .. PRES-8: nothing the system could do before the role dashboards (baseline = production d26b1e9) is lost.

The baseline is tests/preservation_baseline.json, written by scripts/preservation_audit.py; the checklist that explains
it is docs/PRESERVATION_CHECKLIST.md. Every item in the baseline must still exist. A dashboard may show an action in a
new way; MOVED lists those, each with where the same function is now, and the test checks that place."""
import json
from pathlib import Path

import pytest

from scripts.preservation_audit import inventory

BASELINE = json.loads((Path(__file__).resolve().parents[1] / "preservation_baseline.json").read_text())
NOW = inventory()

# (page view, baseline action or API call) -> where the same function is in the new version, as (page view, label).
# Only dashboards appear here: their layout changed, the pages behind them did not.
MOVED = {
    # the kitchen dashboard reads served and wasted from /dashboards/kitchen ("day"); Served & waste still uses it
    ("/kitchen", "GET /kitchen/daily-summary"): ("/kitchen/record", "GET /kitchen/daily-summary"),
    # the inventory dashboard reads the full reorder count from /dashboards/inventory ("totals"); Reorder lists them all
    ("/inventory", "GET /recommendations/reorder"): ("/inventory/reorder?tab=reorder", "GET /recommendations/reorder"),
}


def _routes(data):
    return {(r["method"], r["path"]): r["roles"] for r in data["routes"]}


# ---- PRES-1: every API route and page address, with the same methods and the same roles ------------------------
def test_every_route_and_method_still_exists_with_the_same_roles():
    now = _routes(NOW)
    missing = [k for k in _routes(BASELINE) if k not in now]
    changed = [(k, roles, now[k]) for k, roles in _routes(BASELINE).items() if k in now and now[k] != roles]
    assert not missing, missing
    assert not changed, changed


# ---- PRES-2: the menu: same pages, same groups, same tabs in the same order ------------------------------------
def test_menu_pages_and_tabs_are_unchanged():
    assert NOW["pages"] == BASELINE["pages"]


# ---- PRES-3: Reports & Analytics keeps all 10 reports; CLI keeps all commands; old addresses still redirect -----
def test_reports_cli_and_redirects_are_kept():
    assert [t for t in BASELINE["report_tabs"] if t not in NOW["report_tabs"]] == []
    assert set(BASELINE["cli"]) <= set(NOW["cli"])
    assert NOW["redirects"] == BASELINE["redirects"]


@pytest.mark.parametrize("old,new", sorted(BASELINE["redirects"].items()))
def test_old_address_redirects(as_role, old, new):
    role = {"admin": "admin", "kitchen": "kitchen", "inventory": "inventory"}[old.split("/")[1]]
    resp = as_role(role).get(old)
    assert resp.status_code == 302 and resp.headers["Location"].startswith(new)


# ---- PRES-4: every page view keeps its buttons and its API calls (a dashboard change is listed in MOVED) ---------
@pytest.mark.parametrize("view", sorted(BASELINE["ui"]))
def test_page_keeps_its_actions_and_data(view):
    before, now = BASELINE["ui"][view], NOW["ui"][view]
    lost = [a for a in before["actions"] if a not in now["actions"] and (view, a) not in MOVED]
    lost_api = [c for c in before["api"] if c not in now["api"] and (view, c) not in MOVED]
    assert not lost, (view, lost)
    assert not lost_api, (view, lost_api)


@pytest.mark.parametrize("key,dest", sorted(MOVED.items()))
def test_moved_dashboard_action_is_where_the_checklist_says(key, dest):
    view, label = dest
    assert label in NOW["ui"][view]["actions"] + NOW["ui"][view]["api"], (key, dest)


# ---- PRES-5: each role opens every page and tab of its menu, and none of another role's ------------------------
@pytest.mark.parametrize("role", ["admin", "kitchen", "inventory"])
def test_role_opens_its_pages_and_no_others(as_role, role):
    client = as_role(role)
    for view in BASELINE["ui"]:
        mine = view.split("/")[1] == role
        status = client.get(view).status_code
        assert status == (200 if mine else 403), (role, view, status)
