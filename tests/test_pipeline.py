"""Phase 5/6: the pipeline status view reports what is up and what is down without hanging or raising."""
import time

from fastapi.testclient import TestClient

from api import jobs, pipeline
from api.main import app

client = TestClient(app)


def test_a_failing_check_is_reported_down_not_raised():
    def boom():
        raise ConnectionError("start it with docker compose up")

    r = pipeline._run(("Store", "Thing", boom))
    assert r == {"stage": "Store", "name": "Thing", "status": "down", "detail": "start it with docker compose up"}
    assert pipeline._run(("Store", "Ok", lambda: {"detail": "fine"}))["status"] == "up"


def test_closed_ports_are_down_quickly():
    t = time.time()
    assert pipeline._tcp("localhost", 1) is False and pipeline._http("http://localhost:1/") is False
    assert time.time() - t < 3


def test_status_endpoint_lists_every_service_with_a_stage():
    d = client.get("/pipeline/status").json()
    assert d["total"] == len(pipeline.CHECKS) == len(d["services"])
    assert {s["stage"] for s in d["services"]} >= {"Store", "Stream", "Orchestrate", "Model", "Agent", "Observe", "Evaluate"}
    assert all(s["status"] in ("up", "down") and s["detail"] for s in d["services"])
    assert next(s for s in d["services"] if s["name"] == "Last eval run")["status"] == "up"


def test_recent_jobs_hide_logs_and_come_newest_first():
    jobs._jobs.clear()
    jobs._jobs["a"] = {"id": "a", "name": "retrain", "status": "succeeded", "started": 1.0, "log": "secret-ish output"}
    jobs._jobs["b"] = {"id": "b", "name": "eval", "status": "running", "started": 2.0, "log": ""}
    out = client.get("/jobs").json()
    assert [j["id"] for j in out] == ["b", "a"] and all("log" not in j for j in out)
    jobs._jobs.clear()
