"""Seed catalog: menu, suppliers, ingredients, recipes. All values are invented demo data (synthetic)."""

SUPPLIERS = [
    {"name": "Ceylon Poultry & Meats", "contact_person": "Sales desk", "phone": "011-0000001", "lead_time_days": 2},
    {"name": "Colombo Fresh Produce", "contact_person": "Sales desk", "phone": "011-0000002", "lead_time_days": 1},
    {"name": "Lanka Dry Goods", "contact_person": "Sales desk", "phone": "011-0000003", "lead_time_days": 3},
]

# name, price, batch_size, shelf_life_hours, category, base_daily_demand (used by the generator)
MENU = [
    ("Chicken Burger", 650, 6, 4, "Burgers", 80),
    ("Beef Burger", 850, 6, 4, "Burgers", 45),
    ("Veggie Burger", 590, 4, 4, "Burgers", 25),
    ("Fried Chicken 2 pc", 990, 8, 3, "Chicken", 55),
    ("Chicken Kottu", 1100, 4, 4, "Kottu", 50),
    ("Veg Kottu", 850, 4, 4, "Kottu", 25),
    ("French Fries", 450, 10, 2, "Sides", 140),
    ("Chicken Wrap", 720, 6, 4, "Wraps", 40),
    ("Iced Milo", 350, 10, 6, "Drinks", 50),
    ("Lime Juice", 280, 10, 6, "Drinks", 45),
]

# Items that contain meat (Poya-day effect in the generator).
MEAT_ITEMS = {"Chicken Burger", "Beef Burger", "Fried Chicken 2 pc", "Chicken Kottu", "Chicken Wrap"}
DRINK_ITEMS = {"Iced Milo", "Lime Juice"}
SCHOOL_ITEMS = {"Chicken Burger", "Beef Burger", "Veggie Burger", "French Fries", "Iced Milo", "Lime Juice"}

# name, unit, category, shelf_life_days, supplier_index, min_stock, reorder_level, pack_size, min_order_qty,
# opening stock, unit cost (LKR)
INGREDIENTS = [
    ("Chicken", "kg", "Meat", 4, 0, 20, 60, 10, 40, 30, 1350),
    ("Beef patty", "pcs", "Meat", 5, 0, 50, 100, 50, 100, 180, 190),
    ("Veg patty", "pcs", "Frozen", 30, 2, 28, 56, 28, 56, 90, 95),
    ("Burger bun", "pcs", "Bakery", 4, 2, 170, 340, 50, 200, 500, 32),
    ("Wrap tortilla", "pcs", "Bakery", 7, 2, 45, 90, 25, 100, 150, 28),
    ("Kottu roti", "pcs", "Bakery", 4, 2, 85, 170, 50, 100, 260, 24),
    ("Potato", "kg", "Produce", 14, 1, 40, 80, 10, 50, 35, 220),
    ("Cooking oil", "L", "Dry goods", 180, 2, 14, 28, 5, 20, 60, 640),
    ("Lettuce", "kg", "Produce", 4, 1, 5, 9, 1, 5, 12, 480),
    ("Tomato", "kg", "Produce", 5, 1, 5, 9, 1, 5, 14, 320),
    ("Onion", "kg", "Produce", 21, 1, 4, 8, 1, 5, 25, 280),
    ("Cheese slice", "pcs", "Dairy", 30, 2, 150, 300, 50, 150, 600, 38),
    ("Mayonnaise", "kg", "Dry goods", 60, 2, 4, 8, 1, 4, 20, 950),
    ("Mixed vegetables", "kg", "Produce", 4, 1, 8, 16, 1, 8, 30, 350),
    ("Egg", "pcs", "Produce", 14, 1, 90, 180, 30, 90, 400, 42),
    ("Milo powder", "kg", "Dry goods", 365, 2, 2, 4, 1, 2, 10, 2400),
    ("Milk", "L", "Dairy", 5, 2, 12, 24, 6, 12, 50, 320),
    ("Lime", "kg", "Produce", 7, 1, 5, 9, 1, 5, 20, 600),
    ("Sugar", "kg", "Dry goods", 365, 2, 5, 10, 1, 5, 25, 260),
    ("Fried chicken coating", "kg", "Dry goods", 180, 2, 3, 6, 1, 3, 12, 780),
]

# menu item -> [(ingredient, quantity per portion in the ingredient's unit)]
RECIPES = {
    "Chicken Burger": [("Chicken", "0.120"), ("Burger bun", "1"), ("Lettuce", "0.015"), ("Tomato", "0.020"),
                       ("Mayonnaise", "0.015"), ("Cheese slice", "1")],
    "Beef Burger": [("Beef patty", "1"), ("Burger bun", "1"), ("Lettuce", "0.015"), ("Tomato", "0.020"),
                    ("Onion", "0.020"), ("Cheese slice", "1"), ("Mayonnaise", "0.015")],
    "Veggie Burger": [("Veg patty", "1"), ("Burger bun", "1"), ("Lettuce", "0.015"), ("Tomato", "0.020"),
                      ("Mayonnaise", "0.015")],
    "Fried Chicken 2 pc": [("Chicken", "0.300"), ("Cooking oil", "0.050"), ("Fried chicken coating", "0.040")],
    "Chicken Kottu": [("Kottu roti", "1"), ("Chicken", "0.100"), ("Egg", "1"), ("Mixed vegetables", "0.080"),
                      ("Onion", "0.030"), ("Cooking oil", "0.020")],
    "Veg Kottu": [("Kottu roti", "1"), ("Egg", "1"), ("Mixed vegetables", "0.120"), ("Onion", "0.030"),
                  ("Cooking oil", "0.020")],
    "French Fries": [("Potato", "0.250"), ("Cooking oil", "0.060")],
    "Chicken Wrap": [("Wrap tortilla", "1"), ("Chicken", "0.100"), ("Lettuce", "0.020"), ("Tomato", "0.020"),
                     ("Mayonnaise", "0.020")],
    "Iced Milo": [("Milo powder", "0.025"), ("Milk", "0.200"), ("Sugar", "0.015")],
    "Lime Juice": [("Lime", "0.080"), ("Sugar", "0.025")],
}

# Opening stock is about nine days of need for most items so the first demo is not a wall of alerts; chicken and
# potato are deliberately short (chicken low, potato critical) so the shortage -> alert -> reorder flow is visible.
_SPECIAL_OPENING = {"Chicken": 30, "Potato": 35}
INGREDIENTS = [row[:9] + (_SPECIAL_OPENING.get(row[0], row[9] * 3),) + row[10:] for row in INGREDIENTS]
