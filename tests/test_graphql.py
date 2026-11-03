"""Phase 1: a GraphQL layer next to REST, serving the same numbers with flexible nesting."""
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.main import app
from tests.data import needs_full_data

pytestmark = needs_full_data

client = TestClient(app)
INC = json.loads((Path(__file__).resolve().parent.parent / "agent" / "incidents.json").read_text())[0]


def gql(query: str, **variables):
    r = client.post("/graphql", json={"query": query, "variables": variables})
    assert r.status_code == 200, r.text
    return r.json()


def test_summary_matches_rest():
    data = gql("{ summary { events blocks anomalousBlocks anomalyRatePct } }")["data"]["summary"]
    rest = client.get("/stats/summary").json()
    assert data == {"events": rest["events"], "blocks": rest["blocks"],
                    "anomalousBlocks": rest["anomalous_blocks"], "anomalyRatePct": rest["anomaly_rate_pct"]}


def test_client_picks_only_the_fields_it_wants():
    data = gql("{ summary { anomalyRatePct } }")["data"]["summary"]
    assert data == {"anomalyRatePct": 2.93}


def test_nested_block_query_returns_label_and_events():
    q = """query($id: String!) { block(blockId: $id) { blockId label events(limit: 5) { level component content } } }"""
    b = gql(q, id=INC["block_id"])["data"]["block"]
    assert b["label"] == "Anomaly" and len(b["events"]) == 5
    assert set(b["events"][0]) == {"level", "component", "content"}


def test_volume_and_components():
    d = gql('{ volume(bucket: "day") { bucket events } components { name events } }')["data"]
    assert sum(p["events"] for p in d["volume"]) == 11_175_629
    assert d["components"][0]["name"] == "dfs.FSNamesystem"


def test_unknown_bucket_is_an_error_not_a_sql_injection():
    out = gql("""{ volume(bucket: "year; drop table events") { bucket } }""")
    assert out.get("errors")


def test_anomalous_blocks_respects_limit_cap():
    rows = gql("{ anomalousBlocks(limit: 100000) { blockId } }")["data"]["anomalousBlocks"]
    assert 0 < len(rows) <= 200
