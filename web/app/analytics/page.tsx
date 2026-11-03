"use client";

import { useEffect, useState } from "react";
import Plot from "@/components/Plot";
import { api, type ComponentHealth, type Kpis, type TrendRow, type WindowsInfo } from "@/lib/api";
import PageHeader from "@/components/PageHeader";
import Term from "@/components/Term";

const MODELS = ["mart_kpis", "mart_anomaly_trend", "mart_component_health", "mart_incident_windows", "mart_window_sensitivity", "fact_hourly_events", "dim_block", "int_block_sessions", "stg_events"];
const DEFAULT_GAP = 30;
const fmt = (n: number) => n.toLocaleString("en-US");

function Card({ label, value, sub, id }: { label: string; value: string; sub?: string; id: string }) {
  return (
    <div className="rounded-lg border border-neutral-800 p-4" data-testid={id}>
      <div className="text-sm text-neutral-400">{label}</div>
      <div className="mt-1 text-2xl font-semibold tabular-nums">{value}</div>
      {sub && <div className="mt-1 text-xs text-neutral-400">{sub}</div>}
    </div>
  );
}

export default function Analytics() {
  const [k, setK] = useState<Kpis | null>(null);
  const [trend, setTrend] = useState<TrendRow[]>([]);
  const [comps, setComps] = useState<ComponentHealth[]>([]);
  const [win, setWin] = useState<WindowsInfo | null>(null);
  const [model, setModel] = useState(MODELS[0]);
  const [sql, setSql] = useState("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([api.kpis(), api.trend(), api.componentHealth(), api.windows()])
      .then(([a, b, c, d]) => { setK(a); setTrend(b); setComps(c); setWin(d); })
      .catch((e: Error) => setError(e.message));
  }, []);
  useEffect(() => {
    api.sql(model).then((r) => setSql(r.sql)).catch(() => setSql("-- could not load"));
  }, [model]);

  if (error) return <p className="text-red-400">Could not load analytics: {error}. Run <code>dbt build</code> first.</p>;
  if (!k || !win) return <p className="text-neutral-400">Loading…</p>;

  const spikes = trend.filter((t) => t.is_spike);

  return (
    <div className="space-y-8">
      <PageHeader
        title="When and where the failures happen"
        takeaway={<>Counting incidents depends on one choice: how close in time two failures must be to count as one. So this page shows the whole range, not one flattering number.</>}
      >
        Everything here is calculated in SQL with <Term k="dbt">dbt</Term> from the 11 million events: failure rate by hour, which components fail most, and how many
        separate incidents the failures add up to. 44 automated data tests check every build, including that totals match the raw table. The SQL for each number is at the bottom.
      </PageHeader>

      <section className="grid grid-cols-2 gap-4 md:grid-cols-5">
        <Card id="kpi-rate" label="Failure rate" value={`${k.anomaly_rate_pct}%`} sub={`failed blocks: ${fmt(k.anomalous_blocks)} of ${fmt(k.total_blocks)}`} />
        <Card id="kpi-windows" label="Incidents (time windows)" value={fmt(k.incident_windows)} sub={`failures within ${DEFAULT_GAP} s of each other count as one`} />
        <Card id="kpi-reduction" label="Alert reduction" value={`${k.alert_reduction_pct}%`} sub="fewer alerts if each incident paged once, not each block" />
        <Card id="kpi-median" label="Typical incident size" value={`${k.median_blocks_per_window} blocks`} sub={`p95 ${Math.round(k.p95_blocks_per_window)}, max ${fmt(k.largest_window_blocks)}`} />
        <Card id="kpi-worst" label="Worst hour" value={k.worst_hour.slice(5, 16).replace("T", " ")} sub="highest share of failing events" />
      </section>

      <section>
        <h2 className="mb-1 text-lg font-medium">Hourly failure rate</h2>
        <p className="mb-2 text-sm text-neutral-400">The share of log events that belong to failed blocks, hour by hour. The blue line smooths it over 3 hours; red dots are unusually bad hours (more than 2 standard deviations above average): {spikes.length} of {trend.length}.</p>
        <Plot
          data={[
            { x: trend.map((t) => t.hour_ts), y: trend.map((t) => t.anomaly_rate), type: "scatter", mode: "lines", name: "hourly rate", line: { color: "#525252" } },
            { x: trend.map((t) => t.hour_ts), y: trend.map((t) => t.moving_avg_3h), type: "scatter", mode: "lines", name: "3h moving average", line: { color: "#38bdf8", width: 3 } },
            { x: spikes.map((t) => t.hour_ts), y: spikes.map((t) => t.anomaly_rate), type: "scatter", mode: "markers", name: "spike", marker: { color: "#f87171", size: 10 } },
          ]}
          layout={{ yaxis: { tickformat: ".1%", title: { text: "share in failed blocks" } }, showlegend: true, legend: { orientation: "h", y: -0.2 } }}
        />
      </section>

      <section>
        <h2 className="mb-1 text-lg font-medium">Which components account for the failures</h2>
        <p className="mb-2 text-sm text-neutral-400">A few components usually cause most of the failures. Bars are failing events per component; the orange line is the running share of all failures.</p>
        <Plot
          data={[
            { x: comps.map((c) => c.component), y: comps.map((c) => c.anomalous_events), type: "bar", name: "anomalous events", marker: { color: "#818cf8" } },
            { x: comps.map((c) => c.component), y: comps.map((c) => c.cumulative_pct), type: "scatter", mode: "lines+markers", name: "cumulative %", yaxis: "y2", line: { color: "#f59e0b" } },
          ]}
          layout={{ margin: { l: 60, r: 50, t: 10, b: 110 }, xaxis: { tickangle: -30 }, yaxis2: { overlaying: "y", side: "right", range: [0, 100], tickvals: [0, 25, 50, 75, 100], ticksuffix: "%", showgrid: false }, showlegend: true, legend: { orientation: "h", y: 1.15 } }}
        />
      </section>

      <section>
        <h2 className="mb-1 text-lg font-medium">How much does the incident count depend on the time gap?</h2>
        <p className="mb-2 text-sm text-neutral-400" data-testid="sensitivity-note">
          The alert reduction depends on how close in time two anomalous blocks must be to count as one incident. Anomalous blocks start a median of 2 seconds apart,
          so the answer ranges from {win.sensitivity[0].reduction_pct}% (1s) to {win.sensitivity[win.sensitivity.length - 1].reduction_pct}% (5 min). The dashboard uses {DEFAULT_GAP}s.
          This measures clustering in labelled benchmark data, not a measured drop in real pages.
        </p>
        <Plot
          data={[{ x: win.sensitivity.map((s) => `${s.gap_seconds}s`), y: win.sensitivity.map((s) => s.windows), type: "bar", marker: { color: win.sensitivity.map((s) => (s.gap_seconds === DEFAULT_GAP ? "#38bdf8" : "#525252")) }, text: win.sensitivity.map((s) => `${fmt(s.windows)} (${s.reduction_pct}%)`), textposition: "outside" }]}
          layout={{ yaxis: { type: "log", tickvals: [10, 100, 1000, 10000], ticktext: ["10", "100", "1,000", "10,000"], title: { text: "incident windows (log scale)" } }, xaxis: { title: { text: "gap that joins two blocks into one window" } } }}
        />
        <table className="mt-3 w-full text-sm">
          <thead className="text-left text-neutral-400"><tr><th>Start</th><th>End</th><th>Span (min)</th><th>Anomalous blocks</th></tr></thead>
          <tbody>
            {win.top.map((w) => (
              <tr key={w.window_id} className="border-t border-neutral-800">
                <td>{w.start_ts.slice(5, 19).replace("T", " ")}</td>
                <td>{w.end_ts.slice(5, 19).replace("T", " ")}</td>
                <td className="tabular-nums">{w.span_minutes.toFixed(1)}</td>
                <td className="tabular-nums">{fmt(w.anomalous_blocks)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <section>
        <h2 className="mb-2 text-lg font-medium">The SQL behind each number</h2>
        <div className="mb-2 flex flex-wrap gap-2">
          {MODELS.map((m) => (
            <button key={m} onClick={() => setModel(m)} className={`rounded border px-2 py-1 font-mono text-xs ${m === model ? "border-sky-500 text-sky-300" : "border-neutral-700 text-neutral-400 hover:border-neutral-500"}`}>{m}</button>
          ))}
        </div>
        <pre className="max-h-96 overflow-auto rounded-lg border border-neutral-800 bg-neutral-900 p-4 text-xs leading-relaxed text-neutral-200" data-testid="sql-view">{sql}</pre>
      </section>
    </div>
  );
}
