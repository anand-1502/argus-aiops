"""Pick one anomalous block per anomaly signature as a seeded incident with a known root cause.

The expected runbook comes from our own mapping of signature -> runbook (see kb/runbooks), and the
block is chosen so that it shows exactly one signature, which keeps the ground truth unambiguous.
"""
import json
from pathlib import Path

from api.db import connect

SIGNATURES = [  # (expected runbook, SQL pattern for the signature template)
    ("RB-001", "Unexpected error trying to delete block%"),
    ("RB-002", "writeBlock%received exception java.io.IOException: Could not read from stream%"),
    ("RB-003", "BLOCK* ask%to replicate%"),
    ("RB-004", "%But it does not belong to any file%"),
    ("RB-005", "BLOCK* NameSystem.addStoredBlock: Redundant%"),
    ("RB-006", "Receiving empty packet%"),
]
ALL = [p for _, p in SIGNATURES]


def main() -> list[dict]:
    out = []
    with connect() as conn:
        for rb, pat in SIGNATURES:
            others = [p for p in ALL if p != pat]
            clause = " AND ".join(f"NOT bool_or(e.template LIKE %s)" for _ in others)
            row = conn.execute(
                f"""SELECT e.block_id, min(e.ts) AS first_ts, max(e.ts) AS last_ts, count(*) AS n_events
                    FROM events e JOIN block_labels l USING (block_id)
                    WHERE l.label = 'Anomaly'
                    GROUP BY e.block_id
                    HAVING bool_or(e.template LIKE %s) AND {clause} AND count(*) BETWEEN 3 AND 40
                    ORDER BY e.block_id LIMIT 1""",
                [pat, *others],
            ).fetchone()
            evidence = conn.execute(
                "SELECT ts, content FROM events WHERE block_id = %s AND template LIKE %s ORDER BY ts LIMIT 1",
                [row["block_id"], pat],
            ).fetchone()
            out.append({
                "block_id": row["block_id"],
                "expected_runbook": rb,
                "first_ts": row["first_ts"].isoformat(),
                "last_ts": row["last_ts"].isoformat(),
                "n_events": row["n_events"],
                "signature_line": evidence["content"],
            })
    Path("agent/incidents.json").write_text(json.dumps(out, indent=2))
    return out


if __name__ == "__main__":
    for i in main():
        print(i["expected_runbook"], i["block_id"], i["n_events"], "|", i["signature_line"][:70])
