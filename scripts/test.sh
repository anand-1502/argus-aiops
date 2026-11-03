#!/usr/bin/env bash
# Run everything that does not need the LLM. torch and xgboost cannot share a process on macOS,
# so the in-process torch tests run in their own pytest invocation.
#   scripts/test.sh          fast suite + retrieval tests + frontend checks
#   scripts/test.sh --agent  also run the slow end-to-end agent acceptance tests (needs Ollama)
set -euo pipefail
cd "$(dirname "$0")/.."
export JAVA_HOME="${JAVA_HOME:-/opt/homebrew/opt/openjdk@17}"
uv run pytest -q
uv run pytest -q -m torch tests/test_kb.py tests/test_cluster.py
if [[ -z "${SKIP_WEB:-}" ]]; then (cd web && npx tsc --noEmit && npx eslint . && echo "web: clean"); fi
if [[ "${1:-}" == "--agent" ]]; then uv run pytest -q -m agent tests/test_agent.py; fi
