"""Kafka version of the live feed: a producer streams raw log lines into a topic, and a consumer parses
micro-batches and writes them to `live_events`, the table the dashboard already reads.

  uv run python -m ingest.stream produce --rate 4000        # in one terminal
  uv run python -m ingest.stream consume --reset            # in another
"""
import argparse
import time
from collections.abc import Iterable, Iterator
from pathlib import Path

import psycopg

from ingest.load import PG, ROOT
from ingest.replay import _insert, _scalar, ensure_table, parse_line

TOPIC = "raw-logs"
BOOTSTRAP = "localhost:9092"


def group_batches(items: Iterable, size: int) -> Iterator[list]:
    """Yield lists of at most `size` items, in order."""
    batch: list = []
    for item in items:
        batch.append(item)
        if len(batch) == size:
            yield batch
            batch = []
    if batch:
        yield batch


def produce(path: Path, topic: str = TOPIC, bootstrap: str = BOOTSTRAP, rate: int = 4000, limit: int | None = None) -> int:
    """Publish log lines at roughly `rate` lines per second. Returns lines sent."""
    from confluent_kafka import Producer

    p = Producer({"bootstrap.servers": bootstrap, "linger.ms": 50})
    sent, started = 0, time.time()
    with path.open() as f:
        for line in f:
            p.produce(topic, line.rstrip("\n").encode())
            sent += 1
            if sent % 1000 == 0:
                p.poll(0)
                ahead = sent / rate - (time.time() - started)  # pace the feed instead of flooding the broker
                if ahead > 0:
                    time.sleep(ahead)
            if limit and sent >= limit:
                break
    p.flush()
    return sent


def consume(topic: str = TOPIC, bootstrap: str = BOOTSTRAP, group: str = "argus-live", batch_size: int = 2000,
            max_batches: int | None = None, idle_timeout: float = 15.0, startup_timeout: float = 45.0,
            conn: psycopg.Connection | None = None) -> int:
    """Read micro-batches from Kafka, parse them and insert into live_events.

    Stops after `idle_timeout` seconds of silence once data has flowed. Before the first message it waits up to
    `startup_timeout`, because joining a consumer group on a freshly started broker can take longer than the idle timeout.
    """
    from confluent_kafka import Consumer

    own = conn is None
    conn = conn or psycopg.connect(**PG)
    ensure_table(conn)
    c = Consumer({"bootstrap.servers": bootstrap, "group.id": group, "auto.offset.reset": "earliest", "enable.auto.commit": False})
    c.subscribe([topic])
    batch_no = _scalar(conn, "SELECT coalesce(max(batch), 0) FROM live_events")
    total, done = 0, 0
    try:
        last, limit = time.time(), startup_timeout
        while time.time() - last < limit and (not max_batches or done < max_batches):
            msgs = c.consume(num_messages=batch_size, timeout=2.0)
            rows = [r for m in msgs if not m.error() and (r := parse_line(m.value().decode()))]
            if not rows:
                continue
            last, limit = time.time(), idle_timeout
            batch_no += 1
            _insert(conn, rows, batch_no)
            c.commit()  # commit only after the batch is safely in Postgres: at-least-once delivery
            total += len(rows)
            done += 1
    finally:
        c.close()
        if own:
            conn.close()
    return total


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("produce")
    p.add_argument("--log", type=Path, default=ROOT / "data/hdfs/HDFS.log")
    p.add_argument("--rate", type=int, default=4000)
    p.add_argument("--limit", type=int, default=None)
    c = sub.add_parser("consume")
    c.add_argument("--batch-size", type=int, default=2000)
    c.add_argument("--max-batches", type=int, default=None)
    c.add_argument("--reset", action="store_true")
    a = ap.parse_args()
    if a.cmd == "produce":
        print("sent", produce(a.log, rate=a.rate, limit=a.limit))
    else:
        with psycopg.connect(**PG) as conn:
            ensure_table(conn)
            if a.reset:
                conn.execute("TRUNCATE live_events")
                conn.commit()
            print("consumed", consume(batch_size=a.batch_size, max_batches=a.max_batches, conn=conn))


if __name__ == "__main__":
    main()
