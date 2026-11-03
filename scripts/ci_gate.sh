#!/usr/bin/env bash
# The regression gate. Runs the same way on a laptop and in GitHub Actions.
#   classifier  trains on a committed 20k-block sample and requires an F1/recall floor
#   retrieval   loads 30 golden incidents into an empty database and checks the retrieval chain end to end
#   results     checks the stored agent eval is fresh for this code, above floors, and not regressed
# Locally it uses a separate `argus_ci` database, so your real data is never touched.
set -euo pipefail
cd "$(dirname "$0")/.."
export PGDATABASE="${PGDATABASE:-argus_ci}"
uv run python -m eval.gate classifier
uv run python -m eval.load_fixtures
uv run python -m kb.index
uv run python -m eval.gate retrieval
uv run python -m eval.gate results
