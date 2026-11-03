"""Read-only REST API over the parsed HDFS events."""
import asyncio
import json
import threading
import time
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from api.db import connect
from api.graphql_schema import router as graphql_router
from api.queries import query as _query

app = FastAPI(title="Argus API")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:3000"], allow_methods=["GET", "POST"])
app.include_router(graphql_router, prefix="/graphql")


class Summary(BaseModel):
    events: int
    blocks: int
    anomalous_blocks: int
    anomaly_rate_pct: float


class VolumePoint(BaseModel):
    bucket: str
    events: int


class Count(BaseModel):
    name: str
    events: int


@app.get("/health")
def health() -> dict:
    with connect() as conn:  # deliberately uncached: this must reflect the DB right now
        conn.execute("SELECT 1")
    return {"status": "ok"}


@app.get("/stats/summary", response_model=Summary)
def summary() -> Summary:
    events = _query("SELECT count(*) AS n FROM events")[0]["n"]
    row = _query(
        "SELECT count(*) AS blocks, count(*) FILTER (WHERE label = 'Anomaly') AS bad FROM block_labels"
    )[0]
    blocks, bad = row["blocks"], row["bad"]
    return Summary(
        events=events,
        blocks=blocks,
        anomalous_blocks=bad,
        anomaly_rate_pct=round(100 * bad / blocks, 2) if blocks else 0.0,
    )


@app.get("/stats/volume", response_model=list[VolumePoint])
def volume(bucket: Literal["hour", "day"] = "hour") -> list[VolumePoint]:
    # `bucket` is validated by the Literal above, so interpolating it is safe
    rows = _query(
        f"SELECT to_char(date_trunc('{bucket}', ts), 'YYYY-MM-DD\"T\"HH24:MI:SS') AS bucket, "
        "count(*) AS events FROM events GROUP BY 1 ORDER BY 1"
    )
    return [VolumePoint(**r) for r in rows]


@app.get("/stats/components", response_model=list[Count])
def components() -> list[Count]:
    rows = _query("SELECT component AS name, count(*) AS events FROM events GROUP BY 1 ORDER BY 2 DESC")
    return [Count(**r) for r in rows]


@app.get("/stats/levels", response_model=list[Count])
def levels() -> list[Count]:
    rows = _query("SELECT level AS name, count(*) AS events FROM events GROUP BY 1 ORDER BY 2 DESC")
    return [Count(**r) for r in rows]


# ---- model status (Phase 2) -------------------------------------------------

class ModelStatus(BaseModel):
    version: int
    run_id: str
    metrics: dict[str, float]
    cv_f1_mean: float | None
    baselines: dict[str, dict[str, float]]
    drift: list[dict]
    shifted_status: str | None


@app.get("/model/status", response_model=ModelStatus)
def model_status() -> ModelStatus:
    import mlflow

    from ml.baselines import BASELINES
    from ml.promote import ALIAS, REGISTERED_NAME
    from ml.train import TRACKING_URI

    client = mlflow.MlflowClient(TRACKING_URI)
    try:
        prod = client.get_model_version_by_alias(REGISTERED_NAME, ALIAS)
    except mlflow.exceptions.MlflowException:
        raise HTTPException(status_code=404, detail="no production model yet")
    run = client.get_run(prod.run_id)
    metrics = {k.removeprefix("test_"): v for k, v in run.data.metrics.items() if k.startswith("test_")}

    drift_points: list[dict] = []
    shifted = None
    exp = client.get_experiment_by_name("drift")
    if exp:
        runs = client.search_runs([exp.experiment_id], order_by=["start_time DESC"], max_results=1)
        if runs:
            shifted = runs[0].data.tags.get("shifted_status")
            hist = {n: client.get_metric_history(runs[0].info.run_id, n) for n in ("psi_max", "window_f1", "alert")}
            for psi_m, f1_m, alert_m in zip(hist["psi_max"], hist["window_f1"], hist["alert"]):
                drift_points.append({"window": psi_m.step, "psi_max": psi_m.value, "f1": f1_m.value, "alert": bool(alert_m.value)})

    return ModelStatus(
        version=int(prod.version),
        run_id=prod.run_id,
        metrics=metrics,
        cv_f1_mean=run.data.metrics.get("cv_f1_mean"),
        baselines=BASELINES,
        drift=drift_points,
        shifted_status=shifted,
    )


# ---- agent (Phase 3) --------------------------------------------------------

AGENT_DIR = Path(__file__).resolve().parent.parent / "agent"
_live_lock = asyncio.Lock()  # one live investigation at a time: the local model is the bottleneck


def _incidents() -> list[dict]:
    return json.loads((AGENT_DIR / "incidents.json").read_text())


def _recordings() -> dict:
    f = AGENT_DIR / "demo_runs.json"
    return json.loads(f.read_text()) if f.exists() else {}


class Investigate(BaseModel):
    block_id: str


@app.get("/agent/incidents")
def agent_incidents() -> list[dict]:
    recorded = _recordings()
    return [{**i, "recorded": i["block_id"] in recorded} for i in _incidents()]


@app.get("/agent/runs/{block_id}")
def agent_run(block_id: str) -> dict:
    run = _recordings().get(block_id)
    if not run:
        raise HTTPException(status_code=404, detail="no recorded run for this block")
    return run


@app.post("/agent/investigate")
async def agent_investigate(body: Investigate) -> dict:
    """Run the agent live. Slow (about a minute on a laptop) and serialised by a lock."""
    if body.block_id not in {i["block_id"] for i in _incidents()}:
        raise HTTPException(status_code=422, detail="demo mode only investigates the seeded incidents")
    if _live_lock.locked():
        raise HTTPException(status_code=409, detail="another investigation is running")
    from agent.graph import investigate

    async with _live_lock:
        return await investigate(body.block_id)


# ---- live replay (Phase 1) ---------------------------------------------------

class LiveBatch(BaseModel):
    batch: int
    events: int
    anomalous_events: int


class LiveStatus(BaseModel):
    events: int
    batches: int
    running: bool
    last_ingested_at: str | None
    recent: list[LiveBatch]


@app.get("/live/status", response_model=LiveStatus)
def live_status() -> LiveStatus:
    """State of the timed log replay. Never cached: it changes every second while running."""
    with connect() as conn:
        if not conn.execute("SELECT to_regclass('live_events') AS t").fetchone()["t"]:
            return LiveStatus(events=0, batches=0, running=False, last_ingested_at=None, recent=[])
        tot = conn.execute(
            "SELECT count(*) AS n, coalesce(max(batch), 0) AS b, max(ingested_at) AS last, "
            "coalesce(now() - max(ingested_at) < interval '10 seconds', false) AS running FROM live_events"
        ).fetchone()
        recent = conn.execute(
            """SELECT e.batch, count(*) AS events, count(*) FILTER (WHERE l.label = 'Anomaly') AS anomalous_events
               FROM live_events e LEFT JOIN block_labels l USING (block_id)
               WHERE e.batch > %s GROUP BY e.batch ORDER BY e.batch""",
            (max(tot["b"] - 30, 0),),
        ).fetchall()
    return LiveStatus(
        events=tot["n"], batches=tot["b"], running=bool(tot["running"]),
        last_ingested_at=tot["last"].isoformat() if tot["last"] else None,
        recent=[LiveBatch(**r) for r in recent],
    )


# ---- template clusters (Phase 1) ---------------------------------------------

class MergedCluster(BaseModel):
    cluster_id: int
    representative: str
    members: list[str]
    blocks: int


class Clusters(BaseModel):
    templates: int
    clusters: int
    merged: list[MergedCluster]


@app.get("/stats/clusters", response_model=Clusters)
def clusters() -> Clusters:
    rows = _query("SELECT template, cluster_id, representative, blocks FROM template_clusters ORDER BY cluster_id, blocks DESC")
    groups: dict[int, list[dict]] = {}
    for r in rows:
        groups.setdefault(r["cluster_id"], []).append(r)
    merged = [
        MergedCluster(cluster_id=cid, representative=g[0]["representative"], members=[m["template"] for m in g], blocks=max(m["blocks"] for m in g))
        for cid, g in groups.items() if len(g) > 1
    ]
    return Clusters(templates=len(rows), clusters=len(groups), merged=sorted(merged, key=lambda c: -c.blocks))


# ---- agent evals (Phase 4) ---------------------------------------------------

EVAL_DIR = Path(__file__).resolve().parent.parent / "eval"


def _read_json(path: Path, default):
    return json.loads(path.read_text()) if path.exists() else default


@app.get("/evals/summary")
def evals_summary() -> dict:
    """Latest agent eval, the history of runs (for the trend), the gate thresholds and per-incident results."""
    results = sorted((EVAL_DIR / "results").glob("*.json")) if (EVAL_DIR / "results").exists() else []
    latest_run = _read_json(results[-1], None) if results else None
    return {
        "latest": _read_json(EVAL_DIR / "latest.json", None),
        "history": _read_json(EVAL_DIR / "history.json", []),
        "thresholds": _read_json(EVAL_DIR / "thresholds.json", {}),
        "incidents": [
            {"block_id": i["block_id"], "expected_runbook": i["expected_runbook"], "split": i["split"], "error": i["error"],
             "seconds": i["seconds"], "scores": i["scores"], "judge": i.get("judge"),
             "chosen_runbook": (i.get("postmortem") or {}).get("runbook_id")}
            for i in (latest_run["incidents"] if latest_run else [])
        ],
        "phoenix_url": "http://localhost:6006",
    }


# ---- BI export (Phase 5) -----------------------------------------------------

EXPORT_DIR = Path(__file__).resolve().parent.parent / "exports"
EXPORT_FILES = {"argus.hyper", "argus_powerbi.zip", "argus_bi_export.zip", "recommendations.json"}
_export_lock = asyncio.Lock()


def _build_export() -> dict:
    from bi.build import build, bundle_zip

    out = build(EXPORT_DIR)
    bundle_zip(EXPORT_DIR)
    return {"tables": out["tables"], "charts": out["charts"], "calculated_fields": out["calculated_fields"]}


@app.post("/export/bi")
async def export_bi() -> dict:
    """Build the Tableau .hyper extract and the Power BI package from the current data (takes about a minute)."""
    if _export_lock.locked():
        raise HTTPException(status_code=409, detail="an export is already running")
    async with _export_lock:
        summary = await asyncio.to_thread(_build_export)
    return {**summary, **_export_listing()}


def _export_listing() -> dict:
    files = {f.name: f.stat().st_size for f in EXPORT_DIR.glob("*") if f.is_file() and f.name in EXPORT_FILES} if EXPORT_DIR.exists() else {}
    rec = _read_json(EXPORT_DIR / "recommendations.json", {"charts": [], "calculated_fields": []})
    return {"files": files, "recommendations": rec}


@app.get("/export/status")
def export_status() -> dict:
    return _export_listing()


@app.get("/export/files/{name}")
def export_file(name: str):
    from fastapi.responses import FileResponse

    if name not in EXPORT_FILES or not (EXPORT_DIR / name).is_file():
        raise HTTPException(status_code=404, detail="no such export file")
    return FileResponse(EXPORT_DIR / name, filename=name)


# ---- job runner for the orchestrator (Phase 5) -------------------------------

@app.post("/jobs/{name}")
def start_job(name: str) -> dict:
    from api import jobs

    try:
        return {"id": jobs.start(name), "name": name}
    except KeyError:
        raise HTTPException(status_code=404, detail=f"unknown job {name!r}; allowed: {sorted(jobs.ALLOWED)}")
    except jobs.AlreadyRunning:
        raise HTTPException(status_code=409, detail=f"{name} is already running")


@app.get("/jobs")
def list_jobs() -> list[dict]:
    from api import jobs

    return jobs.recent()


@app.get("/pipeline/status")
def pipeline_status() -> dict:
    from api import pipeline

    return pipeline.status()


@app.get("/jobs/{job_id}")
def job_status(job_id: str) -> dict:
    from api import jobs

    j = jobs.get(job_id)
    if not j:
        raise HTTPException(status_code=404, detail="no such job")
    return j


# ---- multi-tenant config (Phase 5) -------------------------------------------

@app.get("/tenant")
def tenant() -> dict:
    """Which client this deployment is, and how it groups HDFS components in its own vocabulary.

    Configured per Helm release: ARGUS_TENANT (name) and ARGUS_TAXONOMY_FILE (json {component: group})."""
    import os

    name = os.environ.get("ARGUS_TENANT", "default")
    path = os.environ.get("ARGUS_TAXONOMY_FILE")
    taxonomy = json.loads(Path(path).read_text()) if path and Path(path).exists() else {}
    grouped: dict[str, int] = {}
    if taxonomy:
        for r in _query("SELECT component AS name, count(*) AS events FROM events GROUP BY 1"):
            g = taxonomy.get(r["name"], "Other")
            grouped[g] = grouped.get(g, 0) + r["events"]
    return {
        "tenant": name,
        "taxonomy": taxonomy,
        "events_by_group": dict(sorted(grouped.items(), key=lambda kv: -kv[1])),
        "mcp": {"max_rows": int(os.environ.get("ARGUS_MAX_ROWS", "200")),
                "allowed_tools": [t for t in os.environ.get("ARGUS_ALLOWED_TOOLS", "").split(",") if t] or "all"},
    }


# ---- analytics layer (dbt marts) ---------------------------------------------

DBT_MODELS = Path(__file__).resolve().parent.parent / "dbt" / "argus" / "models"
SQL_VIEWABLE = {"mart_anomaly_trend": "marts", "mart_component_health": "marts", "mart_incident_windows": "marts",
                "mart_window_sensitivity": "marts", "mart_kpis": "marts", "fact_hourly_events": "marts", "dim_block": "marts",
                "int_block_sessions": "intermediate", "stg_events": "staging"}


def _plain(value):
    """Postgres numeric arrives as Decimal, which pydantic writes as a JSON string. Charts need real numbers."""
    from decimal import Decimal

    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, dict):
        return {k: _plain(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_plain(v) for v in value]
    return value


@app.get("/analytics/kpis")
def analytics_kpis() -> dict:
    """Headline KPIs from the mart_kpis model (definitions in docs/KPI_DICTIONARY.md)."""
    row = _plain(_query("SELECT * FROM analytics.mart_kpis")[0])
    return {**row, "worst_hour": row["worst_hour"].isoformat()}


@app.get("/analytics/trend")
def analytics_trend() -> list[dict]:
    rows = _plain(_query("SELECT * FROM analytics.mart_anomaly_trend ORDER BY hour_ts"))
    return [{**r, "hour_ts": r["hour_ts"].isoformat()} for r in rows]


@app.get("/analytics/components")
def analytics_components() -> list[dict]:
    return _plain(_query("SELECT * FROM analytics.mart_component_health ORDER BY anomaly_rank, component"))


@app.get("/analytics/windows")
def analytics_windows() -> dict:
    top = _plain(_query("SELECT * FROM analytics.mart_incident_windows ORDER BY anomalous_blocks DESC LIMIT 12"))
    return {
        "top": [{**r, "start_ts": r["start_ts"].isoformat(), "end_ts": r["end_ts"].isoformat()} for r in top],
        "sensitivity": _plain(_query("SELECT * FROM analytics.mart_window_sensitivity ORDER BY gap_seconds")),
    }


@app.get("/analytics/sql/{model}")
def analytics_sql(model: str) -> dict:
    """The SQL behind a model, so a reader can see how a number was produced."""
    if model not in SQL_VIEWABLE:
        raise HTTPException(status_code=404, detail=f"no viewable model {model!r}")
    path = DBT_MODELS / SQL_VIEWABLE[model] / f"{model}.sql"
    return {"model": model, "layer": SQL_VIEWABLE[model], "sql": path.read_text()}


# ---- business impact inputs ---------------------------------------------------

@app.get("/business/inputs")
def business_inputs() -> dict:
    """The measured numbers behind the Business impact page. The savings themselves are computed in the browser
    from assumptions the reader controls, because they are a model and not a measurement."""
    k = analytics_kpis()
    latest = _read_json(EVAL_DIR / "latest.json", None)
    demo = _read_json(Path(__file__).resolve().parent.parent / "agent" / "demo_runs.json", {})
    secs = [r["seconds"] for r in demo.values() if "seconds" in r]
    m = (latest or {}).get("metrics", {})
    return {
        "incident_windows": k["incident_windows"],
        "anomalous_blocks": k["anomalous_blocks"],
        "capture_hours": len(_query("SELECT 1 FROM analytics.mart_anomaly_trend")),
        "agent_seconds": m.get("mean_seconds") or (sum(secs) / len(secs) if secs else None),
        "runbook_accuracy": m.get("runbook_accuracy") or (1.0 if demo else None),
        "verified_rate": m.get("verified_rate") or (1.0 if demo else None),
        "from_eval": bool(latest),
    }


@app.get("/model/analysis")
def model_analysis() -> dict:
    """Confidence intervals, calibration, SHAP, baselines and error analysis (produced by `python -m ml.analysis`)."""
    path = Path(__file__).resolve().parent.parent / "ml" / "analysis_results.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail="run `uv run python -m ml.analysis` first")
    return json.loads(path.read_text())


# ---- model serving (Phase 5, MLE) ---------------------------------------------

class PredictRequest(BaseModel):
    block_id: str


@app.post("/predict")
def predict(req: PredictRequest) -> dict:
    """Score one block with the current `production` model and explain the three features that moved it most."""
    from api.serving import scorer

    if not req.block_id.startswith("blk_") or not req.block_id[4:].lstrip("-").isdigit():
        raise HTTPException(status_code=422, detail="block_id must look like blk_-123...")
    result = scorer().score(req.block_id)
    if result is None:
        raise HTTPException(status_code=404, detail="no events for this block")
    return result


# ---- bring your own logs (Phase 6) -------------------------------------------

UPLOAD_DIR = Path(__file__).resolve().parent.parent / "data" / "uploads"


def _jsonable(row: dict) -> dict:
    return {k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in row.items()}


def _run_ingest(upload_id: str, path: Path) -> None:
    from ingest import upload

    with connect() as conn:
        try:
            upload.ingest(conn, upload_id, path)
        finally:
            path.unlink(missing_ok=True)


@app.post("/uploads", status_code=202)
async def create_upload(file: UploadFile) -> dict:
    from ingest import upload

    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    name = Path(file.filename or "upload.log").name
    tmp = UPLOAD_DIR / f"incoming-{time.time_ns()}"
    size = 0
    with tmp.open("wb") as out:
        while chunk := await file.read(1 << 20):
            size += len(chunk)
            if size > upload.MAX_BYTES:
                out.close()
                tmp.unlink(missing_ok=True)
                raise HTTPException(413, f"file is over the {upload.MAX_BYTES // 2**20} MB limit")
            out.write(chunk)
    with connect() as conn:
        upload_id = upload.create(conn, name, size)
    path = UPLOAD_DIR / f"{upload_id}.log"
    tmp.rename(path)
    threading.Thread(target=_run_ingest, args=(upload_id, path), daemon=True).start()
    return {"id": upload_id, "filename": name, "status": "queued"}


@app.get("/uploads")
def list_uploads() -> list[dict]:
    from ingest import upload

    with connect() as conn:
        return [_jsonable(r) for r in upload.listing(conn)]


@app.get("/uploads/{upload_id}")
def get_upload(upload_id: str) -> dict:
    from ingest import upload

    try:
        with connect() as conn:
            row = upload.get(conn, upload_id) if upload.schema_of(upload_id) else None
    except ValueError:
        raise HTTPException(404, "no such upload")
    if not row:
        raise HTTPException(404, "no such upload")
    return _jsonable(row)


@app.get("/uploads/{upload_id}/summary")
def upload_summary(upload_id: str) -> dict:
    from ingest import upload

    try:
        with connect() as conn:
            row = upload.get(conn, upload_id) if upload.schema_of(upload_id) else None
            if not row:
                raise HTTPException(404, "no such upload")
            if row["status"] != "succeeded":
                raise HTTPException(409, f"upload is {row['status']}")
            return json.loads(json.dumps(upload.summary(conn, upload_id), default=lambda o: o.isoformat() if hasattr(o, "isoformat") else str(o)))
    except ValueError:
        raise HTTPException(404, "no such upload")


@app.get("/uploads/{upload_id}/search")
def upload_search(upload_id: str, q: str, limit: int = 50) -> list[dict]:
    from ingest import upload

    if not q.strip():
        raise HTTPException(422, "q is empty")
    try:
        with connect() as conn:
            if not upload.get(conn, upload_id):
                raise HTTPException(404, "no such upload")
            return [_jsonable(r) for r in upload.search(conn, upload_id, q, limit)]
    except ValueError:
        raise HTTPException(404, "no such upload")


@app.delete("/uploads/{upload_id}")
def delete_upload(upload_id: str) -> dict:
    from ingest import upload

    try:
        with connect() as conn:
            if not upload.delete(conn, upload_id):
                raise HTTPException(404, "no such upload")
    except ValueError:
        raise HTTPException(404, "no such upload")
    return {"deleted": upload_id}
