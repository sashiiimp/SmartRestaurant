"""Final UI review, 17 Oct 2026: the inventory dashboard lists only batches that are still usable under Expiring
soon; the batches already expired are counted, not listed (TESTING.md 4.2 world: chicken has a 5 kg expired batch)."""
from datetime import timedelta

from app.services import dashboard_service as dash
from tests.factories import add_batch
from tests.integration.test_requirements_reorder_alerts import TODAY, kitchen_world  # noqa: F401 (fixture)


def test_expiring_soon_lists_usable_batches_and_counts_the_expired(kitchen_world):
    w = kitchen_world
    d = dash.inventory_dashboard(1)
    assert d["expiring"] == [] and d["totals"]["expired_batches"] == 1          # the expired chicken is counted only
    add_batch(w["chicken"], 4, received=TODAY, expiry=TODAY + timedelta(days=2), batch_no="CHK-SOON")
    d = dash.inventory_dashboard(1)
    assert [b["batch_no"] for b in d["expiring"]] == ["CHK-SOON"] and not d["expiring"][0]["expired"]
    assert (d["totals"]["expiring_batches"], d["totals"]["expired_batches"]) == (1, 1)
