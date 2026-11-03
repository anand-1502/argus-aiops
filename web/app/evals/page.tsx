"use client";

import { useEffect, useState } from "react";
import Plot from "@/components/Plot";
import { api, type EvalSummary } from "@/lib/api";
import PageHeader from "@/components/PageHeader";
import Term from "@/components/Term";

const LABELS: Record<string, string> = {
  runbook_accuracy: "Right runbook",
  verified_rate: "Citations verified",
  signature_cited_rate: "Failure line cited",
  deepeval_faithfulness: "Faithfulness (DeepEval)",
  ragas_faithfulness: "Faithfulness (RAGAS)",
};
const MEANING: Record<string, string> = {
  runbook_accuracy: "Chose the fix procedure that matches the failure.",
  verified_rate: "Every cited log line or runbook section really exists in what it retrieved.",
  signature_cited_rate: "Quoted the log line that actually shows the failure.",
  deepeval_faithfulness: "Claims backed by evidence. A rough score from a small AI judge.",
  ragas_faithfulness: "Same idea, second judge.",
};
const COLORS = ["#38bdf8", "#34d399", "#f59e0b", "#a78bfa", "#f87171"];
const pct = (x: number) => `${(x * 100).toFixed(1)}%`;

export default function Evals() {
  const [d, setD] = useState<EvalSummary | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.evals().then(setD).catch((e: Error) => setError(e.message));
  }, []);

  if (error) return <p className="text-red-400">Could not load evals: {error}</p>;
  if (!d) return <p className="text-neutral-400">Loading…</p>;
  if (!d.latest) return <p className="text-neutral-400">No eval has been run yet. Run <code>uv run python -m eval.run_eval --judge</code>.</p>;

  const m = d.latest.metrics;
  const keys = Object.keys(LABELS).filter((k) => k in m);
  const unseen = d.incidents.filter((i) => i.split === "heldout" && i.scores);
  const unseenRight = unseen.filter((i) => i.scores?.runbook_correct).length;
  const unseenVerified = unseen.filter((i) => i.scores?.verified).length;

  return (
    <div className="space-y-8">
      <PageHeader
        title="How good is the agent?"
        takeaway={
          unseen.length > 0 ? (
            <>
              <b>The fair test:</b> on the {unseen.length} <Term k="Held-out">unseen</Term> incidents it chose the right runbook {unseenRight} times and had every
              citation verified {unseenVerified} times. Each miss is listed in the table below.
            </>
          ) : undefined
        }
      >
        The agent was run on {m.n_incidents} incidents where the right answer is known. Six were used while building it; the rest it had never seen. CI blocks any change
        that drops a score below its floor or below the recorded baseline.
        <span className="mt-2 block text-sm text-neutral-300">
          Latest run <span className="font-mono">{d.latest.label}</span>, {d.latest.at.slice(0, 16).replace("T", " ")} UTC, model {d.latest.model}.
        </span>
      </PageHeader>

      <section className="grid grid-cols-2 gap-4 md:grid-cols-5" data-testid="eval-cards">
        {keys.map((k) => {
          const floor = d.thresholds.agent[k];
          const ok = floor === undefined || m[k] >= floor;
          return (
            <div key={k} className="rounded-lg border border-neutral-800 p-4">
              <div className="text-sm text-neutral-400">{LABELS[k]}</div>
              <div className="mt-1 text-2xl font-semibold tabular-nums">{pct(m[k])}</div>
              <div className="mt-1 text-xs text-neutral-300">{MEANING[k]}</div>
              <div className={`mt-1 text-xs ${ok ? "text-emerald-400" : "text-red-400"}`}>
                {floor === undefined ? "reported, not gated" : `${ok ? "above" : "BELOW"} floor ${pct(floor)}`}
              </div>
            </div>
          );
        })}
      </section>

      <section>
        <h2 className="mb-1 text-lg font-medium">Score trend across runs</h2>
        <p className="mb-2 text-sm text-neutral-400">
          One point per eval run. The faithfulness scores come from a small local judge, so expect noise of a few points between runs.
        </p>
        <Plot
          data={keys.map((k, i) => ({
            x: d.history.filter((h) => k in h.metrics).map((h) => h.at.slice(0, 16).replace("T", " ")),
            y: d.history.filter((h) => k in h.metrics).map((h) => h.metrics[k]),
            type: "scatter" as const,
            mode: "lines+markers" as const,
            name: LABELS[k],
            line: { color: COLORS[i % COLORS.length] },
          }))}
          layout={{ xaxis: { type: "category" }, yaxis: { range: [0, 1.05], tickformat: ".0%" }, showlegend: true, legend: { orientation: "h", y: -0.25 } }}
        />
      </section>

      <section>
        <h2 className="mb-2 text-lg font-medium">Per-incident results (latest run)</h2>
        <div className="overflow-x-auto">
        <table className="w-full text-sm" data-testid="eval-table">
          <thead className="text-left text-neutral-400">
            <tr><th className="py-1">Block</th><th>Split</th><th>Expected</th><th>Chosen</th><th>Verified</th><th>Line cited</th><th>Faithfulness</th><th>s</th></tr>
          </thead>
          <tbody>
            {d.incidents.map((i) => {
              const f = i.judge?.deepeval_faithfulness;
              return (
                <tr key={i.block_id} className="border-t border-neutral-800">
                  <td className="py-1 font-mono text-xs">{i.block_id.slice(0, 18)}…</td>
                  <td>{i.split}</td>
                  <td>{i.expected_runbook}</td>
                  <td className={i.scores?.runbook_correct ? "" : "text-red-400"}>{i.chosen_runbook ?? "crashed"}</td>
                  <td>{i.scores ? (i.scores.verified ? "yes" : "no") : "-"}</td>
                  <td>{i.scores ? (i.scores.signature_cited ? "yes" : "no") : "-"}</td>
                  <td className="tabular-nums">{f == null ? "-" : f.toFixed(2)}</td>
                  <td className="tabular-nums">{i.seconds}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
        </div>
      </section>

      <section className="rounded-lg border border-neutral-800 p-4 text-sm text-neutral-300">
        <h2 className="mb-1 text-lg font-medium text-neutral-100">Traces</h2>
        Every agent run is traced to Arize Phoenix (latency, tokens, tool calls, retrieved context). With the stack running, open{" "}
        <a className="text-sky-400 underline" href={d.phoenix_url} target="_blank" rel="noreferrer">{d.phoenix_url}</a>.
      </section>
    </div>
  );
}
