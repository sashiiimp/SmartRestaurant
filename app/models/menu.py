from app.extensions import db
from app.models.base import OutletScopedMixin, TimestampMixin, check


class MenuItem(OutletScopedMixin, TimestampMixin, db.Model):
    __tablename__ = "menu_items"
    __table_args__ = (
        db.UniqueConstraint("outlet_id", "name", name="uq_menu_items_outlet_name"),
        check("price", "price >= 0"),
        check("batch", "batch_size >= 1"),
    )
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    category = db.Column(db.String(60))
    price = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    portion_unit = db.Column(db.String(30), nullable=False, default="portion")
    shelf_life_hours = db.Column(db.Integer)
    batch_size = db.Column(db.Integer, nullable=False, default=1)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    is_available = db.Column(db.Boolean, nullable=False, default=True)

    recipe_lines = db.relationship("RecipeLine", backref="menu_item", cascade="all, delete-orphan")


class RecipeLine(db.Model):
    __tablename__ = "recipe_lines"
    __table_args__ = (
        db.UniqueConstraint("menu_item_id", "ingredient_id", name="uq_recipe_lines_item_ingredient"),
        check("qty", "quantity_per_portion > 0"),
    )
    id = db.Column(db.Integer, primary_key=True)
    menu_item_id = db.Column(db.Integer, db.ForeignKey("menu_items.id"), nullable=False)
    ingredient_id = db.Column(db.Integer, db.ForeignKey("ingredients.id"), nullable=False)
    quantity_per_portion = db.Column(db.Numeric(12, 4), nullable=False)

    ingredient = db.relationship("Ingredient")
