"""Train and evaluate the XGBoost block-anomaly classifier, tracked in MLflow."""
import argparse
import json
import tempfile
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import mlflow  # noqa: E402
import mlflow.xgboost  # noqa: E402
import pandas as pd  # noqa: E402
from sklearn.metrics import average_precision_score, confusion_matrix, precision_recall_fscore_support  # noqa: E402
from sklearn.model_selection import StratifiedKFold, train_test_split  # noqa: E402
from xgboost import XGBClassifier  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
TRACKING_URI = f"sqlite:///{ROOT / 'mlflow.db'}"
EXPERIMENT = "hdfs-block-anomaly"

DEFAULT_PARAMS = {"n_estimators": 300, "max_depth": 6, "learning_rate": 0.1, "subsample": 0.8, "colsample_bytree": 0.8}


def split(X, y, test_size=0.2, seed=42):
    """Stratified split by block. Each row is one block, so no block appears on both sides."""
    return train_test_split(X, y, test_size=test_size, stratify=y, random_state=seed)


def _model(y_train, params):
    pos = max(int(y_train.sum()), 1)
    return XGBClassifier(
        **params,
        scale_pos_weight=(len(y_train) - pos) / pos,
        eval_metric="aucpr",
        tree_method="hist",
        n_jobs=2,
        random_state=42,
    )


def evaluate(X_train, y_train, X_test, y_test, params=None):
    model = _model(y_train, params or DEFAULT_PARAMS).fit(X_train, y_train)
    return _metrics(model, X_test, y_test)


def _metrics(model, X, y):
    proba = model.predict_proba(X)[:, 1]
    pred = (proba >= 0.5).astype(int)
    p, r, f1, _ = precision_recall_fscore_support(y, pred, average="binary", zero_division=0)
    tn, fp, fn, tp = confusion_matrix(y, pred, labels=[0, 1]).ravel()
    return {
        "precision": float(p), "recall": float(r), "f1": float(f1),
        "pr_auc": float(average_precision_score(y, proba)),
        "tp": int(tp), "fp": int(fp), "fn": int(fn), "tn": int(tn),
    }


def cross_validate(X, y, params, folds=5, seed=42):
    scores = []
    for tr, te in StratifiedKFold(folds, shuffle=True, random_state=seed).split(X, y):
        scores.append(evaluate(X.iloc[tr], y.iloc[tr], X.iloc[te], y.iloc[te], params)["f1"])
    return scores


def main() -> None:
    from ml.features import load_dataset

    ap = argparse.ArgumentParser()
    ap.add_argument("--folds", type=int, default=5)
    ap.add_argument("--promote", action="store_true", help="run the promotion gate after training")
    args = ap.parse_args()

    X, y, templates = load_dataset()
    print(f"{len(X)} blocks, {int(y.sum())} anomalous, {X.shape[1]} features")
    X_train, X_test, y_train, y_test = split(X, y)

    mlflow.set_tracking_uri(TRACKING_URI)
    mlflow.set_experiment(EXPERIMENT)
    with mlflow.start_run(run_name="xgboost-baseline") as run:
        mlflow.log_params({**DEFAULT_PARAMS, "folds": args.folds, "test_size": 0.2, "n_features": X.shape[1]})
        cv = cross_validate(X_train, y_train, DEFAULT_PARAMS, folds=args.folds)
        mlflow.log_metric("cv_f1_mean", sum(cv) / len(cv))
        mlflow.log_metric("cv_f1_min", min(cv))

        model = _model(y_train, DEFAULT_PARAMS).fit(X_train, y_train)
        m = _metrics(model, X_test, y_test)
        mlflow.log_metrics({f"test_{k}": v for k, v in m.items()})

        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            fig, ax = plt.subplots(figsize=(4, 4))
            ax.imshow([[m["tn"], m["fp"]], [m["fn"], m["tp"]]], cmap="Blues")
            for (i, j), v in {(0, 0): m["tn"], (0, 1): m["fp"], (1, 0): m["fn"], (1, 1): m["tp"]}.items():
                ax.text(j, i, v, ha="center", va="center")
            ax.set_xticks([0, 1], ["Normal", "Anomaly"])
            ax.set_yticks([0, 1], ["Normal", "Anomaly"])
            ax.set_xlabel("predicted")
            ax.set_ylabel("actual")
            fig.tight_layout()
            fig.savefig(d / "confusion_matrix.png")
            plt.close(fig)

            imp = pd.Series(model.feature_importances_, index=X.columns).sort_values(ascending=False)
            imp.to_csv(d / "feature_importance.csv", header=["importance"])
            (d / "templates.json").write_text(json.dumps(
                {f"tpl_{i}": t for i, t in enumerate(templates)}, indent=1))
            mlflow.log_artifacts(str(d))

        mlflow.xgboost.log_model(model, name="model", input_example=X_test.head(3))
        print(f"run {run.info.run_id}")
        print(f"CV F1 (train, {args.folds}-fold): {sum(cv) / len(cv):.4f}")
        print("holdout:", {k: round(v, 4) if isinstance(v, float) else v for k, v in m.items()})

    if args.promote:
        from ml.promote import promote

        promote(run.info.run_id)  # exits non-zero if the new model regressed


if __name__ == "__main__":
    main()
