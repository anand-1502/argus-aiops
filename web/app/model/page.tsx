"use client";

import { useEffect, useState } from "react";
import Plot from "@/components/Plot";
import { api, type ModelAnalysis, type ModelStatus } from "@/lib/api";
import PageHeader from "@/components/PageHeader";
import Term from "@/components/Term";

const pct = (x: number) => `${(x * 100).toFixed(2)}%`;

function Stat({ label, value, id, note }: { label: React.ReactNode; value: string; id: string; note?: string }) {
  return (
    <div className="rounded-lg border border-neutral-800 p-4" data-testid={id}>
      <div className="text-sm text-neutral-400">{label}</div>
      <div className="mt-1 text-2xl font-semibold tabular-nums">{value}</div>
      {note && <div className="mt-1 text-xs text-neutral-300">{note}</div>}
    </div>
  );
}

export default function Model() {
  const [m, setM] = useState<ModelStatus | null>(null);
  const [a, setA] = useState<ModelAnalysis | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.modelStatus().then(setM).catch((e: Error) => setError(e.message));
    api.modelAnalysis().then(setA).catch(() => {});
  }, []);

  if (error) return <p className="text-red-400">Could not load the model: {error}</p>;
  if (!m) return <p className="text-neutral-400">Loading…</p>;

  const names = ["Argus XGBoost", ...Object.keys(m.baselines)];
  const f1s = [m.metrics.f1, ...Object.values(m.baselines).map((b) => b.f1)];

  return (
    <div className="space-y-8">
      <PageHeader
        title="How well can a classifier spot failed blocks?"
        takeaway={<>It matches or beats the published supervised results on this benchmark. But the benchmark is close to solved, so the more useful parts are below: how sure the score is, how the data drifts, and where the model is wrong.</>}
      >
        An XGBoost model reads each block&apos;s log session and predicts whether it failed. These scores are on the 20% of blocks it never saw while training
        (no block appears on both sides). Live model: version {m.version}.
      </PageHeader>

      <section className="grid grid-cols-2 gap-4 md:grid-cols-4">
        <Stat id="stat-f1" label={<Term k="F1">F1</Term>} value={pct(m.metrics.f1)} note="balance of the two below" />
        <Stat id="stat-precision" label={<Term k="Precision">Precision</Term>} value={pct(m.metrics.precision)} note="flagged blocks that really failed" />
        <Stat id="stat-recall" label={<Term k="Recall">Recall</Term>} value={pct(m.metrics.recall)} note="failed blocks that were caught" />
        <Stat id="stat-cv" label="Cross-validated F1" value={m.cv_f1_mean ? pct(m.cv_f1_mean) : "n/a"} note="same test repeated on 5 splits of the training data" />
      </section>

      <section>
        <h2 className="mb-1 text-lg font-medium">Compared with published baselines</h2>
        <p className="mb-2 text-sm text-neutral-400">
          F1 on HDFS, random 80/20 split of 575,061 sessions (Le &amp; Zhang, ICSE 2022, Table 4). Only the supervised rows are a
          like-for-like comparison. HDFS is close to saturated, so the gaps are small.
        </p>
        <Plot
          data={[{ x: f1s, y: names, type: "bar", orientation: "h", marker: { color: names.map((n) => (n === "Argus XGBoost" ? "#38bdf8" : "#525252")) }, text: f1s.map((v) => v.toFixed(3)), textposition: "outside" }]}
          layout={{ margin: { l: 190, t: 10, r: 40, b: 40 }, xaxis: { range: [0.8, 1.02], title: { text: "F1" } }, yaxis: { autorange: "reversed" } }}
        />
      </section>

      <section>
        <h2 className="mb-1 text-lg font-medium"><Term k="Drift">Drift</Term>: is the data changing?</h2>
        <p className="mb-2 text-sm text-neutral-400">
          Five time windows compared with the first 40% of blocks, using PSI (above the dotted red line, 0.25, is a large shift). The read traffic (&ldquo;Served block&hellip;&rdquo;) fades over the capture, so
          the data shifts, but F1 holds: a <b>warning</b>, not an alert. A deliberately shifted sample is{" "}
          <b className={m.shifted_status === "alert" ? "text-red-400" : ""}>{m.shifted_status ?? "not run"}</b>.
        </p>
        <Plot
          data={[
            { x: m.drift.map((d) => `window ${d.window}`), y: m.drift.map((d) => d.psi_max), type: "bar", name: "max PSI", marker: { color: "#f59e0b" } },
          ]}
          layout={{
            yaxis: { title: { text: "max PSI" } },
            shapes: [{ type: "line", xref: "paper", x0: 0, x1: 1, y0: 0.25, y1: 0.25, line: { color: "#ef4444", dash: "dot" } }],
          }}
        />
        <table className="mt-2 w-full text-sm" data-testid="drift-table">
          <thead className="text-left text-neutral-400">
            <tr><th>Window</th><th>Max PSI</th><th>F1</th><th>Status</th></tr>
          </thead>
          <tbody>
            {m.drift.map((d) => (
              <tr key={d.window} className="border-t border-neutral-800">
                <td>{d.window}</td>
                <td className="tabular-nums">{d.psi_max.toFixed(2)}</td>
                <td className="tabular-nums">{pct(d.f1)}</td>
                <td>{d.alert ? "alert" : d.psi_max > 0.25 ? "warning" : "ok"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      {a && (
        <>
          <section data-testid="analysis">
            <h2 className="mb-1 text-lg font-medium">How sure are we of these scores?</h2>
            <p className="mb-2 text-sm text-neutral-400">
              The <Term k="Bootstrap interval">95% bootstrap intervals</Term> below are on {a.n_test.toLocaleString("en-US")} held-out blocks ({a.n_positive.toLocaleString("en-US")} anomalous):
              F1 {pct(a.confidence_intervals_95.f1[0])} to {pct(a.confidence_intervals_95.f1[1])}, recall {pct(a.confidence_intervals_95.recall[0])} to {pct(a.confidence_intervals_95.recall[1])}.
              The model&apos;s stated confidence is honest (<Term k="Calibration">calibration</Term> error {a.calibration.ece.toFixed(4)}, close to 0 is best).
            </p>
            <table className="w-full text-sm" data-testid="baseline-table">
              <thead className="text-left text-neutral-400">
                <tr><th className="py-1">Alternative</th><th>F1</th><th>Precision</th><th>Recall</th><th>XGBoost minus it (F1, paired bootstrap)</th></tr>
              </thead>
              <tbody>
                {a.baselines.map((b) => (
                  <tr key={b.model} className="border-t border-neutral-800">
                    <td className="py-1">{b.model}</td>
                    <td className="tabular-nums">{b.f1.toFixed(4)}</td>
                    <td className="tabular-nums">{b.precision.toFixed(4)}</td>
                    <td className="tabular-nums">{b.recall.toFixed(4)}</td>
                    <td className="tabular-nums">
                      {b.xgboost_minus_this_f1.mean_diff >= 0 ? "+" : ""}{b.xgboost_minus_this_f1.mean_diff.toFixed(4)} [{b.xgboost_minus_this_f1.lo.toFixed(4)}, {b.xgboost_minus_this_f1.hi.toFixed(4)}]{" "}
                      <span className={b.xgboost_minus_this_f1.significant ? "text-emerald-400" : "text-amber-400"}>{b.xgboost_minus_this_f1.significant ? "significant" : "not significant"}</span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>

          <section>
            <h2 className="mb-1 text-lg font-medium">What drives its predictions (<Term k="SHAP">SHAP</Term>)</h2>
            <p className="mb-2 text-sm text-neutral-400">Longer bar = that log message type moved the prediction more, averaged over 5,000 held-out blocks.</p>
            <Plot
              data={[{ x: a.shap_top.map((s) => s.mean_abs_shap), y: a.shap_top.map((s) => (s.name.length > 60 ? s.name.slice(0, 58) + "…" : s.name)), type: "bar", orientation: "h", marker: { color: "#a78bfa" } }]}
              layout={{ margin: { l: 360, t: 10, r: 10, b: 40 }, yaxis: { autorange: "reversed" } }}
            />
          </section>

          <section>
            <h2 className="mb-1 text-lg font-medium">Is its confidence honest? (<Term k="Calibration">calibration</Term>)</h2>
            <p className="mb-2 text-sm text-neutral-400">Predicted probability against the share that really were anomalous. The diagonal is perfect. Middle bins hold very few blocks, so read them loosely.</p>
            <Plot
              data={[
                { x: [0, 1], y: [0, 1], type: "scatter", mode: "lines", name: "perfect", line: { color: "#525252", dash: "dot" } },
                { x: a.calibration.bins.map((b) => b.mean_pred), y: a.calibration.bins.map((b) => b.frac_pos), type: "scatter", mode: "markers", name: "model (marker size = blocks in the bin)", marker: { size: a.calibration.bins.map((b) => Math.max(6, Math.min(24, Math.log10(b.n + 1) * 5))), color: "#38bdf8" } },
              ]}
              layout={{ xaxis: { title: { text: "mean predicted probability" }, range: [0, 1] }, yaxis: { title: { text: "share actually anomalous" }, range: [0, 1] }, showlegend: true }}
            />
          </section>

          <section data-testid="errors">
            <h2 className="mb-1 text-lg font-medium">Where it is wrong</h2>
            <p className="mb-2 text-sm text-neutral-400">
              {a.errors.n_false_positive} false positives and {a.errors.n_false_negative} false negatives. Several false positives score above 0.99 on blocks labelled normal,
              with the same replication signature as true anomalies. Those are worth checking as possible label noise before blaming the model.
            </p>
            <ul className="space-y-2 text-sm">
              {[...a.errors.false_negatives.map((e) => ({ ...e, kind: "missed failure" })), ...a.errors.false_positives.slice(0, 4).map((e) => ({ ...e, kind: "false alarm" }))].map((e) => (
                <li key={e.block_id} className="rounded border border-neutral-800 p-3">
                  <span className={`mr-2 rounded px-2 py-0.5 text-xs ${e.kind === "missed failure" ? "bg-red-500/15 text-red-300" : "bg-amber-500/15 text-amber-300"}`}>{e.kind}</span>
                  <span className="font-mono text-xs text-neutral-400">{e.block_id.slice(0, 22)}…</span>
                  <span className="ml-2 text-neutral-400">score {e.proba}</span>
                  <div className="mt-1 text-xs text-neutral-400">pushed by: {e.top_features.map((f) => `${f.name.slice(0, 44)} (${f.value.toFixed(0)}, ${f.shap >= 0 ? "+" : ""}${f.shap})`).join("; ")}</div>
                </li>
              ))}
            </ul>
          </section>
        </>
      )}
    </div>
  );
}
