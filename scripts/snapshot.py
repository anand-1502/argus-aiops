"""Record the live API's answers as JSON files, for the public static site (GitHub Pages).

  uv run python -m scripts.snapshot            # needs the API on :8000 and the full demo data

The static site reads these files instead of calling a backend, so it can be hosted for free. File names come from
`key()`, which web/lib/api.ts mirrors exactly.
"""
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "web" / "public" / "snapshot"
API = "http://localhost:8000"
SAMPLE = ROOT / "tests" / "fixtures" / "modern_app.log"


def key(path: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "_", path.lstrip("/"))


def paths(client: httpx.Client) -> list[str]:
    incidents = json.loads((ROOT / "agent" / "incidents.json").read_text())
    from api.main import SQL_VIEWABLE

    return [
        "/stats/summary", "/stats/volume?bucket=hour", "/stats/volume?bucket=day", "/stats/components", "/stats/levels",
        "/stats/clusters", "/model/status", "/model/analysis", "/agent/incidents", "/live/status", "/evals/summary",
        "/export/status", "/analytics/kpis", "/analytics/trend", "/analytics/components", "/analytics/windows",
        "/business/inputs", "/pipeline/status", "/jobs", "/tenant",
        *[f"/analytics/sql/{m}" for m in SQL_VIEWABLE],
        *[f"/agent/runs/{i['block_id']}" for i in incidents if i.get("recorded", True)],
    ]


def demo_upload() -> tuple[dict, dict]:
    """Run the sample log through the real upload pipeline in the scratch database and keep its summary."""
    import json as _json

    import psycopg
    from psycopg.rows import dict_row

    from ingest import upload
    from ingest.load import PG

    with psycopg.connect(**{**PG, "dbname": "argus_test"}, row_factory=dict_row) as conn:
        uid = upload.create(conn, SAMPLE.name, SAMPLE.stat().st_size)
        try:
            row = upload.ingest(conn, uid, SAMPLE)
            summary = upload.summary(conn, uid)
        finally:
            upload.delete(conn, uid)
    enc = lambda o: o.isoformat() if hasattr(o, "isoformat") else str(o)  # noqa: E731
    row = _json.loads(_json.dumps({**row, "id": "demo", "filename": f"{SAMPLE.name} (synthetic sample)"}, default=enc))
    return row, _json.loads(_json.dumps(summary, default=enc))


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    for old in OUT.glob("*.json"):
        old.unlink()
    failed = []
    with httpx.Client(base_url=API, timeout=60) as c:
        for p in paths(c):
            r = c.get(p)
            if r.status_code != 200:
                failed.append((p, r.status_code))
                continue
            (OUT / f"{key(p)}.json").write_text(json.dumps(r.json(), separators=(",", ":")))
    row, summary = demo_upload()
    (OUT / "uploads.json").write_text(json.dumps([row]))
    (OUT / "uploads_demo_summary.json").write_text(json.dumps(summary, separators=(",", ":")))
    (OUT / "_meta.json").write_text(json.dumps({"taken_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}))
    n = len(list(OUT.glob("*.json")))
    print(f"wrote {n} files to {OUT.relative_to(ROOT)}; failed: {failed or 'none'}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
