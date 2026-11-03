"""Phase 2: per-block feature building and the training split."""
import pandas as pd

from ml.features import build_matrix


def test_pivot_counts_templates_per_block():
    counts = pd.DataFrame({
        "block_id": ["b1", "b1", "b2"],
        "template": ["A", "B", "A"],
        "n": [3, 1, 2],
    })
    stats = pd.DataFrame({
        "block_id": ["b1", "b2"], "n_events": [4, 2], "duration_s": [10.0, 0.0], "n_warn": [0, 1],
    })
    labels = pd.DataFrame({"block_id": ["b1", "b2"], "label": ["Normal", "Anomaly"]})

    X, y = build_matrix(counts, stats, labels, templates=["A", "B"])

    assert list(X.columns) == ["tpl_0", "tpl_1", "n_events", "duration_s", "n_warn"]
    assert X.loc["b1", "tpl_0"] == 3 and X.loc["b1", "tpl_1"] == 1
    assert X.loc["b2", "tpl_1"] == 0  # block never saw template B
    assert list(y) == [0, 1]
    assert list(X.index) == ["b1", "b2"]


def test_unlabeled_blocks_are_dropped():
    counts = pd.DataFrame({"block_id": ["b1", "b2"], "template": ["A", "A"], "n": [1, 1]})
    stats = pd.DataFrame({"block_id": ["b1", "b2"], "n_events": [1, 1], "duration_s": [0.0, 0.0], "n_warn": [0, 0]})
    labels = pd.DataFrame({"block_id": ["b1"], "label": ["Normal"]})
    X, y = build_matrix(counts, stats, labels, templates=["A"])
    assert list(X.index) == ["b1"] and len(y) == 1
