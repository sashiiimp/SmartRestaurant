import numpy as np
import pandas as pd

from app.ml.features import LAGS


def baseline_naive_lag7(df: pd.DataFrame) -> np.ndarray:
    return df["lag_7"].to_numpy(dtype=float)


def baseline_seasonal_mean4(df: pd.DataFrame) -> np.ndarray:
    return df[[f"lag_{k}" for k in LAGS]].mean(axis=1).to_numpy(dtype=float)


BASELINES = {"naive_lag7": baseline_naive_lag7, "seasonal_mean4": baseline_seasonal_mean4}


def predict(artifact: dict, features: pd.DataFrame) -> np.ndarray:
    """Predictions clipped at 0. `artifact` is the dict produced by train (algorithm, model, feature_columns)."""
    algo = artifact["algorithm"]
    if algo in BASELINES:
        out = BASELINES[algo](features)
    else:
        out = artifact["model"].predict(features[artifact["feature_columns"]].to_numpy(dtype=float))
    return np.clip(np.nan_to_num(np.asarray(out, dtype=float), nan=0.0), 0, None)
