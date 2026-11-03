"""The CI gate. Each check exits non-zero with a plain message when something regressed.

  python -m eval.gate classifier   train on the committed feature sample, require an F1 floor
  python -m eval.gate retrieval    run the retrieval chain over the golden fixtures through the MCP servers
  python -m eval.gate results      check eval/latest.json: fresh for this code, above thresholds, no regression
"""
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EVAL = ROOT / "eval"


def thresholds() -> dict:
    return json.loads((EVAL / "thresholds.json").read_text())


def fail(msg: str) -> None:
    print(f"GATE FAILED: {msg}")
    sys.exit(1)


def classifier() -> dict:
    import pandas as pd

    from ml.train import evaluate, split

    df = pd.read_parquet(ROOT / "ml/fixtures/features_sample.parquet")
    X, y = df.drop(columns="label"), df["label"]
    Xtr, Xte, ytr, yte = split(X, y)
    m = evaluate(Xtr, ytr, Xte, yte)
    floor = thresholds()["classifier"]
    print(f"classifier: f1={m['f1']:.4f} recall={m['recall']:.4f} precision={m['precision']:.4f} (floors {floor})")
    if m["f1"] < floor["f1_min"]:
        fail(f"classifier F1 {m['f1']:.4f} is below the floor {floor['f1_min']}")
    if m["recall"] < floor["recall_min"]:
        fail(f"classifier recall {m['recall']:.4f} is below the floor {floor['recall_min']}")
    return m


async def _retrieval() -> dict:
    from agent.mcp_client import Servers

    golden = json.loads((EVAL / "golden.json").read_text())
    top1 = top3 = 0
    misses = []
    async with Servers(only=("logs-db", "kb")) as s:
        for g in golden:
            unusual = await s.call("logs-db", "get_unusual_events", block_id=g["block_id"], top=1)
            query = unusual[0]["template"].replace("<*>", "").strip()
            hits = await s.call("kb", "search_runbooks", query=query, k=3)
            ids = [h["runbook_id"] for h in hits]
            top1 += ids[:1] == [g["expected_runbook"]]
            top3 += g["expected_runbook"] in ids
            if ids[:1] != [g["expected_runbook"]]:
                misses.append((g["block_id"], g["expected_runbook"], ids))
    n = len(golden)
    return {"n": n, "top1": top1 / n, "top3": top3 / n, "misses": misses}


def retrieval() -> dict:
    r = asyncio.run(_retrieval())
    floor = thresholds()["retrieval"]
    print(f"retrieval: top1={r['top1']:.3f} top3={r['top3']:.3f} over {r['n']} golden incidents (floors {floor})")
    for miss in r["misses"]:
        print("  miss:", miss)
    if r["top1"] < floor["top1_min"]:
        fail(f"retrieval top-1 {r['top1']:.3f} is below the floor {floor['top1_min']}")
    if r["top3"] < floor["top3_min"]:
        fail(f"retrieval top-3 {r['top3']:.3f} is below the floor {floor['top3_min']}")
    return r


def results() -> dict:
    from eval.stamp import source_hash

    latest_f = EVAL / "latest.json"
    if not latest_f.exists():
        fail("eval/latest.json is missing: run `uv run python -m eval.run_eval --judge` and commit the result")
    latest = json.loads(latest_f.read_text())
    if latest["source_hash"] != source_hash(latest["model"]):
        fail("agent, retrieval, MCP-server or runbook code changed since the last eval run. "
             "Re-run `uv run python -m eval.run_eval --split all --judge --label pr` and commit eval/latest.json")
    m, floors = latest["metrics"], thresholds()["agent"]
    print(f"agent eval from {latest['at']} ({m['n_incidents']} incidents, model {latest['model']}): " +
          ", ".join(f"{k}={m[k]}" for k in floors if k in m))
    for key, floor in floors.items():
        if key not in m:
            fail(f"metric {key} is missing from eval/latest.json")
        if m[key] < floor:
            fail(f"{key} is {m[key]}, below the floor {floor}")
    base_f = EVAL / "baseline.json"
    if base_f.exists():
        base = json.loads(base_f.read_text())["metrics"]
        tol = thresholds()["regression_tolerance"]
        for key in floors:
            if key in base and key in m and m[key] < base[key] - tol:
                fail(f"{key} regressed: {m[key]} vs baseline {base[key]} (tolerance {tol})")
    return m


CHECKS = {"classifier": classifier, "retrieval": retrieval, "results": results}

if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 else "all"
    for name in (CHECKS if which == "all" else [which]):
        CHECKS[name]()
    print("gate passed")
