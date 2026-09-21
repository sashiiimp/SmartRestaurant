"""Role menus. A link is added here when its page is built; the server still enforces access (C2)."""

NAV = {
    "admin": [("Dashboard", "/admin")],
    "kitchen": [("Dashboard", "/kitchen"), ("Prep plan", "/kitchen/prep"), ("Forecast", "/kitchen/forecast"),
                ("Served & waste", "/kitchen/record")],
    "inventory": [("Dashboard", "/inventory")],
}


def nav_links(role: str):
    return NAV.get(role, [])
