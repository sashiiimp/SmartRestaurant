"""NAV-1 .. NAV-6: merged pages (tabs), old addresses that redirect, and the Role access table (Oct 2026)."""
import pytest

from app.models.forecast import ALERT_TYPES
from app.utils.navigation import HUBS, NAV_GROUPS, REDIRECTS
from tests.conftest import login

OWNER = {"/admin": "admin", "/kitchen": "kitchen", "/inventory": "inventory"}


def owner(path):
    return OWNER["/" + path.split("/")[1]]


def menu(role):
    return [href for _, links in NAV_GROUPS[role] for _, href in links]


# ---- NAV-1: the menu has 14 entries (23 pages before the merge) ----------------------------------------
def test_menu_sizes():
    assert [len(menu(r)) for r in ("admin", "kitchen", "inventory")] == [5, 5, 4]


def test_every_merged_page_is_in_its_role_menu():
    for path in HUBS:
        assert path in menu(owner(path)), path


# ---- NAV-2: every tab of every merged page opens, and marks itself as the current tab --------------------
@pytest.mark.parametrize("path", sorted(HUBS))
def test_each_tab_opens(as_role, path):
    client = as_role(owner(path))
    for key, label, _ in HUBS[path]:
        resp = client.get(f"{path}?tab={key}")
        assert resp.status_code == 200, (path, key)
        html = resp.get_data(as_text=True)
        assert f'href="{path}?tab={key}" aria-current="page">{label.replace("&", "&amp;")}</a>' in html, (path, key)
        assert html.count('aria-current="page"') == 2  # the sidebar link and this tab


def test_missing_or_unknown_tab_opens_the_first_tab(as_role):
    client = as_role("inventory")
    for url in ("/inventory/reorder", "/inventory/reorder?tab=nope"):
        html = client.get(url).get_data(as_text=True)
        assert 'href="/inventory/reorder?tab=reorder" aria-current="page"' in html
        assert "inventory_reorder.js" in html and "inventory_suppliers.js" not in html


# ---- NAV-3: old addresses still work: they redirect to the tab and keep their other arguments --------------
@pytest.mark.parametrize("old", sorted(REDIRECTS))
def test_old_address_redirects_to_its_tab(as_role, old):
    path, tab = REDIRECTS[old]
    resp = as_role(owner(old)).get(old)
    assert resp.status_code == 302
    assert resp.headers["Location"] == f"{path}?tab={tab}"


def test_redirect_keeps_query_arguments(app, users):
    kitchen, inventory = app.test_client(), app.test_client()
    login(kitchen, users["kitchen"].username)
    login(inventory, users["inventory"].username)
    resp = kitchen.get("/kitchen/stock-requests?ingredient=3&qty=2.5")
    assert resp.headers["Location"] == "/kitchen/requirements?tab=requests&ingredient=3&qty=2.5"
    assert inventory.get("/inventory/purchase-orders?open=7").headers["Location"] == "/inventory/reorder?tab=orders&open=7"
    # a stale ?tab= in an old link is replaced, not repeated
    assert inventory.get("/inventory/suppliers?tab=x").headers["Location"] == "/inventory/reorder?tab=suppliers"


def test_old_address_is_still_refused_to_other_roles(app, users):
    client = app.test_client()
    login(client, users["kitchen"].username)
    for old in ("/inventory/movements", "/inventory/purchase-orders", "/admin/settings", "/admin/inventory"):
        assert client.get(old).status_code == 403, old


# ---- NAV-4: Role access table matches what the server really allows -----------------------------------------
def test_role_access_table_matches_the_server(app, users):
    with app.test_request_context():
        from app.utils.navigation import role_access
        rows = role_access()
    assert len(rows) == 14
    for role in ("admin", "kitchen", "inventory"):
        client = app.test_client()
        login(client, users[role].username)
        for r in rows:
            status = client.get(r["path"]).status_code
            assert (status == 200) == r["roles"][role], (role, r["path"], status)
            assert status in (200, 403)


def test_role_access_tab_lists_pages_and_alerts(as_role):
    html = as_role("admin").get("/admin/users?tab=roles").get_data(as_text=True)
    assert "Pages each role can open" in html and "Alerts each role receives" in html
    assert html.count(" can open ") == 14  # one tick per page; each page belongs to one role
    for t in ALERT_TYPES:
        assert t.replace("_", " ") in html
    assert "Prep plan, 7-day forecast" in html


def test_role_access_is_admin_only(app, users):
    for role in ("kitchen", "inventory"):
        client = app.test_client()
        login(client, users[role].username)
        assert client.get("/admin/users?tab=roles").status_code == 403


# ---- NAV-5: alert visibility on the Role access tab is the rule the alert list uses ------------------------
def test_alert_visibility_is_the_alert_rule():
    from app.services import alert_service
    rows = {r["alert_type"]: set(r["roles"]) for r in alert_service.visibility()}
    assert rows == {t: alert_service.VISIBLE_TO[t] for t in ALERT_TYPES}


# ---- NAV-6: Reports took over the Inventory overview tabs ------------------------------------------------
def test_reports_has_the_inventory_overview_tabs(as_role):
    client = as_role("admin")
    assert client.get("/admin/inventory").headers["Location"] == "/admin/monitor?tab=stock"
    js = client.get("/static/js/pages/admin_monitor.js").get_data(as_text=True)
    for key in ("stock", "ingredients", "batches", "inventory", "movements"):
        assert f"['{key}', " in js


# ---- NAV-7: final UI pass (14 Oct 2026) ----------------------------------------------------------------
def test_forecasting_opens_ml_models_and_lists_its_tabs_in_workflow_order(as_role):
    client = as_role("admin")
    html = client.get("/admin/models").get_data(as_text=True)
    assert 'href="/admin/models?tab=models" aria-current="page">ML models</a>' in html
    assert html.index(">Historical data</a>") < html.index(">ML models</a>") < html.index(">Forecast generation</a>")
    runs = client.get("/admin/models?tab=runs").get_data(as_text=True)
    assert "Run forecast now" in runs and "Forecast history" in runs and "Train new model" not in runs
    models = client.get("/admin/models?tab=models").get_data(as_text=True)
    assert "Train new model" in models and "Model versions" in models and "Run forecast now" not in models
    assert client.get("/admin/data").headers["Location"] == "/admin/models?tab=data"


def test_reports_title_and_dashboard_labels(as_role):
    client = as_role("admin")
    assert "Reports &amp; Analytics" in client.get("/admin/monitor").get_data(as_text=True)
    dash = client.get("/admin").get_data(as_text=True)
    assert "Forecast models" not in dash and 'href="/admin/models?tab=runs"><span class="qa-icon">' in dash and "Generate forecast" in dash
    js = client.get("/static/js/pages/admin_monitor.js").get_data(as_text=True)
    for group in ("'Sales'", "'Forecasting'", "'Inventory'", "'Waste & Analytics'"):
        assert group in js


def test_role_access_has_a_phone_list_with_the_same_pages(as_role):
    html = as_role("admin").get("/admin/users?tab=roles").get_data(as_text=True)
    start = html.index('<ul class="role-list d-sm-none">')
    phone = html[start:html.index("</ul>", start)]
    assert phone.count("<li>") == 14


# ---- NAV-8: the workflow step marker in the top bar (viva polish) ------------------------------------------------
@pytest.mark.parametrize("role,url,step", [
    ("admin", "/admin/models?tab=data", "Step 1 of 6 &middot; Historical sales"),
    ("admin", "/admin/models", "Step 2 of 6 &middot; ML demand forecast"),
    ("kitchen", "/kitchen/prep", "Step 3 of 6 &middot; Preparation recommendations"),
    ("kitchen", "/kitchen/requirements", "Step 4 of 6 &middot; BOM &amp; ingredient requirements"),
    ("inventory", "/inventory/reorder", "Step 5 of 6 &middot; Inventory decisions"),
    ("kitchen", "/kitchen/record", "Step 6 of 6 &middot; Food waste monitoring"),
])
def test_page_shows_its_workflow_step(as_role, role, url, step):
    assert step in as_role(role).get(url).get_data(as_text=True)


def test_dashboards_and_reports_have_no_single_step(as_role):
    client = as_role("admin")
    for url in ("/admin", "/admin/monitor"):
        assert "step-chip" not in client.get(url).get_data(as_text=True)


def test_every_step_page_is_a_menu_page_of_its_role():
    from app.utils.navigation import PAGE_STEP, WORKFLOW
    for (path, tab), n in PAGE_STEP.items():
        assert 1 <= n <= len(WORKFLOW) and path in menu(owner(path)) + [p for p in HUBS if owner(p) == owner(path)]
        if tab:
            assert tab in [t[0] for t in HUBS[path]], (path, tab)
