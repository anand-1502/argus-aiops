"""The agent's only door to data: tool calls to the three MCP servers over stdio."""
import json
import os
import sys
import time
from contextlib import AsyncExitStack
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import get_default_environment, stdio_client

from agent.tracing import tracer

ROOT = Path(__file__).resolve().parent.parent
SERVERS = {
    "logs-db": "mcp_servers.logs_db",
    "kb": "mcp_servers.kb_server",
    "metrics": "mcp_servers.metrics_server",
}


def parse(result):
    if result.isError:
        raise RuntimeError("; ".join(getattr(c, "text", str(c)) for c in result.content))
    sc = getattr(result, "structuredContent", None)
    if sc:
        return sc.get("result", sc)
    texts = [json.loads(c.text) for c in result.content if getattr(c, "text", None)]
    return texts[0] if len(texts) == 1 else texts


class Servers:
    """Starts the MCP servers once and records every call for the UI's trace panel."""

    def __init__(self, only: tuple[str, ...] = tuple(SERVERS)):
        self.only = only
        self.sessions: dict[str, ClientSession] = {}
        self.trace: list[dict] = []
        self._stack = AsyncExitStack()

    async def __aenter__(self):
        for name in self.only:
            # the SDK only forwards a minimal environment by default; the servers also need the database settings
            passthrough = {k: v for k, v in os.environ.items() if k.startswith(("PG", "POSTGRES", "ARGUS", "QDRANT"))}
            params = StdioServerParameters(command=sys.executable, args=["-m", SERVERS[name]], cwd=str(ROOT),
                                           env={**get_default_environment(), **passthrough})
            r, w = await self._stack.enter_async_context(stdio_client(params))
            s = await self._stack.enter_async_context(ClientSession(r, w))
            await s.initialize()
            self.sessions[name] = s
        return self

    async def __aexit__(self, *exc):
        await self._stack.aclose()

    async def call(self, server: str, tool: str, **args):
        started = time.time()
        entry = {"server": server, "tool": tool, "args": args}
        with tracer().start_as_current_span(f"mcp.{server}.{tool}") as span:
            span.set_attribute("mcp.server", server)
            span.set_attribute("mcp.tool", tool)
            span.set_attribute("mcp.args", str(args)[:500])
            try:
                result = parse(await self.sessions[server].call_tool(tool, args))
                entry["rows"] = len(result) if hasattr(result, "__len__") else 1
                span.set_attribute("mcp.rows", entry["rows"])
                return result
            except Exception as e:
                entry["error"] = str(e)
                span.record_exception(e)
                raise
            finally:
                entry["ms"] = round((time.time() - started) * 1000)
                self.trace.append(entry)
