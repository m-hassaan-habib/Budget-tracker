"""Seed data for a new household.

These lists used to live inline in the templates -- the category list was
duplicated across expenses/add.html and expenses/edit.html, which meant adding
a category required editing two files and still left the `categories` table
unused. They now seed the database once and every screen reads from there.

Note: the "Acessories" spelling is deliberate. It is the value already stored
on existing expense rows, and renaming it here would orphan that history.
"""

DEFAULT_MEMBERS = ("Faisal", "Hassan", "Faran")

# (name, font-awesome icon, hex colour)
DEFAULT_CATEGORIES = (
    ("Acessories", "fas fa-gem", "#8b5cf6"),
    ("Appliances", "fas fa-blender", "#64748b"),
    ("Baby Food", "fas fa-baby-carriage", "#fbbf24"),
    ("Bakery", "fas fa-bread-slice", "#f59e0b"),
    ("Bills", "fas fa-file-invoice-dollar", "#ef4444"),
    ("Charity", "fas fa-hand-holding-heart", "#ef4444"),
    ("Cleaning", "fas fa-broom", "#a3a3a3"),
    ("Clothing", "fas fa-tshirt", "#3b82f6"),
    ("Cloud", "fas fa-cloud", "#60a5fa"),
    ("Coffee/Tea", "fas fa-mug-hot", "#a16207"),
    ("Courier/Shipping", "fas fa-shipping-fast", "#8b5cf6"),
    ("Domain", "fas fa-globe", "#10b981"),
    ("Eat Out", "fas fa-utensils", "#10b981"),
    ("Education", "fas fa-book", "#0ea5e9"),
    ("Electronics", "fas fa-laptop", "#0284c7"),
    ("Entertainment", "fas fa-film", "#f472b6"),
    ("Family Gift", "fas fa-gift", "#f59e0b"),
    ("Fitness", "fas fa-dumbbell", "#10b981"),
    ("Food Delivery", "fas fa-motorcycle", "#f97316"),
    ("Fruits & Veg", "fas fa-apple-alt", "#22c55e"),
    ("Fuel", "fas fa-gas-pump", "#f59e0b"),
    ("Furniture", "fas fa-couch", "#a16207"),
    ("Gardening", "fas fa-seedling", "#16a34a"),
    ("Grocery", "fas fa-shopping-cart", "#22c55e"),
    ("Healthcare", "fas fa-heartbeat", "#ef4444"),
    ("Home Improvement", "fas fa-hammer", "#f59e0b"),
    ("Hosting", "fas fa-server", "#4b5563"),
    ("Household Expense", "fas fa-home", "#64748b"),
    ("Insurance", "fas fa-shield-alt", "#0ea5e9"),
    ("Internet", "fas fa-wifi", "#6366f1"),
    ("Investment", "fas fa-chart-line", "#0ea5e9"),
    ("Laundry", "fas fa-tint", "#06b6d4"),
    ("Lend Money", "fas fa-hand-holding-usd", "#22c55e"),
    ("Loan Payment", "fas fa-credit-card", "#ef4444"),
    ("Meat & Poultry", "fas fa-drumstick-bite", "#ef4444"),
    ("Miscellaneous", "fas fa-ellipsis-h", "#9ca3af"),
    ("Mobile Top-up", "fas fa-sim-card", "#06b6d4"),
    ("Outdoor", "fas fa-tree", "#16a34a"),
    ("Parking", "fas fa-parking", "#3b82f6"),
    ("Pets", "fas fa-paw", "#84cc16"),
    ("Pharmacy", "fas fa-pills", "#22c55e"),
    ("Phone", "fas fa-mobile-alt", "#06b6d4"),
    ("Rent", "fas fa-home", "#4b5563"),
    ("Repair", "fas fa-tools", "#9ca3af"),
    ("Ride-hailing", "fas fa-taxi", "#f59e0b"),
    ("Salary", "fas fa-money-bill-wave", "#16a34a"),
    ("Savings", "fas fa-piggy-bank", "#84cc16"),
    ("Shopping", "fas fa-shopping-bag", "#8b5cf6"),
    ("Snacking", "fas fa-cookie-bite", "#f59e0b"),
    ("Software", "fas fa-code", "#0ea5e9"),
    ("Stationery", "fas fa-pen", "#6b7280"),
    ("Subscriptions", "fas fa-redo-alt", "#6366f1"),
    ("Taxes", "fas fa-file-invoice", "#ef4444"),
    ("Transportation", "fas fa-bus", "#6b7280"),
    ("Travel", "fas fa-plane", "#3b82f6"),
    ("Utilities", "fas fa-lightbulb", "#f59e0b"),
    ("Vacation", "fas fa-umbrella-beach", "#f59e0b"),
)

FALLBACK_ICON = "fas fa-ellipsis-h"
FALLBACK_COLOR = "#9ca3af"
