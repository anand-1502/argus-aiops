"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import Plot from "@/components/Plot";
import PageHeader from "@/components/PageHeader";
import Term from "@/components/Term";
import { GLOSSARY } from "@/lib/glossary";
import { api, type Clusters, type Count, type EvalSummary, type LiveStatus, type ModelStatus, type Summary, type VolumePoint } from "@/lib/api";

const STEPS = [
  { href: "/model", name: "Detect", text: "A classifier flags which blocks failed, using only the log lines." },
  { href: "/agent", name: "Investigate", text: "A local AI reads the logs, finds the runbook that fits and writes the root cause." },
  { href: "/evals", name: "Check", text: "Code confirms every citation is a real log line. A test set scores the whole agent." },
  { href: "/pipeline", name: "Operate", text: "Kafka, Airflow, Kubernetes and a CI gate keep it running and stop regressions." },
];

function LivePanel() {
  const [live, setLive] = useState<LiveStatus | null>(null);

  useEffect(() => {
    let stop = false;
    const tick = () => api.live().then((l) => !stop && setLive(l)).catch(() => {});
    tick();
    const id = setInterval(tick, 2000);
    return () => {
      stop = true;
      clearInterval(id);
    };
  }, []);

  if (!live) return null;
  return (
    <section className="rounded-lg border border-neutral-800 p-5" data-testid="live-panel">
      <div className="flex flex-wrap items-center gap-3">
        <h2 className="text-lg font-medium">Live feed</h2>
        <span className={`rounded-full px-2 py-0.5 text-xs ${live.running ? "bg-emerald-500/15 text-emerald-300" : "bg-neutral-800 text-neutral-300"}`}>
          {live.running ? "replaying" : "idle"}
        </span>
        <span className="ml-auto text-sm tabular-nums text-neutral-300" data-testid="live-events">
          {live.events.toLocaleString("en-US")} events in {live.batches} batches
        </span>
      </div>
      <p className="mt-1 max-w-3xl text-sm text-neutral-300">
        The real logs replayed in order, as if they were arriving now. Each bar is one batch of log lines; the red part belongs to blocks that failed.
      </p>
      {live.recent.length > 0 ? (
        <Plot
          data={[
            { x: live.recent.map((b) => b.batch), y: live.recent.map((b) => b.events - b.anomalous_events), type: "bar", name: "normal", marker: { color: "#38bdf8" } },
            { x: live.recent.map((b) => b.batch), y: live.recent.map((b) => b.anomalous_events), type: "bar", name: "failed blocks", marker: { color: "#f87171" } },
          ]}
          layout={{ barmode: "stack", margin: { t: 10, r: 10, b: 30, l: 50 }, showlegend: true, legend: { orientation: "h" }, xaxis: { title: { text: "batch" } } }}
        />
      ) : (
        <p className="mt-3 text-sm text-neutral-300">
          Nothing is replaying. Start it with <code className="font-mono">uv run python -m ingest.replay --reset</code> and this chart fills in.
        </p>
      )}
    </section>
  );
}

export default function Overview() {
  const [summary, setSummary] = useState<Summary | null>(null);
  const [volume, setVolume] = useState<VolumePoint[]>([]);
  const [components, setComponents] = useState<Count[]>([]);
  const [clusters, setClusters] = useState<Clusters | null>(null);
  const [model, setModel] = useState<ModelStatus | null>(null);
  const [evals, setEvals] = useState<EvalSummary | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.clusters().then(setClusters).catch(() => {});
    api.modelStatus().then(setModel).catch(() => {});
    api.evals().then(setEvals).catch(() => {});
    Promise.all([api.summary(), api.volume("hour"), api.components()])
      .then(([s, v, c]) => {
        setSummary(s);
        setVolume(v);
        setComponents(c);
      })
      .catch((e: Error) => setError(e.message));
  }, []);

  if (error) {
    return <p className="text-red-400">Could not reach the API: {error}. Is it running on port 8000?</p>;
  }
  if (!summary) return <p className="text-neutral-300">Loading the dashboard…</p>;

  const fmt = (n: number) => n.toLocaleString("en-US");
  const heldout = evals?.incidents.filter((i) => i.split === "heldout" && i.scores) ?? [];
  const right = heldout.filter((i) => i.scores?.runbook_correct).length;
  const verified = heldout.filter((i) => i.scores?.verified).length;
  const totalEvents = components.reduce((a, c) => a + c.events, 0);
  const top3 = components.slice(0, 3);
  const top3Share = totalEvents ? Math.round((100 * top3.reduce((a, c) => a + c.events, 0)) / totalEvents) : null;

  return (
    <div className="space-y-10">
      <PageHeader
        title="From raw server logs to a cited root cause"
        takeaway={
          <>
            <b>Why it matters:</b> when a system fails at 3 a.m., someone has to read thousands of log lines to find out why. Argus does the first pass,
            and shows its evidence so a human can check it quickly.
          </>
        }
      >
        This is {fmt(summary.events)} real log lines from a <Term k="HDFS">Hadoop file-storage cluster</Term>, recorded in 2008 and still the standard
        benchmark for this problem. Argus finds the <Term k="Block">blocks</Term> that failed, then an AI running on this laptop investigates each one and
        writes up the cause, quoting the log lines it relied on.
      </PageHeader>

      <section className="space-y-4" data-testid="how-it-works">
        <h2 className="text-lg font-medium">How it works</h2>
        <ol className="grid divide-y divide-neutral-800 rounded-lg border border-neutral-800 md:grid-cols-4 md:divide-x md:divide-y-0">
          {STEPS.map((s, i) => (
            <li key={s.name} className="p-4">
              <Link href={s.href} className="font-medium text-sky-300 underline-offset-4 hover:underline">
                {i + 1}. {s.name}
              </Link>
              <p className="mt-1 text-sm leading-relaxed text-neutral-300">{s.text}</p>
            </li>
          ))}
        </ol>
        <div className="flex flex-wrap items-center gap-x-6 gap-y-2 text-sm">
          <Link href="/agent" className="rounded bg-sky-600 px-4 py-2 font-medium text-white hover:bg-sky-500" data-testid="start-here">
            Watch the agent investigate a failure
          </Link>
          <Link href="/evals" className="text-sky-300 underline underline-offset-4">See how well it scores</Link>
          <Link href="/upload" className="text-sky-300 underline underline-offset-4">Try it on a log file</Link>
        </div>
      </section>

      <section className="max-w-3xl space-y-3" data-testid="findings">
        <h2 className="text-lg font-medium">What it found</h2>
        <ul className="space-y-3 text-base leading-relaxed text-neutral-200">
          <li>
            <b>{summary.anomaly_rate_pct}% of blocks failed</b> ({fmt(summary.anomalous_blocks)} of {fmt(summary.blocks)}).
            {model && (
              <>
                {" "}A classifier spots them with <Term k="F1">F1</Term> {model.metrics.f1.toFixed(3)} and <Term k="Recall">recall</Term>{" "}
                {(model.metrics.recall * 100).toFixed(1)}%. That part is nearly solved on this benchmark, so the interesting work is what comes next.{" "}
                <Link href="/model" className="text-sky-300 underline underline-offset-4">Model details</Link>
              </>
            )}
          </li>
          {heldout.length > 0 && (
            <li>
              <b>On {heldout.length} incidents it had never seen, the agent chose the right fix in {right}</b>, and every citation checked out in {verified}.
              The misses are listed, not hidden.{" "}
              <Link href="/evals" className="text-sky-300 underline underline-offset-4">Eval results</Link>
            </li>
          )}
          <li>
            <b>A change that makes the agent worse is blocked</b> before it merges, by a gate that compares against a recorded baseline.{" "}
            <Link href="/pipeline" className="text-sky-300 underline underline-offset-4">How it is run</Link>
          </li>
        </ul>
      </section>

      <section className="space-y-3">
        <h2 className="text-lg font-medium">The data in plain words</h2>
        <dl className="max-w-3xl divide-y divide-neutral-800 text-sm">
          {[
            ["stat-events", "Log events", fmt(summary.events), "Lines the cluster wrote while it ran."],
            ["stat-blocks", "Block sessions", fmt(summary.blocks), "A block is one chunk of a file. All the log lines naming it form one session."],
            ["stat-anomalous", "Failed blocks", fmt(summary.anomalous_blocks), "Sessions the benchmark's authors labelled as failures."],
            ["stat-rate", "Failure rate", `${summary.anomaly_rate_pct}%`, "Failed blocks as a share of all blocks."],
          ].map(([id, label, value, meaning]) => (
            <div key={id} className="grid grid-cols-1 items-baseline gap-1 py-2 sm:grid-cols-[9rem_8rem_1fr] sm:gap-4" data-testid={id}>
              <dt className="text-neutral-300">{label}</dt>
              <dd className="font-semibold tabular-nums">{value}</dd>
              <dd className="text-neutral-300">{meaning}</dd>
            </div>
          ))}
        </dl>
      </section>

      <section className="space-y-2">
        <h2 className="text-lg font-medium">Log volume per hour</h2>
        <p className="max-w-3xl text-sm text-neutral-300">Traffic is uneven: a few busy hours write most of the lines, and the cluster idles in between.</p>
        <Plot
          data={[{ x: volume.map((p) => p.bucket), y: volume.map((p) => p.events), type: "scatter", mode: "lines", line: { color: "#38bdf8" } }]}
          layout={{ yaxis: { title: { text: "log lines per hour" } } }}
        />
      </section>

      <section className="space-y-2">
        <h2 className="text-lg font-medium">Which part of the cluster writes the logs</h2>
        <p className="max-w-3xl text-sm text-neutral-300">
          {top3Share !== null && <>Three components write {top3Share}% of all lines. </>}
          <Term k="NameNode">dfs.FSNamesystem</Term> is the <Term k="NameNode">NameNode</Term>, which tracks where every block lives; the{" "}
          <Term k="DataNode">dfs.DataNode</Term> components store and move the blocks themselves.
        </p>
        <Plot
          data={[{ x: components.map((c) => c.events), y: components.map((c) => c.name), type: "bar", orientation: "h", marker: { color: "#818cf8" } }]}
          layout={{ margin: { l: 220, t: 10, r: 10, b: 40 }, yaxis: { autorange: "reversed" }, xaxis: { title: { text: "log lines" } } }}
        />
      </section>

      <LivePanel />

      {clusters && (
        <section data-testid="clusters">
          <details className="group rounded-lg border border-neutral-800 p-4">
            <summary className="cursor-pointer text-lg font-medium">Technical detail: grouping similar log messages</summary>
            <p className="mt-2 max-w-3xl text-sm text-neutral-300">
              Most log lines are the same message with different numbers. Replacing the changing parts leaves {clusters.templates} message{" "}
              <Term k="Template">templates</Term>; a similarity search (FAISS) then merged near-duplicates into {clusters.clusters} groups. Only near-duplicates
              merge, so distinct failure messages stay separate. These are the merges it made:
            </p>
            <ul className="mt-3 space-y-2 text-sm">
              {clusters.merged.map((c) => (
                <li key={c.cluster_id} className="rounded border border-neutral-800 p-3">
                  <div className="font-mono text-xs text-neutral-200">{c.representative}</div>
                  <div className="mt-1 text-xs text-neutral-300">
                    absorbed {c.members.length - 1} variant{c.members.length > 2 ? "s" : ""}
                  </div>
                </li>
              ))}
            </ul>
          </details>
        </section>
      )}

      <section className="max-w-3xl space-y-3" data-testid="glossary">
        <h2 className="text-lg font-medium">Words used in this app</h2>
        <p className="text-sm text-neutral-300">Hover a dotted word on any page for its meaning, or read them all here.</p>
        <dl className="divide-y divide-neutral-800 text-sm">
          {Object.entries(GLOSSARY).map(([term, def]) => (
            <div key={term} className="grid gap-1 py-2 sm:grid-cols-[11rem_1fr] sm:gap-4">
              <dt className="font-medium text-neutral-100">{term}</dt>
              <dd className="text-neutral-300">{def}</dd>
            </div>
          ))}
        </dl>
      </section>
    </div>
  );
}
