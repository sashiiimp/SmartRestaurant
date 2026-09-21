"""Feature building shared by training and inference (ML_PLAN section 3, NFR6).

Every history feature is lagged by 7 days or more, so a forecast for day t only ever uses actuals up to t-7:
no recursive forecasting and no leakage by construction.
"""
import numpy as np
import pandas as pd

LAGS = (7, 14, 21, 28)
CALENDAR = ["dow", "is_weekend", "month"]
CONTEXT = ["is_public_holiday", "is_poya", "is_school_holiday", "promo_discount_pct", "rain_mm", "temp_c"]
HISTORY = ["lag_7", "lag_14", "lag_21", "lag_28", "roll_mean_7", "roll_mean_28"]
BASE_FEATURES = CALENDAR + CONTEXT + HISTORY


def feature_columns(onehot_items) -> list[str]:
    return BASE_FEATURES + [f"item_{i}" for i in sorted(onehot_items)]


def climatology(weather: pd.DataFrame) -> dict:
    """Seasonal average weather per calendar month (ML_PLAN section 4).

    Uses per-month means when the data spans at least 12 months, otherwise the overall mean.
    Returns {"rain": {month: x}, "temp": {month: x}, "overall_rain": x, "overall_temp": x}.
    """
    if weather is None or weather.empty:
        return {"rain": {}, "temp": {}, "overall_rain": 0.0, "overall_temp": 28.0}
    w = weather.copy()
    w["date"] = pd.to_datetime(w["date"])
    span_days = (w["date"].max() - w["date"].min()).days
    overall_rain = float(w["rain_mm"].mean())
    overall_temp = float(w["temp_c"].mean()) if w["temp_c"].notna().any() else 28.0
    rain, temp = {}, {}
    if span_days >= 330:
        by_month = w.groupby(w["date"].dt.month)
        rain = {int(m): float(v) for m, v in by_month["rain_mm"].mean().items()}
        temp = {int(m): float(v) for m, v in by_month["temp_c"].mean().dropna().items()}
    return {"rain": rain, "temp": temp, "overall_rain": overall_rain, "overall_temp": overall_temp}


def history_matrix(sales: pd.DataFrame, items, end_date) -> pd.DataFrame:
    """Daily matrix (rows = dates, columns = item ids) of quantity sold.

    Missing-vs-zero rule (DATABASE.md 2.3): a date is *recorded* if any item has a row; an item without a row on a
    recorded date is 0 sold; an unrecorded date stays NaN; dates before an item's first record stay NaN.
    """
    idx_end = max(pd.Timestamp(end_date), sales["date"].max()) if len(sales) else pd.Timestamp(end_date)
    if sales.empty:
        return pd.DataFrame(columns=list(items), index=pd.date_range(idx_end, idx_end), dtype=float)
    idx = pd.date_range(sales["date"].min(), idx_end)
    m = sales.pivot_table(index="date", columns="item_id", values="qty", aggfunc="sum").reindex(idx)
    m = m.reindex(columns=list(items))
    recorded = pd.Series(idx.isin(sales["date"].unique()), index=idx)
    first_seen = sales.groupby("item_id")["date"].min()
    m = m.astype(float)
    m.loc[recorded] = m.loc[recorded].fillna(0.0)
    for item in m.columns:
        first = first_seen.get(item)
        if first is None:
            m[item] = np.nan
        else:
            m.loc[m.index < first, item] = np.nan
    return m


def build_features(sales: pd.DataFrame, holidays: pd.DataFrame, promos: pd.DataFrame, weather: pd.DataFrame,
                   items, dates, onehot_items, clim: dict, force_estimated: bool = False,
                   with_target: bool = False, impute: bool = True) -> pd.DataFrame:
    """One row per (item, date).

    sales:    [item_id, date, qty]      holidays: [date, holiday_type]
    promos:   [item_id, date, discount_pct] (already expanded per item and day)
    weather:  [date, rain_mm, temp_c]   (actual or entered; missing dates use the climatology)
    """
    items = list(items)
    dates = pd.DatetimeIndex(pd.to_datetime(list(dates)))
    end = dates.max() if len(dates) else pd.Timestamp.today()
    m = history_matrix(sales, items, end)
    shifted = {k: m.shift(k) for k in LAGS}
    roll7 = m.shift(7).rolling(7, min_periods=4).mean()
    roll28 = m.shift(7).rolling(28, min_periods=14).mean()

    idx = pd.MultiIndex.from_product([items, dates], names=["item_id", "date"])
    df = idx.to_frame(index=False)
    dts = pd.DatetimeIndex(df["date"])
    df["dow"] = dts.dayofweek
    df["is_weekend"] = (df["dow"] >= 5).astype(int)
    df["month"] = dts.month

    def flag(kind):
        if holidays is None or holidays.empty:
            return np.zeros(len(df), dtype=int)
        days = set(pd.to_datetime(holidays.loc[holidays["holiday_type"] == kind, "date"]))
        return dts.isin(days).astype(int)

    df["is_public_holiday"] = flag("public")
    df["is_poya"] = flag("poya")
    df["is_school_holiday"] = flag("school")

    df["promo_discount_pct"] = 0.0
    if promos is not None and not promos.empty:
        p = promos.copy()
        p["date"] = pd.to_datetime(p["date"])
        p = p.groupby(["item_id", "date"], as_index=False)["discount_pct"].max()
        df = df.merge(p, on=["item_id", "date"], how="left")
        df["promo_discount_pct"] = df.pop("discount_pct").fillna(0.0).astype(float)

    # weather: entered/observed value if present (and not forced to the estimate), else seasonal average
    w = pd.DataFrame({"date": dates})
    w["rain_mm"] = np.nan
    w["temp_c"] = np.nan
    if weather is not None and not weather.empty and not force_estimated:
        wx = weather.copy()
        wx["date"] = pd.to_datetime(wx["date"])
        w = w[["date"]].merge(wx[["date", "rain_mm", "temp_c"]].drop_duplicates("date"), on="date", how="left")
    w["weather_estimated"] = w["rain_mm"].isna()
    mon = w["date"].dt.month
    est_rain = mon.map(clim["rain"]).fillna(clim["overall_rain"])
    est_temp = mon.map(clim["temp"]).fillna(clim["overall_temp"])
    w["rain_mm"] = w["rain_mm"].fillna(est_rain).astype(float)
    w["temp_c"] = w["temp_c"].fillna(est_temp).astype(float)
    df = df.merge(w, on="date", how="left")

    for k in LAGS:
        df[f"lag_{k}"] = _lookup(shifted[k], df)
    df["roll_mean_7"] = _lookup(roll7, df)
    df["roll_mean_28"] = _lookup(roll28, df)

    df["lags_imputed"] = False
    if impute:
        df = _impute_lags(df)
    if with_target:
        df["y"] = _lookup(m, df)
    for i in sorted(onehot_items):
        df[f"item_{i}"] = (df["item_id"] == i).astype(int)
    return df


def _lookup(matrix: pd.DataFrame, df: pd.DataFrame) -> np.ndarray:
    """matrix[date, item] for each row of df (NaN when out of range)."""
    rows = matrix.index.get_indexer(pd.DatetimeIndex(df["date"]))
    cols = matrix.columns.get_indexer(df["item_id"])
    vals = matrix.to_numpy(dtype=float)
    out = np.full(len(df), np.nan)
    ok = (rows >= 0) & (cols >= 0)
    out[ok] = vals[rows[ok], cols[ok]]
    return out


def _impute_lags(df: pd.DataFrame) -> pd.DataFrame:
    """Fill a missing lag from the next weekly lag, then from roll_mean_28, then the item's own mean (ML_PLAN 3)."""
    order = [f"lag_{k}" for k in LAGS]
    changed = df[order + ["roll_mean_7", "roll_mean_28"]].isna().any(axis=1)
    for i in range(len(order) - 1):
        df[order[i]] = df[order[i]].fillna(df[order[i + 1]])
    df["lag_28"] = df["lag_28"].fillna(df["roll_mean_28"])
    df["roll_mean_28"] = df["roll_mean_28"].fillna(df["roll_mean_7"])
    df["roll_mean_7"] = df["roll_mean_7"].fillna(df["roll_mean_28"])
    item_mean = df.groupby("item_id")[order + ["roll_mean_7", "roll_mean_28"]].transform("mean")
    for c in order + ["roll_mean_7", "roll_mean_28"]:
        df[c] = df[c].fillna(item_mean[c])
    df["lags_imputed"] = changed.to_numpy()
    return df
