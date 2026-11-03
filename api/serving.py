"""Online scoring: build one block's features from Postgres and score it with the production model.

The feature order, template list and threshold come from the same MLflow run that produced the model, so the
serving path cannot drift from training. tests/test_serving.py checks that against the offline pipeline."""
import json
import threading
import time

import numpy as np
import pandas as pd

from api.db import connect

THRESHOLD = 0.5
REFRESH_SECONDS = 60  # how often to check whether `production` points at a newer version


class Scorer:
    def __init__(self):
        self.lock = threading.Lock()
        self.checked = 0.0
        self.version = None

    def _load(self):
        import mlflow
        import mlflow.xgboost

        from ml.promote import ALIAS, REGISTERED_NAME
        from ml.train import TRACKING_URI

        client = mlflow.MlflowClient(TRACKING_URI)
        mv = client.get_model_version_by_alias(REGISTERED_NAME, ALIAS)
        if mv.version == self.version:
            return
        mlflow.set_tracking_uri(TRACKING_URI)
        model = mlflow.xgboost.load_model(f"models:/{REGISTERED_NAME}@{ALIAS}")
        path = client.download_artifacts(mv.run_id, "templates.json")
        templates = json.load(open(path))  # {"tpl_0": "...", ...}
        self.model, self.version, self.run_id = model, mv.version, mv.run_id
        self.feature_names = list(model.get_booster().feature_names)
        self.templates = [templates[f"tpl_{i}"] for i in range(len(templates))]
        self.index = {t: f"tpl_{i}" for i, t in enumerate(self.templates)}

    def ensure_loaded(self):
        with self.lock:
            if time.time() - self.checked > REFRESH_SECONDS or self.version is None:
                self._load()
                self.checked = time.time()

    def features(self, block_id: str) -> pd.DataFrame | None:
        with connect() as conn:
            counts = conn.execute("SELECT template, count(*)::int AS n FROM events WHERE block_id = %s GROUP BY 1", (block_id,)).fetchall()
            stats = conn.execute(
                """SELECT count(*)::int AS n_events, extract(epoch FROM max(ts) - min(ts))::float8 AS duration_s,
                          (count(*) FILTER (WHERE level = 'WARN'))::int AS n_warn FROM events WHERE block_id = %s""", (block_id,)).fetchone()
        if not counts:
            return None
        row = {name: 0 for name in self.feature_names}
        for c in counts:
            col = self.index.get(c["template"])
            if col:
                row[col] = c["n"]
        row.update(n_events=stats["n_events"], duration_s=stats["duration_s"], n_warn=stats["n_warn"])
        return pd.DataFrame([row], columns=self.feature_names, index=[block_id])

    def score(self, block_id: str) -> dict | None:
        started = time.perf_counter()
        self.ensure_loaded()
        X = self.features(block_id)
        if X is None:
            return None
        import xgboost as xgb

        proba = float(self.model.predict_proba(X)[0, 1])
        contrib = self.model.get_booster().predict(xgb.DMatrix(X), pred_contribs=True)[0][:-1]
        top = np.argsort(-np.abs(contrib))[:3]
        names = {f"tpl_{i}": t for i, t in enumerate(self.templates)}
        return {
            "block_id": block_id, "probability": proba, "is_anomaly": proba >= THRESHOLD, "threshold": THRESHOLD,
            "model_version": int(self.version),
            "top_features": [{"name": names.get(self.feature_names[j], self.feature_names[j]), "value": float(X.iloc[0, j]), "shap": round(float(contrib[j]), 3)} for j in top],
            "latency_ms": round((time.perf_counter() - started) * 1000, 1),
        }


_scorer = Scorer()


def scorer() -> Scorer:
    _scorer.ensure_loaded()
    return _scorer
