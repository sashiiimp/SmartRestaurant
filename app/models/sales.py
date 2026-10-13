from app.extensions import db
from app.models.base import BigInt, OutletScopedMixin, TimestampMixin, check, in_list

SALES_SOURCES = ("import", "kitchen", "synthetic", "manual")
PREORDER_STATUSES = ("pending", "confirmed", "completed", "cancelled")
ORDER_STATUSES = ("open", "fulfilled", "cancelled")


class SalesRecord(OutletScopedMixin, TimestampMixin, db.Model):
    __tablename__ = "sales_records"
    __table_args__ = (
        db.UniqueConstraint("outlet_id", "menu_item_id", "sale_date", name="uq_sales_records_item_date"),
        check("qty", "quantity_sold >= 0"),
        check("price", "unit_price >= 0"),
        check("source", in_list("source", SALES_SOURCES)),
        db.Index("ix_sales_records_outlet_date", "outlet_id", "sale_date"),
    )
    id = db.Column(BigInt, primary_key=True)
    menu_item_id = db.Column(db.Integer, db.ForeignKey("menu_items.id"), nullable=False)
    sale_date = db.Column(db.Date, nullable=False)
    quantity_sold = db.Column(db.Integer, nullable=False)
    unit_price = db.Column(db.Numeric(12, 2), nullable=False)
    source = db.Column(db.String(20), nullable=False)
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"))

    menu_item = db.relationship("MenuItem")


class PreOrder(OutletScopedMixin, TimestampMixin, db.Model):
    __tablename__ = "pre_orders"
    __table_args__ = (
        check("qty", "quantity > 0"),
        check("status", in_list("status", PREORDER_STATUSES)),
        db.Index("ix_pre_orders_date", "outlet_id", "target_date"),
    )
    id = db.Column(db.Integer, primary_key=True)
    menu_item_id = db.Column(db.Integer, db.ForeignKey("menu_items.id"), nullable=False)
    target_date = db.Column(db.Date, nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(20), nullable=False, default="pending")
    customer_note = db.Column(db.String(255))
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"))
    # added 13 Oct 2026 (migration c4e1a7b9d052); nullable so pre-orders recorded before then stay valid
    customer_name = db.Column(db.String(100))
    customer_contact = db.Column(db.String(60))
    pickup_time = db.Column(db.Time)
    completed_at = db.Column(db.DateTime)


class Order(OutletScopedMixin, TimestampMixin, db.Model):
    """A daily food order kept as an internal record (K10). No prices, no payment; it feeds no calculation."""

    __tablename__ = "orders"
    __table_args__ = (
        check("qty", "quantity > 0"),
        check("status", in_list("status", ORDER_STATUSES)),
        db.Index("ix_orders_date", "outlet_id", "order_date"),
    )
    id = db.Column(db.Integer, primary_key=True)
    menu_item_id = db.Column(db.Integer, db.ForeignKey("menu_items.id"), nullable=False)
    order_date = db.Column(db.Date, nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(20), nullable=False, default="open")
    customer_note = db.Column(db.String(255))
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"))
