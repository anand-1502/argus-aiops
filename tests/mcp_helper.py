"""Call an MCP server's tools over real stdio, the way the agent will."""
import json
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parent.parent


@asynccontextmanager
async def session(module: str, audit_log: Path | None = None):
    env = {"ARGUS_AUDIT_LOG": str(audit_log)} if audit_log else None
    params = StdioServerParameters(command=sys.executable, args=["-m", module], cwd=str(ROOT), env=env)
    async with stdio_client(params) as (r, w):
        async with ClientSession(r, w) as s:
            await s.initialize()
            yield s


def payload(result):
    """FastMCP returns structured content; fall back to JSON text blocks."""
    if getattr(result, "structuredContent", None):
        sc = result.structuredContent
        return sc.get("result", sc)
    texts = [json.loads(c.text) for c in result.content if getattr(c, "text", None)]
    return texts[0] if len(texts) == 1 else texts
