"use client";

import { useEffect, useState } from "react";
import Term from "@/components/Term";
import PageHeader from "@/components/PageHeader";
import { GLOSSARY } from "@/lib/glossary";
import { api, STATIC, type JobRow, type PipelineStatus } from "@/lib/api";

const STAGES = ["Store", "Stream", "Orchestrate", "Model", "Agent", "Observe", "Evaluate"];
const fmt = (t: number) => new Date(t * 1000).toISOString().replace("T", " ").slice(0, 19);

export default function Pipeline() {
  const [d, setD] = useState<PipelineStatus | null>(null);
  const [jobs, setJobs] = useState<JobRow[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const load = () => {
      api.pipeline().then(setD).catch((e: Error) => setError(e.message));
      api.jobs().then(setJobs).catch(() => {});
    };
    load();
    if (STATIC) return;
    const t = setInterval(load, 10000);
    return () => clearInterval(t);
  }, []);

  if (error) return <p className="text-red-400">{error}</p>;
  if (!d) return <p className="text-neutral-300">Checking services…</p>;

  return (
    <div className="space-y-8">
      <PageHeader
        title="What keeps it running"
        takeaway={
          <span data-testid="pipeline-count">
            <b>{d.up} of {d.total}</b> components are up. {STATIC ? "" : "Grey means not started, which is normal here: the heavy ones start only when needed to save memory on this laptop."}
          </span>
        }
      >
        {STATIC
          ? "A snapshot of the stack when this site was built, not a live view. Only the core services were running then; Kafka and Airflow were each started and verified separately (see the README). Run Argus locally to see this page live."
          : "Every moving part behind the dashboard and whether it is running right now, refreshed every 10 seconds. Where something is down, the line says how to start it."}
      </PageHeader>

      <div className="grid gap-4 md:grid-cols-2" data-testid="pipeline-services">
        {STAGES.flatMap((stage) => d.services.filter((s) => s.stage === stage)).map((s) => (
          <div key={s.name} className="rounded-lg border border-neutral-800 p-4">
            <div className="flex items-center gap-2">
              <span className={`h-2.5 w-2.5 rounded-full ${s.status === "up" ? "bg-emerald-400" : "bg-neutral-600"}`} aria-hidden />
              <span className="font-medium">{(() => { const k = Object.keys(GLOSSARY).find((g) => s.name.includes(g)); return k ? <Term k={k}>{s.name}</Term> : s.name; })()}</span>
              <span className="ml-auto text-xs uppercase tracking-wide text-neutral-300">{s.stage}</span>
              <span className={`text-xs ${s.status === "up" ? "text-emerald-400" : "text-neutral-300"}`}>{s.status}</span>
            </div>
            <p className="mt-2 break-words font-mono text-xs text-neutral-300">{s.detail}</p>
          </div>
        ))}
      </div>

      <div>
        <h2 className="mb-2 text-lg font-medium">Recent jobs</h2>
        <p className="mb-2 text-sm text-neutral-300">
          Started by Airflow through the API&rsquo;s job runner (a fixed allow-list: retrain, eval). The list is kept in memory, so it
          resets when the API restarts.
        </p>
        <table className="w-full text-sm" data-testid="jobs-table">
          <thead className="text-left text-neutral-300"><tr><th className="py-1">Job</th><th>Status</th><th>Started (UTC)</th><th>Seconds</th></tr></thead>
          <tbody>
            {jobs.map((j) => (
              <tr key={j.id} className="border-t border-neutral-800">
                <td className="py-1 font-mono text-xs">{j.name}</td>
                <td>{j.status}</td>
                <td className="tabular-nums">{fmt(j.started)}</td>
                <td className="tabular-nums">{j.finished ? Math.round(j.finished - j.started) : "-"}</td>
              </tr>
            ))}
            {jobs.length === 0 && <tr><td colSpan={4} className="py-2 text-neutral-300">No jobs since the API started.</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  );
}
