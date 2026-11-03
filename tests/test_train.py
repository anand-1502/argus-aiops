"""Phase 2: training returns honest, leak-free metrics."""
import numpy as np
import pandas as pd

from ml.train import evaluate, split


def _toy(n=400, seed=0):
    rng = np.random.default_rng(seed)
    y = pd.Series((rng.random(n) < 0.1).astype(int), index=[f"b{i}" for i in range(n)])
    X = pd.DataFrame({"f0": y * 5 + rng.normal(size=n), "f1": rng.normal(size=n)}, index=y.index)
    return X, y


def test_split_is_disjoint_and_stratified():
    X, y = _toy()
    Xtr, Xte, ytr, yte = split(X, y, test_size=0.2, seed=1)
    assert set(Xtr.index).isdisjoint(Xte.index)
    assert len(Xtr) + len(Xte) == len(X)
    assert abs(ytr.mean() - yte.mean()) < 0.02


def test_evaluate_reports_precision_recall_f1():
    X, y = _toy()
    Xtr, Xte, ytr, yte = split(X, y, test_size=0.25, seed=1)
    m = evaluate(Xtr, ytr, Xte, yte, params={"n_estimators": 50, "max_depth": 3})
    assert set(m) >= {"precision", "recall", "f1", "pr_auc", "tp", "fp", "fn", "tn"}
    assert m["f1"] > 0.8  # the toy signal is strong
    assert m["tp"] + m["fp"] + m["fn"] + m["tn"] == len(yte)
