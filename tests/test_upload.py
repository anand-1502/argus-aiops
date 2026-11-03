"""Phase 6: bring-your-own-logs. Parsing is tested without a database; loading uses a scratch schema in argus_test."""
import socket
from datetime import datetime, timezone
from pathlib import Path

import psycopg
import pytest
from psycopg.rows import dict_row

from ingest import upload
from ingest.load import PG

FIX = Path(__file__).parent / "fixtures"


def test_detects_each_timestamp_format():
    assert upload.detect_format((FIX / "modern_app.log").read_text().splitlines()[:50]) == "iso8601"
    assert upload.detect_format((FIX / "syslog_sample.log").read_text().splitlines()[:50]) == "syslog"
    assert upload.detect_format((FIX / "hdfs_sample.log").read_text().splitlines()) == "compact"
    assert upload.detect_format(["1700000000 started", "1700000005 stopped"]) == "epoch"


def test_no_timestamp_format_when_lines_have_none():
    assert upload.detect_format(["just some text", "more text", "and more"]) is None


def test_parser_strips_timestamp_and_handles_timezones():
    p = upload.make_parser("iso8601")
    ts, rest = p("2026-03-02T09:00:03.250+02:00 INFO hello")
    assert ts == datetime(2026, 3, 2, 7, 0, 3, 250000, tzinfo=timezone.utc) and rest == "INFO hello"
    assert p("no timestamp here") == (None, "no timestamp here")
    assert upload.make_parser(None)("x") == (None, "x")


def test_drain_groups_lines_into_few_templates():
    miner = upload.make_miner()
    lines = (FIX / "modern_app.log").read_text().splitlines()
    ids = {miner.add_log_message(upload.make_parser("iso8601")(l)[1])["cluster_id"] for l in lines}
    assert 3 <= len(ids) < 30  # 800 lines of 6 message shapes plus a stack trace


def test_spikes_flags_only_real_outliers():
    flat = [{"bucket": i, "events": 10} for i in range(20)]
    assert upload.spikes(flat) == []
    bumpy = flat[:10] + [{"bucket": 10, "events": 500}] + flat[11:]
    assert [s["bucket"] for s in upload.spikes(bumpy)] == [10]
    assert upload.spikes(flat[:5]) == []  # too few buckets to say


def test_rejects_binary_and_oversized_line_counts(tmp_path, monkeypatch):
    b = tmp_path / "bin"
    b.write_bytes(b"\x00\x01\x02" * 100)
    with pytest.raises(ValueError, match="binary"):
        list(upload.read_lines(b))
    t = tmp_path / "big.log"
    t.write_text("x\n" * 10)
    monkeypatch.setattr(upload, "MAX_LINES", 5)
    with pytest.raises(ValueError, match="more than"):
        list(upload.read_lines(t))


def test_schema_name_is_validated_against_injection():
    assert upload.schema_of("0123456789ab") == "upload_0123456789ab"
    for bad in ["x; drop schema public", "../../etc", "ABCDEF123456", ""]:
        with pytest.raises(ValueError):
            upload.schema_of(bad)


# ---- database ------------------------------------------------------------------

def _up() -> bool:
    with socket.socket() as s:
        s.settimeout(1)
        return s.connect_ex(("localhost", 5433)) == 0


needs_db = pytest.mark.skipif(not _up(), reason="run `docker compose up -d` first")


@pytest.fixture
def conn():
    with psycopg.connect(**{**PG, "dbname": "postgres"}, autocommit=True) as c:
        if not c.execute("SELECT 1 FROM pg_database WHERE datname = 'argus_test'").fetchone():
            c.execute("CREATE DATABASE argus_test")
    with psycopg.connect(**{**PG, "dbname": "argus_test"}, row_factory=dict_row) as c:
        yield c
        for r in c.execute("SELECT id FROM uploads").fetchall() if _has_registry(c) else []:
            upload.delete(c, r["id"])


def _has_registry(c) -> bool:
    return c.execute("SELECT to_regclass('uploads') AS t").fetchone()["t"] is not None


@needs_db
def test_ingest_modern_log_end_to_end(conn):
    path = FIX / "modern_app.log"
    uid = upload.create(conn, path.name, path.stat().st_size)
    row = upload.ingest(conn, uid, path)
    assert row["status"] == "succeeded" and row["ts_format"] == "iso8601"
    assert row["lines_done"] == row["lines_total"] == 807 - 0
    s = upload.summary(conn, uid)
    assert s["events"] == 807
    assert {l["name"] for l in s["levels"]} >= {"INFO", "DEBUG", "WARN", "ERROR"}
    assert [x["bucket"].minute for x in s["spikes"]] == [10]  # the planted spike at 09:00 + 70 min
    assert any("upstream timeout" in r["example"] for r in s["rare_templates"])
    assert sum(t["n"] for t in conn.execute(f'SELECT n FROM "upload_{uid}".templates').fetchall()) == 807
    hits = upload.search(conn, uid, "upstream timeout")
    assert len(hits) == 1 and hits[0]["level"] == "ERROR"


@needs_db
def test_stack_frames_inherit_the_previous_timestamp(conn):
    path = FIX / "modern_app.log"
    uid = upload.create(conn, path.name, 1)
    upload.ingest(conn, uid, path)
    r = conn.execute(
        f"""SELECT count(*) AS n FROM "upload_{uid}".events
            WHERE content LIKE '%SocketTimeoutException%' AND ts = '2026-03-02T10:10:30Z'"""
    ).fetchone()
    assert r["n"] == 1


@needs_db
def test_syslog_has_no_year_and_still_loads(conn):
    path = FIX / "syslog_sample.log"
    uid = upload.create(conn, path.name, 1)
    row = upload.ingest(conn, uid, path)
    assert row["status"] == "succeeded" and row["ts_format"] == "syslog"
    s = upload.summary(conn, uid)
    assert s["events"] == 401 and s["first_ts"] is not None


@needs_db
def test_uploads_are_isolated_and_deletable(conn):
    a = upload.create(conn, "a.log", 1)
    b = upload.create(conn, "b.log", 1)
    upload.ingest(conn, a, FIX / "modern_app.log")
    upload.ingest(conn, b, FIX / "syslog_sample.log")
    assert upload.search(conn, a, "sshd") == [] and len(upload.search(conn, b, "sshd")) > 0
    assert upload.delete(conn, a) is True
    assert conn.execute("SELECT to_regnamespace(%s) AS s", (f"upload_{a}",)).fetchone()["s"] is None
    assert upload.get(conn, a) is None and upload.get(conn, b)["status"] == "succeeded"


@needs_db
def test_failed_ingest_records_the_error_and_leaves_no_schema(conn, tmp_path):
    bad = tmp_path / "bad.log"
    bad.write_bytes(b"\x00" * 200)
    uid = upload.create(conn, "bad.log", 200)
    row = upload.ingest(conn, uid, bad)
    assert row["status"] == "failed" and "binary" in row["error"]
    assert conn.execute("SELECT to_regnamespace(%s) AS s", (f"upload_{uid}",)).fetchone()["s"] is None
    empty = tmp_path / "empty.log"
    empty.write_text("\n\n  \n")
    uid2 = upload.create(conn, "empty.log", 4)
    assert "no non-empty lines" in upload.ingest(conn, uid2, empty)["error"]
