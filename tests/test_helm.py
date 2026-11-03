"""Phase 5: three Helm releases, three genuinely different client configurations."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.skipif(shutil.which("helm") is None, reason="helm is not installed")
HELM = Path(__file__).resolve().parent.parent / "deploy" / "helm"
CLIENTS = ["acme", "globex", "initech"]


def render(client: str) -> list[dict]:
    out = subprocess.run(["helm", "template", f"argus-{client}", str(HELM / "argus"), "-f", str(HELM / f"values-{client}.yaml")],
                         capture_output=True, text=True, check=True).stdout
    return [d for d in yaml.safe_load_all(out) if d]


def api_env(docs: list[dict]) -> dict:
    dep = next(d for d in docs if d["kind"] == "Deployment" and d["metadata"]["name"].endswith("-api"))
    return {e["name"]: e["value"] for e in dep["spec"]["template"]["spec"]["containers"][0]["env"]}


def runbooks(docs: list[dict]) -> set[str]:
    cm = next(d for d in docs if d["kind"] == "ConfigMap" and d["metadata"]["name"].endswith("-runbooks"))
    return set(cm["data"])


def taxonomy(docs: list[dict]) -> dict:
    cm = next(d for d in docs if d["kind"] == "ConfigMap" and d["metadata"]["name"].endswith("-config"))
    return json.loads(cm["data"]["taxonomy.json"])


def test_each_release_renders_the_same_nine_kinds_of_resource():
    kinds = [sorted(d["kind"] for d in render(c)) for c in CLIENTS]
    assert kinds[0] == kinds[1] == kinds[2] and len(kinds[0]) == 9


def test_mcp_limits_and_tool_allow_lists_differ_per_client():
    env = {c: api_env(render(c)) for c in CLIENTS}
    assert [env[c]["ARGUS_MAX_ROWS"] for c in CLIENTS] == ["200", "100", "50"]
    assert env["acme"]["ARGUS_ALLOWED_TOOLS"] == ""  # everything
    assert "component_summary" not in env["globex"]["ARGUS_ALLOWED_TOOLS"] and "find_anomalous_blocks" in env["globex"]["ARGUS_ALLOWED_TOOLS"]
    assert "find_anomalous_blocks" not in env["initech"]["ARGUS_ALLOWED_TOOLS"]


def test_runbook_knowledge_bases_differ_and_carry_client_specific_documents():
    rb = {c: runbooks(render(c)) for c in CLIENTS}
    assert len(rb["acme"]) == 16 and len(rb["globex"]) == 9 and len(rb["initech"]) == 5
    assert "RB-901.md" in rb["globex"] and "RB-901.md" not in rb["acme"] | rb["initech"]
    assert "RB-902.md" in rb["initech"] and "RB-902.md" not in rb["acme"] | rb["globex"]


def test_component_taxonomies_use_each_clients_own_vocabulary():
    groups = {c: set(taxonomy(render(c)).values()) for c in CLIENTS}
    assert "Metadata plane" in groups["acme"] and "Namenode team" in groups["globex"] and "Control" in groups["initech"]
    assert not (groups["acme"] & groups["globex"]) and not (groups["globex"] & groups["initech"])


def test_each_release_exposes_its_own_node_port_so_three_can_run_together():
    ports = []
    for c in CLIENTS:
        svc = next(d for d in render(c) if d["kind"] == "Service" and d["metadata"]["name"].endswith("-web"))
        ports.append(svc["spec"]["ports"][0]["nodePort"])
    assert ports == [30081, 30082, 30083]


def test_label_values_are_valid_for_kubernetes():
    """The API server rejects label values with spaces ("Acme Storage"). helm lint cannot see that, so check the rendered output."""
    import re

    valid = re.compile(r"(([A-Za-z0-9][-A-Za-z0-9_.]*)?[A-Za-z0-9])?")
    for client in CLIENTS:
        for doc in render(client):
            for labels in (doc["metadata"].get("labels") or {}, ((doc.get("spec") or {}).get("template") or {}).get("metadata", {}).get("labels") or {}):
                for key, value in labels.items():
                    assert len(str(value)) <= 63 and valid.fullmatch(str(value)), (client, doc["kind"], key, value)
    docs = render("acme")
    assert next(d for d in docs if d["kind"] == "ConfigMap")["metadata"]["labels"]["argus/tenant"] == "acme-storage"
