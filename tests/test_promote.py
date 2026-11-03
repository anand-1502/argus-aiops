"""Phase 2: a model can only become `production` if it does not regress."""
import mlflow
import mlflow.sklearn
import pytest
from sklearn.dummy import DummyClassifier

from ml.promote import REGISTERED_NAME, decide, promote


def test_first_model_is_always_promoted():
    ok, _ = decide({"test_f1": 0.5, "test_recall": 0.5}, None)
    assert ok


def test_regression_in_f1_is_blocked():
    ok, reason = decide({"test_f1": 0.90, "test_recall": 0.99}, {"test_f1": 0.99, "test_recall": 0.99})
    assert not ok and "f1" in reason


def test_regression_in_recall_is_blocked():
    ok, reason = decide({"test_f1": 0.99, "test_recall": 0.90}, {"test_f1": 0.99, "test_recall": 0.99})
    assert not ok and "recall" in reason


def test_tiny_noise_within_tolerance_is_allowed():
    ok, _ = decide({"test_f1": 0.9895, "test_recall": 0.9895}, {"test_f1": 0.99, "test_recall": 0.99})
    assert ok


@pytest.fixture
def store(tmp_path):
    uri = f"sqlite:///{tmp_path / 'mlflow.db'}"
    mlflow.set_tracking_uri(uri)
    mlflow.set_experiment("promote-test")
    return uri


def _run(f1, recall):
    with mlflow.start_run() as r:
        mlflow.log_metrics({"test_f1": f1, "test_recall": recall})
        mlflow.sklearn.log_model(DummyClassifier().fit([[0], [1]], [0, 1]), name="model")
        return r.info.run_id


def test_promotion_flow_blocks_regression_and_allows_improvement(store):
    client = mlflow.MlflowClient(store)
    first = _run(0.95, 0.95)
    assert promote(first, tracking_uri=store) == 1
    assert int(client.get_model_version_by_alias(REGISTERED_NAME, "production").version) == 1

    with pytest.raises(SystemExit):
        promote(_run(0.80, 0.80), tracking_uri=store)
    assert int(client.get_model_version_by_alias(REGISTERED_NAME, "production").version) == 1

    assert promote(_run(0.97, 0.97), tracking_uri=store) == 2  # the blocked run was never registered
    assert int(client.get_model_version_by_alias(REGISTERED_NAME, "production").version) == 2
