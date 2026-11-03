"use client";

import { useEffect, useState } from "react";
import { api, STATIC, type AgentRun, type Incident } from "@/lib/api";
import PageHeader from "@/components/PageHeader";
import Term from "@/components/Term";

const SERVER_COLOR: Record<string, string> = {
  "logs-db": "bg-sky-500/15 text-sky-300",
  kb: "bg-violet-500/15 text-violet-300",
  metrics: "bg-emerald-500/15 text-emerald-300",
};

function Citation({ id, run }: { id: string; run: AgentRun }) {
  const ev = run.evidence[id];
  return (
    <span
      title={ev ? ev.text : "not found in the retrieved evidence"}
      className={`mr-2 inline-block cursor-help rounded px-2 py-0.5 font-mono text-xs ${
        ev ? "bg-neutral-800 text-neutral-200" : "bg-red-500/20 text-red-300"
      }`}
    >
      {id.length > 34 ? `…${id.slice(-30)}` : id}
    </span>
  );
}

export default function Agent() {
  const [incidents, setIncidents] = useState<Incident[]>([]);
  const [selected, setSelected] = useState<Incident | null>(null);
  const [run, setRun] = useState<AgentRun | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.incidents().then((i) => {
      setIncidents(i);
      if (i[0]) pick(i[0]);
    }).catch((e: Error) => setError(e.message));
  }, []);

  function pick(i: Incident) {
    setSelected(i);
    setRun(null);
    setError(null);
    if (i.recorded) api.run(i.block_id).then(setRun).catch((e: Error) => setError(e.message));
  }

  async function live() {
    if (!selected) return;
    setBusy(true);
    setError(null);
    try {
      setRun(await api.investigate(selected.block_id));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const pm = run?.postmortem;

  return (
    <div className="space-y-6">
      <PageHeader
        title="Watch an AI investigate a failed block"
        takeaway={
          <>
            The green badge means code checked every <Term k="Citation">citation</Term> against what the AI actually retrieved. That proves the evidence exists,
            not that every conclusion follows from it, which is why the Evals page also scores faithfulness.
          </>
        }
      >
        Pick a failed block on the left. The card shows the AI&apos;s write-up: the root cause, a timeline and what to do next. Hover any grey chip to read the exact
        log line or <Term k="Runbook">runbook</Term> section it cites.
      </PageHeader>

      {error && <p className="text-red-400">{error}</p>}

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[260px_minmax(0,1fr)]">
        <aside className="space-y-2" data-testid="incident-list">
          <div className="text-sm text-neutral-300">Failed blocks to investigate</div>
          {incidents.map((i) => (
            <button
              key={i.block_id}
              onClick={() => pick(i)}
              className={`w-full rounded-lg border p-3 text-left text-sm ${
                selected?.block_id === i.block_id ? "border-sky-500 bg-sky-500/10" : "border-neutral-800 hover:border-neutral-600"
              }`}
            >
              <div className="font-mono text-xs text-neutral-300">{i.block_id.slice(0, 22)}…</div>
              <div className="mt-1 line-clamp-2 text-neutral-400">{i.signature_line.slice(0, 80)}</div>
            </button>
          ))}
        </aside>

        <section className="space-y-6">
          {selected && !run && !busy && (
            <p className="text-neutral-400">
              {selected.recorded ? "Loading…" : "No recording yet."}
            </p>
          )}
          {busy && <p className="text-amber-400">Investigating live on the local model. This takes a minute or two…</p>}

          {pm && run && (
            <>
              <div className="flex flex-wrap items-center gap-3">
                <span
                  data-testid="verified-badge"
                  className={`rounded-full px-3 py-1 text-xs ${
                    run.verification.ok ? "bg-emerald-500/15 text-emerald-300" : "bg-red-500/15 text-red-300"
                  }`}
                >
                  {run.verification.ok ? "Citations verified" : `Not verified: ${run.verification.reason}`}
                </span>
                <span className="text-xs text-neutral-400">
                  model {run.model ?? "n/a"} · {run.seconds ? `${run.seconds}s` : "live"} · runbook {pm.runbook_id}
                </span>
                <button
                  onClick={live}
                  disabled={busy || STATIC}
                  title={STATIC ? "Needs the local model: run Argus locally" : undefined}
                  className="ml-auto rounded border border-neutral-700 px-3 py-1 text-xs hover:border-neutral-500 disabled:opacity-50"
                >
                  Run live
                </button>
              </div>

              <div className="rounded-lg border border-neutral-800 p-5" data-testid="postmortem">
                <h2 className="text-lg font-medium">Root cause</h2>
                <p className="mt-1">{pm.root_cause}</p>
                <h3 className="mt-4 text-sm font-medium text-neutral-400">Summary</h3>
                <p className="mt-1 text-neutral-200">{pm.summary}</p>
                <h3 className="mt-4 text-sm font-medium text-neutral-400">Timeline</h3>
                <ul className="mt-1 list-disc space-y-1 pl-5 text-neutral-200">
                  {pm.timeline.map((t, i) => <li key={i}>{t}</li>)}
                </ul>
                <h3 className="mt-4 text-sm font-medium text-neutral-400">Recommended actions</h3>
                <ul className="mt-1 list-disc space-y-1 pl-5 text-neutral-200">
                  {pm.recommended_actions.map((t, i) => <li key={i}>{t}</li>)}
                </ul>
                <h3 className="mt-4 text-sm font-medium text-neutral-400">Evidence cited (hover to read)</h3>
                <div className="mt-2">
                  {pm.citations.map((c) => <Citation key={c} id={c} run={run} />)}
                </div>
                <p className="mt-3 border-l-2 border-sky-500 pl-3 text-sm text-neutral-300">
                  Key line <span className="font-mono text-xs text-neutral-400">{pm.key_evidence_id.slice(-24)}</span>: &ldquo;{pm.key_evidence_quote}&rdquo;
                </p>
              </div>

              <div data-testid="mcp-panel">
                <h2 className="mb-2 text-lg font-medium">What it looked up ({run.trace.length} calls)</h2>
                <p className="mb-2 text-sm text-neutral-400">
                  Every lookup the agent made, through three <Term k="MCP">MCP</Term> tool servers: logs, runbooks and metrics. It has no other way to reach the data.
                </p>
                <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead className="text-left text-neutral-400">
                    <tr><th className="py-1">Server</th><th>Tool</th><th>Arguments</th><th>Rows</th><th>ms</th></tr>
                  </thead>
                  <tbody>
                    {run.trace.map((c, i) => (
                      <tr key={i} className="border-t border-neutral-800 align-top">
                        <td className="py-1">
                          <span className={`rounded px-2 py-0.5 text-xs ${SERVER_COLOR[c.server] ?? ""}`}>{c.server}</span>
                        </td>
                        <td className="font-mono text-xs">{c.tool}</td>
                        <td className="max-w-md truncate font-mono text-xs text-neutral-400" title={JSON.stringify(c.args)}>
                          {JSON.stringify(c.args)}
                        </td>
                        <td className="tabular-nums">{c.rows ?? "-"}</td>
                        <td className="tabular-nums">{c.ms}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                </div>
              </div>
            </>
          )}
        </section>
      </div>
    </div>
  );
}
