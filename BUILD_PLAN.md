# Argus build plan — milestones, done-criteria, resume bullets

**Rule:** never start a milestone until the previous one is demoable
end-to-end. A polished M1–M3 beats a half-finished M1–M5.

---

## M1 — Ingest + Analyze (DA core)

**What gets built:** Download the Loghub HDFS dataset. A Kafka topic
(`raw-logs`) streams the raw log lines in, simulating a live production feed
instead of a static load. A PySpark (local mode) job consumes the stream in
micro-batches, parses each line into a structured event (timestamp,
component, log level, block ID, parsed template), and writes it to Postgres.
Airflow schedules the batch job and a nightly data-quality check. A Next.js
+ TypeScript dashboard (Plotly) reads from the FastAPI backend and shows log
volume over time, the labeled anomaly rate (should track Loghub's published
2.93%), and a breakdown by component.

**How it works end to end:** `docker compose up` → Kafka/Postgres/Qdrant/
Redis/Airflow containers start → a producer script streams the HDFS log
file into Kafka → PySpark consumer parses + writes to Postgres → FastAPI
serves aggregates → dashboard renders them.

**Done when:** one command (`docker compose up`) gets you a running
pipeline, and within a few minutes of streaming, the dashboard shows real
anomaly-rate and volume stats matching the published HDFS benchmark numbers.

**Resume bullets (DA):**
- "Built a Kafka-streaming + PySpark batch-processing pipeline ingesting
  11M+ real production log events into Postgres."
- "Shipped an analytics dashboard (Next.js + TypeScript + Plotly) with
  anomaly-rate and volume trend visualizations over real benchmark data."

---

## M1.5 — BI Export Agent (DA / SDE)

**What gets built:** An MCP tool (`bi_export`) that takes the structured
log/incident data from M1 and generates (a) a Tableau `.hyper` extract via
the free Hyper API, and (b) a Power BI-ready package — clean Parquet/CSV
plus a documented semantic model (table relationships + DAX measure
definitions) that imports into free Power BI Desktop with no manual
modeling. A small rule-based recommender inspects column types/distributions
to suggest chart types and calculated fields for both exports. Exposed as a
button in the dashboard.

**Done when:** clicking the export button produces a `.hyper` file that
opens cleanly in Tableau Public and a package that imports cleanly into
Power BI Desktop, both with suggested visualizations already defined.

**Resume bullets (DA/SDE):** "Built a BI export agent auto-generating
Tableau Hyper extracts and Power BI-ready semantic models with recommended
visualizations from pipeline data."

---

## M2 — Predict (DS / MLE core)

**What gets built:** An XGBoost classifier trained on the labeled HDFS block
sessions (anomaly vs. normal) with cross-validation, logged to MLflow
(metrics, confusion matrix, feature importance, model artifact). An Airflow
DAG retrains the model nightly on newly streamed data. A drift-detection
script compares a rolling window of live predictions against ground truth
and logs a drift metric to MLflow/Phoenix, alerting if it crosses a
threshold. CI blocks promoting a model version to "production" in the MLflow
registry if its eval metrics regress versus the current production model.

**Done when:** one command trains the classifier and logs a reported
F1/precision/recall that can be compared to Loghub's published baselines;
the Airflow DAG is schedulable and runs end-to-end; the drift script
produces a real metric on a held-out shifted sample.

**Resume bullets (DS):** "Trained an XGBoost anomaly classifier on the
Loghub HDFS benchmark (11.17M log messages, 16,838 labeled sessions),
benchmarked against published academic F1 baselines, tracked in MLflow."

**Resume bullets (MLE):** "Built an Airflow-orchestrated retraining
pipeline with automated drift detection and CI-gated model promotion in the
MLflow registry."

---

## M3 — Chat: MCP agent + RAG (AI core)

**What gets built:** Three custom MCP servers (`logs-db`, `kb`, `metrics`)
built with the MCP Python SDK — the agent's *only* way to reach Postgres,
Qdrant, and the simulated metrics store. A LangGraph agent, backed by
Ollama (quantized Llama 3.1 8B / Mistral 7B), takes a question like "why did
block X fail at time T" and: calls `logs-db` to pull the relevant log
events, calls `kb` (Qdrant + FAISS-assisted clustering + bge-reranker) to
retrieve relevant runbook sections, calls `metrics` for correlated service
signals, then drafts a postmortem that explicitly cites the log lines and
runbook sections it used as evidence.

**Done when:** for a seeded known-root-cause incident, the agent produces a
postmortem whose cited evidence is verifiably correct, using only MCP tool
calls (no raw SQL/API calls anywhere in agent code).

**Resume bullets (AI):**
- "Designed and shipped 3 custom MCP servers connecting an LLM agent to
  production log, knowledge-base, and metrics systems under access control."
- "Built a LangGraph incident-triage agent with hybrid retrieval (Qdrant +
  FAISS + bge-reranker) and self-hosted inference via Ollama."

---

## M4 — Ship: Evals + Observability + Deploy (SDE / FDE core)

**What gets built:** A nightly Airflow DAG runs RAGAS + DeepEval against a
held-out set of known-root-cause incidents, scoring the agent's postmortem
groundedness/faithfulness, with results tracked over time and visualized in
Phoenix. Every agent run is traced via OpenTelemetry into Arize Phoenix
(latency, token cost, tool calls, retrieved context). GitHub Actions CI runs
the eval suite as a gate — a PR that regresses groundedness or classifier
accuracy fails the build. The whole stack reproduces from a clean clone via
`docker compose up`.

**Done when:** the Phoenix dashboard shows a real eval-score trend line over
multiple nightly runs, and a deliberately regressed test PR is blocked by CI.

**Resume bullets (SDE):** "Shipped a full-stack platform (FastAPI +
Strawberry GraphQL, Next.js/TypeScript, Postgres/Redis) with OpenTelemetry/
Phoenix tracing and a CI eval-gate blocking regressions."

**Resume bullets (FDE, all variants):** "Built evals engineering practice —
golden dataset, regression suite, tracked failure modes over time — the
loop FDE technical screens test for."

---

## M5 — Stretch: multi-tenant Kind deploy

**What gets built:** Terraform provisions a local Kind Kubernetes cluster.
Helm charts deploy the full stack as 3 separate releases, each simulating a
different "client" — different MCP server configs, different log-component
taxonomies, different runbook knowledge bases.

**Done when:** 3 Helm releases run simultaneously on the local Kind cluster,
each demonstrably configured differently, documented with a short walkthrough
in the README.

**Skip if M1–M4 aren't fully polished — a half-done K8s layer hurts more
than it helps in an interview.**

**Resume bullets (FDE, all variants):** "Deployed and customized the
platform across 3 simulated client environments via Kubernetes (Kind) and
Helm, provisioned with Terraform."

---

## Datasets used (all free, all real)

- **Loghub HDFS** (logpai/loghub) — 11.17M log messages, 16,838 labeled
  block sessions — flagship dataset for M1–M3.
- Runbook/knowledge-base text — written/curated troubleshooting docs for the
  simulated microservice topology, used as the RAG corpus for `kb`.

## Explicitly cut (documented, not built)

- **vLLM** — needs GPU to be practical; Ollama used instead, same
  self-hosted-inference bullet, zero cost.
- **AWS/GCP free tier, Snowflake, BigQuery** — real billing-surprise risk;
  Terraform targets Kind/local only, PySpark local mode replaces
  Spark-on-cluster.
- **Google Borg traces** — real and relevant, but the 2019 trace is 2.8 TiB,
  not practical at $0.
- **CI Failure Predictor (TravisTorrent)** — a solid alternative project,
  kept as a documented "next extension" rather than the flagship.
