"""Phase 5: the job runner only runs allow-listed commands, one at a time, and reports honestly."""
import time

import pytest

from api import jobs


def wait(job_id, timeout=10):
    end = time.time() + timeout
    while time.time() < end:
        j = jobs.get(job_id)
        if j["status"] != "running":
            return j
        time.sleep(0.05)
    raise AssertionError("job did not finish")


def test_success_and_failure_are_reported_with_exit_codes_and_log_tail():
    cmds = {"ok": ["python3", "-c", "print('hello')"], "bad": ["python3", "-c", "import sys; print('boom'); sys.exit(3)"]}
    ok = wait(jobs.start("ok", cmds))
    assert ok["status"] == "succeeded" and ok["returncode"] == 0 and "hello" in ok["log"]
    bad = wait(jobs.start("bad", cmds))
    assert bad["status"] == "failed" and bad["returncode"] == 3 and "boom" in bad["log"]


def test_unknown_job_names_are_refused():
    with pytest.raises(KeyError):
        jobs.start("rm -rf /", {"ok": ["true"]})
    assert set(jobs.ALLOWED) == {"retrain", "eval"}


def test_a_second_run_of_the_same_job_is_refused_while_one_is_running():
    cmds = {"slow": ["python3", "-c", "import time; time.sleep(1)"]}
    first = jobs.start("slow", cmds)
    with pytest.raises(jobs.AlreadyRunning):
        jobs.start("slow", cmds)
    wait(first)
    wait(jobs.start("slow", cmds))  # fine again once the first one finished


def test_a_missing_script_fails_cleanly():
    j = wait(jobs.start("x", {"x": ["./definitely-not-here.sh"]}))
    assert j["status"] == "failed" and j["returncode"] == -1


def test_http_layer_rejects_unknown_jobs_and_ids():
    from fastapi.testclient import TestClient

    from api.main import app

    c = TestClient(app)
    assert c.post("/jobs/not-a-job").status_code == 404
    assert c.get("/jobs/nope").status_code == 404
