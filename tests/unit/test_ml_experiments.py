"""Cross-validation, ablation and segment errors (app/ml/experiments.py, ML_EVALUATION.md sections 4 to 6)."""
import pandas as pd
import pytest

from app.ml.experiments import feature_sets, fold_windows, run_experiments
from app.ml.features import BASE_FEATURES
from app.ml.train import train_and_compare

from tests.unit.test_ml_train import EMPTY_HOL, EMPTY_PROMO, EMPTY_W, synthetic


def test_fold_windows_hand_values():
    w = fold_windows(pd.Timestamp("2026-03-31"), n_folds=2, fold_days=7)
    assert w == [(pd.Timestamp("2026-03-18"), pd.Timestamp("2026-03-24")),
                 (pd.Timestamp("2026-03-25"), pd.Timestamp("2026-03-31"))]


def test_feature_sets_are_cumulative_and_end_with_the_shipped_set():
    sets = dict(feature_sets())
    history = ["lag_7", "lag_14", "lag_21", "lag_28", "roll_mean_7", "roll_mean_28"]
    assert sets["calendar + history"] == ["dow", "is_weekend", "month"] + history
    assert sets["+ holidays"] == ["dow", "is_weekend", "month", "is_public_holiday", "is_poya", "is_school_holiday"] + history
    assert sets["+ promotions"] == sets["+ holidays"][:6] + ["promo_discount_pct"] + history
    assert sets["+ weather (all features)"] == BASE_FEATURES


def test_each_fold_trains_only_on_earlier_days():
    r = run_experiments(synthetic(days=300), EMPTY_HOL, EMPTY_PROMO, EMPTY_W, [1, 2], n_folds=3, fold_days=14)
    folds = r["folds"]
    assert [f["test_end"] for f in folds][-1] == "2026-10-27"          # day 300 of the series
    for f in folds:
        assert pd.Timestamp(f["train_end"]) < pd.Timestamp(f["test_start"])
        assert f["n_test"] == 14 * 2
    for a, b in zip(folds, folds[1:]):                                    # contiguous, no overlap
        assert pd.Timestamp(b["test_start"]) == pd.Timestamp(a["test_end"]) + pd.Timedelta(days=1)
        assert b["n_train"] == a["n_train"] + 14 * 2                       # expanding window


def test_full_feature_set_reproduces_the_shipped_holdout_numbers():
    """The ablation's last row is the same model on the same hold-out as `flask smartrest train`."""
    s = synthetic(days=300)
    r = run_experiments(s, EMPTY_HOL, EMPTY_PROMO, EMPTY_W, [1, 2], n_folds=2, fold_days=14)
    t = train_and_compare(s, EMPTY_HOL, EMPTY_PROMO, EMPTY_W, [1, 2])
    assert r["ablation"][-1]["holdout"] == t.metrics["overall"]["xgboost"]


def test_results_are_deterministic_and_complete():
    s = synthetic(days=300)
    a = run_experiments(s, EMPTY_HOL, EMPTY_PROMO, EMPTY_W, [1, 2], n_folds=2, fold_days=14)
    b = run_experiments(s, EMPTY_HOL, EMPTY_PROMO, EMPTY_W, [1, 2], n_folds=2, fold_days=14)
    assert a == b
    assert set(a["cv"]) == {"naive_lag7", "seasonal_mean4", "random_forest", "xgboost"}
    assert [x["feature_set"] for x in a["ablation"]] == [name for name, _ in feature_sets()]


def test_segment_row_counts_hand_values():
    """2 holidays and a 3-day promotion on item 1 inside the 2 x 14-day test windows (2026-09-30 .. 2026-10-27)."""
    s = synthetic(days=300)
    hol = pd.DataFrame({"date": pd.to_datetime(["2026-10-01", "2026-10-20", "2026-05-01"]),
                        "holiday_type": ["poya", "public", "public"]})        # the May one is outside the windows
    promo = pd.DataFrame({"item_id": [1, 1, 1], "date": pd.to_datetime(["2026-10-10", "2026-10-11", "2026-10-12"]),
                          "discount_pct": [10, 10, 10]})
    wx = pd.DataFrame({"date": pd.date_range("2026-01-01", periods=300), "rain_mm": 0.0, "temp_c": 28.0})
    wx.loc[wx["date"].isin(pd.to_datetime(["2026-10-05", "2026-10-06"])), "rain_mm"] = 12.0
    r = run_experiments(s, hol, promo, wx, [1, 2], n_folds=2, fold_days=14)
    # holiday days: 2 dates x 2 items = 4; promotion item-days: 3; wet days: 2 dates x 2 items = 4
    assert r["segment_rows"] == {"holiday days": 4, "promotion item-days": 3, "wet days": 4, "total": 56}


def test_too_little_history_is_refused():
    with pytest.raises(ValueError, match="Not enough history"):
        run_experiments(synthetic(days=260), EMPTY_HOL, EMPTY_PROMO, EMPTY_W, [1, 2], n_folds=6, fold_days=28)
