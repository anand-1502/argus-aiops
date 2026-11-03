#!/usr/bin/env bash
# Nightly retrain: rebuild features from Postgres, train, and promote only if the model does not regress.
# Schedule with cron, e.g.:  0 2 * * *  /path/to/argus-aiops/scripts/retrain.sh >> retrain.log 2>&1
# (Phase 5 replaces this with an Airflow DAG that calls the same command.)
set -euo pipefail
cd "$(dirname "$0")/.."
uv run python -m ml.train --promote
uv run python -m ml.drift
