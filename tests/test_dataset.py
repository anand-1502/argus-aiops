"""Phase 0 check: the downloaded HDFS data matches Loghub's published counts."""
import csv
from pathlib import Path

import pytest

DATA = Path(__file__).resolve().parent.parent / "data" / "hdfs"
LOG = DATA / "HDFS.log"
LABELS = DATA / "preprocessed" / "anomaly_label.csv"

pytestmark = pytest.mark.skipif(not LOG.exists(), reason="run scripts/download_hdfs.py first")


def test_message_count():
    with LOG.open("rb") as f:
        assert sum(1 for _ in f) == 11_175_629


def test_block_and_anomaly_counts():
    with LABELS.open() as f:
        rows = list(csv.DictReader(f))
    anomalies = sum(1 for r in rows if r["Label"] == "Anomaly")
    assert len(rows) == 575_061
    assert anomalies == 16_838
    assert round(100 * anomalies / len(rows), 2) == 2.93
