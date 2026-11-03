"""Check that a postmortem's evidence is real: every cited id must exist in what the MCP tools returned."""
from dataclasses import dataclass, field


class EvidenceIndex:
    """Everything the agent was shown, keyed by citation id."""

    def __init__(self):
        self.items: dict[str, dict] = {}

    def add_log(self, cid: str, text: str):
        self.items[cid] = {"kind": "log", "text": text}

    def add_runbook(self, cid: str, text: str):
        self.items[cid] = {"kind": "runbook", "text": text}

    def add_metric(self, name: str, text: str):
        self.items[f"metric:{name}"] = {"kind": "metric", "text": text}

    def __contains__(self, cid: str) -> bool:
        return cid in self.items

    def contains_text(self, cid: str, fragment: str) -> bool:
        return cid in self.items and fragment.lower() in self.items[cid]["text"].lower()

    def runbook_ids(self) -> set[str]:
        return {cid.split("#")[0] for cid, item in self.items.items() if item["kind"] == "runbook"}

    def kind(self, cid: str) -> str | None:
        return self.items.get(cid, {}).get("kind")


@dataclass
class Verification:
    ok: bool
    reason: str
    unknown: list[str] = field(default_factory=list)
    counts: dict[str, int] = field(default_factory=dict)


def verify_postmortem(citations: list[str], index: EvidenceIndex, key: tuple[str, str] | None = None, runbook_id: str | None = None) -> Verification:
    """`key` is (evidence id, verbatim quote): the headline log line must really contain that text."""
    if not citations:
        return Verification(False, "no citations")
    unknown = [c for c in citations if c not in index]
    if unknown:
        return Verification(False, f"{len(unknown)} citation(s) not in the evidence", unknown)
    counts: dict[str, int] = {}
    for c in citations:
        counts[index.kind(c)] = counts.get(index.kind(c), 0) + 1
    if not counts.get("log"):
        return Verification(False, "no log line cited", [], counts)
    if runbook_id is not None and runbook_id not in index.runbook_ids():
        return Verification(False, f"runbook_id {runbook_id!r} must be one of {sorted(index.runbook_ids())}", [], counts)
    if key is not None:
        cid, quote = key
        if index.kind(cid) != "log" or not quote.strip() or not index.contains_text(cid, quote):
            return Verification(False, f"the key quote {quote!r} is not in log line {cid}", [], counts)
    return Verification(True, "all citations resolve to retrieved evidence", [], counts)
