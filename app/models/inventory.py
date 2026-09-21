from app.extensions import db
from app.models.base import BigInt, OutletScopedMixin, TimestampMixin, check, in_list, utcnow

MOVEMENT_TYPES = ("stock_in", "stock_out", "wastage", "adjustment")
PO_STATUSES = ("draft", "sent", "partially_received", "received", "cancelled")
STOCK_REQUEST_STATUSES = ("pending", "approved", "issued", "rejected", "cancelled")


class Supplier(OutletScopedMixin, TimestampMixin, db.Model):
    __tablename__ = "suppliers"
    __table_args__ = (
        db.UniqueConstraint("outlet_id", "name", name="uq_suppliers_outlet_name"),
        check("lead", "lead_time_days >= 0"),
    )
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    contact_person = db.Column(db.String(120))
    phone = db.Column(db.String(40))
    email = db.Column(db.String(160))
    lead_time_days = db.Column(db.Integer, nullable=False, default=2)
    notes = db.Column(db.String(255))
    is_active = db.Column(db.Boolean, nullable=False, default=True)


class Ingredient(OutletScopedMixin, TimestampMixin, db.Model):
    __tablename__ = "ingredients"
    __table_args__ = (
        db.UniqueConstraint("outlet_id", "name", name="uq_ingredients_outlet_name"),
        check("levels", "min_stock >= 0 AND reorder_level >= min_stock"),
        check("pack", "pack_size > 0 AND reorder_qty >= 0"),
    )
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    unit = db.Column(db.String(20), nullable=False)
    category = db.Column(db.String(60))
    shelf_life_days = db.Column(db.Integer)
    default_supplier_id = db.Column(db.Integer, db.ForeignKey("suppliers.id"))
    min_stock = db.Column(db.Numeric(12, 3), nullable=False, default=0)
    reorder_level = db.Column(db.Numeric(12, 3), nullable=False, default=0)
    pack_size = db.Column(db.Numeric(12, 3), nullable=False, default=1)
    reorder_qty = db.Column(db.Numeric(12, 3), nullable=False, default=0)
    is_active = db.Column(db.Boolean, nullable=False, default=True)

    default_supplier = db.relationship("Supplier")


class StockBatch(OutletScopedMixin, TimestampMixin, db.Model):
    __tablename__ = "stock_batches"
    __table_args__ = (
        check("qty", "qty_received > 0 AND qty_remaining >= 0"),
        check("expiry", "expiry_date IS NULL OR expiry_date >= received_date"),
        db.Index("ix_stock_batches_fefo", "outlet_id", "ingredient_id", "expiry_date"),
    )
    id = db.Column(db.Integer, primary_key=True)
    ingredient_id = db.Column(db.Integer, db.ForeignKey("ingredients.id"), nullable=False)
    batch_no = db.Column(db.String(60))
    received_date = db.Column(db.Date, nullable=False)
    expiry_date = db.Column(db.Date)
    qty_received = db.Column(db.Numeric(12, 3), nullable=False)
    qty_remaining = db.Column(db.Numeric(12, 3), nullable=False)
    unit_cost = db.Column(db.Numeric(12, 2))
    supplier_id = db.Column(db.Integer, db.ForeignKey("suppliers.id"))
    purchase_order_id = db.Column(db.Integer, db.ForeignKey("purchase_orders.id"))

    ingredient = db.relationship("Ingredient")


class StockMovement(OutletScopedMixin, db.Model):
    """Immutable: there is no update or delete code path (DB9)."""

    __tablename__ = "stock_movements"
    __table_args__ = (
        check("type", in_list("movement_type", MOVEMENT_TYPES)),
        check(
            "sign",
            "(movement_type = 'stock_in' AND quantity > 0) OR "
            "(movement_type IN ('stock_out','wastage') AND quantity < 0) OR "
            "(movement_type = 'adjustment' AND quantity <> 0)",
        ),
        db.Index("ix_stock_movements_ing_date", "outlet_id", "ingredient_id", "movement_date"),
    )
    id = db.Column(BigInt, primary_key=True)
    ingredient_id = db.Column(db.Integer, db.ForeignKey("ingredients.id"), nullable=False)
    batch_id = db.Column(db.Integer, db.ForeignKey("stock_batches.id"), nullable=False)
    movement_type = db.Column(db.String(20), nullable=False)
    quantity = db.Column(db.Numeric(12, 3), nullable=False)
    reason = db.Column(db.String(40))
    note = db.Column(db.String(255))
    movement_date = db.Column(db.Date, nullable=False)
    reference_type = db.Column(db.String(30))
    reference_id = db.Column(db.Integer)
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"))
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)


class PurchaseOrder(OutletScopedMixin, TimestampMixin, db.Model):
    __tablename__ = "purchase_orders"
    __table_args__ = (
        db.UniqueConstraint("outlet_id", "po_number", name="uq_purchase_orders_outlet_number"),
        check("status", in_list("status", PO_STATUSES)),
    )
    id = db.Column(db.Integer, primary_key=True)
    supplier_id = db.Column(db.Integer, db.ForeignKey("suppliers.id"), nullable=False)
    po_number = db.Column(db.String(40), nullable=False)
    status = db.Column(db.String(30), nullable=False, default="draft")
    order_date = db.Column(db.Date)
    expected_date = db.Column(db.Date)
    notes = db.Column(db.String(255))
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"))

    lines = db.relationship("PurchaseOrderLine", backref="purchase_order", cascade="all, delete-orphan")


class PurchaseOrderLine(db.Model):
    __tablename__ = "purchase_order_lines"
    __table_args__ = (check("qty", "qty_ordered > 0 AND qty_received >= 0"),)
    id = db.Column(db.Integer, primary_key=True)
    purchase_order_id = db.Column(db.Integer, db.ForeignKey("purchase_orders.id"), nullable=False)
    ingredient_id = db.Column(db.Integer, db.ForeignKey("ingredients.id"), nullable=False)
    qty_ordered = db.Column(db.Numeric(12, 3), nullable=False)
    qty_received = db.Column(db.Numeric(12, 3), nullable=False, default=0)
    unit_cost = db.Column(db.Numeric(12, 2))


class StockRequest(OutletScopedMixin, TimestampMixin, db.Model):
    """Ingredients the kitchen asks the inventory section for (K11); the inventory manager approves, rejects or issues (I15)."""

    __tablename__ = "stock_requests"
    __table_args__ = (
        check("status", in_list("status", STOCK_REQUEST_STATUSES)),
        check("reject", "status <> 'rejected' OR reject_reason IS NOT NULL"),
        db.Index("ix_stock_requests_status", "outlet_id", "status"),
    )
    id = db.Column(db.Integer, primary_key=True)
    requested_by = db.Column(db.Integer, db.ForeignKey("users.id"))
    needed_date = db.Column(db.Date)
    note = db.Column(db.String(255))
    status = db.Column(db.String(20), nullable=False, default="pending")
    reject_reason = db.Column(db.String(255))
    decided_by = db.Column(db.Integer, db.ForeignKey("users.id"))
    decided_at = db.Column(db.DateTime)

    lines = db.relationship("StockRequestLine", backref="stock_request", cascade="all, delete-orphan",
                            order_by="StockRequestLine.id")


class StockRequestLine(db.Model):
    __tablename__ = "stock_request_lines"
    __table_args__ = (check("qty", "qty_requested > 0 AND qty_issued >= 0 AND qty_issued <= qty_requested"),)
    id = db.Column(db.Integer, primary_key=True)
    stock_request_id = db.Column(db.Integer, db.ForeignKey("stock_requests.id"), nullable=False, index=True)
    ingredient_id = db.Column(db.Integer, db.ForeignKey("ingredients.id"), nullable=False)
    qty_requested = db.Column(db.Numeric(12, 3), nullable=False)
    qty_issued = db.Column(db.Numeric(12, 3), nullable=False, default=0)
