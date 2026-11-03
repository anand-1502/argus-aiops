"""Phase 5: the Kafka path. The batching logic is unit-tested; the round trip needs a running broker."""
import socket
from pathlib import Path

import psycopg
import pytest

from ingest.stream import group_batches

FIXTURE = Path(__file__).parent / "fixtures" / "hdfs_sample.log"


def test_group_batches_keeps_order_and_the_remainder():
    assert list(group_batches(range(7), 3)) == [[0, 1, 2], [3, 4, 5], [6]]
    assert list(group_batches([], 3)) == []
    assert list(group_batches("ab", 5)) == [["a", "b"]]


def _broker_up() -> bool:
    with socket.socket() as s:
        s.settimeout(1)
        return s.connect_ex(("localhost", 9092)) == 0


@pytest.mark.skipif(not _broker_up(), reason="start Kafka: docker compose --profile streaming up -d kafka")
def test_round_trip_through_kafka_lands_every_line_in_postgres():
    import uuid

    from ingest.load import PG
    from ingest.replay import ensure_table
    from ingest.stream import consume, produce

    topic = f"test-{uuid.uuid4().hex[:8]}"
    with psycopg.connect(**{**PG, "dbname": "argus_test"}) as conn:
        ensure_table(conn)
        conn.execute("TRUNCATE live_events")
        conn.commit()
        assert produce(FIXTURE, topic=topic, rate=100000) == 4
        got = consume(topic=topic, group=topic, batch_size=3, idle_timeout=6, conn=conn)
        assert got == 4
        assert conn.execute("SELECT count(*) FROM live_events").fetchone()[0] == 4
        assert conn.execute("SELECT count(DISTINCT batch) FROM live_events").fetchone()[0] >= 1
