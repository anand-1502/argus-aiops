"""Phase 3: the MCP servers are the only door to the data, and they behave like a governed one."""
import asyncio
import json
from pathlib import Path

import pytest

from tests.data import needs_full_data
from tests.mcp_helper import payload, session

INCIDENTS = json.loads((Path(__file__).resolve().parent.parent / "agent" / "incidents.json").read_text())
INC = {i["expected_runbook"]: i for i in INCIDENTS}


def run(coro):
    return asyncio.run(coro)


def test_logs_db_exposes_only_the_allow_listed_tools():
    async def go():
        async with session("mcp_servers.logs_db") as s:
            return {t.name for t in (await s.list_tools()).tools}

    assert run(go()) == {"get_block_events", "get_block_label", "get_unusual_events", "find_anomalous_blocks", "component_summary"}


def test_metrics_and_kb_tool_lists():
    async def go(mod):
        async with session(mod) as s:
            return {t.name for t in (await s.list_tools()).tools}

    assert run(go("mcp_servers.metrics_server")) == {"list_metrics", "get_metric"}
    assert run(go("mcp_servers.kb_server")) == {"search_runbooks"}


@needs_full_data
def test_get_block_events_returns_citable_events_including_the_signature():
    inc = INC["RB-001"]

    async def go():
        async with session("mcp_servers.logs_db") as s:
            return payload(await s.call_tool("get_block_events", {"block_id": inc["block_id"]}))

    events = run(go())
    assert len(events) == inc["n_events"]
    assert all(e["citation"].startswith(inc["block_id"] + "#") for e in events)
    assert any(inc["signature_line"] == e["content"] for e in events)


@needs_full_data
def test_row_cap_is_enforced_server_side():
    async def go():
        async with session("mcp_servers.logs_db") as s:
            return payload(await s.call_tool("component_summary", {"start": "2008-11-09T00:00:00", "end": "2008-11-12T00:00:00"}))

    assert len(run(go())) <= 50


@needs_full_data
def test_bad_input_is_rejected_and_audited(tmp_path):
    log = tmp_path / "audit.jsonl"

    async def go():
        async with session("mcp_servers.logs_db", audit_log=log) as s:
            bad = await s.call_tool("get_block_events", {"block_id": "'; DROP TABLE events; --"})
            ok = await s.call_tool("get_block_label", {"block_id": INC["RB-002"]["block_id"]})
            return bad, payload(ok)

    bad, ok = run(go())
    assert bad.isError
    assert ok["label"] == "Anomaly"
    entries = [json.loads(line) for line in log.read_text().splitlines()]
    assert [e["tool"] for e in entries] == ["get_block_events", "get_block_label"]
    assert entries[0]["ok"] is False and entries[1]["ok"] is True


@needs_full_data
def test_metrics_correlate_with_the_incident_window():
    inc = INC["RB-001"]

    async def go():
        async with session("mcp_servers.metrics_server") as s:
            listing = payload(await s.call_tool("list_metrics", {}))
            m = payload(await s.call_tool("get_metric", {
                "service": "datanode", "metric": "delete_errors_per_min",
                "start": inc["first_ts"], "end": inc["last_ts"]}))
            return listing, m

    listing, m = run(go())
    assert {"service": "datanode", "metric": "cpu_pct", "source": "simulated"} in listing
    assert m["source"] == "derived-from-logs"
    assert m["max"] >= 1  # the incident block's own delete error is counted in this minute
    assert 0 < len(m["points"]) <= 120


@needs_full_data
def test_kb_server_returns_cited_runbook_sections():
    async def go():
        async with session("mcp_servers.kb_server") as s:
            return payload(await s.call_tool("search_runbooks", {"query": "BlockInfo not found in volumeMap", "k": 2}))

    hits = run(go())
    assert hits[0]["runbook_id"] == "RB-001"
    assert hits[0]["citation"].startswith("RB-001#")


@needs_full_data
@pytest.mark.parametrize("rb", sorted(INC))
def test_unusual_events_surface_the_failure_signature(rb):
    """Rarity across all blocks (no labels used) must put the signature line first for every seeded incident."""
    inc = INC[rb]

    async def go():
        async with session("mcp_servers.logs_db") as s:
            return payload(await s.call_tool("get_unusual_events", {"block_id": inc["block_id"], "top": 3}))

    hits = run(go())
    assert hits and hits[0]["content"] == inc["signature_line"], [h["content"][:60] for h in hits]
    assert hits[0]["frac_blocks"] < 0.2 and hits[0]["citation"].startswith(inc["block_id"] + "#")
    assert [h["frac_blocks"] for h in hits] == sorted(h["frac_blocks"] for h in hits)
