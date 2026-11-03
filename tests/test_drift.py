"""Phase 2: drift detection flags a shifted sample and stays quiet on a stable one."""
import numpy as np
import pandas as pd

from ml.drift import F1_DROP_ALERT, PSI_ALERT, check_window, psi


def _frame(n, seed, shift=1.0):
    rng = np.random.default_rng(seed)
    y = pd.Series((rng.random(n) < 0.1).astype(int))
    X = pd.DataFrame({"f0": y * 5 + rng.normal(size=n), "f1": rng.normal(size=n) * shift})
    return X, y


def test_psi_is_near_zero_for_same_distribution():
    rng = np.random.default_rng(0)
    assert psi(rng.normal(size=5000), rng.normal(size=5000)) < 0.05


def test_psi_is_large_for_shifted_distribution():
    rng = np.random.default_rng(0)
    assert psi(rng.normal(size=5000), rng.normal(loc=2.0, size=5000)) > PSI_ALERT


def test_psi_handles_constant_columns():
    assert psi(np.zeros(100), np.zeros(100)) == 0.0


class _Perfect:
    """Stands in for a trained model whose predictions are the labels."""

    def __init__(self, y):
        self.y = y

    def predict_proba(self, X):
        p = self.y.loc[X.index].to_numpy()
        return np.column_stack([1 - p, p])


def test_stable_window_does_not_alert():
    Xr, yr = _frame(3000, 1)
    Xc, yc = _frame(3000, 2)
    r = check_window(_Perfect(pd.concat([yr, yc.set_axis(yc.index + 3000)])), Xr, Xc.set_axis(Xc.index + 3000), yc.set_axis(yc.index + 3000), baseline_f1=1.0)
    assert r["status"] == "ok" and not r["alert"]


def test_shifted_window_warns_on_data_drift_without_paging():
    Xr, yr = _frame(3000, 1)
    Xc, yc = _frame(3000, 2, shift=4.0)
    Xc, yc = Xc.set_axis(Xc.index + 3000), yc.set_axis(yc.index + 3000)
    r = check_window(_Perfect(pd.concat([yr, yc])), Xr, Xc, yc, baseline_f1=1.0)
    # the model still predicts perfectly, so this is a warning, not an alert
    assert r["status"] == "warning" and not r["alert"]
    assert r["psi_max"] > PSI_ALERT and r["psi_worst_feature"] == "f1"


def test_performance_drop_alerts():
    Xr, yr = _frame(3000, 1)
    Xc, yc = _frame(3000, 2)
    Xc, yc = Xc.set_axis(Xc.index + 3000), yc.set_axis(yc.index + 3000)
    wrong = pd.concat([yr, 1 - yc])  # the model now disagrees with ground truth
    r = check_window(_Perfect(wrong), Xr, Xc, yc, baseline_f1=0.99)
    assert r["status"] == "alert" and r["f1_drop"] > F1_DROP_ALERT


def test_excluded_features_do_not_trigger_alerts():
    Xr, yr = _frame(3000, 1)
    Xc, yc = _frame(3000, 2, shift=4.0)  # f1 is shifted
    Xc, yc = Xc.set_axis(Xc.index + 3000), yc.set_axis(yc.index + 3000)
    r = check_window(_Perfect(pd.concat([yr, yc])), Xr, Xc, yc, baseline_f1=1.0, exclude=("f1",))
    assert r["status"] == "ok" and r["psi_worst_feature"] == "f0"
