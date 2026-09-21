"""Prepared / served / waste recording (Kitchen Operations service, ARCH section 3)."""
from app.extensions import db
from app.models import FoodWaste, PreparationRecord
from app.services import audit


def bulk_load_history(outlet_id: int, prep_rows: list[dict], waste_rows: list[dict], source: str = "synthetic") -> dict:
    """Load historical preparation and waste rows in bulk (used by the synthetic-data generator only)."""
    if prep_rows:
        db.session.bulk_insert_mappings(PreparationRecord, [{"outlet_id": outlet_id, **r} for r in prep_rows])
    if waste_rows:
        db.session.bulk_insert_mappings(FoodWaste, [{"outlet_id": outlet_id, **r} for r in waste_rows])
    audit.record(outlet_id, None, "history.bulk_load", "kitchen", None,
                 {"prepared": len(prep_rows), "waste": len(waste_rows), "source": source})
    db.session.commit()
    return {"prepared": len(prep_rows), "waste": len(waste_rows)}
