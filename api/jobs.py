"""A tiny job runner so an orchestrator (Airflow) can start long jobs on this machine and poll them.

Only a fixed allow-list of commands can run: there is no way to pass a command through the API.
One run per job name at a time.
"""
import subprocess
import threading
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ALLOWED: dict[str, list[str]] = {
    "retrain": ["scripts/retrain.sh"],
    "eval": ["scripts/nightly_eval.sh"],
}
LOG_TAIL = 4000

_jobs: dict[str, dict] = {}
_lock = threading.Lock()


class AlreadyRunning(Exception):
    pass


def start(name: str, commands: dict[str, list[str]] | None = None) -> str:
    cmds = commands or ALLOWED
    if name not in cmds:
        raise KeyError(name)
    with _lock:
        if any(j["name"] == name and j["status"] == "running" for j in _jobs.values()):
            raise AlreadyRunning(name)
        job_id = uuid.uuid4().hex[:12]
        _jobs[job_id] = {"id": job_id, "name": name, "status": "running", "returncode": None, "started": time.time(), "log": ""}
    threading.Thread(target=_run, args=(job_id, cmds[name]), daemon=True).start()
    return job_id


def _run(job_id: str, cmd: list[str]) -> None:
    try:
        proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
        log, code = (proc.stdout + proc.stderr)[-LOG_TAIL:], proc.returncode
    except Exception as e:  # e.g. the script does not exist
        log, code = f"{type(e).__name__}: {e}", -1
    with _lock:
        _jobs[job_id].update(status="succeeded" if code == 0 else "failed", returncode=code, log=log, finished=time.time())


def get(job_id: str) -> dict | None:
    with _lock:
        j = _jobs.get(job_id)
        return dict(j) if j else None


def recent(limit: int = 10) -> list[dict]:
    """Most recent jobs first, without their logs."""
    with _lock:
        rows = sorted(_jobs.values(), key=lambda j: j["started"], reverse=True)[:limit]
    return [{k: v for k, v in j.items() if k != "log"} for j in rows]
