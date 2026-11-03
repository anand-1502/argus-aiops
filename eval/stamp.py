"""A fingerprint of everything that determines the agent's behaviour.

CI compares it with the fingerprint stored in eval/latest.json: if agent, retrieval, MCP-server or
runbook code changed since the last eval run, the stored scores no longer describe the code, and the PR
must include a fresh eval (CI cannot run the local LLM itself).
"""
import hashlib
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TRACKED = ["agent/*.py", "kb/*.py", "kb/runbooks/*.md", "mcp_servers/*.py"]
EXCLUDE = {"agent/tracing.py"}  # observability only, does not change behaviour


def source_hash(model: str | None = None) -> str:
    h = hashlib.sha256()
    for pattern in TRACKED:
        for path in sorted(ROOT.glob(pattern)):
            rel = path.relative_to(ROOT).as_posix()
            if rel in EXCLUDE:
                continue
            h.update(rel.encode())
            h.update(path.read_bytes())
    h.update((model or os.environ.get("ARGUS_MODEL", "qwen3.5:4b")).encode())
    return h.hexdigest()[:16]
