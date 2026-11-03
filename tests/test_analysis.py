"""Data-science rigor: confidence intervals, calibration, explanations and a significance test."""
import numpy as np
import pandas as pd
import pytest
from sklearn.metrics import f1_score
from xgboost import XGBClassifier

from ml.analysis import bootstrap_ci, calibration, error_analysis, paired_bootstrap_diff, shap_values


def _data(n=4000, seed=0, noise=1.0):
    rng = np.random.default_rng(seed)
    y = (rng.random(n) < 0.15).astype(int)
    X = pd.DataFrame({"a": y * 2.0 + rng.normal(0, noise, n), "b": rng.normal(size=n), "c": rng.normal(size=n)})
    return X, pd.Series(y)


def test_bootstrap_interval_is_ordered_contains_the_estimate_and_shrinks_with_more_data():
    rng = np.random.default_rng(1)
    for n in (300, 3000):
        y = (rng.random(n) < 0.2).astype(int)
        pred = np.where(rng.random(n) < 0.9, y, 1 - y)  # 90% right
        lo, hi = bootstrap_ci(y, pred, f1_score, n_boot=300, seed=0)
        assert lo <= f1_score(y, pred) <= hi
        width = hi - lo
        if n == 300:
            wide = width
    assert width < wide


def test_paired_bootstrap_detects_a_clearly_better_model_and_not_a_copy():
    rng = np.random.default_rng(2)
    y = (rng.random(2000) < 0.2).astype(int)
    good = np.where(rng.random(2000) < 0.97, y, 1 - y)
    bad = np.where(rng.random(2000) < 0.80, y, 1 - y)
    d = paired_bootstrap_diff(y, good, bad, f1_score, n_boot=300, seed=0)
    assert d["lo"] > 0 and d["mean_diff"] > 0.1 and d["significant"]
    same = paired_bootstrap_diff(y, good, good.copy(), f1_score, n_boot=300, seed=0)
    assert same["mean_diff"] == 0 and not same["significant"]


def test_calibration_of_a_calibrated_score_is_near_zero_and_of_an_overconfident_one_is_not():
    rng = np.random.default_rng(3)
    p = rng.random(20000)
    y = (rng.random(20000) < p).astype(int)  # labels drawn from p, so p is calibrated by construction
    good = calibration(y, p)
    assert good["ece"] < 0.02 and len(good["bins"]) >= 8
    over = calibration(y, np.clip(p * 2 - 0.5, 0.001, 0.999))
    assert over["ece"] > good["ece"] + 0.05


def test_shap_values_add_up_to_the_models_raw_prediction():
    X, y = _data()
    m = XGBClassifier(n_estimators=40, max_depth=3, eval_metric="logloss").fit(X, y)
    contrib, bias = shap_values(m, X.head(200))
    margin = m.predict(X.head(200), output_margin=True)
    assert np.allclose(contrib.sum(axis=1) + bias, margin, atol=1e-3)  # the additivity property of SHAP
    assert contrib.shape == (200, 3)
    assert np.abs(contrib[:, 0]).mean() > 5 * np.abs(contrib[:, 1]).mean()  # the informative feature dominates


def test_error_analysis_lists_the_mistakes_with_the_features_that_drove_them():
    X, y = _data(noise=2.0)  # noisy on purpose, so there are errors
    m = XGBClassifier(n_estimators=30, max_depth=3, eval_metric="logloss").fit(X, y)
    proba = m.predict_proba(X)[:, 1]
    e = error_analysis(m, X, y, proba, {"a": "feature a", "b": "feature b", "c": "feature c"}, k=5)
    assert e["n_false_positive"] > 0 and e["n_false_negative"] > 0
    assert len(e["false_positives"]) <= 5 and all("top_features" in r for r in e["false_positives"])
    assert all(r["actual"] == 0 and r["proba"] >= 0.5 for r in e["false_positives"])
    assert all(r["actual"] == 1 and r["proba"] < 0.5 for r in e["false_negatives"])
