"""Phase 1: FAISS clusters near-duplicate log templates without merging distinct failure signatures."""
import numpy as np
import pytest

from api.db import connect
from tests.data import needs_full_data
from ingest.cluster import THRESHOLD, build_clusters, cluster_templates

# torch (via the embedder) and faiss share a process here; torch and xgboost must not (see scripts/test.sh)
pytestmark = pytest.mark.torch


def _unit(*v):
    a = np.array(v, dtype="float32")
    return a / np.linalg.norm(a)


def test_near_duplicates_merge_and_distinct_stay_apart():
    emb = np.stack([_unit(1, 0, 0), _unit(1, 0.05, 0), _unit(0, 1, 0), _unit(0, 0.99, 0.05)])
    labels = cluster_templates(["a", "a2", "b", "b2"], emb)
    assert labels == [0, 0, 1, 1]


def test_cluster_ids_follow_first_appearance_so_frequent_templates_lead():
    emb = np.stack([_unit(0, 0, 1), _unit(1, 0, 0), _unit(0, 0, 1)])
    assert cluster_templates(["x", "y", "x2"], emb) == [0, 1, 0]


def test_threshold_is_strict_enough_to_keep_close_but_different_meanings_apart():
    # cosine 0.90, as between "addStoredBlock request received" and "Redundant addStoredBlock request"
    a, b = _unit(1, 0), _unit(0.90, np.sqrt(1 - 0.90**2))
    assert THRESHOLD > 0.90
    assert cluster_templates(["a", "b"], np.stack([a, b])) == [0, 1]


@needs_full_data
def test_real_templates_cluster_and_keep_the_six_signatures_separate():
    build_clusters()
    with connect() as c:
        rows = c.execute("SELECT template, cluster_id FROM template_clusters").fetchall()
    assert len(rows) == 54
    assert len({r["cluster_id"] for r in rows}) < 54  # something merged
    patterns = ["Unexpected error trying to delete block", "writeBlock%Could not read from stream", "BLOCK* ask%to replicate",
                "%But it does not belong to any file", "BLOCK* NameSystem.addStoredBlock: Redundant", "Receiving empty packet"]
    import re
    ids = []
    for p in patterns:
        rx = re.compile(re.escape(p).replace("%", ".*").replace(r"\.\*", ".*"))
        hit = [r["cluster_id"] for r in rows if rx.search(r["template"])]
        assert hit, p
        ids.append(hit[0])
    assert len(set(ids)) == 6, ids
