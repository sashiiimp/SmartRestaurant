"""The Diebold-Mariano helper of scripts/research_supplement.py (ML_EVALUATION_SUPPLEMENT.md section 3)."""
import importlib.util
import os

import numpy as np

_path = os.path.join(os.path.dirname(__file__), "..", "..", "scripts", "research_supplement.py")
_spec = importlib.util.spec_from_file_location("research_supplement", _path)
rs = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rs)


def test_dm_no_difference_is_not_significant():
    d = np.tile([1.0, -1.0], 50)          # mean 0
    r = rs.dm_test(d)
    assert r["mean_diff"] == 0 and r["dm"] == 0 and r["p_value"] == 1.0 and r["days"] == 100


def test_dm_consistent_advantage_is_significant_and_signed():
    rng = np.random.default_rng(0)
    d = -2.0 + rng.normal(0, 1, 60)       # A clearly better than B
    r = rs.dm_test(d)
    assert r["dm"] < -5 and r["p_value"] < 1e-6 and r["nw_lag"] == 3   # floor(60 ** (1/3)) = 3


def test_dm_matches_a_step_by_step_calculation():
    """Newey-West variance with Bartlett weights (lag = floor(n^(1/3)) = 2 for n = 8), then the HLN factor for h = 1."""
    d = np.array([-1.0, 0.5, -2.0, -0.5, -1.5, 0.0, -1.0, -0.5])
    n, mean = 8, d.mean()                                    # mean = -0.75
    e = d - mean
    g0 = (e @ e) / n
    g1 = (e[1:] @ e[:-1]) / n
    g2 = (e[2:] @ e[:-2]) / n
    lrv = g0 + 2 * ((1 - 1 / 3) * g1 + (1 - 2 / 3) * g2)
    hln = np.sqrt((n + 1 - 2) / n)
    expected = mean / np.sqrt(lrv / n) * hln
    r = rs.dm_test(d)
    assert r["nw_lag"] == 2 and abs(r["dm"] - round(expected, 3)) < 1e-9
