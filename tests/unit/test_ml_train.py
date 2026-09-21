"""ML-4, ML-5: training, determinism, honest selection."""
import numpy as np
import pandas as pd

from app.ml.evaluate import metrics
from app.ml.features import climatology
from app.ml.predict import predict
from app.ml.train import train_and_compare

EMPTY_HOL = pd.DataFrame({"date": pd.to_datetime([]), "holiday_type": []})
EMPTY_PROMO = pd.DataFrame({"item_id": [], "date": pd.to_datetime([]), "discount_pct": []})
EMPTY_W = pd.DataFrame({"date": pd.to_datetime([]), "rain_mm": [], "temp_c": []})


def synthetic(days=260, noise=2.0, seed=3):
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2026-01-01", periods=days)
    rows = []
    for item, base in ((1, 40), (2, 70)):
        for d in dates:
            rows.append((item, d, max(0.0, round(base * (1.5 if d.dayofweek >= 4 else 1.0) + rng.normal(0, noise)))))
    return pd.DataFrame(rows, columns=["item_id", "date", "qty"])


def test_metrics_hand_values():
    m = metrics([10, 20, 0, 30], [12, 18, 1, 30])
    assert m["mae"] == 1.25            # (2+2+1+0)/4
    assert m["bias"] == 0.25           # (2-2+1+0)/4
    assert m["mape_excluded"] == 1     # the actual-0 row
    assert m["mape"] == round((0.2 + 0.1 + 0.0) / 3 * 100, 3)
    assert m["wape"] == round(5 / 60 * 100, 3)


def test_training_returns_all_metrics_and_is_deterministic():
    s = synthetic()
    a = train_and_compare(s, EMPTY_HOL, EMPTY_PROMO, EMPTY_W, [1, 2])
    b = train_and_compare(s, EMPTY_HOL, EMPTY_PROMO, EMPTY_W, [1, 2])
    assert set(a.metrics["overall"]) == {"naive_lag7", "seasonal_mean4", "random_forest", "xgboost"}
    for m in a.metrics["overall"].values():
        assert all(k in m for k in ("mae", "rmse", "mape", "wape", "r2", "bias"))
    assert a.metrics["overall"] == b.metrics["overall"] and a.algorithm == b.algorithm
    assert a.metrics["holdout_rows"] == 56 * 2


def test_selection_picks_lowest_mae_and_reports_beats_baseline():
    r = train_and_compare(synthetic(), EMPTY_HOL, EMPTY_PROMO, EMPTY_W, [1, 2])
    overall = r.metrics["overall"]
    assert overall[r.algorithm]["mae"] == min(v["mae"] for v in overall.values())
    assert r.beats_baseline == (overall[r.algorithm]["mae"] < overall["naive_lag7"]["mae"])
    assert r.artifact["item_ids"] == [1, 2] and "climatology" in r.artifact


def test_baseline_wins_is_reported_honestly():
    """Pure noise around a constant: nothing should beat the naive baseline by much, and the result says what it is."""
    rng = np.random.default_rng(5)
    dates = pd.date_range("2026-01-01", periods=260)
    s = pd.DataFrame({"item_id": 1, "date": dates, "qty": (50 + rng.normal(0, 8, len(dates))).round()})
    r = train_and_compare(s, EMPTY_HOL, EMPTY_PROMO, EMPTY_W, [1])
    if r.algorithm in ("naive_lag7", "seasonal_mean4"):
        assert not r.beats_baseline or r.algorithm == "seasonal_mean4"
        assert "baseline" in r.selection_reason
    else:
        assert r.beats_baseline
    # predictions from a baseline artifact need no model object
    if r.artifact["model"] is None:
        assert (predict(r.artifact, pd.DataFrame({"lag_7": [5.0], "lag_14": [6.0], "lag_21": [7.0], "lag_28": [8.0]})) >= 0).all()


def test_too_little_history_raises_readable_error():
    import pytest
    with pytest.raises(ValueError, match="more history"):
        train_and_compare(synthetic(days=80), EMPTY_HOL, EMPTY_PROMO, EMPTY_W, [1, 2])
