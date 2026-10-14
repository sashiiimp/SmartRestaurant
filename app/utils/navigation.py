"""Role menus, grouped under short headings. A link is added here when its page is built; the server still enforces
access (C2). Labels are plain names for what the page does.

Related pages are merged into one menu entry with tabs (HUBS). A merged page keeps the URL of its first tab; the URLs
of the other tabs still work and redirect to the right tab (REDIRECTS), so bookmarks and old links keep working."""
from urllib.parse import urlencode

from flask import current_app, redirect, render_template, request

NAV_GROUPS = {
    "admin": [
        ("Overview", [("Dashboard", "/admin"), ("Reports & Analytics", "/admin/monitor"), ("Forecasting", "/admin/models")]),
        ("Setup", [("Menu & recipes", "/admin/catalog"), ("Administration", "/admin/users")]),
    ],
    "kitchen": [
        ("Today", [("Dashboard", "/kitchen"), ("Plan & prepare", "/kitchen/prep"), ("Served & waste", "/kitchen/record")]),
        ("Supplies & orders", [("Ingredients", "/kitchen/requirements"), ("Orders & pre-orders", "/kitchen/orders")]),
    ],
    "inventory": [
        ("Today", [("Dashboard", "/inventory"), ("Kitchen requests", "/inventory/requests")]),
        ("Stock & buying", [("Stock", "/inventory/stock"), ("Purchasing", "/inventory/reorder")]),
    ],
}

# page path -> tabs as (key, label, template). The first tab opens when ?tab= is missing or unknown.
HUBS = {
    "/admin/models": [("data", "Historical data", "admin/data.html"), ("models", "ML models", "admin/models.html"),
                      ("runs", "Forecast generation", "admin/models.html")],
    "/admin/users": [("users", "Users", "admin/users.html"), ("settings", "Settings & alerts", "admin/settings.html"),
                     ("roles", "Role access", "admin/roles.html")],
    "/kitchen/prep": [("prep", "Prep plan", "kitchen/prep.html"), ("forecast", "7-day forecast", "kitchen/forecast.html")],
    "/kitchen/requirements": [("needs", "Needs & shortages", "kitchen/requirements.html"),
                              ("requests", "Stock requests", "kitchen/stock_requests.html")],
    "/inventory/stock": [("levels", "Stock levels", "inventory/stock.html"), ("record", "Record stock", "inventory/movements.html")],
    "/inventory/reorder": [("reorder", "Reorder", "inventory/reorder.html"), ("demand", "Ingredient demand", "inventory/forecast.html"),
                           ("orders", "Purchase orders", "inventory/purchase_orders.html"),
                           ("suppliers", "Suppliers", "inventory/suppliers.html")],
}

# merged pages whose first tab is not the one to open by default (Forecasting lists its tabs in workflow order)
DEFAULT_TAB = {"/admin/models": "models"}

# old page path -> (merged page, tab). Reports switches its tabs inside the page, so its tab is a Reports tab key.
REDIRECTS = {
    "/admin/data": ("/admin/models", "data"),
    "/admin/settings": ("/admin/users", "settings"),
    "/admin/inventory": ("/admin/monitor", "stock"),
    "/kitchen/forecast": ("/kitchen/prep", "forecast"),
    "/kitchen/stock-requests": ("/kitchen/requirements", "requests"),
    "/inventory/movements": ("/inventory/stock", "record"),
    "/inventory/forecast": ("/inventory/reorder", "demand"),
    "/inventory/purchase-orders": ("/inventory/reorder", "orders"),
    "/inventory/suppliers": ("/inventory/reorder", "suppliers"),
}


def nav_groups(role: str):
    return NAV_GROUPS.get(role, [])


def nav_links(role: str):
    """The same links as one flat list (used for the page title in the top bar)."""
    return [link for _, links in nav_groups(role) for link in links]


def render_hub(path: str, **context):
    """Render the tab of a merged page that ?tab= names (else its default tab); context goes to the tab's template."""
    tabs = HUBS[path]
    key = request.args.get("tab") or DEFAULT_TAB.get(path)
    current = next((t for t in tabs if t[0] == key), tabs[0])
    hub = {"path": path, "tab": current[0], "tabs": [{"key": k, "label": label} for k, label, _ in tabs]}
    return render_template(current[2], hub=hub, **context)


def redirect_to_tab(old_path: str):
    """Send an old page address to its tab on the merged page, keeping the other query arguments (?open=, ?ingredient=)."""
    path, tab = REDIRECTS[old_path]
    args = [("tab", tab)] + [(k, v) for k, v in request.args.items(multi=True) if k != "tab"]
    return redirect(f"{path}?{urlencode(args)}")


def role_access():
    """Which role may open each menu page, read from the access rule the server applies to that page (the blueprint
    guard) rather than from the menu, so the table cannot show access that the server would refuse."""
    adapter = current_app.url_map.bind("localhost")
    rows = []
    for role in NAV_GROUPS:
        for _, links in nav_groups(role):
            for label, href in links:
                endpoint, _ = adapter.match(href)
                allowed = getattr(current_app.blueprints[endpoint.split(".")[0]], "allowed_roles", frozenset())
                rows.append({"page": label, "path": href, "tabs": [t[1] for t in HUBS.get(href, [])],
                             "roles": {r: r in allowed for r in NAV_GROUPS}})
    return rows


# The decision chain the whole system follows (proposal: forecast -> decision -> outcome). Shown on the dashboards and,
# as "Step n of 6", in the top bar of the page where that step happens. Display only.
WORKFLOW = ["Historical sales", "ML demand forecast", "Preparation recommendations", "BOM & ingredient requirements",
            "Inventory decisions", "Food waste monitoring"]

# (page path, tab) -> step number; tab None = the page's only (or default) view. Reports & Analytics and the dashboards
# cover several steps, so they have none.
PAGE_STEP = {
    ("/admin/models", "data"): 1, ("/admin/models", "models"): 2, ("/admin/models", "runs"): 2, ("/admin/catalog", None): 4,
    ("/kitchen/prep", "prep"): 3, ("/kitchen/prep", "forecast"): 2, ("/kitchen/orders", None): 3,
    ("/kitchen/requirements", "needs"): 4, ("/kitchen/requirements", "requests"): 5, ("/kitchen/record", None): 6,
    ("/inventory/stock", "levels"): 5, ("/inventory/stock", "record"): 5, ("/inventory/requests", None): 5,
    ("/inventory/reorder", "reorder"): 5, ("/inventory/reorder", "demand"): 4, ("/inventory/reorder", "orders"): 5,
    ("/inventory/reorder", "suppliers"): 5,
}


def workflow_step(path: str):
    """(number, name) of the workflow step the current page belongs to, or None."""
    tab = None
    if path in HUBS:
        keys = [t[0] for t in HUBS[path]]
        tab = request.args.get("tab") if request.args.get("tab") in keys else (DEFAULT_TAB.get(path) or keys[0])
    n = PAGE_STEP.get((path, tab))
    return (n, WORKFLOW[n - 1]) if n else None
