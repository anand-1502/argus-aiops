"""`metrics` MCP server: per-minute service metrics for the mock HDFS topology.

Error-style metrics are derived from the real logs; cpu/disk/rpc are simulated. Each point says which.
"""
from mcp.server.fastmcp import FastMCP

from api.db import connect
from mcp_servers.common import registrar, audited, parse_ts

mcp = FastMCP("metrics")
tool = registrar(mcp)
MAX_POINTS = 120


@tool
@audited("metrics")
def list_metrics() -> list[dict]:
    """List available (service, metric) pairs and whether each is derived from logs or simulated."""
    with connect() as conn:
        rows = conn.execute("SELECT DISTINCT service, metric, source FROM service_metrics ORDER BY 1, 2").fetchall()
    return [dict(r) for r in rows]


@tool
@audited("metrics")
def get_metric(service: str, metric: str, start: str, end: str) -> dict:
    """Per-minute values of one metric between two ISO timestamps (UTC), with min/max/mean and the peak minute."""
    s, e = parse_ts(start), parse_ts(end)
    with connect() as conn:
        rows = conn.execute(
            """SELECT ts, value, source FROM service_metrics
               WHERE service = %s AND metric = %s AND ts BETWEEN %s AND %s ORDER BY ts LIMIT %s""",
            (service, metric, s, e, MAX_POINTS),
        ).fetchall()
    if not rows:
        return {"service": service, "metric": metric, "points": [], "note": "no data in range"}
    vals = [r["value"] for r in rows]
    peak = max(rows, key=lambda r: r["value"])
    return {
        "service": service, "metric": metric, "source": rows[0]["source"],
        "min": min(vals), "max": max(vals), "mean": sum(vals) / len(vals),
        "peak_at": peak["ts"].isoformat(),
        "points": [{"ts": r["ts"].isoformat(), "value": round(r["value"], 2)} for r in rows],
    }


if __name__ == "__main__":
    mcp.run()
