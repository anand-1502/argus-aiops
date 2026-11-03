"""Shared access-control helpers for the MCP servers: argument validation and an audit log."""
import functools
import json
import os
import time
from datetime import datetime
from pathlib import Path

AUDIT_LOG = Path(os.environ.get("ARGUS_AUDIT_LOG", Path(__file__).resolve().parent.parent / "logs" / "mcp_audit.jsonl"))
MAX_ROWS = int(os.environ.get("ARGUS_MAX_ROWS", "200"))  # per-client: how many rows any tool may return
# per-client: comma-separated tool names this deployment exposes; empty means all of them
ALLOWED_TOOLS = {t.strip() for t in os.environ.get("ARGUS_ALLOWED_TOOLS", "").split(",") if t.strip()}


def tool_enabled(name: str) -> bool:
    return not ALLOWED_TOOLS or name in ALLOWED_TOOLS


def registrar(mcp):
    """A decorator that registers a function as an MCP tool only if this deployment allows it."""

    def tool(fn):
        return mcp.tool()(fn) if tool_enabled(fn.__name__) else fn

    return tool


def clamp(limit: int, default: int = 50) -> int:
    """Row caps are enforced server side, whatever the agent asks for."""
    if limit is None or limit < 1:
        return default
    return min(int(limit), MAX_ROWS)


def parse_ts(value: str) -> datetime:
    try:
        return datetime.fromisoformat(value)
    except ValueError as e:
        raise ValueError(f"timestamp must be ISO 8601, got {value!r}") from e


def audited(server: str):
    """Record every tool call (server, tool, arguments, result size, outcome) as one JSON line."""

    def deco(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            entry = {"at": time.time(), "server": server, "tool": fn.__name__, "args": kwargs}
            try:
                result = fn(*args, **kwargs)
                entry["ok"] = True
                entry["rows"] = len(result) if hasattr(result, "__len__") else 1
                return result
            except Exception as e:
                entry.update(ok=False, error=str(e))
                raise
            finally:
                AUDIT_LOG.parent.mkdir(parents=True, exist_ok=True)
                with AUDIT_LOG.open("a") as f:
                    f.write(json.dumps(entry, default=str) + "\n")

        return wrapper

    return deco
