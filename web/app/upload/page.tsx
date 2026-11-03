"use client";

import { useCallback, useEffect, useState } from "react";
import Plot from "@/components/Plot";
import PageHeader from "@/components/PageHeader";
import Term from "@/components/Term";
import { api, STATIC, type LogLine, type TemplateRow, type UploadRow, type UploadSummary } from "@/lib/api";

const fmtTs = (s: string | null) => (s ? s.replace("T", " ").slice(0, 19) : "n/a");
const mb = (n: number | null) => (n == null ? "" : n > 1e6 ? `${(n / 1e6).toFixed(1)} MB` : `${Math.max(1, Math.round(n / 1e3))} KB`);

function Templates({ title, note, rows }: { title: string; note: string; rows: TemplateRow[] }) {
  return (
    <div>
      <h2 className="text-lg font-medium">{title}</h2>
      <p className="mb-2 text-sm text-neutral-400">{note}</p>
      <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead className="text-left text-neutral-400"><tr><th className="w-16 py-1">Lines</th><th>Template</th></tr></thead>
        <tbody>
          {rows.map((t) => (
            <tr key={t.template_id} className="border-t border-neutral-800 align-top">
              <td className="py-1 tabular-nums">{t.n}</td>
              <td className="font-mono text-xs">
                {t.template}
                {t.example && <div className="mt-1 text-neutral-400">e.g. {t.example}</div>}
              </td>
            </tr>
          ))}
          {rows.length === 0 && <tr><td colSpan={2} className="py-2 text-neutral-400">None.</td></tr>}
        </tbody>
      </table>
      </div>
    </div>
  );
}

export default function Upload() {
  const [rows, setRows] = useState<UploadRow[]>([]);
  const [sel, setSel] = useState<UploadRow | null>(null);
  const [loaded, setSum] = useState<{ id: string; data: UploadSummary } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [q, setQ] = useState("");
  const [hits, setHits] = useState<LogLine[] | null>(null);

  const refresh = useCallback(() => api.uploads().then((r) => { setRows(r); if (STATIC && r[0]) setSel((cur) => cur ?? r[0]); }).catch((e: Error) => setError(e.message)), []);
  useEffect(() => { refresh(); }, [refresh]);

  // follow the selected upload while it is still being parsed
  useEffect(() => {
    if (!sel) return;
    if (sel.status === "succeeded") {
      api.uploadSummary(sel.id).then((data) => setSum({ id: sel.id, data })).catch((e: Error) => setError(e.message));
      return;
    }
    if (sel.status === "failed") return;
    const t = setInterval(() => {
      api.upload(sel.id).then((r) => { setSel(r); refresh(); }).catch(() => {});
    }, 1000);
    return () => clearInterval(t);
  }, [sel, refresh]);

  async function onFile(f: File | undefined) {
    if (!f) return;
    setBusy(true); setError(null); setHits(null);
    try {
      const { id } = await api.uploadCreate(f);
      setSel(await api.upload(id));
      refresh();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function remove(id: string) {
    await api.uploadDelete(id).catch((e: Error) => setError(e.message));
    if (sel?.id === id) { setSel(null); setSum(null); setHits(null); }
    refresh();
  }

  const sum = loaded && sel && loaded.id === sel.id && sel.status === "succeeded" ? loaded.data : null;
  const pct = sel && sel.lines_total ? Math.round(((sel.lines_done ?? 0) / sel.lines_total) * 100) : 0;

  return (
    <div className="space-y-8">
      <PageHeader
        title="Try it on your own logs"
        takeaway={<>There are no failure labels on a file you bring, so this page shows what the text alone can tell you: volume spikes, rare messages and a search box. It is not the failure classifier.</>}
      >
        Upload a plain-text log (up to 50 MB or 500,000 lines). Argus guesses the timestamp format, groups similar messages into <Term k="Template">templates</Term> and loads
        the file into its own private schema, so it never mixes with the demo data or another upload. Delete it any time.
      </PageHeader>

      <label className="block rounded-lg border border-dashed border-neutral-700 p-6 text-sm text-neutral-300 hover:border-neutral-500">
        <input data-testid="file-input" type="file" disabled={busy || STATIC} onChange={(e) => onFile(e.target.files?.[0])} className="block text-sm file:mr-3 file:cursor-pointer file:rounded file:border file:border-neutral-600 file:bg-neutral-900 file:px-3 file:py-1.5 file:text-sm file:text-neutral-100 hover:file:border-neutral-400 disabled:opacity-60 disabled:file:cursor-not-allowed" />
        {STATIC && <span className="mt-2 block text-amber-400">This is the static demo, so uploads are off. Below is a real run of the sample file through the parser. Run Argus locally to upload your own.</span>}
        <span className="mt-2 block text-neutral-300">No log handy? Use <code className="font-mono">tests/fixtures/modern_app.log</code> from the repo: a synthetic two-hour application log with one traffic spike and one rare error planted for the page to find.</span>
        <span className="mt-2 block text-neutral-300">Syslog, ISO-8601 application logs, epoch timestamps or the HDFS layout. Files with no timestamps still load, just without time charts.</span>
      </label>

      {error && <p className="text-red-400" data-testid="error">{error}</p>}

      {rows.length > 0 && (
        <div>
          <h2 className="mb-2 text-lg font-medium">Your uploads</h2>
          <div className="overflow-x-auto">
          <table className="w-full text-sm" data-testid="upload-list">
            <thead className="text-left text-neutral-400"><tr><th className="py-1">File</th><th>Status</th><th>Lines</th><th>Templates</th><th /></tr></thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.id} className={`border-t border-neutral-800 ${sel?.id === r.id ? "bg-sky-500/5" : ""}`}>
                  <td className="py-1"><button className="text-sky-400 hover:underline" onClick={() => { setSel(r); setHits(null); }}>{r.filename}</button> <span className="text-xs text-neutral-400">{mb(r.bytes)}</span></td>
                  <td>{r.status}{r.status === "failed" ? "" : r.stage && r.status !== "succeeded" ? ` (${r.stage})` : ""}</td>
                  <td className="tabular-nums">{r.lines_total?.toLocaleString() ?? "-"}</td>
                  <td className="tabular-nums">{r.templates ?? "-"}</td>
                  <td className="text-right">{!STATIC && <button className="text-xs text-neutral-400 hover:text-red-400" onClick={() => remove(r.id)}>Delete</button>}</td>
                </tr>
              ))}
            </tbody>
          </table>
          </div>
        </div>
      )}

      {sel && sel.status !== "succeeded" && sel.status !== "failed" && (
        <div data-testid="progress">
          <div className="mb-1 text-sm text-neutral-300">{sel.stage} {sel.lines_total ? `${(sel.lines_done ?? 0).toLocaleString()} / ${sel.lines_total.toLocaleString()} lines` : ""}</div>
          <div className="h-2 rounded bg-neutral-800"><div className="h-2 rounded bg-sky-500 transition-all" style={{ width: `${pct}%` }} /></div>
        </div>
      )}
      {sel?.status === "failed" && <p className="text-red-400" data-testid="failed">Could not parse {sel.filename}: {sel.error}</p>}

      {sum && sel && (
        <div className="space-y-8" data-testid="summary">
          <div className="grid gap-4 sm:grid-cols-4">
            {[
              ["Events", sum.events.toLocaleString()],
              ["Templates", String(sel.templates)],
              ["Error share", `${sum.error_share_pct}%`],
              ["Time range", sum.first_ts ? `${fmtTs(sum.first_ts)} to ${fmtTs(sum.last_ts)}` : "no timestamps"],
            ].map(([k, v]) => (
              <div key={k} className="rounded-lg border border-neutral-800 p-4">
                <div className="text-xs text-neutral-400">{k}</div>
                <div className="mt-1 text-sm font-medium tabular-nums">{v}</div>
              </div>
            ))}
          </div>

          {sum.volume.length > 1 && (
            <div>
              <h2 className="text-lg font-medium">Volume per {sum.bucket}</h2>
              <p className="mb-2 text-sm text-neutral-400">
                {sum.spikes.length
                  ? `${sum.spikes.length} bucket(s) more than 3 standard deviations above the mean: ${sum.spikes.map((s) => `${fmtTs(s.bucket)} (${s.events} events, z=${s.z})`).join("; ")}.`
                  : "No bucket stands out by more than 3 standard deviations."}
              </p>
              <Plot
                data={[
                  { x: sum.volume.map((v) => v.bucket), y: sum.volume.map((v) => v.events), type: "scatter", mode: "lines", line: { color: "#38bdf8" }, name: "events" },
                  { x: sum.spikes.map((s) => s.bucket), y: sum.spikes.map((s) => s.events), type: "scatter", mode: "markers", marker: { color: "#f59e0b", size: 10 }, name: "spike" },
                ]}
                layout={{ showlegend: false }}
              />
            </div>
          )}

          <div className="flex flex-wrap gap-2">
            {sum.levels.map((l) => (
              <span key={l.name} className="rounded-full bg-neutral-800 px-3 py-1 text-xs">{l.name} <span className="tabular-nums text-neutral-400">{l.n.toLocaleString()}</span></span>
            ))}
          </div>

          <Templates title="Rare templates" note="Message shapes seen at most 5 times and in under 1% of lines. Often where the interesting failure is, but rarity alone is a hint, not a verdict." rows={sum.rare_templates} />
          <Templates title="Most common templates" note="What this system normally says." rows={sum.top_templates} />

          {!STATIC && <div>
            <h2 className="mb-2 text-lg font-medium">Search</h2>
            <form onSubmit={(e) => { e.preventDefault(); if (q.trim()) api.uploadSearch(sel.id, q).then(setHits).catch((x: Error) => setError(x.message)); }} className="flex gap-2">
              <input data-testid="search-input" value={q} onChange={(e) => setQ(e.target.value)} placeholder="text to find" className="w-80 rounded border border-neutral-700 bg-transparent px-3 py-1 text-sm" />
              <button className="rounded border border-neutral-700 px-3 py-1 text-sm hover:border-neutral-500">Search</button>
            </form>
            {hits && (
              <ul className="mt-3 space-y-1 font-mono text-xs" data-testid="hits">
                {hits.map((h) => <li key={h.line_no}><span className="text-neutral-400">#{h.line_no} {h.level}</span> {h.content}</li>)}
                {hits.length === 0 && <li className="text-neutral-400">No matches.</li>}
              </ul>
            )}
          </div>}
        </div>
      )}
    </div>
  );
}
