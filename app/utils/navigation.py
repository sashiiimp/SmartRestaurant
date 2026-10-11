"""Role menus, grouped under short headings. A link is added here when its page is built; the server still enforces
access (C2). Labels are plain names for what the page does; the URLs never change."""

NAV_GROUPS = {
    "admin": [
        ("Overview", [("Dashboard", "/admin"), ("Reports", "/admin/monitor"), ("Inventory overview", "/admin/inventory")]),
        ("Forecasting", [("Forecast models", "/admin/models"), ("Import data", "/admin/data")]),
        ("Setup", [("Menu & recipes", "/admin/catalog"), ("Users", "/admin/users"), ("Settings", "/admin/settings")]),
    ],
    "kitchen": [
        ("Today", [("Dashboard", "/kitchen"), ("Demand forecast", "/kitchen/forecast"), ("Prep plan", "/kitchen/prep"),
                   ("Served & waste", "/kitchen/record")]),
        ("Ingredients", [("Ingredient needs", "/kitchen/requirements"), ("Stock requests", "/kitchen/stock-requests")]),
        ("Orders", [("Orders & pre-orders", "/kitchen/orders")]),
    ],
    "inventory": [
        ("Stock", [("Dashboard", "/inventory"), ("Stock levels", "/inventory/stock"), ("Record stock", "/inventory/movements"),
                   ("Kitchen requests", "/inventory/requests")]),
        ("Purchasing", [("Ingredient demand", "/inventory/forecast"), ("Reorder", "/inventory/reorder"),
                        ("Purchase orders", "/inventory/purchase-orders"), ("Suppliers", "/inventory/suppliers")]),
    ],
}


def nav_groups(role: str):
    return NAV_GROUPS.get(role, [])


def nav_links(role: str):
    """The same links as one flat list (used for the page title in the top bar)."""
    return [link for _, links in nav_groups(role) for link in links]
