"""Statistical analysis of the production classifier: how sure are we, is it calibrated, why does it say what it says,
where does it fail, and is it really better than simple alternatives?"""
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import brier_score_loss, f1_score, precision_score, recall_score

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "ml" / "analysis_results.json"


def bootstrap_ci(y, pred, metric, n_boot: int = 500, alpha: float = 0.05, seed: int = 0) -> tuple[float, float]:
    """Percentile bootstrap interval for a metric: resample rows with replacement and recompute it."""
    y, pred = np.asarray(y), np.asarray(pred)
    rng = np.random.default_rng(seed)
    vals = []
    for _ in range(n_boot):
        idx = rng.integers(0, len(y), len(y))
        vals.append(metric(y[idx], pred[idx]))
    return float(np.quantile(vals, alpha / 2)), float(np.quantile(vals, 1 - alpha / 2))


def paired_bootstrap_diff(y, pred_a, pred_b, metric, n_boot: int = 500, alpha: float = 0.05, seed: int = 0) -> dict:
    """metric(A) - metric(B) on the *same* resamples, so a difference is not mistaken for noise (or the reverse)."""
    y, a, b = np.asarray(y), np.asarray(pred_a), np.asarray(pred_b)
    rng = np.random.default_rng(seed)
    diffs = []
    for _ in range(n_boot):
        idx = rng.integers(0, len(y), len(y))
        diffs.append(metric(y[idx], a[idx]) - metric(y[idx], b[idx]))
    lo, hi = float(np.quantile(diffs, alpha / 2)), float(np.quantile(diffs, 1 - alpha / 2))
    return {"mean_diff": float(np.mean(diffs)), "lo": lo, "hi": hi, "significant": bool(lo > 0 or hi < 0)}


def calibration(y, proba, bins: int = 10) -> dict:
    """Reliability: in each score bin, does the share of true positives match the score? Also Brier score and ECE."""
    y, proba = np.asarray(y), np.asarray(proba)
    edges = np.linspace(0, 1, bins + 1)
    which = np.clip(np.digitize(proba, edges[1:-1]), 0, bins - 1)
    out, ece = [], 0.0
    for b in range(bins):
        m = which == b
        if not m.any():
            continue
        mean_p, frac = float(proba[m].mean()), float(y[m].mean())
        out.append({"mean_pred": mean_p, "frac_pos": frac, "n": int(m.sum())})
        ece += m.mean() * abs(mean_p - frac)
    return {"bins": out, "brier": float(brier_score_loss(y, proba)), "ece": float(ece)}


def shap_values(model, X: pd.DataFrame):
    """Exact TreeSHAP from XGBoost itself. Returns (contributions [rows x features], bias). Row sums plus bias equal the
    raw model output, which the tests check."""
    import xgboost as xgb

    contribs = model.get_booster().predict(xgb.DMatrix(X), pred_contribs=True)
    return contribs[:, :-1], float(contribs[0, -1])


def error_analysis(model, X, y, proba, names: dict, k: int = 8) -> dict:
    """The model's mistakes, each with the three features that pushed it most."""
    y = np.asarray(y)
    pred = (np.asarray(proba) >= 0.5).astype(int)
    contrib, _ = shap_values(model, X)
    cols = list(X.columns)

    def describe(i: int) -> dict:
        top = np.argsort(-np.abs(contrib[i]))[:3]
        return {"block_id": str(X.index[i]), "actual": int(y[i]), "proba": round(float(proba[i]), 4),
                "top_features": [{"feature": cols[j], "name": names.get(cols[j], cols[j]), "value": float(X.iloc[i, j]),
                                  "shap": round(float(contrib[i, j]), 3)} for j in top]}

    fp = [i for i in np.where((pred == 1) & (y == 0))[0]]
    fn = [i for i in np.where((pred == 0) & (y == 1))[0]]
    fp.sort(key=lambda i: -proba[i])
    fn.sort(key=lambda i: proba[i])
    return {"n_false_positive": len(fp), "n_false_negative": len(fn),
            "false_positives": [describe(i) for i in fp[:k]], "false_negatives": [describe(i) for i in fn[:k]]}


def _metrics(y, pred) -> dict:
    return {"f1": float(f1_score(y, pred)), "precision": float(precision_score(y, pred, zero_division=0)),
            "recall": float(recall_score(y, pred))}


def main() -> None:
    import mlflow
    from sklearn.linear_model import LogisticRegression

    from ml.features import load_dataset
    from ml.promote import ALIAS, REGISTERED_NAME
    from ml.train import TRACKING_URI, split

    mlflow.set_tracking_uri(TRACKING_URI)
    model = mlflow.xgboost.load_model(f"models:/{REGISTERED_NAME}@{ALIAS}")
    X, y, templates = load_dataset()
    Xtr, Xte, ytr, yte = split(X, y)
    names = {f"tpl_{i}": t for i, t in enumerate(templates)}
    proba = model.predict_proba(Xte)[:, 1]
    pred = (proba >= 0.5).astype(int)

    # honest baselines: always "normal", a rarity rule with no labels, and logistic regression
    train_share = (Xtr[[c for c in X.columns if c.startswith("tpl_")]] > 0).mean()
    rare_cols = list(train_share[train_share < 0.05].index)
    rule = (Xte[rare_cols] > 0).any(axis=1).astype(int).to_numpy()
    lr = LogisticRegression(max_iter=300, class_weight="balanced").fit(np.log1p(Xtr), ytr)
    lr_pred = lr.predict(np.log1p(Xte))
    always_normal = np.zeros(len(yte), dtype=int)

    candidates = {"always normal": always_normal, "rarity rule (no labels)": rule, "logistic regression": lr_pred}
    comparison = []
    for name, p in candidates.items():
        diff = paired_bootstrap_diff(yte, pred, p, f1_score)
        comparison.append({"model": name, **_metrics(yte, p), "xgboost_minus_this_f1": diff})

    contrib, _ = shap_values(model, Xte.sample(5000, random_state=0))
    imp = np.abs(contrib).mean(axis=0)
    shap_top = [{"feature": c, "name": names.get(c, c), "mean_abs_shap": round(float(v), 4)}
                for c, v in sorted(zip(X.columns, imp), key=lambda t: -t[1])[:12]]

    result = {
        "n_test": int(len(yte)), "n_positive": int(yte.sum()),
        "xgboost": _metrics(yte, pred),
        "confidence_intervals_95": {m: bootstrap_ci(yte, pred, fn) for m, fn in
                                    [("f1", f1_score), ("precision", lambda a, b: precision_score(a, b, zero_division=0)), ("recall", recall_score)]},
        "calibration": calibration(yte, proba),
        "baselines": comparison,
        "shap_top": shap_top,
        "errors": error_analysis(model, Xte, yte, proba, names),
    }
    RESULTS.write_text(json.dumps(result, indent=1))
    mlflow.set_experiment("model-analysis")
    with mlflow.start_run(run_name="analysis"):
        mlflow.log_metrics({"ece": result["calibration"]["ece"], "brier": result["calibration"]["brier"],
                            "f1_ci_lo": result["confidence_intervals_95"]["f1"][0], "f1_ci_hi": result["confidence_intervals_95"]["f1"][1]})
        mlflow.log_artifact(str(RESULTS))
    print(json.dumps({k: result[k] for k in ("xgboost", "confidence_intervals_95")}, indent=1))
    print("ece", round(result["calibration"]["ece"], 4), "| errors:", result["errors"]["n_false_positive"], "FP,", result["errors"]["n_false_negative"], "FN")


if __name__ == "__main__":
    main()
