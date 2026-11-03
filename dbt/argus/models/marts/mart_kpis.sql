-- One row of headline numbers, each defined once so the dashboard, the BI export and the report cannot disagree.
-- See docs/KPI_DICTIONARY.md for the business definition of each column.
with blocks as (
    select count(*) as total_blocks, count(*) filter (where is_anomaly) as anomalous_blocks from {{ ref('dim_block') }}
),
events as (
    select sum(events) as total_events from {{ ref('fact_hourly_events') }}
),
windows as (
    select
        count(*)                                                       as incident_windows,
        percentile_cont(0.5)  within group (order by anomalous_blocks) as median_blocks_per_window,
        percentile_cont(0.95) within group (order by anomalous_blocks) as p95_blocks_per_window,
        max(anomalous_blocks)                                          as largest_window_blocks
    from {{ ref('mart_incident_windows') }}
),
worst as (
    select hour_ts as worst_hour from {{ ref('mart_anomaly_trend') }} order by anomaly_rate desc nulls last limit 1
)
select
    e.total_events,
    b.total_blocks,
    b.anomalous_blocks,
    round(100.0 * b.anomalous_blocks / b.total_blocks, 2)   as anomaly_rate_pct,
    w.incident_windows,
    round(b.anomalous_blocks::numeric / w.incident_windows, 1) as anomalous_blocks_per_window,
    round(100.0 * (1 - w.incident_windows::numeric / b.anomalous_blocks), 1) as alert_reduction_pct,
    w.median_blocks_per_window,
    w.p95_blocks_per_window,
    w.largest_window_blocks,
    x.worst_hour
from events e, blocks b, windows w, worst x
