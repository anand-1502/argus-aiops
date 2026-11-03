# SQL performance notes

Measured, not claimed: `scripts/sql_tuning_demo.py` ran each query on a 2,000,000-row temporary copy of `events`
(median of 3 `EXPLAIN (ANALYZE)` runs, Postgres 16 in Docker with a 768 MB memory limit, on an 8 GB laptop) and wrote this file.
Re-run it to regenerate the numbers on your machine.

| # | Problem | Before | After | Speed-up |
| --- | --- | --- | --- | --- |
| 1 | Find all events of one block | 182.9 ms (`Seq Scan on ev  (cost=0.00..83563.46 rows=15 width=204) (actual time=71.680..182.853 rows=17 loops=1)`) | 0.03 ms (`Bitmap Heap Scan on ev  (cost=4.54..64.01 rows=15 width=204) (actual time=0.007..0.009 rows=17 loops=1)`) | 6,306x |
| 2 | Distinct blocks per template | 3,582 ms with `count(DISTINCT block_id)` | 758 ms deduplicating `(template, block_id)` first | 4.7x |
| 3 | Hourly event counts, asked repeatedly | 348 ms scanning the raw table | 0.00 ms reading a pre-aggregated table | 87,027x |

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
