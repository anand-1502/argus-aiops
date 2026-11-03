"""Phase 1 done-checks: the API serves the full HDFS benchmark numbers."""
import socket

import pytest
from fastapi.testclient import TestClient

from api.main import app


def _loaded() -> bool:
    with socket.socket() as s:
        s.settimeout(1)
        if s.connect_ex(("localhost", 5433)) != 0:
            return False
    try:
        from api.db import connect

        with connect() as c:
            return c.execute("SELECT count(*) AS n FROM events").fetchone()["n"] > 1_000_000
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _loaded(), reason="full HDFS load not present")
client = TestClient(app)


def test_health():
    assert client.get("/health").json() == {"status": "ok"}


def test_summary_matches_published_benchmark():
    s = client.get("/stats/summary").json()
    assert s == {"events": 11_175_629, "blocks": 575_061, "anomalous_blocks": 16_838, "anomaly_rate_pct": 2.93}


def test_volume_sums_to_total_events():
    pts = client.get("/stats/volume", params={"bucket": "hour"}).json()
    assert pts and sum(p["events"] for p in pts) == 11_175_629
    assert pts == sorted(pts, key=lambda p: p["bucket"])


def test_volume_rejects_unknown_bucket():
    assert client.get("/stats/volume", params={"bucket": "year; drop table events"}).status_code == 422


def test_components_and_levels():
    comps = client.get("/stats/components").json()
    assert sum(c["events"] for c in comps) == 11_175_629
    assert {c["name"] for c in comps} >= {"dfs.DataNode$DataXceiver", "dfs.FSNamesystem"}
    levels = {l["name"] for l in client.get("/stats/levels").json()}
    assert levels == {"INFO", "WARN"}  # HDFS_v1 has no ERROR-level lines


def test_model_status_reports_production_model_and_baselines():
    r = client.get("/model/status")
    assert r.status_code == 200
    m = r.json()
    assert m["metrics"]["f1"] > 0.98 and m["metrics"]["recall"] > 0.99
    assert m["cv_f1_mean"] > 0.98
    assert "LogRobust (supervised)" in m["baselines"]
    assert len(m["drift"]) == 5 and m["shifted_status"] == "alert"


def test_agent_incidents_lists_the_six_seeded_incidents():
    rows = client.get("/agent/incidents").json()
    assert [r["expected_runbook"] for r in rows] == [f"RB-00{i}" for i in range(1, 7)]
    assert all(r["block_id"].startswith("blk_") and r["signature_line"] for r in rows)


def test_unknown_block_has_no_recording_and_cannot_be_investigated():
    assert client.get("/agent/runs/blk_nope").status_code == 404
    assert client.post("/agent/investigate", json={"block_id": "blk_1"}).status_code == 422


def test_live_status_reflects_a_replay_and_resets_cleanly():
    from pathlib import Path

    from api.db import connect
    from ingest.replay import ensure_table, replay

    log = Path(__file__).parent / "fixtures" / "hdfs_sample.log"
    with connect() as conn:
        ensure_table(conn)
        conn.execute("TRUNCATE live_events")
        conn.commit()
        try:
            replay(log, conn, batch_size=2, interval=0, sleep=lambda s: None)
            s = client.get("/live/status").json()
            assert (s["events"], s["batches"], s["running"]) == (4, 2, True)
            assert [b["events"] for b in s["recent"]] == [2, 2]
            assert s["last_ingested_at"]
        finally:
            conn.execute("TRUNCATE live_events")
            conn.commit()
    empty = client.get("/live/status").json()
    assert empty["events"] == 0 and empty["running"] is False and empty["recent"] == []


def test_template_clusters_report_what_merged():
    c = client.get("/stats/clusters").json()
    assert c["templates"] == 54 and 0 < c["clusters"] < 54
    assert c["merged"] and all(len(m["members"]) > 1 for m in c["merged"])
    assert c["clusters"] == c["templates"] - sum(len(m["members"]) - 1 for m in c["merged"])


def test_evals_summary_has_the_documented_shape():
    r = client.get("/evals/summary")
    assert r.status_code == 200
    d = r.json()
    assert set(d) == {"latest", "history", "thresholds", "incidents", "phoenix_url"}
    assert d["thresholds"]["agent"]["runbook_accuracy"] > 0


def test_model_analysis_reports_intervals_baselines_and_errors():
    a = client.get("/model/analysis").json()
    lo, hi = a["confidence_intervals_95"]["f1"]
    assert lo <= a["xgboost"]["f1"] <= hi and hi - lo < 0.02
    assert {b["model"] for b in a["baselines"]} == {"always normal", "rarity rule (no labels)", "logistic regression"}
    assert all(b["xgboost_minus_this_f1"]["significant"] for b in a["baselines"])
    assert a["calibration"]["ece"] < 0.01
    assert a["errors"]["n_false_positive"] == len(a["errors"]["false_positives"]) or a["errors"]["n_false_positive"] > 8
