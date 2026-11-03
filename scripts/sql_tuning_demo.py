"""Measure three real SQL optimisations on this dataset and write docs/SQL_PERFORMANCE.md from the measurements.

Everything runs on temporary copies, so the real tables are never touched. Times are the median of 3 runs of
EXPLAIN (ANALYZE) execution time on this laptop's Postgres in Docker (768 MB limit).
"""
import re
import statistics
from pathlib import Path

from api.db import connect

OUT = Path(__file__).resolve().parent.parent / "docs" / "SQL_PERFORMANCE.md"
SAMPLE_ROWS = 2_000_000


def timed(conn, sql: str, params=(), runs: int = 3) -> tuple[float, str]:
    """Median execution time in ms, and the top line of the plan."""
    times, plan_head = [], ""
    for _ in range(runs):
        rows = conn.execute("EXPLAIN (ANALYZE, BUFFERS) " + sql, params).fetchall()
        text = "\n".join(next(iter(r.values())) for r in rows)
        times.append(float(re.search(r"Execution Time: ([\d.]+) ms", text).group(1)))
        plan_head = next(iter(rows[0].values())).strip()[:110]
    return statistics.median(times), plan_head


def main() -> None:
    with connect() as conn:
        conn.execute("SET work_mem = '64MB'")
        conn.execute(f"CREATE TEMP TABLE ev AS SELECT * FROM events WHERE block_id <> '' LIMIT {SAMPLE_ROWS}")
        conn.execute("ANALYZE ev")
        target = conn.execute("SELECT block_id FROM ev OFFSET 1000000 LIMIT 1").fetchone()["block_id"]
        n_rows = conn.execute("SELECT count(*) AS n FROM ev").fetchone()["n"]

        # 1. point lookup: sequential scan vs b-tree index
        q1 = "SELECT * FROM ev WHERE block_id = %s"
        before1, plan_b1 = timed(conn, q1, (target,))
        conn.execute("CREATE INDEX ev_block_idx ON ev (block_id)")
        conn.execute("ANALYZE ev")
        after1, plan_a1 = timed(conn, q1, (target,))

        # 2. distinct count per group: count(DISTINCT) vs deduplicating first
        q2a = "SELECT template, count(DISTINCT block_id) FROM ev GROUP BY template"
        q2b = "SELECT template, count(*) FROM (SELECT template, block_id FROM ev GROUP BY 1, 2) d GROUP BY template"
        before2, _ = timed(conn, q2a)
        after2, _ = timed(conn, q2b)

        # 3. repeated aggregation: scan the raw table every time vs read a pre-aggregated table
        q3a = "SELECT date_trunc('hour', ts) AS h, count(*) FROM ev GROUP BY 1"
        conn.execute("CREATE TEMP TABLE hourly AS SELECT date_trunc('hour', ts) AS h, count(*) AS n FROM ev GROUP BY 1")
        before3, _ = timed(conn, q3a)
        after3, _ = timed(conn, "SELECT h, n FROM hourly")

    def x(a, b):
        return f"{a / b:,.0f}x" if b else "n/a"

    OUT.write_text(f"""# SQL performance notes

Measured, not claimed: `scripts/sql_tuning_demo.py` ran each query on a {n_rows:,}-row temporary copy of `events`
(median of 3 `EXPLAIN (ANALYZE)` runs, Postgres 16 in Docker with a 768 MB memory limit, on an 8 GB laptop) and wrote this file.
Re-run it to regenerate the numbers on your machine.

| # | Problem | Before | After | Speed-up |
| --- | --- | --- | --- | --- |
| 1 | Find all events of one block | {before1:,.1f} ms (`{plan_b1}`) | {after1:,.2f} ms (`{plan_a1}`) | {x(before1, after1)} |
| 2 | Distinct blocks per template | {before2:,.0f} ms with `count(DISTINCT block_id)` | {after2:,.0f} ms deduplicating `(template, block_id)` first | {before2 / after2:.1f}x |
| 3 | Hourly event counts, asked repeatedly | {before3:,.0f} ms scanning the raw table | {after3:,.2f} ms reading a pre-aggregated table | {x(before3, after3)} |

## What each one teaches
1. **Index the column you filter on.** Without an index Postgres reads every row; a b-tree index jumps to the matching rows.
   The loader builds `events_block_id_idx` *after* the bulk load, because maintaining an index during an 11M-row insert is slower.
2. **`count(DISTINCT x)` inside a `GROUP BY` can sort the whole table per group.** Collapsing to unique `(group, x)` pairs first lets
   Postgres hash-aggregate, then count. On the full 11M rows the first form ran for more than ten minutes before I cancelled it
   during development; the second finished in about 15 seconds. (That full-size comparison was observed once, not re-measured here.)
3. **Aggregate once, query many times.** `fact_hourly_events` in the dbt project exists so dashboards do not rescan 11M rows.
   The price is staleness: it must be rebuilt (`dbt build`) after new data arrives.

## How to read the plans yourself
```sql
EXPLAIN (ANALYZE, BUFFERS) SELECT * FROM events WHERE block_id = 'blk_-1038022846623317329';
```
Look for `Seq Scan` (reads everything) versus `Index Scan` or `Bitmap Heap Scan` (jumps), the estimated versus actual row counts,
and the buffer hits.
""")
    print(OUT.read_text()[:900])


if __name__ == "__main__":
    main()
