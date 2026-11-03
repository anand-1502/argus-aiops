"use client";

import { useEffect, useState } from "react";
import { api, STATIC, type ExportListing } from "@/lib/api";
import PageHeader from "@/components/PageHeader";

const LABEL: Record<string, string> = {
  "argus_bi_export.zip": "Everything (zip)",
  "argus.hyper": "Tableau extract (.hyper)",
  "argus_powerbi.zip": "Power BI package (zip)",
  "recommendations.json": "Recommendations (json)",
};
const mb = (n: number) => (n > 1e6 ? `${(n / 1e6).toFixed(1)} MB` : `${Math.max(1, Math.round(n / 1e3))} KB`);

export default function Export() {
  const [d, setD] = useState<ExportListing | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.exportStatus().then(setD).catch((e: Error) => setError(e.message));
  }, []);

  async function build() {
    setBusy(true);
    setError(null);
    try {
      setD(await api.exportBuild());
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const files = d ? Object.keys(LABEL).filter((f) => f in d.files) : [];
  const rec = d?.recommendations;

  return (
    <div className="space-y-8">
      <PageHeader
        title="Take the data into Tableau or Power BI"
        takeaway={<>Both files hold the same tables as this dashboard and the totals match, so an analyst can rebuild any chart here in their own tool.</>}
      >
        Analysts work in their own tools. One click builds a Tableau <code>.hyper</code> extract and a Power BI package (data files, a documented model, DAX measures and
        a Power Query loader), with suggested charts and calculated fields already defined.
      </PageHeader>

      <div className="flex items-center gap-4">
        <button
          onClick={build}
          disabled={busy || STATIC}
          title={STATIC ? "Needs the database: run Argus locally" : undefined}
          data-testid="export-button"
          className="rounded bg-sky-600 px-4 py-2 text-sm font-medium hover:bg-sky-500 disabled:opacity-50"
        >
          {busy ? "Building… (about a minute)" : files.length ? "Rebuild export" : "Generate export"}
        </button>
        {error && <span className="text-sm text-red-400">{error}</span>}
      </div>

      {files.length > 0 && (
        <section data-testid="export-files">
          <h2 className="mb-2 text-lg font-medium">Downloads</h2>
          <ul className="space-y-1 text-sm">
            {files.map((f) => (
              <li key={f}>
                {STATIC ? <span>{LABEL[f]}</span> : <a className="text-sky-400 underline" href={api.exportUrl(f)}>{LABEL[f]}</a>}
                <span className="ml-2 text-neutral-400">{mb(d!.files[f])}</span>
              </li>
            ))}
          </ul>
        </section>
      )}

      {rec && rec.charts.length > 0 && (
        <section data-testid="export-recommendations">
          <h2 className="mb-1 text-lg font-medium">Suggested visuals</h2>
          <p className="mb-2 text-sm text-neutral-400">Each comes from a rule on the column types and distributions. The reason is shown with it.</p>
          <ul className="space-y-2 text-sm">
            {rec.charts.map((c, i) => (
              <li key={i} className="rounded border border-neutral-800 p-3">
                <span className="mr-2 rounded bg-neutral-800 px-2 py-0.5 text-xs">{c.chart}</span>
                <span className="font-mono text-xs text-neutral-300">{c.table}{c.x ? `: ${c.x} by ${c.y}` : c.field ? `: ${c.field}` : ""}</span>
                <div className="mt-1 text-neutral-400">{c.reason}</div>
              </li>
            ))}
          </ul>
          <h2 className="mb-1 mt-6 text-lg font-medium">Calculated fields</h2>
          <ul className="space-y-2 text-sm">
            {rec.calculated_fields.map((f) => (
              <li key={f.name + f.table} className="rounded border border-neutral-800 p-3">
                <div className="font-medium">{f.name} <span className="text-neutral-400">on {f.table}</span></div>
                <div className="mt-1 font-mono text-xs text-neutral-400">Tableau: {f.tableau}</div>
                <div className="font-mono text-xs text-neutral-400">DAX: {f.dax}</div>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}
