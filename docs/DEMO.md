# Demo walkthrough (about 5 minutes)

A script for showing Argus live or recording it. Every step names the page, what to click and what it proves, so the demo
never claims more than the project does. Screenshots of each page are in `docs/screenshots/`.

## Before you start

```bash
docker compose --profile obs up -d              # Postgres, Redis, Qdrant, Phoenix
OLLAMA_MAX_LOADED_MODELS=1 ollama serve &       # only needed for "Run live"
uv run uvicorn api.main:app --port 8000 &
cd web && npm run dev                           # http://localhost:3000
```

No Docker or model handy? The public static site shows the same pages from recorded data (agent runs, uploads and exports
are read-only there).

## The five minutes

| Time | Page | Do | Say |
| --- | --- | --- | --- |
| 0:00 | **Overview** | Point at the four numbers and the volume chart. | "11.2 million real HDFS log lines, 575 thousand block sessions, 2.93% anomalous. These match the published benchmark exactly, so I can compare against papers." |
| 0:30 | **Analytics** | Click "show the SQL" on a mart. | "This is a dbt star schema with window functions and gaps-and-islands. The incident-window count swings from 9,830 to 18 depending on one gap parameter, so I publish the whole sensitivity curve instead of one flattering number." |
| 1:15 | **Model** | Show F1, the confidence interval and the drift panel. | "F1 0.995, but HDFS is a saturated benchmark, so the interesting parts are the intervals, calibration, SHAP and the promotion gate. Drift flagged a real shift in the data." |
| 1:45 | **Agent** | Pick an incident, hover a citation, open the MCP call table. | "A local 4B model investigates. It can only reach data through three governed MCP servers, and code checks that every citation exists in what those servers returned." |
| 2:45 | **Evals** | Show the four cards and the per-incident table. | "30 incidents. 6 were used to tune the agent, 24 were never seen. 23 of the 24 got the right runbook. The misses are all one runbook, which I can show you." |
| 3:15 | **Pipeline** | Point at which services are up. | "Kafka, Airflow, Phoenix and the model run on demand to fit an 8 GB laptop. Each was run end to end, not just written." |
| 3:45 | **Upload** | Upload `tests/fixtures/modern_app.log`. | "Any log file. It guesses the timestamp format, mines templates with Drain3 and loads into its own isolated schema. It found the planted traffic spike and the rare error with no labels." |
| 4:30 | **Export** | Click Generate. | "Same data as a Tableau extract and a Power BI package, with suggested visuals." |

## Say these out loud

These are the limits. Saying them first is the strongest move in the demo.

- The logs are from 2008. HDFS is the standard benchmark, not a modern system.
- I wrote the runbooks, so a high retrieval score mostly shows the plumbing works. A Hadoop engineer should review them.
- Faithfulness is 0.64 from a noisy 4B judge, and RAGAS could not run on a model that small.
- The business savings page is a model with assumptions you set, not a measurement.
- The three Kubernetes "clients" differ in configuration, not in data.

## Where each claim lives

| Claim | Evidence |
| --- | --- |
| Numbers match the benchmark | `tests/test_api.py::test_summary_matches_published_benchmark` |
| Citations are checked | `agent/verify.py`, `tests/test_verify.py` |
| Agent quality | `eval/results/*-baseline-1.json`, Evals page |
| A regression is blocked | `scripts/ci_gate.sh`, `eval/gate.py` |
| Kafka lost nothing | `tests/test_stream.py` round trip, 50,000 lines in and out |
| Three isolated clients | `deploy/`, `tests/test_helm.py` |
