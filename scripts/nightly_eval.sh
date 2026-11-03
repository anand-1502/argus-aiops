#!/usr/bin/env bash
# Nightly agent eval: runs every golden incident, judges groundedness, records the run (MLflow + eval/history.json).
# Cron:  0 3 * * *  /path/to/argus-aiops/scripts/nightly_eval.sh >> eval/nightly.log 2>&1
# (Phase 5 turns this into an Airflow DAG that calls the same command.)
set -euo pipefail
cd "$(dirname "$0")/.."
export ARGUS_TRACE=1
uv run python -m eval.run_eval --split all --judge --label "nightly-$(date +%Y%m%d)"
