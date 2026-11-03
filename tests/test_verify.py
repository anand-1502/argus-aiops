"""Phase 3: every citation in a postmortem must resolve to evidence the MCP tools actually returned."""
from agent.verify import EvidenceIndex, verify_postmortem


def _index():
    idx = EvidenceIndex()
    idx.add_log("blk_1#1", "Receiving block blk_1")
    idx.add_log("blk_1#2", "Unexpected error trying to delete block blk_1. BlockInfo not found in volumeMap.")
    idx.add_runbook("RB-001#Fix", "Usually harmless on its own.")
    idx.add_metric("datanode/delete_errors_per_min", "peak 4 at 2008-11-10T03:12")
    return idx


def test_all_known_citations_pass():
    r = verify_postmortem(["blk_1#2", "RB-001#Fix", "metric:datanode/delete_errors_per_min"], _index())
    assert r.ok and r.unknown == [] and r.counts == {"log": 1, "runbook": 1, "metric": 1}


def test_invented_citation_is_flagged():
    r = verify_postmortem(["blk_1#2", "blk_1#99", "RB-042#Fix"], _index())
    assert not r.ok and r.unknown == ["blk_1#99", "RB-042#Fix"]


def test_no_citations_is_not_grounded():
    r = verify_postmortem([], _index())
    assert not r.ok and "no citations" in r.reason


def test_citation_without_a_log_line_is_not_grounded():
    r = verify_postmortem(["RB-001#Fix"], _index())
    assert not r.ok and "log" in r.reason


def test_quote_check_catches_misattributed_text():
    idx = _index()
    assert idx.contains_text("blk_1#2", "BlockInfo not found in volumeMap")
    assert not idx.contains_text("blk_1#1", "BlockInfo not found in volumeMap")


def test_key_quote_must_appear_verbatim_in_the_cited_line():
    idx = _index()
    ok = verify_postmortem(["blk_1#2"], idx, key=("blk_1#2", "BlockInfo not found in volumeMap"))
    assert ok.ok
    wrong_line = verify_postmortem(["blk_1#2"], idx, key=("blk_1#1", "BlockInfo not found in volumeMap"))
    assert not wrong_line.ok and "not in log line" in wrong_line.reason
    invented = verify_postmortem(["blk_1#2"], idx, key=("blk_1#2", "the NameNode corrupted the volume map"))
    assert not invented.ok


def test_chosen_runbook_must_be_one_that_was_retrieved():
    idx = _index()
    assert verify_postmortem(["blk_1#2"], idx, runbook_id="RB-001").ok
    bad = verify_postmortem(["blk_1#2"], idx, runbook_id="RB-001#Checks")
    assert not bad.ok and "runbook_id" in bad.reason
    assert not verify_postmortem(["blk_1#2"], idx, runbook_id="RB-012").ok


def test_agent_code_never_touches_data_stores_directly():
    import pathlib, re

    forbidden = re.compile(r"psycopg|qdrant_client|api\.db|sqlalchemy|SELECT\s|INSERT\s", re.I)
    for f in pathlib.Path("agent").glob("*.py"):
        assert not forbidden.search(f.read_text()), f"{f} reaches a data store directly"
