from app.extensions import db
from app.models.base import OutletScopedMixin, TimestampMixin, check, in_list

HOLIDAY_TYPES = ("public", "poya", "school", "other")
WEATHER_SOURCES = ("manual", "imported", "api", "synthetic")


class Holiday(OutletScopedMixin, TimestampMixin, db.Model):
    __tablename__ = "holidays"
    __table_args__ = (
        db.UniqueConstraint("outlet_id", "holiday_date", "name", name="uq_holidays_outlet_date_name"),
        check("type", in_list("holiday_type", HOLIDAY_TYPES)),
    )
    id = db.Column(db.Integer, primary_key=True)
    holiday_date = db.Column(db.Date, nullable=False, index=True)
    name = db.Column(db.String(120), nullable=False)
    holiday_type = db.Column(db.String(20), nullable=False)
    source = db.Column(db.String(40))


class Promotion(OutletScopedMixin, TimestampMixin, db.Model):
    __tablename__ = "promotions"
    __table_args__ = (
        check("dates", "end_date >= start_date"),
        check("pct", "discount_pct >= 0 AND discount_pct <= 100"),
    )
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    applies_to_all = db.Column(db.Boolean, nullable=False, default=False)
    promo_type = db.Column(db.String(30), nullable=False, default="percent_off")
    discount_pct = db.Column(db.Numeric(5, 2), nullable=False, default=0)
    is_active = db.Column(db.Boolean, nullable=False, default=True)

    items = db.relationship("PromotionItem", backref="promotion", cascade="all, delete-orphan")


class PromotionItem(db.Model):
    __tablename__ = "promotion_items"
    __table_args__ = (db.UniqueConstraint("promotion_id", "menu_item_id", name="uq_promotion_items_pair"),)
    id = db.Column(db.Integer, primary_key=True)
    promotion_id = db.Column(db.Integer, db.ForeignKey("promotions.id"), nullable=False)
    menu_item_id = db.Column(db.Integer, db.ForeignKey("menu_items.id"), nullable=False)


class WeatherDaily(OutletScopedMixin, TimestampMixin, db.Model):
    __tablename__ = "weather_daily"
    __table_args__ = (
        db.UniqueConstraint("outlet_id", "weather_date", name="uq_weather_daily_outlet_date"),
        check("rain", "rain_mm >= 0"),
        check("source", in_list("source", WEATHER_SOURCES)),
    )
    id = db.Column(db.Integer, primary_key=True)
    weather_date = db.Column(db.Date, nullable=False)
    rain_mm = db.Column(db.Numeric(6, 1), nullable=False, default=0)
    temp_c = db.Column(db.Numeric(4, 1))
    source = db.Column(db.String(20), nullable=False)
