"""Browser smoke test (Playwright, headless Chromium) against a running dev server. Not part of `pytest`.

Usage: python tests/ui/smoke.py [kitchen|inventory|admin|all] [--shots DIR] [--base URL] [--browser chromium|firefox|webkit]
Checks that pages render, have no console errors, and that the main interactions work. Also saves screenshots.
"""
import os
import sys

from dotenv import dotenv_values
from playwright.sync_api import sync_playwright

ENV = dotenv_values(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))
PASSWORD = os.environ.get("SMOKE_PASSWORD") or ENV.get("SEED_PASSWORD")
# The seeded demo accounts; SMOKE_USERS="kitchen1=kitchen,inventory1=inventory" maps them to other usernames
# (used for the deployment rehearsal on a copy of the production data, whose accounts are named differently).
USERS = dict(p.split("=", 1) for p in os.environ.get("SMOKE_USERS", "").split(",") if "=" in p)
BASE = "http://127.0.0.1:5055"
SHOTS = os.path.join(os.path.dirname(__file__), "..", "..", "instance", "ui_shots")  # git-ignored; --shots DIR overrides
problems = []


def login(page, username):
    page.goto(BASE + "/login")
    page.fill("#username", USERS.get(username, username))
    page.fill("#password", PASSWORD)
    seen = []
    note = lambda r: seen.append(f"{r.status} {r.request.method} {r.url.replace(BASE, '')}")  # noqa: E731
    page.on("response", note)
    page.click("button[type=submit]")
    # headless WebKit now and then drops the click without sending the form; click once more only if nothing was sent
    try:
        page.wait_for_url(lambda u: "/login" not in u, timeout=5000, wait_until="commit")
    except Exception:
        if not any(" POST /login" in r for r in seen):
            print(f"  (login as {username}: the click sent nothing, trying once more)")
            page.goto(BASE + "/login")
            page.fill("#username", USERS.get(username, username))
            page.fill("#password", PASSWORD)
            page.click("button[type=submit]")
    # wait until the browser has really left /login: WebKit can report "network idle" before the redirect starts
    try:
        page.wait_for_url(lambda u: "/login" not in u, timeout=15000, wait_until="commit")
    except Exception:
        if SHOTS:
            os.makedirs(SHOTS, exist_ok=True)
            page.screenshot(path=os.path.join(SHOTS, f"login_failed_{username}.png"))
        raise AssertionError(f"login as {username} stayed on {page.url}; responses: {seen[-5:]}")
    finally:
        page.remove_listener("response", note)
    page.wait_for_load_state("networkidle")


# WebKit reports a fetch that the browser cancelled because the page was left ("... due to access control checks") as a
# page error, even though the page code catches it; Chromium and Firefox stay silent. Those are not application errors.
CANCELLED = "due to access control checks"


def visit(page, path, shot, wait=".card, table, .alert, h1", width=None):
    errors = []
    on_error = lambda e: errors.append(f"pageerror: {e}") if CANCELLED not in str(e) else None  # noqa: E731
    on_console = lambda m: errors.append(f"console.{m.type}: {m.text}") if m.type == "error" and CANCELLED not in m.text else None  # noqa: E731
    page.on("pageerror", on_error)
    page.on("console", on_console)
    resp = page.goto(BASE + path)
    page.wait_for_load_state("networkidle")
    page.wait_for_selector(wait, timeout=8000)
    page.remove_listener("pageerror", on_error)   # errors after this belong to the next page, not this one
    page.remove_listener("console", on_console)
    if resp.status != 200:
        problems.append(f"{path}: HTTP {resp.status}")
    for e in errors:
        problems.append(f"{path}: {e}")
    if SHOTS:
        os.makedirs(SHOTS, exist_ok=True)
        page.screenshot(path=os.path.join(SHOTS, shot + ".png"), full_page=True)
    return page


def kitchen(browser):
    ctx = browser.new_context(viewport={"width": 390, "height": 844})
    page = ctx.new_page()
    login(page, "kitchen1")
    assert page.url.endswith("/kitchen"), page.url
    visit(page, "/kitchen/prep?tab=forecast", "k_forecast")
    assert page.locator("table tbody tr").count() >= 10, "forecast table empty"
    page.locator(".hub-tab", has_text="Prep plan").click()   # tabs of a merged page are plain links
    page.wait_for_selector(".card-item", timeout=8000)
    assert "tab=prep" in page.url, page.url
    visit(page, "/kitchen/prep", "k_prep", wait=".card-item")
    n = page.locator(".card-item").count()
    print("prep cards:", n)
    first = page.locator(".card-item").first
    first.get_by_role("button", name="Accept").click()
    page.wait_for_function("document.querySelector('.card-item.accepted') !== null", timeout=8000)
    assert page.locator(".card-item.accepted").first.get_by_role("button", name="Accept").count() == 0, "no second Accept once accepted"
    page.wait_for_selector(".card-item.accepted", timeout=5000)
    second = page.locator(".card-item").nth(1)
    second.get_by_role("button", name="Override").click()
    second.locator("input").nth(0).fill("50")
    second.get_by_role("button", name="Save override").click()
    # reason missing -> the server answers 422 and the field error appears; the form stays open
    second.locator("text=is required").first.wait_for(timeout=8000)
    assert "Reason (required)" in second.inner_text(), "override form must stay open after the error"
    second.locator("input").nth(1).fill("Rain expected")
    second.get_by_role("button", name="Save override").click()
    page.wait_for_selector(".card-item.overridden", timeout=5000)
    first.locator("input[inputmode=numeric]").last.fill("24")
    first.get_by_role("button", name="+ Add").click()
    page.wait_for_selector("text=24", timeout=5000)
    visit(page, "/kitchen/prep", "k_prep_after", wait=".card-item")
    acc, ovr = page.locator(".card-item.accepted").count(), page.locator(".card-item.overridden").count()
    assert (acc, ovr) == (1, 1), f"after reload: {acc} accepted and {ovr} overridden cards, expected 1 and 1"
    visit(page, "/kitchen/record", "k_record", wait="input[id^=s]")
    page.locator("input[id^=s]").first.fill("999")
    page.get_by_role("button", name="Save served quantities").click()
    page.wait_for_selector("text=served above prepared", timeout=5000)
    assert page.locator("[role=tab]").count() == 2, "Daily record and Ingredient usage"
    page.wait_for_selector(".rec-row .rec-b.is-neg", timeout=3000)       # 999 served: more used than prepared
    page.locator("input[id^=s]").nth(1).fill("1")                       # typed, not saved: must survive the waste entry
    page.locator(".rec-row").first.get_by_role("button", name="Waste / other").click()   # waste and other use under the row
    page.wait_for_selector(".rec-detail #w-qty", timeout=3000)
    page.fill("#w-qty", "-4")
    page.get_by_role("button", name="Record waste").click()
    page.wait_for_selector("text=must be greater than 0", timeout=5000)
    page.fill("#w-qty", "3")
    page.get_by_role("button", name="Record waste").click()
    page.wait_for_selector("text=Waste recorded", timeout=5000)
    page.fill("#u-qty", "2")
    page.get_by_role("button", name="Record other use").click()
    page.wait_for_selector(".rec-entries li", timeout=5000)
    assert page.locator("input[id^=s]").nth(1).input_value() == "1", "unsaved served quantity kept after recording waste"
    page.wait_for_function("document.querySelectorAll('.rec-status li.is-done').length >= 2", timeout=5000)   # waste and other use
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1"), "horizontal scroll at 390px"
    visit(page, "/kitchen", "k_dashboard", wait=".kpis")
    assert page.locator(".kpis .stat-tile").count() == 4 and page.locator(".wf").count() == 0, "kitchen figures, no shared strip"
    page.wait_for_selector("h2:has-text('Needs attention')", timeout=8000)
    page.wait_for_selector(".act-list, .act-clear", timeout=8000)
    assert "Not recorded" not in page.locator(".kpis").inner_text(), "served was recorded above"
    visit(page, "/kitchen/requirements", "k_requirements", wait="table")
    first = page.locator("tbody tr").first
    first.get_by_role("button", name="Ask inventory").click()          # one action, two choices
    page.wait_for_selector(".ask-panel", timeout=3000)
    assert page.locator(".ask-panel").get_by_role("button", name="Report shortage").count() == 1
    page.locator(".ask-panel").get_by_role("link", name="Request stock").click()
    page.wait_for_selector("text=New stock request", timeout=8000)      # Stock requests tab with the form filled in
    assert "tab=requests" in page.url, page.url
    page.locator("input[inputmode=decimal]").first.fill("2")
    page.get_by_role("button", name="Send request").click()            # inventory approves, then issues it (below)
    page.wait_for_selector(".sr-badge:has-text('Pending')", timeout=8000)
    page.goto(BASE + "/kitchen/stock-requests")                          # old address
    assert "/kitchen/requirements?tab=requests" in page.url, page.url
    r = page.goto(BASE + "/admin")
    assert r.status == 403, r.status
    ctx.close()
    # desktop: the prep plan is a comparison table with the same actions
    ctx = browser.new_context(viewport={"width": 1366, "height": 900})
    page = ctx.new_page()
    login(page, "kitchen1")
    visit(page, "/kitchen/prep", "k_prep_desktop", wait=".prep-table")
    rows, cards = page.locator(".prep-table tbody tr").count(), page.locator(".card-item").count()
    assert rows >= 10 and cards == 0, f"desktop prep plan: {rows} table rows, {cards} cards"
    row = page.locator(".prep-table tbody tr", has=page.get_by_role("button", name="Override")).first
    row.get_by_role("button", name="Override").click()
    page.wait_for_selector(".override-row", timeout=3000)
    page.locator(".override-row").get_by_role("button", name="Cancel").click()
    assert page.locator(".override-row").count() == 0, "Cancel must close the override row"
    ctx.close()


def inventory(browser):
    ctx = browser.new_context(viewport={"width": 1280, "height": 900})
    page = ctx.new_page()
    login(page, "inventory1")
    assert page.url.endswith("/inventory"), page.url
    visit(page, "/inventory", "i_dashboard", wait=".kpis")
    assert page.locator(".kpis .stat-tile").count() == 4 and page.locator(".wf").count() == 0, "inventory figures, no shared strip"
    page.wait_for_selector("h2:has-text('Kitchen requests')", timeout=8000)
    page.wait_for_selector(".act-list, .act-clear", timeout=8000)
    assert "Chicken" in page.inner_text("main"), "chicken alert/reorder expected on the dashboard"
    visit(page, "/inventory/stock", "i_stock", wait="table tbody tr")
    assert page.locator("table tbody tr").count() >= 20
    page.get_by_role("button", name="Add ingredient").click()
    page.get_by_role("button", name="Save", exact=True).click()
    page.wait_for_selector("text=is required", timeout=4000)
    page.get_by_role("button", name="Cancel").click()
    visit(page, "/inventory/stock?tab=record", "i_movements", wait="#m-ing")
    page.select_option("#m-ing", label="Chicken (kg)")
    page.fill("#m-qty", "100")
    page.get_by_role("button", name="Save", exact=True).click()
    page.wait_for_selector("text=Usable stock is now", timeout=5000)
    page.get_by_role("button", name="Issue to kitchen").click()
    page.select_option("#m-ing", label="Potato (kg)")
    page.fill("#m-qty", "9999")
    page.get_by_role("button", name="Save", exact=True).click()
    page.wait_for_selector("text=available", timeout=5000)
    page.get_by_role("button", name="Stock wastage").click()
    page.select_option("#m-ing", label="Chicken (kg)")
    page.fill("#m-qty", "5")
    page.get_by_role("button", name="Save", exact=True).click()
    page.wait_for_selector("text=Saved", timeout=5000)
    # a kitchen request: approval and issue stay two separate, recorded steps
    visit(page, "/inventory/requests", "i_requests", wait="table tbody tr")
    page.locator("tbody tr", has_text="Pending").first.get_by_role("button", name="Open").click()
    page.wait_for_selector(".req-steps", timeout=5000)
    assert page.get_by_role("button", name="Issue to kitchen").count() == 0, "issue only after approval"
    page.get_by_role("button", name="Approve").click()
    page.wait_for_selector("text=Request approved", timeout=5000)
    page.get_by_role("button", name="Issue to kitchen").click()
    page.wait_for_selector("h3:has-text('Issue to kitchen')", timeout=5000)
    if page.locator("text=Nothing can be issued yet").count():                # zero usable stock: nothing to press
        assert page.get_by_role("button", name="Issue", exact=True).is_disabled()
    visit(page, "/inventory/reorder?tab=demand", "i_forecast", wait="table tbody tr")
    visit(page, "/inventory/reorder", "i_reorder", wait="table, .text-center")
    visit(page, "/inventory/reorder?tab=orders", "i_purchase_orders", wait="h2")
    visit(page, "/inventory/reorder?tab=suppliers", "i_suppliers", wait="table tbody tr")
    page.goto(BASE + "/inventory/purchase-orders")                       # old address
    assert "/inventory/reorder?tab=orders" in page.url, page.url
    r = page.goto(BASE + "/kitchen")
    assert r.status == 403, r.status
    ctx.close()
    # phones: purchasing lists are cards with the key figure and the actions in view (no sideways table)
    ctx = browser.new_context(viewport={"width": 390, "height": 844})
    page = ctx.new_page()
    login(page, "inventory1")
    visit(page, "/inventory/reorder", "i_reorder_phone", wait=".m-list, .sr-empty")
    if page.locator(".m-list li").count():
        assert page.locator(".m-list li .m-key strong").first.is_visible(), "suggested quantity visible on a phone"
    visit(page, "/inventory/reorder?tab=suppliers", "i_suppliers_phone", wait=".m-list")
    assert page.locator(".m-list li").first.get_by_role("button", name="Edit").is_visible()
    visit(page, "/inventory/reorder?tab=demand", "i_demand_phone", wait=".m-list, .sr-empty")
    ctx.close()


def admin(browser):
    import datetime
    import tempfile

    ctx = browser.new_context(viewport={"width": 1280, "height": 900})
    page = ctx.new_page()
    page.on("dialog", lambda d: d.accept())
    login(page, "admin")
    assert page.url.endswith("/admin"), page.url
    visit(page, "/admin", "a_dashboard", wait=".wf-step")
    assert page.locator(".wf .wf-step").count() == 6, "admin workflow strip"
    page.wait_for_selector(".wf-step:has-text('to prepare')", timeout=8000)            # step 3 read from the prep plan
    assert page.locator(".wf a.wf-step").count() == 5, "steps 1, 2, 4, 5, 6 link to admin pages; 3 is the kitchen's"
    page.wait_for_selector("h2:has-text('Forecasting performance')", timeout=8000)
    page.wait_for_selector("text=Hold-out error", timeout=8000)                        # read from the active model
    visit(page, "/admin/monitor", "a_monitor_sales", wait="canvas")
    page.get_by_role("tab", name="Forecasting").click()                 # report groups, then the report
    page.get_by_role("button", name="Forecast accuracy").click()
    page.wait_for_selector("text=Forecasts compared", timeout=8000)
    page.screenshot(path=os.path.join(SHOTS, "a_monitor_forecast.png"), full_page=True)
    page.get_by_role("tab", name="Waste & Analytics").click()
    page.wait_for_selector("text=Food waste (prepared portions)", timeout=8000)
    page.get_by_role("tab", name="Inventory").click()
    page.get_by_role("button", name="Ingredient demand").click()        # tabs taken over from Inventory overview
    page.wait_for_selector("text=Days of cover", timeout=8000)
    page.get_by_role("button", name="Stock & expiry").click()           # stock levels and batches in one report
    page.wait_for_selector("text=Days to expiry", timeout=8000)
    page.get_by_role("button", name="Stock history").click()            # day-by-day stock and the movements
    page.wait_for_selector("text=stock day by day", timeout=8000)
    page.wait_for_selector("h2:has-text('Movements')", timeout=8000)
    page.goto(BASE + "/admin/monitor?tab=movements")                     # earlier report address
    page.wait_for_selector("text=stock day by day", timeout=8000)
    visit(page, "/admin/inventory", "a_inventory", wait="text=Stock OK")   # old address opens Reports, Stock levels
    assert "/admin/monitor?tab=stock" in page.url, page.url
    visit(page, "/admin/models", "a_models", wait=".card")
    page.get_by_role("button", name="Train new model").click()
    page.wait_for_selector("text=Trained v", timeout=90000)
    page.get_by_role("button", name="Activate").first.click()
    page.wait_for_selector("text=is now active", timeout=8000)
    visit(page, "/admin/models?tab=runs", "a_forecast_runs", wait=".card")
    page.get_by_role("button", name="Run forecast now").click()
    page.wait_for_selector("text=Forecast run ok", timeout=15000)
    visit(page, "/admin/models?tab=data", "a_data", wait="input[type=file]")
    today = datetime.date.today().isoformat()
    with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False) as f:
        f.write(f"date,item,quantity\n{today},Lime Juice,55\n{today},Lime Juise,5\n")
    page.set_input_files("input[type=file]", f.name)
    page.get_by_role("button", name="Check file").click()
    page.wait_for_selector("text=1 rows accepted, 1 rejected", timeout=8000)
    assert "Unknown menu item" in page.inner_text("main")
    page.get_by_role("button", name="Save 1 rows").click()
    page.wait_for_selector("text=1 rows saved", timeout=8000)
    visit(page, "/admin/catalog", "a_catalog", wait="table tbody tr")
    page.wait_for_selector("text=Recipe (BOM):", timeout=4000)          # the first item's recipe opens read-only
    page.get_by_role("button", name="Edit recipe").click()
    page.wait_for_selector("text=Save recipe", timeout=4000)
    page.get_by_role("button", name="Cancel").click()
    visit(page, "/admin/users", "a_users", wait="table tbody tr")
    page.get_by_role("button", name="Add user").click()
    page.get_by_role("button", name="Create").click()
    page.wait_for_selector("text=is required", timeout=4000)
    page.fill("#u-name", "Temp Kitchen"); page.fill("#u-user", "tempk"); page.fill("#u-pw", "temppass1")
    page.get_by_role("button", name="Create").click()
    page.wait_for_selector("text=tempk", timeout=5000)
    page.locator("tr", has_text="tempk").get_by_role("button", name="Deactivate").click()
    page.wait_for_selector("tr:has-text('tempk') >> text=Deactivated", timeout=5000)
    page.locator("tr", has_text="admin").first.get_by_role("button", name="Deactivate").click()
    page.wait_for_selector("text=last active administrator", timeout=5000)
    visit(page, "/admin/users?tab=settings", "a_settings", wait="text=Thresholds")
    visit(page, "/admin/users?tab=roles", "a_roles", wait=".role-table")   # now a section under Users
    assert page.locator(".hub-tab").count() == 2, "Users and Settings & alerts"
    assert page.locator(".role-yes").count() == 14 + 14, "one tick per page and one per alert recipient"
    r = page.goto(BASE + "/kitchen")
    assert r.status == 403, r.status
    ctx.close()


PAGES = {
    "kitchen1": ["/kitchen", "/kitchen/prep", "/kitchen/prep?tab=forecast", "/kitchen/record", "/kitchen/requirements",
                 "/kitchen/requirements?tab=requests", "/kitchen/orders"],
    "inventory1": ["/inventory", "/inventory/stock", "/inventory/stock?tab=record", "/inventory/requests", "/inventory/reorder",
                   "/inventory/reorder?tab=demand", "/inventory/reorder?tab=orders", "/inventory/reorder?tab=suppliers"],
    "admin": ["/admin", "/admin/monitor", "/admin/monitor?tab=forecast", "/admin/monitor?tab=stock", "/admin/monitor?tab=ingredients",
              "/admin/monitor?tab=waste", "/admin/models", "/admin/models?tab=data", "/admin/models?tab=runs", "/admin/catalog",
              "/admin/users", "/admin/users?tab=settings", "/admin/users?tab=roles"],
}


def responsive(browser):
    """NFR4: every page at 360, 768 and 1280 px wide has no page-level horizontal scroll."""
    for user, paths in PAGES.items():
        for width in (360, 768, 1280):
            ctx = browser.new_context(viewport={"width": width, "height": 800})
            page = ctx.new_page()
            login(page, user)
            for path in paths:
                page.goto(BASE + path)
                page.wait_for_load_state("networkidle")
                page.wait_for_timeout(300)
                over = page.evaluate("document.documentElement.scrollWidth - window.innerWidth")
                if over > 1:
                    problems.append(f"{path} at {width}px: page scrolls sideways by {over}px")
            ctx.close()


if __name__ == "__main__":
    option_values = {sys.argv[i + 1] for i, a in enumerate(sys.argv[:-1]) if a.startswith("--")}
    which = [a for a in sys.argv[1:] if not a.startswith("--") and a not in option_values] or ["all"]
    engine = sys.argv[sys.argv.index("--browser") + 1] if "--browser" in sys.argv else "chromium"
    if "--shots" in sys.argv:
        SHOTS = sys.argv[sys.argv.index("--shots") + 1]
    if "--base" in sys.argv:
        BASE = sys.argv[sys.argv.index("--base") + 1]
    with sync_playwright() as p:
        browser = getattr(p, engine).launch()
        print("browser:", engine, browser.version)
        for name in ("kitchen", "inventory", "admin", "responsive"):
            if "all" in which or name in which:
                fn = globals().get(name)
                if fn:
                    try:
                        fn(browser)
                        print(f"[ok] {name}")
                    except Exception as e:  # report and continue
                        problems.append(f"{name}: {type(e).__name__}: {str(e)[:300]}")
        browser.close()
    print("PROBLEMS:" if problems else "no problems", *problems, sep="\n  ")
    sys.exit(1 if problems else 0)
