"""Run the agent on every seeded incident and save the full results for the demo UI and the static site."""
import asyncio
import json
import time
from pathlib import Path

from agent.graph import MODEL, investigate

ROOT = Path(__file__).resolve().parent.parent


async def main() -> None:
    incidents = json.loads((ROOT / "agent" / "incidents.json").read_text())
    runs = {}
    for inc in incidents:
        started = time.time()
        out = await investigate(inc["block_id"])
        out["seconds"] = round(time.time() - started, 1)
        out["model"] = MODEL
        out["expected_runbook"] = inc["expected_runbook"]
        runs[inc["block_id"]] = out
        print(inc["expected_runbook"], out["postmortem"]["runbook_id"], out["verification"]["ok"], out["seconds"], flush=True)
    (ROOT / "agent" / "demo_runs.json").write_text(json.dumps(runs, indent=1, default=str))


if __name__ == "__main__":
    asyncio.run(main())
