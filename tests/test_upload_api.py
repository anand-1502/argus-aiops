"""Phase 6: the upload endpoints, end to end through FastAPI, against the scratch database."""
import socket
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.main import app

FIX = Path(__file__).parent / "fixtures"


def _up() -> bool:
    with socket.socket() as s:
        s.settimeout(1)
        return s.connect_ex(("localhost", 5433)) == 0


pytestmark = pytest.mark.skipif(not _up(), reason="run `docker compose up -d` first")
client = TestClient(app)


@pytest.fixture(autouse=True)
def scratch_db(monkeypatch):
    monkeypatch.setenv("PGDATABASE", "argus_test")


def _wait(uid: str, timeout: float = 30) -> dict:
    end = time.time() + timeout
    while time.time() < end:
        r = client.get(f"/uploads/{uid}").json()
        if r["status"] in ("succeeded", "failed"):
            return r
        time.sleep(0.2)
    raise AssertionError("ingest did not finish")


def _upload(path: Path) -> str:
    with path.open("rb") as f:
        r = client.post("/uploads", files={"file": (path.name, f)})
    assert r.status_code == 202
    return r.json()["id"]


def test_upload_progress_summary_search_delete():
    uid = _upload(FIX / "modern_app.log")
    row = _wait(uid)
    assert row["status"] == "succeeded" and row["lines_done"] == row["lines_total"] > 800
    assert uid in [u["id"] for u in client.get("/uploads").json()]

    s = client.get(f"/uploads/{uid}/summary").json()
    assert s["events"] == row["lines_total"] and s["spikes"] and s["rare_templates"]
    assert s["bucket"] == "minute"

    hits = client.get(f"/uploads/{uid}/search", params={"q": "upstream timeout"}).json()
    assert len(hits) == 1
    assert client.get(f"/uploads/{uid}/search", params={"q": " "}).status_code == 422

    assert client.delete(f"/uploads/{uid}").json() == {"deleted": uid}
    assert client.get(f"/uploads/{uid}").status_code == 404
    assert client.delete(f"/uploads/{uid}").status_code == 404
    assert not list((Path(__file__).parent.parent / "data" / "uploads").glob(f"{uid}*"))  # temp file is gone


def test_bad_ids_and_unfinished_uploads_are_rejected():
    for bad in ["nope", "x;drop", "ABCDEF123456"]:
        assert client.get(f"/uploads/{bad}").status_code == 404
        assert client.get(f"/uploads/{bad}/summary").status_code == 404
        assert client.delete(f"/uploads/{bad}").status_code == 404


def test_binary_upload_fails_cleanly_and_summary_says_so(tmp_path):
    p = tmp_path / "x.bin"
    p.write_bytes(b"\x00\x01" * 500)
    uid = _upload(p)
    row = _wait(uid)
    assert row["status"] == "failed" and "binary" in row["error"]
    assert client.get(f"/uploads/{uid}/summary").status_code == 409
    client.delete(f"/uploads/{uid}")


def test_oversized_upload_is_refused(monkeypatch, tmp_path):
    from ingest import upload

    monkeypatch.setattr(upload, "MAX_BYTES", 1000)
    p = tmp_path / "big.log"
    p.write_text("line\n" * 1000)
    with p.open("rb") as f:
        assert client.post("/uploads", files={"file": ("big.log", f)}).status_code == 413
