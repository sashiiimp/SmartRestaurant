"""Role menus. A link is added here when its page is built; the server still enforces access (C2)."""

NAV = {
    "admin": [("Dashboard", "/admin"), ("Monitoring", "/admin/monitor"), ("Models", "/admin/models"), ("Data", "/admin/data"),
              ("Menu & recipes", "/admin/catalog"), ("Users", "/admin/users"), ("Settings", "/admin/settings")],
    "kitchen": [("Dashboard", "/kitchen"), ("Prep plan", "/kitchen/prep"), ("Forecast", "/kitchen/forecast"), ("Ingredients", "/kitchen/requirements"),
                ("Served & waste", "/kitchen/record")],
    "inventory": [("Dashboard", "/inventory"), ("Stock", "/inventory/stock"), ("Record stock", "/inventory/movements"),
                  ("Ingredient demand", "/inventory/forecast"), ("Reorder", "/inventory/reorder")],
}


def nav_links(role: str):
    return NAV.get(role, [])
