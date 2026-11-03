"""Measure /predict latency: warm requests through the full stack (HTTP handler, SQL feature build, model, SHAP)."""
import statistics
import time

import numpy as np
from fastapi.testclient import TestClient

from api.db import connect
from api.main import app


def main(n: int = 300) -> dict:
    with connect() as c:
        ids = [r["block_id"] for r in c.execute("SELECT block_id FROM block_labels ORDER BY md5(block_id) LIMIT %s", (n,)).fetchall()]
    client = TestClient(app)
    client.post("/predict", json={"block_id": ids[0]})  # load the model once
    ms = []
    for b in ids:
        t = time.perf_counter()
        r = client.post("/predict", json={"block_id": b})
        ms.append((time.perf_counter() - t) * 1000)
        assert r.status_code == 200
    out = {"requests": n, "p50_ms": round(float(np.percentile(ms, 50)), 1), "p95_ms": round(float(np.percentile(ms, 95)), 1),
           "p99_ms": round(float(np.percentile(ms, 99)), 1), "mean_ms": round(statistics.mean(ms), 1),
           "throughput_rps": round(n / (sum(ms) / 1000), 1)}
    print(out)
    return out


if __name__ == "__main__":
    main()
