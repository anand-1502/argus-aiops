"""Phase 5: per-client configuration changes what each deployment exposes."""
import json

from fastapi.testclient import TestClient

from api.main import app
from mcp_servers import common
from tests.data import needs_full_data

client = TestClient(app)


def test_default_tenant_has_no_taxonomy():
    t = client.get("/tenant").json()
    assert t["tenant"] == "default" and t["taxonomy"] == {} and t["mcp"]["allowed_tools"] == "all"


@needs_full_data
def test_taxonomy_regroups_components_in_the_clients_own_words(tmp_path, monkeypatch):
    f = tmp_path / "taxonomy.json"
    f.write_text(json.dumps({"dfs.FSNamesystem": "Metadata plane", "dfs.DataNode$DataXceiver": "Storage plane"}))
    monkeypatch.setenv("ARGUS_TENANT", "acme")
    monkeypatch.setenv("ARGUS_TAXONOMY_FILE", str(f))
    t = client.get("/tenant").json()
    assert t["tenant"] == "acme"
    assert set(t["events_by_group"]) == {"Metadata plane", "Storage plane", "Other"}
    assert sum(t["events_by_group"].values()) == 11_175_629


def test_tool_allow_list_hides_tools_that_the_client_does_not_get(monkeypatch):
    monkeypatch.setattr(common, "ALLOWED_TOOLS", {"search_runbooks"})
    assert common.tool_enabled("search_runbooks") and not common.tool_enabled("get_block_events")
    monkeypatch.setattr(common, "ALLOWED_TOOLS", set())
    assert common.tool_enabled("anything")  # empty list means everything
