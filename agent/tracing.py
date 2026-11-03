"""OpenTelemetry tracing to Arize Phoenix. Off unless ARGUS_TRACE=1 (or enable() is called)."""
import os

ENDPOINT = os.environ.get("PHOENIX_COLLECTOR_ENDPOINT", "http://localhost:6006/v1/traces")
_enabled = False


def enable(project: str = "argus") -> bool:
    """Send every LangChain/LangGraph step (LLM calls, token counts, latency) and every MCP call to Phoenix."""
    global _enabled
    if _enabled:
        return True
    from openinference.instrumentation.langchain import LangChainInstrumentor
    from phoenix.otel import register

    provider = register(project_name=project, endpoint=ENDPOINT, auto_instrument=False, batch=False)
    LangChainInstrumentor().instrument(tracer_provider=provider)
    _enabled = True
    return True


def tracer():
    from opentelemetry import trace

    return trace.get_tracer("argus.mcp")


if os.environ.get("ARGUS_TRACE") == "1":
    enable()
