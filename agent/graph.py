"""LangGraph incident-triage agent.

Flow: fetch logs -> plan (LLM) -> retrieve runbooks -> correlate metrics -> draft (LLM) -> verify.
The LLM decides what to search for, which metrics to check and how to write the postmortem;
code verifies that every cited id is real evidence. All data access goes through MCP tools.
"""
import os
from datetime import datetime, timedelta
from typing import TypedDict

from langchain_ollama import ChatOllama
from langgraph.graph import END, StateGraph
from pydantic import BaseModel, Field

from agent.mcp_client import Servers
from agent.verify import EvidenceIndex, Verification, verify_postmortem

MODEL = os.environ.get("ARGUS_MODEL", "qwen3.5:4b")
MAX_DRAFTS = 2


class MetricRef(BaseModel):
    service: str
    metric: str


class Plan(BaseModel):
    runbook_queries: list[str] = Field(description="1-2 short search queries about the failure, using wording from the log lines")
    metrics: list[MetricRef] = Field(description="up to 3 metrics from the available list that could corroborate the failure")


class Postmortem(BaseModel):
    root_cause: str = Field(description="one or two sentences naming the most likely root cause")
    runbook_id: str = Field(description="the id of the single most relevant runbook, like RB-001")
    summary: str = Field(description="what happened, 2-4 sentences")
    timeline: list[str] = Field(description="3-6 short steps in time order, each mentioning the evidence id it is based on")
    recommended_actions: list[str] = Field(description="2-4 concrete next steps taken from the runbook")
    key_evidence_id: str = Field(description="the id of the single log line that best shows the failure, like blk_-123#4")
    key_evidence_quote: str = Field(description="a short phrase copied word for word from that log line")
    citations: list[str] = Field(description="evidence ids exactly as given in the evidence list; include at least one log id and one runbook id")


class State(TypedDict, total=False):
    block_id: str
    label: str | None
    events: list[dict]
    unusual: list[dict]
    plan: Plan
    runbook_hits: list[dict]
    metric_notes: list[dict]
    postmortem: Postmortem
    verification: Verification
    drafts: int
    feedback: str
    notes: list[str]
    available: list[dict]


def build_graph(servers: Servers, index: EvidenceIndex, llm=None):
    llm = llm or ChatOllama(model=MODEL, temperature=0, num_ctx=8192, reasoning=False)

    async def fetch_logs(state: State) -> State:
        events = await servers.call("logs-db", "get_block_events", block_id=state["block_id"], limit=60)
        label = (await servers.call("logs-db", "get_block_label", block_id=state["block_id"]))["label"]
        unusual = await servers.call("logs-db", "get_unusual_events", block_id=state["block_id"], top=3)
        if not events:
            raise ValueError(f"no log events for {state['block_id']}")
        for e in events:
            index.add_log(e["citation"], f"{e['ts']} {e['level']} {e['component']}: {e['content']}")
        return {"events": events, "label": label, "unusual": unusual}

    async def plan(state: State) -> State:
        available = await servers.call("metrics", "list_metrics")
        lines = "\n".join(f"- {e['content'][:160]}" for e in state["events"])
        rare = "\n".join(f"- {u['content'][:160]}  (appears in only {u['frac_blocks']:.2%} of blocks)" for u in state["unusual"])
        menu = "\n".join(f"- {m['service']}/{m['metric']}" for m in available)
        prompt = (
            "You are triaging an HDFS block failure. Log lines for the block:\n"
            f"{lines}\n\nThe rarest events in this block (most likely the failure):\n{rare or '(none)'}\n\nAvailable metrics:\n{menu}\n\n"
            "Write 1-2 search queries to find the matching runbook (reuse distinctive wording from the log lines, "
            "especially any exception or error text) and pick up to 3 metrics that would corroborate the failure."
        )
        note = None
        try:
            p = await llm.with_structured_output(Plan, method="function_calling").ainvoke(prompt)
        except Exception as e:
            p, note = None, f"plan fell back to log-line queries: {type(e).__name__}: {str(e)[:120]}"
        if p is not None and not p.runbook_queries:
            p, note = None, "plan fell back to log-line queries: the model returned no queries"
        if p is None:  # fall back to the least routine log lines
            odd = [e["content"] for e in state["events"] if e["level"] != "INFO" or "exception" in e["content"].lower() or "error" in e["content"].lower()]
            p = Plan(runbook_queries=(odd or [e["content"] for e in state["events"]])[:2], metrics=[])
        # the rarest events' message templates are the strongest search queries, so they always go first
        rare_queries = [u["template"].replace("<*>", "").strip() for u in state["unusual"][:2]]
        p.runbook_queries = list(dict.fromkeys(rare_queries + p.runbook_queries))[:3]
        valid = {(m["service"], m["metric"]) for m in available}
        p.metrics = [m for m in p.metrics if (m.service, m.metric) in valid][:3]
        return {"plan": p, "available": available, "notes": [note] if note else []}

    async def retrieve(state: State) -> State:
        hits, seen = [], set()
        for q in state["plan"].runbook_queries[:3]:
            for h in await servers.call("kb", "search_runbooks", query=q, k=3):
                if h["citation"] not in seen:
                    seen.add(h["citation"])
                    hits.append(h)
                    index.add_runbook(h["citation"], f"{h['title']} - {h['section']}: {h['text']}")
        return {"runbook_hits": hits}

    async def correlate(state: State) -> State:
        first = datetime.fromisoformat(state["events"][0]["ts"]) - timedelta(minutes=10)
        last = datetime.fromisoformat(state["events"][-1]["ts"]) + timedelta(minutes=10)
        notes = []
        # always check the metrics derived from real logs, plus whatever the model asked for
        wanted = {(m.service, m.metric) for m in state["plan"].metrics} | {(m["service"], m["metric"]) for m in state["available"] if m["source"] == "derived-from-logs"}
        for service, metric in sorted(wanted):
            m = MetricRef(service=service, metric=metric)
            r = await servers.call("metrics", "get_metric", service=m.service, metric=m.metric, start=first.isoformat(), end=last.isoformat())
            if not r.get("points") or r["max"] <= 0:
                continue  # nothing happened on this metric in the window
            text = f"{m.service}/{m.metric} ({r['source']}): max {r['max']:.1f} at {r['peak_at']}, mean {r['mean']:.2f} over the window"
            index.add_metric(f"{m.service}/{m.metric}", text)
            notes.append({"id": f"metric:{m.service}/{m.metric}", "text": text})
        return {"metric_notes": notes}

    async def draft(state: State) -> State:
        rare_ids = {u["citation"] for u in state["unusual"]}
        logs = "\n".join(f"[{e['citation']}] {'(RARE) ' if e['citation'] in rare_ids else ''}{e['ts']} {e['level']} {e['content'][:200]}" for e in state["events"])
        books = "\n".join(f"[{h['citation']}] {h['title']} - {h['section']}: {h['text'][:300]}" for h in state["runbook_hits"])
        mets = "\n".join(f"[{n['id']}] {n['text']}" for n in state.get("metric_notes", [])) or "(none)"
        prompt = (
            f"Write an incident postmortem for HDFS block {state['block_id']} (benchmark label: {state['label']}).\n\n"
            f"LOG EVIDENCE:\n{logs}\n\nRUNBOOK EVIDENCE:\n{books}\n\nMETRIC EVIDENCE:\n{mets}\n\n"
            "The (RARE) log lines are the most likely failure; choose the runbook whose Symptom describes them. "
            "Rules: base every statement on the evidence above. In `citations`, copy evidence ids exactly as they appear "
            "inside the square brackets (for example blk_-123#4 or RB-001#Fix). Cite the log line that shows the failure "
            "and the runbook section that explains it. Do not invent ids.\n"
            "Wording rules: name the failure using words from the log line you cite, and describe causes only as "
            "'likely' causes taken from the runbook. Do not describe internal mechanisms that no evidence shows. "
            "`key_evidence_quote` must be copied exactly from the log line named in `key_evidence_id`."
        )
        if state.get("feedback"):
            prompt += f"\n\nYour previous draft was rejected: {state['feedback']} Fix this."
        pm = await llm.with_structured_output(Postmortem, method="function_calling").ainvoke(prompt)
        return {"postmortem": pm, "drafts": state.get("drafts", 0) + 1}

    async def verify(state: State) -> State:
        pm = state["postmortem"]
        pm.runbook_id = pm.runbook_id.split("#")[0].strip()
        v = verify_postmortem(pm.citations, index, key=(pm.key_evidence_id, pm.key_evidence_quote), runbook_id=pm.runbook_id)
        fb = ""
        if not v.ok:
            fb = f"{v.reason}." + (f" Unknown ids: {', '.join(v.unknown)}. Use only ids from the evidence lists." if v.unknown else "")
        return {"verification": v, "feedback": fb}

    def after_verify(state: State) -> str:
        return END if state["verification"].ok or state["drafts"] >= MAX_DRAFTS else "draft"

    g = StateGraph(State)
    for name, fn in [("fetch_logs", fetch_logs), ("plan", plan), ("retrieve", retrieve), ("correlate", correlate), ("draft", draft), ("verify", verify)]:
        g.add_node(name, fn)
    g.set_entry_point("fetch_logs")
    for a, b in [("fetch_logs", "plan"), ("plan", "retrieve"), ("retrieve", "correlate"), ("correlate", "draft"), ("draft", "verify")]:
        g.add_edge(a, b)
    g.add_conditional_edges("verify", after_verify, {END: END, "draft": "draft"})
    return g.compile()


async def investigate(block_id: str, llm=None, servers: Servers | None = None) -> dict:
    """Run the agent on one block and return the postmortem, its verification and the MCP call trace.

    Pass `servers` to reuse running MCP servers across many incidents (an eval run does this)."""
    index = EvidenceIndex()
    if servers is None:
        async with Servers() as own:
            return await _run(block_id, llm, own, index)
    return await _run(block_id, llm, servers, index)


async def _run(block_id: str, llm, servers: Servers, index: EvidenceIndex) -> dict:
    first_call = len(servers.trace)
    final = await build_graph(servers, index, llm).ainvoke({"block_id": block_id})
    return {
        "block_id": block_id,
        "label": final["label"],
        "postmortem": final["postmortem"].model_dump(),
        "verification": vars(final["verification"]),
        "drafts": final["drafts"],
        "notes": final.get("notes", []),
        "trace": servers.trace[first_call:],
        "evidence": index.items,
    }


if __name__ == "__main__":
    import argparse
    import asyncio
    import json

    ap = argparse.ArgumentParser()
    ap.add_argument("--block", required=True)
    out = asyncio.run(investigate(ap.parse_args().block))
    print(json.dumps({k: v for k, v in out.items() if k != "evidence"}, indent=2, default=str))
