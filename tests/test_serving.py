"""MLOps: the serving path must score a block exactly like the training pipeline would (no train/serve skew)."""
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from tests.data import needs_full_data

pytestmark = needs_full_data
ROOT = Path(__file__).resolve().parent.parent
SAMPLE = ROOT / "ml" / "fixtures" / "features_sample.parquet"
INC = json.loads((ROOT / "agent" / "incidents.json").read_text())


@pytest.fixture(scope="module")
def client():
    from api.main import app

    return TestClient(app)


def test_train_serve_parity_on_blocks_the_offline_pipeline_scored(client):
    """The offline feature matrix and the serving feature builder are different code. They must agree."""
    from api.serving import scorer

    df = pd.read_parquet(SAMPLE)
    rows = pd.concat([df[df["label"] == 1].sample(15, random_state=1), df[df["label"] == 0].sample(15, random_state=1)])
    m = scorer()
    offline = m.model.predict_proba(rows.drop(columns="label")[m.feature_names])[:, 1]
    online = np.array([client.post("/predict", json={"block_id": b}).json()["probability"] for b in rows.index])
    assert np.allclose(offline, online, atol=1e-5), np.abs(offline - online).max()


def test_anomalous_incident_is_flagged_with_an_explanation(client):
    r = client.post("/predict", json={"block_id": INC[0]["block_id"]}).json()
    assert r["is_anomaly"] and r["probability"] > 0.9
    assert r["model_version"] >= 1 and 0 < len(r["top_features"]) <= 3
    assert all({"name", "value", "shap"} <= set(f) for f in r["top_features"])


def test_a_normal_block_is_not_flagged(client):
    from api.db import connect

    with connect() as c:
        normal = c.execute("SELECT block_id FROM block_labels WHERE label = 'Normal' ORDER BY md5(block_id) LIMIT 1").fetchone()["block_id"]
    r = client.post("/predict", json={"block_id": normal}).json()
    assert not r["is_anomaly"] and r["probability"] < 0.5


def test_bad_input_and_unknown_blocks_are_rejected(client):
    assert client.post("/predict", json={"block_id": "'; drop table events; --"}).status_code == 422
    assert client.post("/predict", json={"block_id": "blk_0000000000000000001"}).status_code == 404


def test_warm_latency_is_interactive(client):
    client.post("/predict", json={"block_id": INC[0]["block_id"]})  # warm the model
    times = []
    for inc in INC * 3:
        t = time.perf_counter()
        assert client.post("/predict", json={"block_id": inc["block_id"]}).status_code == 200
        times.append((time.perf_counter() - t) * 1000)
    assert np.percentile(times, 95) < 250, f"p95 {np.percentile(times, 95):.0f} ms"
