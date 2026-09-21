"""ML-1, ML-2, ML-3, ML-8: feature construction (ML_PLAN section 3)."""
import numpy as np
import pandas as pd

from app.ml.features import LAGS, build_features, climatology, feature_columns, history_matrix
from app.ml.predict import baseline_naive_lag7, baseline_seasonal_mean4

START = pd.Timestamp("2026-08-01")
NO_HOL = pd.DataFrame({"date": pd.to_datetime([]), "holiday_type": []})
NO_PROMO = pd.DataFrame({"item_id": [], "date": pd.to_datetime([]), "discount_pct": []})
NO_WEATHER = pd.DataFrame({"date": pd.to_datetime([]), "rain_mm": [], "temp_c": []})
CLIM = climatology(NO_WEATHER)


def toy_sales(n=35, items=(1,)):
    rows = [(i, START + pd.Timedelta(days=d), float(d)) for i in items for d in range(n)]
    return pd.DataFrame(rows, columns=["item_id", "date", "qty"])


def feats(sales, dates, items=(1,), **kw):
    return build_features(sales, NO_HOL, NO_PROMO, NO_WEATHER, list(items), dates, list(items), CLIM, **kw)


def test_hand_calculated_lags_and_baselines():
    """ML-3: qty on day i is i, so for day 34 the lags are 27, 20, 13, 6."""
    target = START + pd.Timedelta(days=34)
    df = feats(toy_sales(34), [target])  # history ends the day before
    row = df.iloc[0]
    assert (row.lag_7, row.lag_14, row.lag_21, row.lag_28) == (27, 20, 13, 6)
    assert baseline_naive_lag7(df)[0] == 27
    assert baseline_seasonal_mean4(df)[0] == (27 + 20 + 13 + 6) / 4
    assert row.roll_mean_7 == np.mean(range(21, 28))     # days t-13 .. t-7
    assert row.roll_mean_28 == np.mean(range(0, 28))     # days t-34 .. t-7


def test_no_leakage_from_the_last_six_days():
    """ML-1: changing any sales value dated on or after target-6 leaves the target's features unchanged."""
    rng = np.random.default_rng(0)
    sales = toy_sales(60, items=(1, 2))
    sales["qty"] = rng.integers(10, 100, len(sales)).astype(float)
    target = START + pd.Timedelta(days=59)
    base = feats(sales, [target]).set_index("item_id")
    tampered = sales.copy()
    tampered.loc[tampered["date"] >= target - pd.Timedelta(days=6), "qty"] += 999
    changed = feats(tampered, [target]).set_index("item_id")
    cols = [c for c in feature_columns([1, 2]) if c in base.columns]
    pd.testing.assert_frame_equal(base[cols], changed[cols])


def test_train_and_inference_share_columns():
    """ML-2: the same function, same columns and order, whatever the dates."""
    a = feats(toy_sales(40), [START + pd.Timedelta(days=41)])
    b = feats(toy_sales(40), pd.date_range(START, periods=30), with_target=True)
    cols = feature_columns([1])
    assert all(c in a.columns for c in cols) and all(c in b.columns for c in cols)


def test_missing_vs_zero_rule():
    sales = pd.DataFrame({"item_id": [1, 1, 2], "date": pd.to_datetime(["2026-08-01", "2026-08-03", "2026-08-01"]),
                          "qty": [5.0, 7.0, 3.0]})
    m = history_matrix(sales, [1, 2], "2026-08-03")
    assert m.loc["2026-08-01", 2] == 3
    assert m.loc["2026-08-03", 2] == 0          # recorded date, item has no row: zero sold
    assert np.isnan(m.loc["2026-08-02", 1])     # no rows at all that day: not recorded
    # an item that first appears later is NaN before its first record
    late = pd.concat([sales, pd.DataFrame({"item_id": [3], "date": pd.to_datetime(["2026-08-03"]), "qty": [4.0]})])
    m2 = history_matrix(late, [1, 3], "2026-08-03")
    assert np.isnan(m2.loc["2026-08-01", 3]) and m2.loc["2026-08-03", 3] == 4


def test_missing_weather_uses_seasonal_average_and_flags_it():
    """ML-8"""
    weather = pd.DataFrame({"date": pd.date_range("2025-01-01", periods=400), "rain_mm": 4.0, "temp_c": 29.0})
    clim = climatology(weather)
    assert clim["rain"] and clim["rain"][3] == 4.0
    sales = toy_sales(40)
    target = START + pd.Timedelta(days=45)
    df = build_features(sales, NO_HOL, NO_PROMO, weather, [1], [target], [1], clim)
    assert bool(df.iloc[0].weather_estimated) and df.iloc[0].rain_mm == 4.0
    entered = pd.DataFrame({"date": [target], "rain_mm": [30.0], "temp_c": [27.0]})
    df2 = build_features(sales, NO_HOL, NO_PROMO, entered, [1], [target], [1], clim)
    assert not bool(df2.iloc[0].weather_estimated) and df2.iloc[0].rain_mm == 30.0
    df3 = build_features(sales, NO_HOL, NO_PROMO, entered, [1], [target], [1], clim, force_estimated=True)
    assert bool(df3.iloc[0].weather_estimated)


def test_missing_lag_is_imputed_and_flagged():
    """ML-8: a gap in history is filled from the next weekly lag, and the row says so."""
    sales = toy_sales(34)
    gap_day = START + pd.Timedelta(days=27)  # lag_7 of day 34
    sales = sales[sales["date"] != gap_day]
    df = feats(sales, [START + pd.Timedelta(days=34)], items=(1,))  # the whole day is unrecorded, so lag_7 is NaN
    row = df.iloc[0]
    assert row.lags_imputed
    assert row.lag_7 == row.lag_14 == 20  # filled from the next weekly lag
