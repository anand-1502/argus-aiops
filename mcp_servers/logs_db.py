"""`logs-db` MCP server: read-only, parameterised access to parsed HDFS events in Postgres.

The agent never sees SQL or a connection string. It gets four fixed tools, each with a row cap.
Every event it returns carries a citation id (`<block_id>#<n>`) that can be verified later.
"""
from mcp.server.fastmcp import FastMCP

from api.db import connect
from mcp_servers.common import registrar, audited, clamp, parse_ts

mcp = FastMCP("logs-db")
tool = registrar(mcp)
MAX_COMPONENT_ROWS = 50


def event_citation(block_id: str, n: int) -> str:
    return f"{block_id}#{n}"


@tool
@audited("logs-db")
def get_block_events(block_id: str, limit: int = 50) -> list[dict]:
    """Return the log events recorded for one HDFS block, oldest first. Each has a citation id."""
    if not block_id.startswith("blk_"):
        raise ValueError("block_id must look like blk_-123...")
    with connect() as conn:
        rows = conn.execute(
            """SELECT row_number() OVER (ORDER BY ts, pid, content) AS n, ts, level, component, content
               FROM events WHERE block_id = %s ORDER BY ts, pid, content LIMIT %s""",
            (block_id, clamp(limit)),
        ).fetchall()
    return [{"citation": event_citation(block_id, r["n"]), "ts": r["ts"].isoformat(), "level": r["level"],
             "component": r["component"], "content": r["content"]} for r in rows]


@tool
@audited("logs-db")
def get_unusual_events(block_id: str, top: int = 3) -> list[dict]:
    """Return the block's rarest events: those whose message template appears in the fewest blocks overall
    (no labels involved). Routine lines are excluded. Each event has a citation id and its template."""
    if not block_id.startswith("blk_"):
        raise ValueError("block_id must look like blk_-123...")
    with connect() as conn:
        rows = conn.execute(
            """WITH numbered AS (
                 SELECT row_number() OVER (ORDER BY ts, pid, content) AS n, ts, level, component, content, template
                 FROM events WHERE block_id = %s)
               SELECT n.n, n.ts, n.level, n.component, n.content, n.template, s.frac_blocks
               FROM numbered n JOIN template_stats s USING (template)
               WHERE s.frac_blocks < 0.5 ORDER BY s.frac_blocks, n.n LIMIT %s""",
            (block_id, min(max(int(top), 1), 10)),
        ).fetchall()
    return [{"citation": event_citation(block_id, r["n"]), "ts": r["ts"].isoformat(), "level": r["level"],
             "component": r["component"], "content": r["content"], "template": r["template"],
             "frac_blocks": round(r["frac_blocks"], 5)} for r in rows]


@tool
@audited("logs-db")
def get_block_label(block_id: str) -> dict:
    """Return the benchmark label (Normal or Anomaly) for a block, or null if it is not labelled."""
    with connect() as conn:
        row = conn.execute("SELECT label FROM block_labels WHERE block_id = %s", (block_id,)).fetchone()
    return {"block_id": block_id, "label": row["label"] if row else None}


@tool
@audited("logs-db")
def find_anomalous_blocks(start: str, end: str, limit: int = 20) -> list[dict]:
    """List anomalous blocks whose first event falls between two ISO timestamps (UTC)."""
    s, e = parse_ts(start), parse_ts(end)
    with connect() as conn:
        rows = conn.execute(
            """SELECT ev.block_id, min(ev.ts) AS first_ts, count(*) AS n_events
               FROM events ev JOIN block_labels l USING (block_id)
               WHERE l.label = 'Anomaly' AND ev.ts BETWEEN %s AND %s
               GROUP BY ev.block_id ORDER BY first_ts LIMIT %s""",
            (s, e, clamp(limit, 20)),
        ).fetchall()
    return [{"block_id": r["block_id"], "first_ts": r["first_ts"].isoformat(), "n_events": r["n_events"]} for r in rows]


@tool
@audited("logs-db")
def component_summary(start: str, end: str) -> list[dict]:
    """Count events per component and level between two ISO timestamps (UTC)."""
    s, e = parse_ts(start), parse_ts(end)
    with connect() as conn:
        rows = conn.execute(
            """SELECT component, level, count(*) AS events FROM events
               WHERE ts BETWEEN %s AND %s GROUP BY 1, 2 ORDER BY events DESC LIMIT %s""",
            (s, e, MAX_COMPONENT_ROWS),
        ).fetchall()
    return [dict(r) for r in rows]


if __name__ == "__main__":
    mcp.run()
