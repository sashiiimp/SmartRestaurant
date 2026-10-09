from app.extensions import db
from app.models.base import BigInt, OutletScopedMixin, TimestampMixin, check, in_list, utcnow

ALGORITHMS = ("random_forest", "xgboost", "naive_lag7", "seasonal_mean4")
MODEL_STATUSES = ("trained", "active", "retired")
RUN_TRIGGERS = ("cli", "admin", "backfill")
RUN_STATUSES = ("running", "ok", "partial", "skipped", "failed")
ALERT_TYPES = (
    "low_stock", "critical_stock", "projected_stockout", "expiry_warning",
    "waste_risk", "forecast_failed", "manual_shortage",
)
SEVERITIES = ("info", "warning", "critical")
ALERT_STATUSES = ("open", "acknowledged", "closed")
PREP_STATUSES = ("planned", "in_progress", "done")


class Setting(OutletScopedMixin, db.Model):
    __tablename__ = "settings"
    __table_args__ = (db.UniqueConstraint("outlet_id", "setting_key", name="uq_settings_outlet_key"),)
    id = db.Column(db.Integer, primary_key=True)
    setting_key = db.Column(db.String(80), nullable=False)
    value = db.Column(db.String(255))
    updated_by = db.Column(db.Integer, db.ForeignKey("users.id"))
    updated_at = db.Column(db.DateTime, nullable=False, default=utcnow, onupdate=utcnow)


class ModelVersion(OutletScopedMixin, TimestampMixin, db.Model):
    __tablename__ = "model_versions"
    __table_args__ = (
        check("algo", in_list("algorithm", ALGORITHMS)),
        check("status", in_list("status", MODEL_STATUSES)),
    )
    id = db.Column(db.Integer, primary_key=True)
    version_label = db.Column(db.String(40), nullable=False, unique=True)
    algorithm = db.Column(db.String(30), nullable=False)
    status = db.Column(db.String(20), nullable=False, default="trained")
    trained_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    train_start = db.Column(db.Date)
    train_end = db.Column(db.Date)
    holdout_start = db.Column(db.Date)
    holdout_end = db.Column(db.Date)
    n_train_rows = db.Column(db.Integer)
    feature_set = db.Column(db.JSON)
    params = db.Column(db.JSON)
    metrics = db.Column(db.JSON)
    beats_baseline = db.Column(db.Boolean, nullable=False, default=False)
    selection_reason = db.Column(db.String(255))
    artifact_path = db.Column(db.String(255))
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"))


class ForecastRun(OutletScopedMixin, TimestampMixin, db.Model):
    __tablename__ = "forecast_runs"
    __table_args__ = (
        check("trigger", in_list("trigger_type", RUN_TRIGGERS)),
        check("status", in_list("status", RUN_STATUSES)),
    )
    id = db.Column(db.Integer, primary_key=True)
    model_version_id = db.Column(db.Integer, db.ForeignKey("model_versions.id"))
    as_of_date = db.Column(db.Date, nullable=False)
    horizon_days = db.Column(db.Integer, nullable=False)
    trigger_type = db.Column(db.String(20), nullable=False)
    status = db.Column(db.String(20), nullable=False, default="running")
    reason = db.Column(db.String(255))
    items_forecast = db.Column(db.Integer, nullable=False, default=0)
    started_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    finished_at = db.Column(db.DateTime)
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"))

    model_version = db.relationship("ModelVersion")


class Forecast(OutletScopedMixin, db.Model):
    __tablename__ = "forecasts"
    __table_args__ = (
        check("qty", "predicted_qty >= 0"),
        check("method", in_list("method", ("model", "baseline"))),
        db.Index("ix_forecasts_lookup", "outlet_id", "menu_item_id", "target_date", "is_latest"),
    )
    id = db.Column(BigInt, primary_key=True)
    run_id = db.Column(db.Integer, db.ForeignKey("forecast_runs.id"), nullable=False)
    model_version_id = db.Column(db.Integer, db.ForeignKey("model_versions.id"))
    menu_item_id = db.Column(db.Integer, db.ForeignKey("menu_items.id"), nullable=False)
    target_date = db.Column(db.Date, nullable=False)
    predicted_qty = db.Column(db.Numeric(10, 2), nullable=False)
    method = db.Column(db.String(20), nullable=False)
    input_snapshot = db.Column(db.JSON)
    generated_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    is_latest = db.Column(db.Boolean, nullable=False, default=True)

    run = db.relationship("ForecastRun")
    model_version = db.relationship("ModelVersion")


class Recommendation(OutletScopedMixin, TimestampMixin, db.Model):
    """Written only when the manager decides; undecided plans are computed live."""

    __tablename__ = "recommendations"
    __table_args__ = (
        db.UniqueConstraint("outlet_id", "menu_item_id", "target_date", name="uq_recommendations_item_date"),
        check("status", in_list("status", ("accepted", "overridden"))),
        check("reason", "status <> 'overridden' OR override_reason IS NOT NULL"),
        check("final", "final_qty >= 0"),
        check("prep_status", in_list("prep_status", PREP_STATUSES)),
    )
    id = db.Column(db.Integer, primary_key=True)
    menu_item_id = db.Column(db.Integer, db.ForeignKey("menu_items.id"), nullable=False)
    target_date = db.Column(db.Date, nullable=False)
    forecast_id = db.Column(BigInt, db.ForeignKey("forecasts.id"))
    forecast_qty = db.Column(db.Numeric(10, 2), nullable=False)
    buffer_pct = db.Column(db.Numeric(5, 2), nullable=False)
    preorder_qty = db.Column(db.Integer, nullable=False, default=0)
    batch_size = db.Column(db.Integer, nullable=False, default=1)
    recommended_qty = db.Column(db.Integer, nullable=False)
    final_qty = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(20), nullable=False)
    override_reason = db.Column(db.String(255))
    decided_by = db.Column(db.Integer, db.ForeignKey("users.id"))
    decided_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    # Food Preparation Management (K4): planned -> in_progress -> done, kept on the decision row (one per item and day)
    prep_status = db.Column(db.String(20), nullable=False, default="planned", server_default="planned")
    prep_started_at = db.Column(db.DateTime)
    prep_done_at = db.Column(db.DateTime)
    prep_done_by = db.Column(db.Integer, db.ForeignKey("users.id"))


class Alert(OutletScopedMixin, db.Model):
    __tablename__ = "alerts"
    __table_args__ = (
        db.UniqueConstraint("outlet_id", "open_key", name="uq_alerts_outlet_open_key"),
        check("type", in_list("alert_type", ALERT_TYPES)),
        check("severity", in_list("severity", SEVERITIES)),
        check("status", in_list("status", ALERT_STATUSES)),
        db.Index("ix_alerts_status", "outlet_id", "status"),
    )
    id = db.Column(db.Integer, primary_key=True)
    alert_type = db.Column(db.String(30), nullable=False)
    severity = db.Column(db.String(20), nullable=False)
    entity_type = db.Column(db.String(20), nullable=False)
    entity_id = db.Column(db.Integer)
    target_date = db.Column(db.Date)
    message = db.Column(db.String(255), nullable=False)
    details = db.Column(db.JSON)
    status = db.Column(db.String(20), nullable=False, default="open")
    dedupe_key = db.Column(db.String(120), nullable=False)
    # Equals dedupe_key while the alert is open/acknowledged, NULL once closed: a portable partial-unique.
    open_key = db.Column(db.String(120))
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    acknowledged_by = db.Column(db.Integer, db.ForeignKey("users.id"))
    acknowledged_at = db.Column(db.DateTime)
    closed_at = db.Column(db.DateTime)
    closed_reason = db.Column(db.String(20))
