"""Drift detection: compare a recent window of blocks against a reference window.

Two signals:
  * data drift: population stability index (PSI) per feature; > 0.25 is the usual "major shift" rule
  * performance drift: window F1 against the F1 measured when the model was promoted
"""
import argparse

import mlflow
import numpy as np
import pandas as pd
from sklearn.metrics import f1_score

PSI_ALERT = 0.25
F1_DROP_ALERT = 0.05


def psi(reference, current, bins: int = 10) -> float:
    ref = np.asarray(reference, dtype=float)
    cur = np.asarray(current, dtype=float)
    edges = np.unique(np.quantile(ref, np.linspace(0, 1, bins + 1)))
    if len(edges) < 3:  # constant or near-constant feature: nothing to compare
        return 0.0
    edges[0], edges[-1] = -np.inf, np.inf
    r = np.histogram(ref, edges)[0] / len(ref)
    c = np.histogram(cur, edges)[0] / len(cur)
    r, c = np.clip(r, 1e-4, None), np.clip(c, 1e-4, None)
    return float(np.sum((c - r) * np.log(c / r)))


# duration_s is right-censored: the HDFS capture has a fixed end, so blocks that start later look
# "shorter" no matter what the system does. Including it would alert on every window.
CENSORED = ("duration_s",)


def check_window(model, X_ref, X_cur, y_cur, baseline_f1: float, exclude=()) -> dict:
    psis = {col: psi(X_ref[col], X_cur[col]) for col in X_ref.columns if col not in exclude}
    worst = max(psis, key=psis.get)
    pred = (model.predict_proba(X_cur)[:, 1] >= 0.5).astype(int)
    f1 = float(f1_score(y_cur, pred, zero_division=0))
    drop = baseline_f1 - f1
    data_drift = psis[worst] > PSI_ALERT
    perf_drift = drop > F1_DROP_ALERT
    # data drift alone is an early warning; a measured F1 drop is what pages someone
    status = "alert" if perf_drift else "warning" if data_drift else "ok"
    return {
        "psi_max": psis[worst],
        "psi_worst_feature": worst,
        "window_f1": f1,
        "f1_drop": drop,
        "status": status,
        "alert": status == "alert",
    }


def shift_sample(X: pd.DataFrame) -> pd.DataFrame:
    """A deliberately shifted sample: a 'software upgrade' that triples logging volume
    and doubles the most frequent templates."""
    out = X.copy()
    out["n_events"] = out["n_events"] * 3
    for col in [c for c in out.columns if c.startswith("tpl_")][:5]:
        out[col] = out[col] * 2
    return out


def main() -> None:
    from ml.features import load_dataset
    from ml.promote import ALIAS, REGISTERED_NAME
    from ml.train import TRACKING_URI
    from api.db import connect

    ap = argparse.ArgumentParser()
    ap.add_argument("--windows", type=int, default=5)
    args = ap.parse_args()

    mlflow.set_tracking_uri(TRACKING_URI)
    model = mlflow.xgboost.load_model(f"models:/{REGISTERED_NAME}@{ALIAS}")
    prod = mlflow.MlflowClient(TRACKING_URI).get_model_version_by_alias(REGISTERED_NAME, ALIAS)
    baseline_f1 = mlflow.MlflowClient(TRACKING_URI).get_run(prod.run_id).data.metrics["test_f1"]

    X, y, _ = load_dataset()
    with connect() as conn:
        start = pd.Series({r["block_id"]: r["t"] for r in conn.execute(
            "SELECT block_id, min(ts) AS t FROM events WHERE block_id <> '' GROUP BY 1").fetchall()})
    order = start.loc[X.index].sort_values().index
    X, y = X.loc[order], y.loc[order]

    cut = int(len(X) * 0.4)
    X_ref = X.iloc[:cut]
    rest = np.array_split(np.arange(cut, len(X)), args.windows)

    mlflow.set_experiment("drift")
    with mlflow.start_run(run_name="drift-check"):
        mlflow.log_param("baseline_f1", round(baseline_f1, 4))
        for i, idx in enumerate(rest):
            r = check_window(model, X_ref, X.iloc[idx], y.iloc[idx], baseline_f1, exclude=CENSORED)
            mlflow.log_metrics({k: v for k, v in r.items() if isinstance(v, float)}, step=i)
            mlflow.log_metric("alert", float(r["alert"]), step=i)
            print(f"window {i}: psi_max={r['psi_max']:.3f} ({r['psi_worst_feature']}) f1={r['window_f1']:.4f} status={r['status']}")

        shifted = shift_sample(X.iloc[rest[-1]])
        r = check_window(model, X_ref, shifted, y.iloc[rest[-1]], baseline_f1, exclude=CENSORED)
        mlflow.log_metrics({f"shifted_{k}": v for k, v in r.items() if isinstance(v, float)})
        mlflow.log_metric("shifted_alert", float(r["alert"]))
        mlflow.set_tag("shifted_status", r["status"])
        print(f"shifted sample: psi_max={r['psi_max']:.3f} ({r['psi_worst_feature']}) f1={r['window_f1']:.4f} status={r['status']}")


if __name__ == "__main__":
    main()
