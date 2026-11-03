"""One view of every moving part: which services are reachable and what each one last did.

Each check has a short timeout and never raises, so a stopped service shows as `down` instead of hanging the page.
"""
import json
import os
import socket
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TIMEOUT = 1.0


def _tcp(host: str, port: int) -> bool:
    with socket.socket() as s:
        s.settimeout(TIMEOUT)
        return s.connect_ex((host, port)) == 0


def _http(url: str) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=TIMEOUT) as r:
            return r.status < 500
    except Exception:  # noqa: BLE001 - any failure means "not reachable"
        return False


def _postgres() -> dict:
    from api.db import connect

    with connect() as c:
        events = c.execute("SELECT count(*) AS n FROM events").fetchone()["n"]
        live = c.execute("SELECT to_regclass('live_events') AS t").fetchone()["t"]
        live_n = c.execute("SELECT count(*) AS n FROM live_events").fetchone()["n"] if live else 0
        up = c.execute("SELECT to_regclass('uploads') AS t").fetchone()["t"]
        up_n = c.execute("SELECT count(*) AS n FROM uploads").fetchone()["n"] if up else 0
    return {"detail": f"{events:,} events, {live_n:,} live events, {up_n} uploads"}


def _qdrant() -> dict:
    with urllib.request.urlopen("http://localhost:6333/collections/runbooks", timeout=TIMEOUT) as r:
        n = json.load(r)["result"]["points_count"]
    return {"detail": f"{n} runbook chunks indexed"}


def _model() -> dict:
    from api.main import model_status

    m = model_status()
    return {"detail": f"production v{m.version}, F1 {m.metrics.get('f1', 0):.3f}, drift {m.shifted_status or 'n/a'}"}


def _eval() -> dict:
    f = ROOT / "eval" / "latest.json"
    if not f.exists():
        raise FileNotFoundError("no eval run yet")
    d = json.loads(f.read_text())
    m = d["metrics"]
    return {"detail": f"{d['label']} on {d['at'][:10]}: {m['runbook_accuracy']:.0%} right runbook over {m['n_incidents']} incidents"}


def _probe(check, ok_detail: str, down_detail: str):
    """A health check from a yes/no probe: healthy returns the detail, otherwise it raises with a hint on how to start it."""
    def run() -> dict:
        if not check():
            raise ConnectionError(down_detail)
        return {"detail": ok_detail}

    return run


# (stage, name, check). A check returns {"detail"} when healthy and raises when not.
CHECKS = [
    ("Store", "Postgres", _postgres),
    ("Store", "Qdrant", _qdrant),
    ("Stream", "Kafka broker", _probe(lambda: _tcp("localhost", 9092), "broker accepting connections on :9092",
                                       "start with: docker compose --profile streaming up -d kafka")),
    ("Orchestrate", "Airflow", _probe(lambda: _http(os.environ.get("AIRFLOW_URL", "http://localhost:8080/health")),
                                       "scheduler healthy, DAGs: argus_retrain, argus_nightly_eval",
                                       "start with: docker compose --profile orchestration up -d airflow")),
    ("Model", "MLflow registry", _model),
    ("Agent", "Ollama (local LLM)", _probe(lambda: _http("http://localhost:11434/api/tags"), "serving local models",
                                            "start with: OLLAMA_MAX_LOADED_MODELS=1 ollama serve")),
    ("Observe", "Arize Phoenix", _probe(lambda: _http("http://localhost:6006"), "collecting agent traces on :6006",
                                         "start with: docker compose --profile obs up -d phoenix")),
    ("Evaluate", "Last eval run", _eval),
]


def _run(item) -> dict:
    stage, name, check = item
    try:
        return {"stage": stage, "name": name, "status": "up", **check()}
    except Exception as e:  # noqa: BLE001
        return {"stage": stage, "name": name, "status": "down", "detail": str(e)[:160] or type(e).__name__}


def status() -> dict:
    with ThreadPoolExecutor(max_workers=len(CHECKS)) as pool:
        services = list(pool.map(_run, CHECKS))
    return {"services": services, "up": sum(s["status"] == "up" for s in services), "total": len(services)}
