# Customer onboarding playbook

How to take Argus from "a new customer says yes" to "their on-call team trusts it". Every step names the file or command that
does it in this repository. The three simulated clients (`acme`, `globex`, `initech`) were onboarded this way; no real customer
has been, so treat the timings and thresholds as starting points.

## 1. Discovery (day 0 to 1)
Ask, and write the answers into the client's values file as comments:
- Which system produces the logs, in what format, and how much per day?
- Who is on call, how do they get paged, and what do they read first?
- What do they call their components and teams? (becomes the **taxonomy**)
- What runbooks exist, who owns them, and are they current? (becomes the **knowledge base**)
- Which data may the AI read, and which tools should it never have? (becomes the **MCP allow-list**)
- What counts as success, and how will they judge it? (becomes the **acceptance test**)

## 2. Data access
Give the deployment read-only credentials to a log store or a replicated copy. Never write access, never production credentials
in the repository. The agent does not hold credentials at all: only the MCP servers do.

## 3. Check the log format
Run a sample through the parser. If it is not the HDFS format, the generic parser path (Drain3, planned for the upload flow)
produces templates, and `python -m ingest.cluster` merges near-duplicates. Check the number of templates is plausible (tens to a
few hundred, not thousands).

## 4. Map their vocabulary
Create `deploy/helm/values-<client>.yaml`:
```yaml
tenant: Client Name
kb: client                      # folder under deploy/helm/argus/kbs/
taxonomy:                       # their component names -> their groups
  dfs.FSNamesystem: Metadata plane
mcp:
  maxRows: 100                  # the most rows any tool may return
  allowedTools: "get_block_events,get_block_label,search_runbooks"   # empty means all
webNodePort: 30084
```

## 5. Load their runbooks
Put their documents in `deploy/helm/argus/kbs/<client>/` in the runbook format (`kb/runbooks/RB-001.md` is the template:
symptom, likely causes, checks, fix, escalate). Prefer five accurate runbooks over thirty stale ones. Add client-specific
procedures such as escalation paths or change-freeze rules (see `RB-901` for Globex and `RB-902` for Initech).

## 6. Security review
Show the client what the AI can do, in their terms:
- the exact tool list (`ARGUS_ALLOWED_TOOLS`) and the row cap (`ARGUS_MAX_ROWS`),
- that agent code has no database client (a test enforces this),
- the audit log, one line per tool call, including refused ones.

## 7. Deploy
```bash
helm install argus-<client> deploy/helm/argus -f deploy/helm/values-<client>.yaml -n <client> --create-namespace
```
or add the client to `local.clients` in `deploy/terraform/main.tf` and `terraform apply`. `tests/test_helm.py` checks that each
release differs from the others in the ways the client asked for.

## 8. Acceptance test on their own incidents
Ask for 10 to 30 past incidents with a known cause. Add them to a client golden set in the format of `eval/golden.json` and run
`python -m eval.run_eval`. Agree the pass line **before** running it (for example: right runbook on at least 80%, citations
verified on at least 90%). Report misses honestly; usually they point to a missing or ambiguous runbook, not a model problem.

## 9. Handover
- Walk the on-call team through one live investigation, including the MCP call panel.
- Show them how to read a citation and how to tell when the agent is wrong (an unverified badge, a runbook that does not match).
- Leave the KPI dictionary (`docs/KPI_DICTIONARY.md`) so everyone uses the same numbers.

## 10. After go-live
- Weekly for the first month: review every postmortem the team marked wrong, and fix the runbook or the retrieval.
- Re-run the eval after any runbook change; CI refuses to merge a change that lowers a gated metric.
- Review drift monthly (`python -m ml.drift`). A data-drift warning with stable F1 is a nudge, not an emergency.

## What this playbook does not cover
Authentication and single sign-on, multi-user permissions, data retention policy, and integration with the client's paging and
ticketing tools. These are the first things a real engagement would add.
