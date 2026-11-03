"""Promotion gate: a run becomes the `production` model only if it does not regress."""
import argparse

import mlflow

from ml.train import TRACKING_URI

REGISTERED_NAME = "argus-block-classifier"
ALIAS = "production"
TOLERANCE = 0.002  # allowed drop in F1 / recall versus the current production model
GATED = ("test_f1", "test_recall")


def decide(candidate: dict, current: dict | None, tol: float = TOLERANCE) -> tuple[bool, str]:
    if current is None:
        return True, "no production model yet"
    for key in GATED:
        if candidate[key] < current[key] - tol:
            name = key.removeprefix("test_")
            return False, f"{name} regressed: {candidate[key]:.4f} < {current[key]:.4f} (tolerance {tol})"
    return True, "no regression versus production"


def promote(run_id: str, tracking_uri: str = TRACKING_URI) -> int:
    """Register the run's model and move the `production` alias to it. Exits 1 on regression."""
    mlflow.set_tracking_uri(tracking_uri)
    client = mlflow.MlflowClient(tracking_uri)
    candidate = client.get_run(run_id).data.metrics

    try:
        prod_version = client.get_model_version_by_alias(REGISTERED_NAME, ALIAS)
        current = client.get_run(prod_version.run_id).data.metrics
    except mlflow.exceptions.MlflowException:
        current = None

    ok, reason = decide(candidate, current)
    if not ok:
        raise SystemExit(f"promotion blocked: {reason}")

    version = mlflow.register_model(f"runs:/{run_id}/model", REGISTERED_NAME)
    client.set_registered_model_alias(REGISTERED_NAME, ALIAS, version.version)
    print(f"promoted version {version.version} to '{ALIAS}': {reason}")
    return int(version.version)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", required=True)
    promote(ap.parse_args().run_id)
