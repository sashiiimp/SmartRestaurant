"""Browser smoke test (Playwright, headless Chromium) against a running dev server. Not part of `pytest`.

Usage: python tests/ui/smoke.py [kitchen|inventory|admin|all] [--shots DIR] [--base URL]
Checks that pages render, have no console errors, and that the main interactions work. Also saves screenshots.
"""
import os
import sys

from dotenv import dotenv_values
from playwright.sync_api import sync_playwright

ENV = dotenv_values(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))
PASSWORD = ENV.get("SEED_PASSWORD")
BASE = "http://127.0.0.1:5055"
SHOTS = "/tmp/claude-0/shots"
problems = []


def login(page, username):
    page.goto(BASE + "/login")
    page.fill("#username", username)
    page.fill("#password", PASSWORD)
    page.click("button[type=submit]")
    page.wait_for_load_state("networkidle")


def visit(page, path, shot, wait=".card, table, .alert, h1", width=None):
    errors = []
    page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
    page.on("console", lambda m: errors.append(f"console.{m.type}: {m.text}") if m.type in ("error",) else None)
    resp = page.goto(BASE + path)
    page.wait_for_load_state("networkidle")
    page.wait_for_selector(wait, timeout=8000)
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
    visit(page, "/kitchen/forecast", "k_forecast")
    assert page.locator("table tbody tr").count() >= 10, "forecast table empty"
    visit(page, "/kitchen/prep", "k_prep", wait=".card-item")
    n = page.locator(".card-item").count()
    print("prep cards:", n)
    first = page.locator(".card-item").first
    first.get_by_role("button", name="Accept").click()
    page.wait_for_selector(".card-item.accepted", timeout=5000)
    second = page.locator(".card-item").nth(1)
    second.get_by_role("button", name="Override").click()
    second.locator("input").nth(0).fill("50")
    second.get_by_role("button", name="Save override").click()
    page.wait_for_selector("text=Reason (required)", timeout=2000)  # reason missing -> field error shown, form stays open
    assert "is required" in second.inner_text()
    second.locator("input").nth(1).fill("Rain expected")
    second.get_by_role("button", name="Save override").click()
    page.wait_for_selector(".card-item.overridden", timeout=5000)
    first.locator("input[inputmode=numeric]").last.fill("24")
    first.get_by_role("button", name="+ Add").click()
    page.wait_for_selector("text=24", timeout=5000)
    visit(page, "/kitchen/prep", "k_prep_after", wait=".card-item")
    assert page.locator(".card-item.accepted").count() == 1 and page.locator(".card-item.overridden").count() == 1
    visit(page, "/kitchen/record", "k_record", wait="#w-item")
    page.locator("input[id^=s]").first.fill("30")
    page.get_by_role("button", name="Save served quantities").click()
    page.wait_for_selector("text=served above prepared", timeout=5000)
    page.fill("#w-qty", "-4")
    page.get_by_role("button", name="Record waste").click()
    page.wait_for_selector("text=must be greater than 0", timeout=5000)
    page.fill("#w-qty", "3")
    page.get_by_role("button", name="Record waste").click()
    page.wait_for_selector("text=Waste recorded", timeout=5000)
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1"), "horizontal scroll at 390px"
    r = page.goto(BASE + "/admin")
    assert r.status == 403, r.status
    ctx.close()


if __name__ == "__main__":
    which = [a for a in sys.argv[1:] if not a.startswith("--")] or ["all"]
    if "--shots" in sys.argv:
        SHOTS = sys.argv[sys.argv.index("--shots") + 1]
    if "--base" in sys.argv:
        BASE = sys.argv[sys.argv.index("--base") + 1]
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for name in ("kitchen", "inventory", "admin"):
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
