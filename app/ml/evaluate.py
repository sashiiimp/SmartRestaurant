"""Forecast error metrics (ML_PLAN section 6)."""
import numpy as np
import pandas as pd


def metrics(y_true, y_pred) -> dict:
    y = np.asarray(y_true, dtype=float)
    p = np.asarray(y_pred, dtype=float)
    err = p - y
    n = len(y)
    if n == 0:
        return {k: None for k in ("mae", "rmse", "mape", "mape_excluded", "wape", "r2", "bias", "n")}
    mae = float(np.abs(err).mean())
    rmse = float(np.sqrt((err ** 2).mean()))
    nz = y > 0
    mape = float((np.abs(err[nz]) / y[nz]).mean() * 100) if nz.any() else None
    total = float(y.sum())
    wape = float(np.abs(err).sum() / total * 100) if total > 0 else None
    sst = float(((y - y.mean()) ** 2).sum())
    r2 = float(1 - (err ** 2).sum() / sst) if sst > 0 else None
    return {"mae": round(mae, 4), "rmse": round(rmse, 4), "mape": None if mape is None else round(mape, 3),
            "mape_excluded": int((~nz).sum()), "wape": None if wape is None else round(wape, 3),
            "r2": None if r2 is None else round(r2, 4), "bias": round(float(err.mean()), 4), "n": int(n)}


def oracle_mae(actual: pd.DataFrame, expected: pd.DataFrame, start) -> float | None:
    """MAE of the noise-free expected demand against actual sales: the best any model could do on synthetic data.

    actual: [item_id, date, qty]; expected: [item_id, date, expected_qty]
    """
    merged = actual.merge(expected, on=["item_id", "date"])
    merged = merged[merged["date"] >= pd.Timestamp(start)]
    if merged.empty:
        return None
    return round(float((merged["qty"] - merged["expected_qty"]).abs().mean()), 4)
