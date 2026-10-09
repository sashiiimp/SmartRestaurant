from app.extensions import db
from app.models.base import BigInt, OutletScopedMixin, TimestampMixin, check, in_list, utcnow

WASTE_REASONS = ("overproduction", "quality", "expired", "other")


class PreparationRecord(OutletScopedMixin, TimestampMixin, db.Model):
    __tablename__ = "preparation_records"
    __table_args__ = (
        check("qty", "quantity > 0"),
        db.Index("ix_preparation_records_date_item", "outlet_id", "prep_date", "menu_item_id"),
    )
    id = db.Column(BigInt, primary_key=True)
    menu_item_id = db.Column(db.Integer, db.ForeignKey("menu_items.id"), nullable=False)
    prep_date = db.Column(db.Date, nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    prepared_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"))


class FoodWaste(OutletScopedMixin, TimestampMixin, db.Model):
    __tablename__ = "food_waste"
    __table_args__ = (
        check("qty", "quantity > 0"),
        check("reason", in_list("reason", WASTE_REASONS)),
        db.Index("ix_food_waste_date", "outlet_id", "waste_date"),
    )
    id = db.Column(BigInt, primary_key=True)
    menu_item_id = db.Column(db.Integer, db.ForeignKey("menu_items.id"), nullable=False)
    waste_date = db.Column(db.Date, nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    reason = db.Column(db.String(20), nullable=False)
    unit_price = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    note = db.Column(db.String(255))
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"))


class IngredientUsage(OutletScopedMixin, TimestampMixin, db.Model):
    """The kitchen's recorded actual ingredient use for a day (K8). It never moves stock (DATABASE.md DB8); the expected
    figure (prepared x recipe) is computed, not stored."""

    __tablename__ = "ingredient_usage"
    __table_args__ = (
        db.UniqueConstraint("outlet_id", "ingredient_id", "usage_date", name="uq_ingredient_usage_day"),
        check("qty", "quantity >= 0"),
    )
    id = db.Column(db.Integer, primary_key=True)
    ingredient_id = db.Column(db.Integer, db.ForeignKey("ingredients.id"), nullable=False)
    usage_date = db.Column(db.Date, nullable=False)
    quantity = db.Column(db.Numeric(12, 3), nullable=False)
    note = db.Column(db.String(255))
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"))


FOOD_USAGE_TYPES = ("staff_meal", "complimentary", "sample", "other")


class FoodUsage(OutletScopedMixin, TimestampMixin, db.Model):
    """Actual Food Usage (K14): prepared portions used other than sold or wasted (staff meals, complimentary portions,
    tasting samples, other). One figure per item, day and type; it never changes sales, stock or the forecast."""

    __tablename__ = "food_usage"
    __table_args__ = (
        db.UniqueConstraint("outlet_id", "menu_item_id", "usage_date", "usage_type", name="uq_food_usage_item_day_type"),
        check("qty", "quantity > 0"),
        check("usage_type", in_list("usage_type", FOOD_USAGE_TYPES)),
        db.Index("ix_food_usage_date", "outlet_id", "usage_date"),
    )
    id = db.Column(db.Integer, primary_key=True)
    menu_item_id = db.Column(db.Integer, db.ForeignKey("menu_items.id"), nullable=False)
    usage_date = db.Column(db.Date, nullable=False)
    usage_type = db.Column(db.String(20), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    note = db.Column(db.String(255))
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"))
