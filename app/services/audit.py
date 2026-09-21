from app.extensions import db
from app.models import AuditLog


def record(outlet_id: int, user_id: int | None, action: str, entity_type: str | None = None,
           entity_id=None, detail: dict | None = None) -> None:
    """Add an audit row to the current transaction (the calling service commits)."""
    db.session.add(AuditLog(outlet_id=outlet_id, user_id=user_id, action=action, entity_type=entity_type,
                            entity_id=str(entity_id) if entity_id is not None else None, detail=detail))
