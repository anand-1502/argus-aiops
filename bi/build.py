"""Build the BI export from the database: aggregate tables, profile them, recommend visuals, write both formats."""
import json
import shutil
import tempfile
import zipfile
from pathlib import Path

import pandas as pd

from api.db import connect
from bi.powerbi import write_package
from bi.profile import profile_table
from bi.recommend import recommend_charts, recommend_fields

ROOT = Path(__file__).resolve().parent.parent
NORMAL_SAMPLE = 20_000  # all anomalous blocks plus a sample of normal ones, so the extract stays small

HOURLY = """SELECT date_trunc('hour', e.ts) AS hour, count(*)::bigint AS events,
            count(*) FILTER (WHERE l.label = 'Anomaly')::bigint AS anomalous_events
            FROM events e LEFT JOIN block_labels l USING (block_id) GROUP BY 1 ORDER BY 1"""
COMPONENTS = """SELECT e.component, e.level, count(*)::bigint AS events,
                count(*) FILTER (WHERE l.label = 'Anomaly')::bigint AS anomalous_events
                FROM events e LEFT JOIN block_labels l USING (block_id) GROUP BY 1, 2 ORDER BY events DESC"""
BLOCKS = """WITH s AS (SELECT block_id, count(*)::bigint AS n_events, min(ts) AS first_ts,
                       extract(epoch FROM max(ts) - min(ts))::float8 AS duration_s,
                       (count(*) FILTER (WHERE level = 'WARN'))::bigint AS n_warn
                FROM events WHERE block_id <> '' GROUP BY 1)
            SELECT s.block_id, l.label, s.n_events, s.first_ts, s.duration_s, s.n_warn
            FROM s JOIN block_labels l USING (block_id)
            WHERE l.label = 'Anomaly' OR (l.label = 'Normal' AND hashtext(s.block_id) % 29 = 0)
            ORDER BY s.first_ts"""


def agent_table() -> pd.DataFrame:
    """Per-incident agent results from the newest eval run, or from the recorded demo runs."""
    results = sorted((ROOT / "eval" / "results").glob("*.json")) if (ROOT / "eval" / "results").exists() else []
    rows = []
    if results:
        for i in json.loads(results[-1].read_text())["incidents"]:
            s = i.get("scores") or {}
            rows.append({"block_id": i["block_id"], "expected_runbook": i["expected_runbook"],
                         "chosen_runbook": (i.get("postmortem") or {}).get("runbook_id"),
                         "runbook_correct": bool(s.get("runbook_correct")), "verified": bool(s.get("verified")),
                         "signature_cited": bool(s.get("signature_cited")), "seconds": float(i["seconds"])})
    else:
        demo = json.loads((ROOT / "agent" / "demo_runs.json").read_text())
        for bid, r in demo.items():
            rows.append({"block_id": bid, "expected_runbook": r["expected_runbook"], "chosen_runbook": r["postmortem"]["runbook_id"],
                         "runbook_correct": r["postmortem"]["runbook_id"] == r["expected_runbook"], "verified": r["verification"]["ok"],
                         "signature_cited": True, "seconds": float(r.get("seconds", 0))})
    return pd.DataFrame(rows)


MARTS = [("anomaly_trend", "SELECT * FROM analytics.mart_anomaly_trend ORDER BY hour_ts"),
         ("component_health", "SELECT * FROM analytics.mart_component_health ORDER BY anomaly_rank"),
         ("incident_windows", "SELECT * FROM analytics.mart_incident_windows ORDER BY window_id")]


def load_tables() -> dict[str, pd.DataFrame]:
    with connect() as conn:
        tables = {n: pd.DataFrame(conn.execute(q).fetchall()) for n, q in
                  [("hourly_volume", HOURLY), ("component_level", COMPONENTS), ("block_summary", BLOCKS)]}
        # the dbt marts, when they exist, so Tableau and Power BI show the same numbers as the dashboard
        if conn.execute("SELECT to_regclass('analytics.mart_kpis') AS t").fetchone()["t"]:
            for n, q in MARTS:
                tables[n] = pd.DataFrame(conn.execute(q).fetchall()).astype({"window_id": "int64"} if n == "incident_windows" else {})
    for n, cols in {"anomaly_trend": ["hour_ts"], "incident_windows": ["start_ts", "end_ts"]}.items():
        for c in cols:
            if n in tables:
                tables[n][c] = pd.to_datetime(tables[n][c]).dt.tz_localize(None)
    for df in tables.values():  # Postgres numeric arrives as Decimal; BI tools want plain numbers
        for c in df.columns:
            if df[c].dtype == object and len(df) and df[c].map(lambda v: type(v).__name__ == "Decimal").all():
                df[c] = df[c].astype(float)
    tables["hourly_volume"]["hour"] = pd.to_datetime(tables["hourly_volume"]["hour"]).dt.tz_localize(None)
    tables["block_summary"]["first_ts"] = pd.to_datetime(tables["block_summary"]["first_ts"]).dt.tz_localize(None)
    tables["agent_incidents"] = agent_table()
    return tables


def build(out_dir: Path, tables: dict[str, pd.DataFrame] | None = None) -> dict:
    """Write argus.hyper and the Power BI package into out_dir; return what was produced."""
    from bi.hyper import write_hyper

    tables = tables or load_tables()
    profiles = [profile_table(n, d) for n, d in tables.items()]
    charts, fields = recommend_charts(profiles), recommend_fields(profiles)
    out_dir.mkdir(parents=True, exist_ok=True)
    hyper = write_hyper(out_dir / "argus.hyper", tables, profiles)
    pbi_zip = write_package(out_dir / "argus_powerbi", tables, profiles, charts, fields)
    (out_dir / "recommendations.json").write_text(json.dumps({"charts": charts, "calculated_fields": fields}, indent=1))
    return {"hyper": hyper, "powerbi_zip": pbi_zip, "tables": {p["name"]: p["rows"] for p in profiles},
            "charts": len(charts), "calculated_fields": len(fields)}


def bundle_zip(out_dir: Path) -> Path:
    """One zip with the extract, the Power BI package and the recommendations, for the dashboard's button."""
    z = out_dir / "argus_bi_export.zip"
    with zipfile.ZipFile(z, "w", zipfile.ZIP_DEFLATED) as f:
        for p in ["argus.hyper", "recommendations.json", "argus_powerbi.zip"]:
            f.write(out_dir / p, p)
    return z


if __name__ == "__main__":
    dest = ROOT / "exports"
    shutil.rmtree(dest / "argus_powerbi", ignore_errors=True)
    print(build(dest))
    print(bundle_zip(dest))
