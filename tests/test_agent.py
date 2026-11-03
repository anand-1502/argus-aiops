"""Phase 3 acceptance: for each seeded incident the agent finds the known root cause with verified evidence.

Run with:  uv run pytest -m agent tests/test_agent.py
"""
import asyncio
import json
from pathlib import Path

import pytest

from agent.graph import investigate

INCIDENTS = json.loads((Path(__file__).resolve().parent.parent / "agent" / "incidents.json").read_text())
pytestmark = pytest.mark.agent


@pytest.mark.parametrize("inc", INCIDENTS, ids=[i["expected_runbook"] for i in INCIDENTS])
def test_agent_finds_known_root_cause_with_verified_evidence(inc):
    out = asyncio.run(investigate(inc["block_id"]))
    pm = out["postmortem"]

    assert out["verification"]["ok"], out["verification"]["reason"]
    assert pm["runbook_id"] == inc["expected_runbook"], f"agent chose {pm['runbook_id']}"

    # the cited evidence must include the log line that actually carries the failure signature
    cited_logs = [out["evidence"][c]["text"] for c in pm["citations"] if out["evidence"][c]["kind"] == "log"]
    assert any(inc["signature_line"] in text for text in cited_logs), "signature line not cited"

    # governed access: the whole run went through the three MCP servers
    assert {c["server"] for c in out["trace"]} <= {"logs-db", "kb", "metrics"}
    assert all("error" not in c for c in out["trace"])
