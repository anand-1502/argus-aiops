# Business requirements: Argus incident intelligence

## 1. Problem
On-call engineers lose time deciding which of thousands of log lines matter, which runbook applies and what to tell the team.
Postmortems are written by hand, after the fact, and rarely cite their evidence. Argus shortens that path and makes every
claim checkable.

## 2. Stakeholders and what each needs
| Stakeholder | Needs | Measured by |
| --- | --- | --- |
| On-call engineer | A likely cause and next step within minutes, with the log lines and runbook section it rests on | Agent runbook accuracy, citations verified rate, agent time per incident |
| SRE lead | Fewer, better-grouped incidents; a view of which components fail | Incident windows, alert reduction, component share of anomalies |
| Engineering manager | Evidence that the tool is accurate before relying on it, and that it does not get worse over time | Eval trend, CI gate status |
| Data and BI analysts | The same numbers in Tableau and Power BI as on the dashboard | Export reconciliation (extract totals equal the database) |
| Platform / customer-facing engineer | A deployment per client with its own vocabulary, limits and runbooks | Helm release differences, tool allow-lists |
| Security / compliance | The AI can only read data through governed, logged tools | MCP allow-list, row caps, audit log |

## 3. Goals and success criteria
| ID | Goal | Success criterion | Where it is checked |
| --- | --- | --- | --- |
| G1 | Reproduce the published benchmark facts | 11,175,629 events, 575,061 blocks, 16,838 anomalous (2.93%) | `tests/test_dataset.py`, dbt test `assert_anomaly_rate_matches_published_benchmark` |
| G2 | Flag failed blocks with accuracy comparable to published work | F1 at or above 0.98 on a held-out 20% | `ml/train.py`, CI classifier gate |
| G3 | Produce a cited postmortem for a failed block | Every citation resolves to retrieved evidence | `agent/verify.py`, eval `verified_rate` |
| G4 | Choose the right runbook | At least 80% on a golden set (floor in `eval/thresholds.json`) | `eval/run_eval.py`, CI results gate |
| G5 | Never regress silently | A pull request that lowers a gated metric fails CI | `eval/gate.py`, `.github/workflows/ci.yml` |
| G6 | Keep AI access governed | Agent code cannot import a database client; tools are allow-listed, capped and audited | `tests/test_verify.py::test_agent_code_never_touches_data_stores_directly`, `tests/test_mcp_servers.py` |

## 4. User stories and acceptance criteria
| ID | Story | Acceptance criteria | Verified by |
| --- | --- | --- | --- |
| US-01 | As an on-call engineer, I pick a failed block and get a root cause, timeline and actions | Postmortem has root cause, timeline, actions; shows which tools were called | `tests/test_agent.py`, Agent page |
| US-02 | As an on-call engineer, I can see the evidence for each claim | Each citation shows its source text on hover; unverifiable citations are marked | `agent/verify.py`, `tests/test_verify.py` |
| US-03 | As an SRE lead, I see failures grouped into incidents, with the parameter stated | Windows shown with the gap used and the full sensitivity curve | dbt model `mart_window_sensitivity`, `tests/test_analytics_api.py` |
| US-04 | As an SRE lead, I see which components carry the anomalies | Pareto chart with running share ending at 100% | dbt test `assert_component_pareto_ends_at_100` |
| US-05 | As a manager, I see whether the agent is getting better or worse | Eval trend across runs with the floors drawn | `eval/history.json`, Evals page |
| US-06 | As a manager, a change that lowers quality cannot be merged | CI fails when a metric is below its floor or below baseline by more than the tolerance | `eval/gate.py` |
| US-07 | As an analyst, I export the data to Tableau or Power BI with suggested visuals | `.hyper` extract and a Power BI package; totals equal the database | `tests/test_bi_hyper.py`, `tests/test_bi_powerbi.py` |
| US-08 | As a customer-facing engineer, I deploy one release per client with that client's vocabulary and limits | Three releases differ in taxonomy, row cap, tool list and runbooks | `tests/test_helm.py` |
| US-09 | As security, I can audit every data access made by the AI | One log line per tool call, including rejected calls | `tests/test_mcp_servers.py::test_bad_input_is_rejected_and_audited` |
| US-10 | As an analyst, I can read the SQL behind any dashboard number | SQL viewer on the Analytics page | `tests/test_analytics_api.py` |

## 5. In scope and out of scope
In scope: the HDFS benchmark logs, a local LLM, simulated service metrics, one agent flow (block failure to postmortem).
Out of scope: live integration with a real paging or ticketing system, authentication and multi-user accounts, any cloud
service, and claims about production savings.

## 6. Assumptions and risks
| # | Assumption or risk | Impact | Mitigation |
| --- | --- | --- | --- |
| A1 | The 2008 HDFS logs resemble modern operational logs | Results may not transfer | Say so plainly; add a second, newer dataset through the upload flow |
| A2 | Runbooks are written by the project author, not an operator | Retrieval scores look better than they would on real documents | Mark as authored; have an operator review before relying on them |
| A3 | A 4B local model is good enough for triage | Hallucinated claims | Citation verification, verbatim key quote, judged faithfulness, eval gate |
| A4 | Incident windows measure real on-call load | Overstated benefit | The KPI states it is clustering of labelled data and shows its sensitivity |
| R1 | An 8 GB laptop is slow | Runs take minutes | Recorded demo runs, and a static site for sharing |

## 7. Business impact (illustrative)
The Business impact page lets a reader enter their own assumptions (minutes to triage by hand, engineer cost, review time with
the agent) and shows what the measured numbers would imply. It is a model, not a measurement of savings.
