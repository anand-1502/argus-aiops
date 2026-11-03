// Default: the same-origin proxy (app/api/[...path]), which forwards to API_INTERNAL_URL at runtime.
const BASE = process.env.NEXT_PUBLIC_API_URL ?? "/api";

export type Summary = {
  events: number;
  blocks: number;
  anomalous_blocks: number;
  anomaly_rate_pct: number;
};
export type VolumePoint = { bucket: string; events: number };
export type DriftPoint = { window: number; psi_max: number; f1: number; alert: boolean };
export type ModelStatus = {
  version: number;
  run_id: string;
  metrics: { precision: number; recall: number; f1: number; pr_auc: number };
  cv_f1_mean: number | null;
  baselines: Record<string, { precision: number; recall: number; f1: number }>;
  drift: DriftPoint[];
  shifted_status: string | null;
};
export type Incident = {
  block_id: string;
  expected_runbook: string;
  signature_line: string;
  first_ts: string;
  n_events: number;
  recorded: boolean;
};
export type TraceCall = { server: string; tool: string; args: Record<string, unknown>; rows?: number; ms: number; error?: string };
export type AgentRun = {
  block_id: string;
  label: string | null;
  model?: string;
  seconds?: number;
  postmortem: {
    root_cause: string;
    runbook_id: string;
    summary: string;
    timeline: string[];
    recommended_actions: string[];
    key_evidence_id: string;
    key_evidence_quote: string;
    citations: string[];
  };
  verification: { ok: boolean; reason: string; unknown: string[]; counts: Record<string, number> };
  trace: TraceCall[];
  evidence: Record<string, { kind: string; text: string }>;
  notes?: string[];
};
export type LiveStatus = {
  events: number;
  batches: number;
  running: boolean;
  last_ingested_at: string | null;
  recent: { batch: number; events: number; anomalous_events: number }[];
};
export type Clusters = {
  templates: number;
  clusters: number;
  merged: { cluster_id: number; representative: string; members: string[]; blocks: number }[];
};
export type EvalMetrics = Record<string, number>;
export type EvalSummary = {
  latest: { label: string; at: string; model: string; source_hash: string; metrics: EvalMetrics } | null;
  history: { at: string; label: string; model: string; metrics: EvalMetrics }[];
  thresholds: { agent: Record<string, number>; classifier: Record<string, number>; retrieval: Record<string, number>; regression_tolerance: number };
  incidents: {
    block_id: string;
    expected_runbook: string;
    split: string;
    error: string | null;
    seconds: number;
    chosen_runbook: string | null;
    scores: { runbook_correct: boolean; verified: boolean; signature_cited: boolean; first_draft: boolean } | null;
    judge?: { deepeval_faithfulness: number | null; ragas_faithfulness: number | null } | null;
  }[];
  phoenix_url: string;
};
export type ExportListing = {
  files: Record<string, number>;
  recommendations: {
    charts: { table: string; chart: string; x?: string; y?: string; field?: string; reason: string }[];
    calculated_fields: { table: string; name: string; tableau: string; dax: string; reason: string }[];
  };
  tables?: Record<string, number>;
};
export type Kpis = {
  total_events: number; total_blocks: number; anomalous_blocks: number; anomaly_rate_pct: number;
  incident_windows: number; anomalous_blocks_per_window: number; alert_reduction_pct: number;
  median_blocks_per_window: number; p95_blocks_per_window: number; largest_window_blocks: number; worst_hour: string;
};
export type TrendRow = {
  hour_ts: string; events: number; anomalous_events: number; anomaly_rate: number; cumulative_rate: number;
  moving_avg_3h: number; change_vs_prev_hour: number | null; zscore: number | null; is_spike: boolean;
};
export type ComponentHealth = {
  component: string; plane: string; events: number; anomalous_events: number; pct_of_events: number;
  pct_of_anomalous_events: number; cumulative_pct: number; anomaly_rank: number;
};
export type WindowsInfo = {
  top: { window_id: number; start_ts: string; end_ts: string; span_minutes: number; anomalous_blocks: number }[];
  sensitivity: { gap_seconds: number; windows: number; anomalous_blocks: number; reduction_pct: number }[];
};
export type BusinessInputs = {
  incident_windows: number;
  anomalous_blocks: number;
  capture_hours: number;
  agent_seconds: number | null;
  runbook_accuracy: number | null;
  verified_rate: number | null;
  from_eval: boolean;
};
export type ModelAnalysis = {
  n_test: number;
  n_positive: number;
  xgboost: { f1: number; precision: number; recall: number };
  confidence_intervals_95: Record<"f1" | "precision" | "recall", [number, number]>;
  calibration: { ece: number; brier: number; bins: { mean_pred: number; frac_pos: number; n: number }[] };
  baselines: { model: string; f1: number; precision: number; recall: number; xgboost_minus_this_f1: { mean_diff: number; lo: number; hi: number; significant: boolean } }[];
  shap_top: { feature: string; name: string; mean_abs_shap: number }[];
  errors: {
    n_false_positive: number;
    n_false_negative: number;
    false_negatives: { block_id: string; proba: number; top_features: { name: string; value: number; shap: number }[] }[];
    false_positives: { block_id: string; proba: number; top_features: { name: string; value: number; shap: number }[] }[];
  };
};
export type Count = { name: string; events: number };

// Static mode (GitHub Pages): reads come from JSON files recorded by scripts/snapshot.py, and anything that needs a backend is off.
export const STATIC = process.env.NEXT_PUBLIC_STATIC === "1";
const BASE_PATH = process.env.NEXT_PUBLIC_BASE_PATH ?? "";
const snapshotKey = (path: string) => path.replace(/^\//, "").replace(/[^A-Za-z0-9._-]/g, "_"); // mirrors key() in scripts/snapshot.py
const needsBackend = (): never => {
  throw new Error("Not available in the static demo. Run Argus locally to use this.");
};

async function get<T>(path: string): Promise<T> {
  if (STATIC) {
    if (path === "/uploads/demo") return (await get<UploadRow[]>("/uploads"))[0] as T;
    const res = await fetch(`${BASE_PATH}/snapshot/${snapshotKey(path)}.json`);
    if (!res.ok) throw new Error(`${path} is not in the snapshot`);
    return res.json() as Promise<T>;
  }
  const res = await fetch(`${BASE}${path}`);
  if (!res.ok) throw new Error(`${path} failed: ${res.status}`);
  return res.json() as Promise<T>;
}

export type UploadRow = {
  id: string; filename: string; status: "queued" | "running" | "succeeded" | "failed"; stage: string | null;
  bytes: number | null; lines_total: number | null; lines_done: number | null; templates: number | null;
  ts_format: string | null; error: string | null; created_at: string; finished_at: string | null;
};
export type TemplateRow = { template_id: number; template: string; n: number; example?: string };
export type UploadSummary = {
  events: number; first_ts: string | null; last_ts: string | null; bucket: "minute" | "hour" | "day";
  levels: { name: string; n: number }[]; volume: { bucket: string; events: number }[];
  spikes: { bucket: string; events: number; z: number }[];
  top_templates: TemplateRow[]; rare_templates: TemplateRow[]; error_share_pct: number;
};
export type LogLine = { line_no: number; ts: string | null; level: string; content: string };

export type PipelineService = { stage: string; name: string; status: "up" | "down"; detail: string };
export type PipelineStatus = { services: PipelineService[]; up: number; total: number };
export type JobRow = { id: string; name: string; status: string; returncode: number | null; started: number; finished?: number };

export const api = {
  summary: () => get<Summary>("/stats/summary"),
  volume: (bucket: "hour" | "day" = "hour") => get<VolumePoint[]>(`/stats/volume?bucket=${bucket}`),
  components: () => get<Count[]>("/stats/components"),
  modelStatus: () => get<ModelStatus>("/model/status"),
  incidents: () => get<Incident[]>("/agent/incidents"),
  run: (blockId: string) => get<AgentRun>(`/agent/runs/${encodeURIComponent(blockId)}`),
  investigate: async (blockId: string): Promise<AgentRun> => {
    if (STATIC) needsBackend();
    const res = await fetch(`${BASE}/agent/investigate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ block_id: blockId }),
    });
    if (!res.ok) throw new Error(`investigate failed: ${res.status}`);
    return res.json() as Promise<AgentRun>;
  },
  live: () => get<LiveStatus>("/live/status"),
  clusters: () => get<Clusters>("/stats/clusters"),
  evals: () => get<EvalSummary>("/evals/summary"),
  exportStatus: () => get<ExportListing>("/export/status"),
  exportBuild: async (): Promise<ExportListing> => {
    if (STATIC) needsBackend();
    const res = await fetch(`${BASE}/export/bi`, { method: "POST" });
    if (!res.ok) throw new Error(`export failed: ${res.status}`);
    return res.json() as Promise<ExportListing>;
  },
  exportUrl: (name: string) => `${BASE}/export/files/${name}`,
  kpis: () => get<Kpis>("/analytics/kpis"),
  trend: () => get<TrendRow[]>("/analytics/trend"),
  componentHealth: () => get<ComponentHealth[]>("/analytics/components"),
  windows: () => get<WindowsInfo>("/analytics/windows"),
  sql: (model: string) => get<{ model: string; layer: string; sql: string }>(`/analytics/sql/${model}`),
  business: () => get<BusinessInputs>("/business/inputs"),
  modelAnalysis: () => get<ModelAnalysis>("/model/analysis"),
  levels: () => get<Count[]>("/stats/levels"),
  pipeline: () => get<PipelineStatus>("/pipeline/status"),
  jobs: () => get<JobRow[]>("/jobs"),
  uploads: () => get<UploadRow[]>("/uploads"),
  upload: (id: string) => get<UploadRow>(`/uploads/${id}`),
  uploadSummary: (id: string) => get<UploadSummary>(`/uploads/${id}/summary`),
  uploadSearch: (id: string, q: string) => (STATIC ? needsBackend() : get<LogLine[]>(`/uploads/${id}/search?q=${encodeURIComponent(q)}`)),
  uploadCreate: async (file: File): Promise<{ id: string }> => {
    if (STATIC) needsBackend();
    const body = new FormData();
    body.append("file", file);
    const res = await fetch(`${BASE}/uploads`, { method: "POST", body });
    if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail ?? `upload failed: ${res.status}`);
    return res.json();
  },
  uploadDelete: async (id: string) => {
    if (STATIC) needsBackend();
    const res = await fetch(`${BASE}/uploads/${id}`, { method: "DELETE" });
    if (!res.ok) throw new Error(`delete failed: ${res.status}`);
  },
};
