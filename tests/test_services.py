"""Phase 0 check: core services from docker-compose.yml are up and answering."""
import socket
import subprocess
import urllib.request

import pytest


def _up(port: int) -> bool:
    with socket.socket() as s:
        s.settimeout(1)
        return s.connect_ex(("localhost", port)) == 0


needs_stack = pytest.mark.skipif(not _up(5433), reason="run `docker compose up -d` first")


@needs_stack
def test_postgres_answers():
    out = subprocess.run(
        ["docker", "compose", "exec", "-T", "postgres", "psql", "-U", "argus", "-tAc", "select 1"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    assert out == "1"


@needs_stack
def test_redis_answers():
    out = subprocess.run(
        ["docker", "compose", "exec", "-T", "redis", "redis-cli", "ping"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    assert out == "PONG"


@needs_stack
def test_qdrant_healthy():
    with urllib.request.urlopen("http://localhost:6333/healthz", timeout=3) as r:
        assert r.status == 200
