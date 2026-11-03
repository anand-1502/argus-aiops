"""Run the agent on the golden incidents, score it, and record the run.

  uv run python -m eval.run_eval --split heldout --judge --label nightly

Outputs: eval/results/<timestamp>-<label>.json (full), eval/history.json (one line per run, for the trend),
eval/latest.json (what CI checks, unless --no-latest), and an MLflow run in the `agent-evals` experiment.
"""
import argparse
import asyncio
import json
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path

from agent.graph import MODEL, investigate
from agent.mcp_client import Servers
from eval.stamp import source_hash

ROOT = Path(__file__).resolve().parent.parent
EVAL = ROOT / "eval"
QUESTION = "What is the root cause of this HDFS block failure, and what should the on-call engineer do?"


def score_deterministic(inc: dict, out: dict) -> dict:
    pm, ev = out["postmortem"], out["evidence"]
    cited_logs = [ev[c]["text"] for c in pm["citations"] if c in ev and ev[c]["kind"] == "log"]
    return {
        "runbook_correct": pm["runbook_id"] == inc["expected_runbook"],
        "verified": out["verification"]["ok"],
        "signature_cited": any(inc["signature_line"] in t for t in cited_logs),
        "first_draft": out["drafts"] == 1,
        "plan_fallback": bool(out.get("notes")),
    }


async def run_agent(incidents: list[dict]) -> list[dict]:
    results = []
    async with Servers() as servers:
        for n, inc in enumerate(incidents, 1):
            started = time.time()
            try:
                out = await investigate(inc["block_id"], servers=servers)
                row = {**inc, "error": None, "seconds": round(time.time() - started, 1), "output": out,
                       "scores": score_deterministic(inc, out)}
            except Exception as e:  # a crashed run counts against every rate; it is never silently dropped
                row = {**inc, "error": f"{type(e).__name__}: {str(e)[:200]}", "seconds": round(time.time() - started, 1), "output": None, "scores": None}
            results.append(row)
            ok = row["scores"] and row["scores"]["runbook_correct"] and row["scores"]["verified"]
            print(f"[{n}/{len(incidents)}] {inc['expected_runbook']} {'ok' if ok else 'FAIL'} {row['seconds']}s", flush=True)
    return results


RAGAS_MAX_CONSECUTIVE_FAILURES = 3  # a small local judge often cannot follow RAGAS's JSON prompts; stop wasting time


def sample_for_judging(results: list[dict], k: int) -> list[dict]:
    """A fixed, evenly spread sample (every n-th incident), so runs stay comparable."""
    usable = [r for r in results if r["output"]]
    if k >= len(usable):
        return usable
    step = len(usable) / k
    return [usable[int(i * step)] for i in range(k)]


async def run_judges(results: list[dict], sample: int) -> None:
    from eval.judges import deepeval_faithfulness, ragas_faithfulness

    ragas_failures = 0
    for n, r in enumerate(sample_for_judging(results, sample), 1):
        r["judge"] = {"deepeval_faithfulness": None, "ragas_faithfulness": None, "errors": []}
        pm, ev = r["output"]["postmortem"], r["output"]["evidence"]
        try:
            r["judge"]["deepeval_faithfulness"] = await asyncio.to_thread(deepeval_faithfulness, pm, ev, QUESTION)
        except Exception as e:
            r["judge"]["errors"].append(f"deepeval_faithfulness: {type(e).__name__}: {str(e)[:120]}")
        if ragas_failures < RAGAS_MAX_CONSECUTIVE_FAILURES:
            try:
                r["judge"]["ragas_faithfulness"] = await ragas_faithfulness(pm, ev, QUESTION)
                ragas_failures = 0
            except Exception as e:
                ragas_failures += 1
                r["judge"]["errors"].append(f"ragas_faithfulness: {type(e).__name__}: {str(e)[:120]}")
        else:
            r["judge"]["errors"].append("ragas_faithfulness: skipped after repeated failures in this run")
        print(f"judged {n}: {r['judge']}", flush=True)


def summarize(results: list[dict]) -> dict:
    n = len(results)
    ok = [r for r in results if r["scores"]]
    rate = lambda key: round(sum(r["scores"][key] for r in ok) / n, 4)  # crashed runs count as failures
    m = {
        "n_incidents": n, "n_crashed": n - len(ok),
        "runbook_accuracy": rate("runbook_correct"), "verified_rate": rate("verified"),
        "signature_cited_rate": rate("signature_cited"), "first_draft_rate": rate("first_draft"),
        "plan_fallback_rate": rate("plan_fallback"),
        "mean_seconds": round(statistics.mean(r["seconds"] for r in results), 1),
    }
    for key in ("deepeval_faithfulness", "ragas_faithfulness"):
        vals = [r["judge"][key] for r in results if r.get("judge") and r["judge"][key] is not None]
        judged = [r for r in results if r.get("judge")]
        if judged:
            m[key + "_n"] = len(vals)  # how many incidents produced a score; the rest failed or were skipped
        if vals:
            m[key] = round(statistics.mean(vals), 4)
    return m


def record(results: list[dict], metrics: dict, label: str, update_latest: bool) -> Path:
    stamp = datetime.now(timezone.utc)
    run = {"label": label, "at": stamp.isoformat(timespec="seconds"), "model": MODEL, "source_hash": source_hash(),
           "metrics": metrics,
           "incidents": [{k: v for k, v in r.items() if k != "output"} | {"postmortem": (r["output"] or {}).get("postmortem")} for r in results]}
    (EVAL / "results").mkdir(exist_ok=True)
    path = EVAL / "results" / f"{stamp.strftime('%Y%m%dT%H%M%SZ')}-{label}.json"
    path.write_text(json.dumps(run, indent=1, default=str))

    hist_file = EVAL / "history.json"
    hist = json.loads(hist_file.read_text()) if hist_file.exists() else []
    hist.append({"at": run["at"], "label": label, "model": MODEL, "source_hash": run["source_hash"], "metrics": metrics})
    hist_file.write_text(json.dumps(hist, indent=1))
    if update_latest:
        (EVAL / "latest.json").write_text(json.dumps({k: run[k] for k in ("label", "at", "model", "source_hash", "metrics")}, indent=1))

    import mlflow

    from ml.train import TRACKING_URI

    mlflow.set_tracking_uri(TRACKING_URI)
    mlflow.set_experiment("agent-evals")
    with mlflow.start_run(run_name=label):
        mlflow.log_params({"model": MODEL, "source_hash": run["source_hash"], "n_incidents": metrics["n_incidents"]})
        mlflow.log_metrics({k: v for k, v in metrics.items() if isinstance(v, (int, float))})
        mlflow.log_artifact(str(path))
    return path


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", choices=["heldout", "seeded", "all"], default="heldout")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--judge", action="store_true", help="also score faithfulness with RAGAS and DeepEval")
    ap.add_argument("--judge-sample", type=int, default=8, help="how many incidents to judge (judging is slow on a local model)")
    ap.add_argument("--label", default="manual")
    ap.add_argument("--no-latest", action="store_true", help="do not overwrite eval/latest.json")
    args = ap.parse_args()

    golden = json.loads((EVAL / "golden.json").read_text())
    incidents = [g for g in golden if args.split == "all" or g["split"] == args.split]
    if args.limit:
        incidents = incidents[: args.limit]

    results = asyncio.run(run_agent(incidents))
    if args.judge:
        asyncio.run(run_judges(results, args.judge_sample))
    metrics = summarize(results)
    path = record(results, metrics, args.label, update_latest=not args.no_latest)
    print(json.dumps(metrics, indent=1))
    print("saved", path)


if __name__ == "__main__":
    main()
