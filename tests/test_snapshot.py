"""The static site reads recorded JSON. These checks keep the recording and the web client in step."""
import json
import re
from pathlib import Path

from scripts.snapshot import OUT, key

WEB = Path(__file__).resolve().parent.parent / "web"
API_TS = (WEB / "lib" / "api.ts").read_text()


def test_python_and_typescript_agree_on_file_names():
    assert 'path.replace(/^\\//, "").replace(/[^A-Za-z0-9._-]/g, "_")' in API_TS  # the TS twin of key()
    assert key("/stats/volume?bucket=hour") == "stats_volume_bucket_hour"
    assert key("/uploads/demo/summary") == "uploads_demo_summary"
    assert key("/agent/runs/blk_-123") == "agent_runs_blk_-123"


def test_every_fixed_path_the_client_reads_has_a_snapshot_file():
    paths = re.findall(r'get<[^>]*(?:<[^>]*>)?[^>]*>\("(/[^"]+)"\)', API_TS)
    assert len(paths) >= 15  # the pattern still finds the client's calls
    missing = [p for p in paths if not (OUT / f"{key(p)}.json").exists()]
    assert not missing, f"run `uv run python -m scripts.snapshot`; missing: {missing}"


def test_snapshot_files_are_valid_json_and_the_demo_upload_is_there():
    files = list(OUT.glob("*.json"))
    assert len(files) > 30
    for f in files:
        json.loads(f.read_text())
    assert json.loads((OUT / "uploads.json").read_text())[0]["id"] == "demo"
    assert json.loads((OUT / "uploads_demo_summary.json").read_text())["spikes"]


def test_snapshot_has_one_recorded_run_per_seeded_incident():
    incidents = json.loads((Path(__file__).resolve().parent.parent / "agent" / "incidents.json").read_text())
    for i in incidents:
        assert (OUT / f"agent_runs_{key(i['block_id'])}.json").exists(), i["block_id"]
