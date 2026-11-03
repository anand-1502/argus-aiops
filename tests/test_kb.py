"""Phase 3: runbook retrieval finds the right runbook for each anomaly signature."""
import socket

import pytest

# torch and xgboost ship different OpenMP runtimes on macOS and crash or hang when loaded into one
# process, so these in-process torch tests run separately (see scripts/test.sh).
pytestmark = [
    pytest.mark.torch,
    pytest.mark.skipif(socket.socket().connect_ex(("localhost", 6333)) != 0, reason="run `docker compose up -d` first"),
]

CASES = [
    ("Unexpected error trying to delete block BlockInfo not found in volumeMap", "RB-001"),
    ("writeBlock received exception java.io.IOException: Could not read from stream", "RB-002"),
    ("ask datanode to replicate block, Starting thread to transfer block, Transmitted block", "RB-003"),
    ("addStoredBlock request received but it does not belong to any file", "RB-004"),
    ("Redundant addStoredBlock request received", "RB-005"),
    ("Receiving empty packet for block", "RB-006"),
]


@pytest.fixture(scope="module")
def searcher():
    from kb.index import build_index
    from kb.search import Searcher

    build_index()
    return Searcher()


@pytest.mark.parametrize("query,expected", CASES)
def test_signature_finds_its_runbook(searcher, query, expected):
    hits = searcher.search(query, k=3)
    assert hits[0]["runbook_id"] == expected, [h["runbook_id"] for h in hits]


def test_hits_carry_citable_evidence(searcher):
    hit = searcher.search("datanode disk is full", k=1)[0]
    assert hit["runbook_id"] == "RB-007"
    assert hit["section"] and hit["text"] and hit["score"] is not None
    assert hit["citation"] == f"{hit['runbook_id']}#{hit['section']}"


def test_chunking_is_per_section():
    from kb.index import load_chunks

    chunks = load_chunks()
    sections = {c["section"] for c in chunks}
    assert {"Symptom", "Likely causes", "Checks", "Fix", "Escalate"} <= sections
    assert len({c["runbook_id"] for c in chunks}) == 16
