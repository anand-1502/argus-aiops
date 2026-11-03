"use client";

import { useEffect, useState } from "react";
import { api, type BusinessInputs } from "@/lib/api";
import PageHeader from "@/components/PageHeader";
import Term from "@/components/Term";

const money = (n: number) => `$${Math.round(n).toLocaleString("en-US")}`;
const hours = (n: number) => `${n.toFixed(1)} h`;

function Field({ label, value, onChange, unit, id }: { label: string; value: number; onChange: (n: number) => void; unit: string; id: string }) {
  return (
    <label className="block text-sm">
      <span className="text-neutral-400">{label}</span>
      <div className="mt-1 flex items-center gap-2">
        <input
          data-testid={id}
          type="number"
          min={0}
          value={value}
          onChange={(e) => onChange(Math.max(0, Number(e.target.value)))}
          className="w-28 rounded border border-neutral-700 bg-neutral-900 px-2 py-1 tabular-nums"
        />
        <span className="text-neutral-400">{unit}</span>
      </div>
    </label>
  );
}

export default function Business() {
  const [b, setB] = useState<BusinessInputs | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [manualMin, setManualMin] = useState(45);
  const [reviewMin, setReviewMin] = useState(10);
  const [rate, setRate] = useState(90);
  const [monthly, setMonthly] = useState(false);

  useEffect(() => {
    api.business().then(setB).catch((e: Error) => setError(e.message));
  }, []);

  if (error) return <p className="text-red-400">Could not load: {error}</p>;
  if (!b) return <p className="text-neutral-400">Loading…</p>;

  const acc = b.runbook_accuracy ?? 0;
  const scale = monthly ? 720 / b.capture_hours : 1;
  const windows = b.incident_windows * scale;
  const manualHours = (windows * manualMin) / 60;
  // when the agent picks the wrong runbook the engineer still does the manual work, on top of the review
  const agentHours = (windows * (acc * reviewMin + (1 - acc) * (reviewMin + manualMin))) / 60;
  const saved = manualHours - agentHours;
  const breakEven = acc * manualMin;

  return (
    <div className="space-y-8">
      <PageHeader
        title="Would this save an on-call engineer time?"
        takeaway={<>Change the yellow assumptions below. The result flips from savings to extra cost if checking the agent&apos;s write-up takes too long, and the break-even point is stated in words further down.</>}
      >
        A calculator, not a measurement. The incident count and the agent&apos;s accuracy come from real runs. The minutes and the hourly cost are numbers you set, because
        this project has no real on-call data. Definitions are in <code>docs/KPI_DICTIONARY.md</code>.
      </PageHeader>

      <section className="grid gap-4 md:grid-cols-4" data-testid="measured">
        <div className="rounded-lg border border-neutral-800 p-4">
          <div className="text-sm text-neutral-400"><Term k="Incident window">Incidents</Term> in the capture (measured)</div>
          <div className="mt-1 text-2xl font-semibold tabular-nums">{b.incident_windows}</div>
          <div className="mt-1 text-xs text-neutral-400">over {b.capture_hours} hours; failures within 30 s count as one</div>
        </div>
        <div className="rounded-lg border border-neutral-800 p-4">
          <div className="text-sm text-neutral-400">Agent picks the right runbook</div>
          <div className="mt-1 text-2xl font-semibold tabular-nums">{(acc * 100).toFixed(0)}%</div>
          <div className="mt-1 text-xs text-neutral-400">{b.from_eval ? "from the latest eval run" : "from the 6 recorded demo runs"}</div>
        </div>
        <div className="rounded-lg border border-neutral-800 p-4">
          <div className="text-sm text-neutral-400">Citations verified</div>
          <div className="mt-1 text-2xl font-semibold tabular-nums">{((b.verified_rate ?? 0) * 100).toFixed(0)}%</div>
        </div>
        <div className="rounded-lg border border-neutral-800 p-4">
          <div className="text-sm text-neutral-400">Agent time per incident</div>
          <div className="mt-1 text-2xl font-semibold tabular-nums">{b.agent_seconds ? `${Math.round(b.agent_seconds)} s` : "n/a"}</div>
          <div className="mt-1 text-xs text-neutral-400">on an 8 GB laptop</div>
        </div>
      </section>

      <section className="rounded-lg border border-amber-500/30 bg-amber-500/5 p-5">
        <h2 className="mb-3 text-lg font-medium">Assumptions (change these)</h2>
        <div className="flex flex-wrap gap-8">
          <Field id="manual" label="Minutes to triage one incident by hand" value={manualMin} onChange={setManualMin} unit="min" />
          <Field id="review" label="Minutes to review the agent's postmortem" value={reviewMin} onChange={setReviewMin} unit="min" />
          <Field id="rate" label="Loaded cost of an on-call engineer" value={rate} onChange={setRate} unit="$ / hour" />
          <label className="flex items-center gap-2 text-sm text-neutral-300">
            <input type="checkbox" checked={monthly} onChange={(e) => setMonthly(e.target.checked)} />
            Extrapolate to 30 days (assumes this failure rate continues)
          </label>
        </div>
      </section>

      <section className="grid gap-4 md:grid-cols-3" data-testid="result">
        <div className="rounded-lg border border-neutral-800 p-4">
          <div className="text-sm text-neutral-400">By hand</div>
          <div className="mt-1 text-2xl font-semibold tabular-nums">{hours(manualHours)}</div>
          <div className="text-xs text-neutral-400">{money(manualHours * rate)}</div>
        </div>
        <div className="rounded-lg border border-neutral-800 p-4">
          <div className="text-sm text-neutral-400">With the agent</div>
          <div className="mt-1 text-2xl font-semibold tabular-nums">{hours(agentHours)}</div>
          <div className="text-xs text-neutral-400">{money(agentHours * rate)}</div>
        </div>
        <div className="rounded-lg border border-neutral-800 p-4">
          <div className="text-sm text-neutral-400">Modelled difference {monthly ? "(30 days)" : "(this capture)"}</div>
          <div className={`mt-1 text-2xl font-semibold tabular-nums ${saved >= 0 ? "text-emerald-400" : "text-red-400"}`} data-testid="saved">
            {saved >= 0 ? "" : "-"}{hours(Math.abs(saved))}
          </div>
          <div className="text-xs text-neutral-400">{money(Math.abs(saved) * rate)} {saved >= 0 ? "saved" : "extra cost"}</div>
        </div>
      </section>

      <section className="max-w-3xl space-y-2 text-sm text-neutral-300">
        <h2 className="text-lg font-medium text-neutral-100">What the model says</h2>
        <p data-testid="breakeven">
          The agent pays off only while reviewing its output takes less than <b>{breakEven.toFixed(1)} minutes</b> ({(acc * 100).toFixed(0)}% accuracy x {manualMin} minutes by hand).
          Past that, the time spent checking a postmortem costs more than the triage it saves.
        </p>
        <p>
          When the agent is wrong, the engineer pays for the review <i>and</i> the manual work. That is why accuracy and the citation checks matter
          more than speed: a fast wrong answer is worse than none.
        </p>
        <p className="text-neutral-400">
          Not modelled: the cost of running the system, alert fatigue, incidents the benchmark never labelled, and the fact that 145 windows come from
          a 38-hour benchmark capture, not a live production feed.
        </p>
      </section>
    </div>
  );
}
