"""Phase 1: the timed replay makes the dashboard live, using a parser identical to the Spark one."""
from pathlib import Path

import psycopg
import pytest

from ingest.load import PG
from ingest.replay import ensure_table, parse_line, replay

FIXTURE = Path(__file__).parent / "fixtures" / "hdfs_sample.log"
REAL_LOG = Path(__file__).resolve().parent.parent / "data" / "hdfs" / "HDFS.log"
TEST_DB = "argus_test"


def test_parse_line_fields():
    row = parse_line(FIXTURE.read_text().splitlines()[0])
    assert row["level"] == "INFO" and row["pid"] == 143
    assert row["component"] == "dfs.DataNode$DataXceiver"
    assert row["block_id"] == "blk_-1608999687919862906"
    assert row["template"] == "Receiving block <*> src: <*> dest: <*>"
    assert row["ts"].isoformat() == "2008-11-09T20:35:18+00:00"


def test_malformed_lines_are_skipped():
    assert parse_line("this is not an hdfs log line") is None
    assert parse_line("") is None


@pytest.mark.skipif(not REAL_LOG.exists(), reason="run scripts/download_hdfs.py first")
def test_python_parser_matches_spark_parser_on_real_lines(spark, tmp_path):
    from itertools import islice

    from pyspark.sql import functions as F

    from ingest.parser import parse_logs

    with REAL_LOG.open() as f:
        lines = list(islice(f, 3000))
    sample = tmp_path / "sample.log"
    sample.write_text("".join(lines))

    spark_rows = {(r.ts.timestamp(), r.pid, r.content): r for r in parse_logs(spark.read.text(str(sample))).collect()}
    mine = [parse_line(line.rstrip("\n")) for line in lines]
    assert all(mine)
    for m in mine:
        s = spark_rows[(m["ts"].timestamp(), m["pid"], m["content"])]
        assert (m["level"], m["component"], m["block_id"], m["template"]) == (s.level, s.component, s.block_id, s.template)


@pytest.fixture
def test_conn():
    pg = {**PG, "dbname": TEST_DB}
    with psycopg.connect(**{**PG, "dbname": "postgres"}, autocommit=True) as c:
        if not c.execute("SELECT 1 FROM pg_database WHERE datname = %s", (TEST_DB,)).fetchone():
            c.execute(f"CREATE DATABASE {TEST_DB}")
    with psycopg.connect(**pg) as conn:
        ensure_table(conn)
        conn.execute("TRUNCATE live_events")
        conn.commit()
        yield conn


def test_replay_inserts_timed_batches(test_conn):
    sleeps = []
    n = replay(FIXTURE, test_conn, batch_size=3, interval=0.5, sleep=sleeps.append)
    assert n == 4
    rows = test_conn.execute("SELECT batch, count(*) FROM live_events GROUP BY 1 ORDER BY 1").fetchall()
    assert rows == [(1, 3), (2, 1)]
    assert sleeps == [0.5, 0.5]  # one pause after each batch


def test_replay_resumes_from_offset(test_conn):
    replay(FIXTURE, test_conn, batch_size=2, interval=0, sleep=lambda s: None, max_batches=1)
    replay(FIXTURE, test_conn, batch_size=2, interval=0, sleep=lambda s: None, skip=2)
    assert test_conn.execute("SELECT count(*) FROM live_events").fetchone()[0] == 4
