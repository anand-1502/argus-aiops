"use client";

import dynamic from "next/dynamic";
import type { Layout, Data } from "plotly.js-dist-min";

// Plotly touches `window`, so it is loaded in the browser only.
const Inner = dynamic(
  async () => {
    const Plotly = (await import("plotly.js-dist-min")).default;
    const factory = (await import("react-plotly.js/factory")).default;
    return factory(Plotly);
  },
  { ssr: false, loading: () => <div className="h-72 animate-pulse rounded bg-neutral-800" /> },
);

export default function Plot({ data, layout }: { data: Data[]; layout?: Partial<Layout> }) {
  return (
    <Inner
      data={data}
      layout={{
        paper_bgcolor: "rgba(0,0,0,0)",
        plot_bgcolor: "rgba(0,0,0,0)",
        font: { color: "#d4d4d4" },
        margin: { t: 10, r: 10, b: 40, l: 60 },
        autosize: true,
        ...(layout ?? {}),
        xaxis: { gridcolor: "#262626", zerolinecolor: "#404040", ...(layout?.xaxis ?? {}) },
        yaxis: { gridcolor: "#262626", zerolinecolor: "#404040", ...(layout?.yaxis ?? {}) },
      }}
      config={{ displayModeBar: false, responsive: true }}
      useResizeHandler
      style={{ width: "100%", height: "320px" }}
    />
  );
}
