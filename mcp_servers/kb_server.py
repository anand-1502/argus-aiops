"""`kb` MCP server: semantic search over runbooks (Qdrant + MiniLM, reranked by bge-reranker)."""
from mcp.server.fastmcp import FastMCP

from mcp_servers.common import registrar, audited

mcp = FastMCP("kb")
tool = registrar(mcp)
_searcher = None


def _get():
    global _searcher
    if _searcher is None:  # models load on first use so the server starts instantly
        from kb.search import Searcher

        _searcher = Searcher()
    return _searcher


@tool
@audited("kb")
def search_runbooks(query: str, k: int = 3) -> list[dict]:
    """Search the runbook knowledge base. Returns the best sections, each with a citation like RB-001#Fix."""
    hits = _get().search(query, k=max(1, min(int(k), 5)))
    return [{"citation": h["citation"], "runbook_id": h["runbook_id"], "title": h["title"],
             "section": h["section"], "text": h["text"], "score": round(h["score"], 3)} for h in hits]


if __name__ == "__main__":
    mcp.run()
