"""Build the `service_metrics` table the `metrics` MCP server reads.

Error-style metrics are derived from real per-minute log counts. Generic host metrics
(cpu, disk, rpc latency) are simulated with a fixed seed and nudged upward when the
derived error counts are high, so they correlate with real incidents. Every row says which.
"""
import numpy as np
import psycopg

from api.db import connect

DERIVED = {  # (service, metric): SQL predicate on the parsed events
    ("datanode", "delete_errors_per_min"): "template LIKE 'Unexpected error trying to delete block%'",
    ("datanode", "write_exceptions_per_min"): "template LIKE 'writeBlock%received exception%'",
    ("namenode", "replication_requests_per_min"): "template LIKE 'BLOCK* ask%to replicate%'",
    ("namenode", "orphan_block_reports_per_min"): "template LIKE '%But it does not belong to any file%'",
    ("namenode", "redundant_reports_per_min"): "template LIKE 'BLOCK* NameSystem.addStoredBlock: Redundant%'",
    ("datanode", "empty_packets_per_min"): "template LIKE 'Receiving empty packet%'",
}


def main(seed: int = 7) -> int:
    rng = np.random.default_rng(seed)
    with connect() as conn:
        conn.execute(open("infra/sql/metrics.sql").read())
        minutes = [r["m"] for r in conn.execute(
            "SELECT generate_series(date_trunc('minute', min(ts)), date_trunc('minute', max(ts)), interval '1 minute') AS m FROM events").fetchall()]
        index = {m: i for i, m in enumerate(minutes)}
        rows = []
        error_load = np.zeros(len(minutes))
        for (service, metric), pred in DERIVED.items():
            counts = conn.execute(
                f"SELECT date_trunc('minute', ts) AS m, count(*) AS n FROM events WHERE {pred} GROUP BY 1").fetchall()
            series = np.zeros(len(minutes))
            for r in counts:
                series[index[r["m"]]] = r["n"]
            error_load += series / max(series.max(), 1)
            rows += [(m, service, metric, float(v), "derived-from-logs") for m, v in zip(minutes, series)]
        load = error_load / max(error_load.max(), 1)  # 0..1 across all error signals
        for service, metric, base, spread, gain in [
            ("datanode", "cpu_pct", 35, 6, 40), ("datanode", "disk_util_pct", 50, 5, 30), ("namenode", "rpc_latency_ms", 4, 1, 25),
        ]:
            vals = np.clip(base + rng.normal(0, spread, len(minutes)) + gain * load, 0, None)
            rows += [(m, service, metric, float(v), "simulated") for m, v in zip(minutes, vals)]
        with conn.cursor() as cur, cur.copy("COPY service_metrics (ts, service, metric, value, source) FROM STDIN") as cp:
            for r in rows:
                cp.write_row(r)
        return len(rows)


if __name__ == "__main__":
    print(f"wrote {main()} metric rows")
