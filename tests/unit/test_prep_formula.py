"""REC-1: table 4.1 of TESTING.md, expected values calculated by hand."""
import pytest

from app.services.recommendation_service import compute_recommended


@pytest.mark.parametrize("forecast,buffer,pre,batch,expected", [
    ("47.3", 10, 0, 6, 54),     # 52.03 / 6 = 8.67 -> 9 -> 54
    ("47.3", 10, 58, 6, 60),    # need = max(52.03, 58) = 58 -> 9.67 -> 10 -> 60
    ("0", 10, 0, 6, 0),         # need 0
    ("0", 10, 5, 6, 6),         # pre-orders lift the floor, then batch
    ("0.3", 10, 0, 6, 6),       # 0.33 rounds up to one batch
    ("60.0", 0, 0, 10, 60),     # exact multiple stays
    ("12.0", 10, 0, 1, 14),     # 13.2 -> 14
    ("45.45", 10, 0, 5, 50),    # 49.995 / 5 = 9.999 -> 10; Decimal must not lose this to float noise
    (None, 10, 0, 6, None),     # no forecast: no number
])
def test_prep_quantity_table(forecast, buffer, pre, batch, expected):
    assert compute_recommended(forecast, buffer, pre, batch) == expected


def test_result_is_a_batch_multiple_and_never_below_preorders():
    for f in ("3.3", "18.9", "101.1"):
        for pre in (0, 7, 40):
            r = compute_recommended(f, 10, pre, 6)
            assert r % 6 == 0 and r >= pre
