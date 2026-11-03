# KPI dictionary

Every number shown on the dashboard, in the BI export and in reports is defined here once. Each has an owner in the SQL
layer (a dbt model), so two reports cannot disagree. Source model names refer to `dbt/argus/models/`.

| KPI | Business definition | Formula | Source | Grain | Watch out for |
| --- | --- | --- | --- | --- | --- |
| Log events | Parsed log lines processed | `count(*)` of events | `fact_hourly_events.events` | hour x component x level | Lines that do not match the HDFS format are dropped by the parser and never counted |
| Block sessions | Distinct HDFS blocks seen in the logs | `count(distinct block_id)` | `dim_block` | block | 575,061 in the benchmark |
| Anomalous blocks | Blocks the benchmark labels as failed | `count(*) where is_anomaly` | `dim_block` | block | Ground truth from the Loghub labels, not from our model |
| Anomaly rate | Share of blocks that failed | `anomalous_blocks / total_blocks` | `mart_kpis.anomaly_rate_pct` | whole capture | 2.93% matches the published figure. Per **block**, not per log line |
| Hourly anomaly rate | Share of an hour's events that belong to anomalous blocks | `anomalous_events / events` | `mart_anomaly_trend.anomaly_rate` | hour | An event is counted in the hour it was logged, not the hour its block started |
| Spike hour | An hour whose rate is more than 2 standard deviations above the mean | `zscore > 2` | `mart_anomaly_trend.is_spike` | hour | Few data points (about 40 hours), so the z-score is rough |
| Incident window | A run of anomalous blocks where each starts within N seconds of the previous one | gaps-and-islands, N = `incident_gap_seconds` (default 30) | `mart_incident_windows` | window | **Very sensitive to N**: 9,830 windows at 1s, 145 at 30s, 18 at 5 min. See `mart_window_sensitivity` |
| Alert reduction | How much smaller the work queue is if on-call handles one window instead of one block | `1 - windows / anomalous_blocks` | `mart_kpis.alert_reduction_pct` | whole capture | Compares against a hypothetical "alert per anomalous block", not a measured baseline. Changes with N |
| Median / p95 window size | Typical and large-end number of blocks in one window | percentiles of `anomalous_blocks` | `mart_kpis` | whole capture | The mean is skewed by a few very large windows |
| Component share of anomalies | Which components carry the anomalous events | `anomalous_events / total anomalous_events` | `mart_component_health.pct_of_anomalous_events` | component | A component logging a lot is not the same as a component failing |
| Classifier F1 / precision / recall | How well the model flags failed blocks | standard definitions on a held-out 20% of blocks | MLflow run `test_f1`, `test_precision`, `test_recall` | model version | HDFS is close to a solved benchmark, so scores are high for simple models too |
| Agent runbook accuracy | Share of golden incidents where the agent chose the expected runbook | `runbook_correct / n` | `eval/latest.json` | eval run | The first six incidents were used to tune the agent; the other 24 were not |
| Citations verified rate | Share of postmortems where every cited id exists in the evidence the tools returned | `verified / n` | `eval/latest.json` | eval run | Proves the evidence exists, not that every claim follows from it |
| Faithfulness | Share of claims in a postmortem supported by its evidence, judged by an LLM | DeepEval and RAGAS faithfulness | `eval/latest.json` | judged sample | Small local judge, so noisy; RAGAS may fail on a 4B model and is reported with its success count |
| Agent time per incident | Wall-clock seconds from request to a verified postmortem | `seconds` per run | eval results | incident | Measured on an 8 GB laptop; a server would be faster |

## Rules for changing a KPI
1. Change the dbt model, not a report.
2. Update this table in the same pull request.
3. If the change moves a published number, say so in the PR description.
