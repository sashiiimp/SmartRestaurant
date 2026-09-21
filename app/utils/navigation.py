"""Role menus. A link is added here when its page is built; the server still enforces access (C2)."""

NAV = {
    "admin": [("Dashboard", "/admin"), ("Monitoring", "/admin/monitor"), ("Inventory", "/admin/inventory"), ("Models", "/admin/models"), ("Data", "/admin/data"),
              ("Menu & recipes", "/admin/catalog"), ("Users", "/admin/users"), ("Settings", "/admin/settings")],
    "kitchen": [("Dashboard", "/kitchen"), ("Prep plan", "/kitchen/prep"), ("Forecast", "/kitchen/forecast"), ("Orders", "/kitchen/orders"), ("Ingredients", "/kitchen/requirements"), ("Stock requests", "/kitchen/stock-requests"),
                ("Served & waste", "/kitchen/record")],
    "inventory": [("Dashboard", "/inventory"), ("Stock", "/inventory/stock"), ("Record stock", "/inventory/movements"),
                  ("Ingredient demand", "/inventory/forecast"), ("Reorder", "/inventory/reorder"), ("Purchase orders", "/inventory/purchase-orders"), ("Kitchen requests", "/inventory/requests"),
                  ("Suppliers", "/inventory/suppliers")],
}


def nav_links(role: str):
    return NAV.get(role, [])
