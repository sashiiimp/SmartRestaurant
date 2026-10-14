"""Inventory of every function the system offers, for the preservation checklist (docs/PRESERVATION_CHECKLIST.md).

Reads the code, not the database: routes with their methods and allowed roles, menu pages and their tabs, old
addresses that redirect, CLI commands, the API calls each page script makes, and the buttons and action links each
page template shows. Read-only.

    python scripts/preservation_audit.py              print the inventory as JSON
    python scripts/preservation_audit.py --write      also refresh tests/preservation_baseline.json

tests/api/test_preservation.py compares the running code with the saved baseline: nothing in the baseline may
disappear. The baseline is refreshed only when a change is intended and recorded in the checklist."""
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
BASELINE = ROOT / "tests" / "preservation_baseline.json"

TAG = re.compile(r"<[^>]+>")
SPACE = re.compile(r"\s+")


def _text(html: str) -> str:
    return SPACE.sub(" ", TAG.sub(" ", html)).replace("&amp;", "&").strip()


def page_actions(template: str) -> list[str]:
    """Visible labels of buttons and button-styled links (Vue [[ ]] expressions kept as written)."""
    src = (ROOT / "app" / "templates" / template).read_text()
    out = set()
    for m in re.finditer(r"<button\b[^>]*>(.*?)</button>", src, re.S):
        t = _text(m.group(1))
        if t and len(t) < 80:
            out.add(t)
    for m in re.finditer(r"<a\b[^>]*class=\"[^\"]*\bbtn\b[^\"]*\"[^>]*>(.*?)</a>", src, re.S):
        t = _text(m.group(1))
        if t and len(t) < 80:
            out.add(t)
    for m in re.finditer(r"<sr-date-nav\b", src):
        out.add("(date navigation)")
    for m in re.finditer(r"<sr-csv-import\b[^>]*endpoint=\"([^\"]+)\"", src):
        out.add(f"(CSV import {m.group(1)})")
    for m in re.finditer(r"<sr-alert-list\b", src):
        out.add("(alert list with Acknowledge)")
    return sorted(out)


def api_calls(script: str, template: str | None = None) -> list[str]:
    """API paths a page script calls, as 'METHOD /path' with ids and query strings left out, plus the CSV downloads
    the page links to (in the script or in its template)."""
    path = ROOT / "app" / "static" / "js" / "pages" / script
    if not path.exists():
        return []
    src = path.read_text() + ((ROOT / "app" / "templates" / template).read_text() if template else "")
    out = set()
    for m in re.finditer(r"api\.(get|post|patch|put|del)\(\s*(['`])(/[^'`]*)\2(?!\s*\+)", src):
        p = re.sub(r"\$\{[^}]*\}", "<id>", m.group(3)).split("?")[0].rstrip("/")
        out.add(f"{m.group(1).upper().replace('DEL', 'DELETE')} {p}")
    for m in re.finditer(r"api\.(get|post|patch|put|del)\(\s*'(/[^']*)'\s*\+", src):
        out.add(f"{m.group(1).upper().replace('DEL', 'DELETE')} {m.group(2).rstrip('/')}/<id>")
    for m in re.finditer(r"['\"](/api/v1/[^'\"?]+)\?[^'\"]*format=csv", src):
        out.add(f"CSV {m.group(1)}")
    for m in re.finditer(r"csvUrl\(\s*'([^']+)'", src):
        out.add(f"CSV {m.group(1)}")
    return sorted(out)


def inventory() -> dict:
    os.environ.setdefault("APP_ENV", "dev")
    os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
    from app import create_app
    from app.utils import navigation as nav

    app = create_app()
    routes = []
    for rule in app.url_map.iter_rules():
        if rule.endpoint == "static":
            continue
        view = app.view_functions[rule.endpoint]
        roles = getattr(view, "allowed_roles", None)
        if roles is None:
            bp = app.blueprints.get(rule.endpoint.split(".")[0])
            guard = getattr(bp, "allowed_roles", None) if bp else None
            roles = guard if guard is not None else ["(any / public)"]
        for method in sorted(rule.methods - {"HEAD", "OPTIONS"}):
            routes.append({"method": method, "path": rule.rule, "roles": sorted(roles)})
    routes.sort(key=lambda r: (r["path"], r["method"]))

    pages = []
    templates = {}
    for role, groups in nav.NAV_GROUPS.items():
        for heading, links in groups:
            for label, href in links:
                tabs = [{"key": k, "label": lab, "template": t} for k, lab, t in nav.HUBS.get(href, [])]
                pages.append({"role": role, "group": heading, "label": label, "path": href, "tabs": tabs})
                for t in tabs:
                    templates[f"{href}?tab={t['key']}"] = t["template"]
                if not tabs:
                    templates[href] = None
    with app.test_request_context():
        for path in list(templates):
            if templates[path] is None:
                endpoint, _ = app.url_map.bind("localhost").match(path)
                templates[path] = {"admin.dashboard": "admin/dashboard.html", "admin.monitor": "admin/monitor.html",
                                   "admin.catalog": "admin/catalog.html", "kitchen.dashboard": "kitchen/dashboard.html",
                                   "kitchen.record": "kitchen/record.html", "kitchen.orders": "kitchen/orders.html",
                                   "inventory.dashboard": "inventory/dashboard.html",
                                   "inventory.requests": "inventory/requests.html"}[endpoint]

    def script_for(template):
        src = (ROOT / "app" / "templates" / template).read_text()
        m = re.search(r"js/pages/([a-z_]+\.js)", src)
        return m.group(1) if m else None

    ui = {}
    for path, template in sorted(templates.items()):
        script = script_for(template)
        ui[path] = {"template": template, "script": script, "actions": page_actions(template),
                    "api": api_calls(script, template) if script else []}

    report_tabs = []
    monitor_js = (ROOT / "app" / "static" / "js" / "pages" / "admin_monitor.js").read_text()
    block = monitor_js[monitor_js.index("tabs: ["):monitor_js.index("groups: [")]
    for key, label in re.findall(r"\['([a-z_]+)',\s*'([^']+)'\]", block):
        report_tabs.append({"key": key, "label": label})

    cli = sorted(re.findall(r'@group\.command\("([a-z0-9-]+)"\)', (ROOT / "app" / "cli.py").read_text()))
    redirects = {old: f"{new}?tab={tab}" for old, (new, tab) in sorted(nav.REDIRECTS.items())}
    return {"routes": routes, "pages": pages, "report_tabs": report_tabs, "redirects": redirects, "cli": cli, "ui": ui}


if __name__ == "__main__":
    data = inventory()
    if "--write" in sys.argv:
        BASELINE.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n")
        print(f"wrote {BASELINE.relative_to(ROOT)}: {len(data['routes'])} route methods, {len(data['pages'])} pages, "
              f"{len(data['ui'])} page views, {len(data['report_tabs'])} report tabs, {len(data['cli'])} CLI commands")
    else:
        print(json.dumps(data, indent=1, ensure_ascii=False))
