"""Phase 1: the Spark job lands parsed events and labels in Postgres."""
import socket
import subprocess
import sys
from pathlib import Path

import psycopg
import pytest

import os

from ingest.load import PG

FIXTURE = Path(__file__).parent / "fixtures" / "hdfs_sample.log"
LABELS = Path(__file__).parent / "fixtures" / "labels_sample.csv"


def _up() -> bool:
    with socket.socket() as s:
        s.settimeout(1)
        return s.connect_ex(("localhost", 5433)) == 0


pytestmark = pytest.mark.skipif(not _up(), reason="run `docker compose up -d` first")


TEST_DB = "argus_test"  # never the real `argus` database: the loader drops `events`


def _ensure_test_db() -> None:
    with psycopg.connect(**{**PG, "dbname": "postgres"}, autocommit=True) as conn:
        if not conn.execute("SELECT 1 FROM pg_database WHERE datname = %s", (TEST_DB,)).fetchone():
            conn.execute(f"CREATE DATABASE {TEST_DB}")


def test_load_fixture_into_postgres():
    _ensure_test_db()
    subprocess.run(
        [sys.executable, "-m", "ingest.load", "--log", str(FIXTURE), "--labels", str(LABELS)],
        check=True,
        env={**os.environ, "JAVA_HOME": "/opt/homebrew/opt/openjdk@17", "PGDATABASE": TEST_DB},
    )
    with psycopg.connect(**{**PG, "dbname": TEST_DB}) as conn:
        assert conn.execute("SELECT count(*) FROM events").fetchone()[0] == 4
        row = conn.execute(
            "SELECT level, component, block_id FROM events WHERE pid = 142"
        ).fetchone()
        assert row == ("WARN", "dfs.DataNode$PacketResponder", "blk_7503483334202473044")
        labels = dict(conn.execute("SELECT label, count(*) FROM block_labels GROUP BY label").fetchall())
        assert labels == {"Normal": 1, "Anomaly": 1}
