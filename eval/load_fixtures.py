"""Load the committed golden fixtures into an empty Postgres database, so CI (and a laptop) can run the
retrieval gate without the 11M-row dataset. Defaults to the database named by PGDATABASE."""
import csv
from pathlib import Path

import psycopg

from api.db import connect

FIX = Path(__file__).resolve().parent / "fixtures"
ROOT = FIX.parent.parent


def load() -> dict:
    with connect() as conn:
        conn.execute((ROOT / "infra/sql/schema.sql").read_text())
        conn.execute("DROP TABLE IF EXISTS template_stats")
        conn.execute("CREATE TABLE template_stats (template text PRIMARY KEY, blocks int, frac_blocks float8)")
        with conn.cursor() as cur:
            with cur.copy("COPY events (block_id, ts, pid, level, component, content, template) FROM STDIN WITH (FORMAT csv, HEADER true)") as cp:
                cp.write((FIX / "golden_events.csv").read_bytes())
            with cur.copy("COPY template_stats (template, blocks, frac_blocks) FROM STDIN WITH (FORMAT csv, HEADER true)") as cp:
                cp.write((FIX / "template_stats.csv").read_bytes())
        conn.commit()
        n = conn.execute("SELECT count(*) AS n FROM events").fetchone()["n"]
        t = conn.execute("SELECT count(*) AS n FROM template_stats").fetchone()["n"]
    return {"events": n, "templates": t}


def ensure_database(name: str) -> None:
    """Create `name` if it does not exist (used for the local `argus_ci` database)."""
    from ingest.load import PG

    with psycopg.connect(**{**PG, "dbname": "postgres"}, autocommit=True) as c:
        if not c.execute("SELECT 1 FROM pg_database WHERE datname = %s", (name,)).fetchone():
            c.execute(f'CREATE DATABASE "{name}"')


if __name__ == "__main__":
    import os

    if os.environ.get("PGDATABASE", "argus") != "argus":
        ensure_database(os.environ["PGDATABASE"])
    print(load())
