"""Replay the HDFS log in timed batches so the dashboard behaves like a live feed.

Each batch is parsed and inserted into `live_events`. In Phase 5 a Kafka producer and consumer
replace this loop; the parsing and table stay the same.
"""
import argparse
import re
import time
from datetime import datetime, timezone
from pathlib import Path

import psycopg

from ingest.load import PG, ROOT

LINE = re.compile(r"^(\d{6}) (\d{6}) (\d+) (\w+) ([^:]+): (.*)$")
BLOCK = re.compile(r"blk_-?\d+")
# identical to ingest.parser._MASKS, applied in the same order
MASKS = [BLOCK, re.compile(r"/?\d+\.\d+\.\d+\.\d+(:\d+)?"), re.compile(r"/\S+"), re.compile(r"\b\d+\b")]
COLUMNS = "ts, pid, level, component, block_id, content, template, batch"


def parse_line(line: str) -> dict | None:
    m = LINE.match(line)
    if not m:
        return None
    d, t, pid, level, component, content = m.groups()
    template = content
    for mask in MASKS:
        template = mask.sub("<*>", template)
    block = BLOCK.search(content)
    return {
        "ts": datetime.strptime(d + t, "%y%m%d%H%M%S").replace(tzinfo=timezone.utc),
        "pid": int(pid), "level": level, "component": component,
        "block_id": block.group(0) if block else "", "content": content, "template": template,
    }


def _scalar(conn: psycopg.Connection, sql: str):
    """First column of the first row, whether the connection returns tuples or dicts."""
    row = conn.execute(sql).fetchone()
    return row[0] if isinstance(row, tuple) else next(iter(row.values()))


def ensure_table(conn: psycopg.Connection) -> None:
    conn.execute((ROOT / "infra" / "sql" / "live.sql").read_text())
    conn.commit()


def _insert(conn: psycopg.Connection, rows: list[dict], batch: int) -> None:
    with conn.cursor() as cur, cur.copy(f"COPY live_events ({COLUMNS}) FROM STDIN") as cp:
        for r in rows:
            cp.write_row((r["ts"], r["pid"], r["level"], r["component"], r["block_id"], r["content"], r["template"], batch))
    conn.commit()


def replay(path: Path, conn: psycopg.Connection, batch_size: int = 2000, interval: float = 1.0,
           sleep=time.sleep, max_batches: int | None = None, skip: int = 0) -> int:
    """Insert the file in batches, pausing `interval` seconds after each. Returns lines inserted."""
    start = _scalar(conn, "SELECT coalesce(max(batch), 0) FROM live_events") + 1
    total, batch, buf = 0, start, []
    with path.open() as f:
        for i, line in enumerate(f):
            if i < skip:
                continue
            row = parse_line(line.rstrip("\n"))
            if row:
                buf.append(row)
            if len(buf) == batch_size:
                _insert(conn, buf, batch)
                total += len(buf)
                buf, batch = [], batch + 1
                sleep(interval)
                if max_batches and batch - start >= max_batches:
                    return total
        if buf:
            _insert(conn, buf, batch)
            total += len(buf)
            sleep(interval)
    return total


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--log", type=Path, default=ROOT / "data/hdfs/HDFS.log")
    ap.add_argument("--batch-size", type=int, default=2000)
    ap.add_argument("--interval", type=float, default=1.0, help="seconds between batches")
    ap.add_argument("--max-batches", type=int, default=None)
    ap.add_argument("--reset", action="store_true", help="empty live_events first")
    args = ap.parse_args()
    with psycopg.connect(**PG) as conn:
        ensure_table(conn)
        if args.reset:
            conn.execute("TRUNCATE live_events")
            conn.commit()
        n = replay(args.log, conn, args.batch_size, args.interval, max_batches=args.max_batches)
    print(f"replayed {n} lines")


if __name__ == "__main__":
    main()
