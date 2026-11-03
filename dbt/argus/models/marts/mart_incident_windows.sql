-- Gaps and islands: anomalous blocks that start within `incident_gap_seconds` of the previous one belong to one incident window.
-- The count depends strongly on the gap (see mart_window_sensitivity), so it is a parameter, not a constant.
with anomalous as (
    select block_id, first_ts from {{ ref('dim_block') }} where is_anomaly
),
marked as (
    select
        block_id,
        first_ts,
        case when lag(first_ts) over (order by first_ts) is null
                  or first_ts - lag(first_ts) over (order by first_ts) > make_interval(secs => {{ var('incident_gap_seconds') }})
             then 1 else 0 end as starts_new_window
    from anomalous
),
numbered as (
    select *, sum(starts_new_window) over (order by first_ts rows between unbounded preceding and current row) as window_id
    from marked
)
select
    window_id,
    min(first_ts)                                          as start_ts,
    max(first_ts)                                          as end_ts,
    extract(epoch from max(first_ts) - min(first_ts)) / 60 as span_minutes,
    count(*)                                               as anomalous_blocks
from numbered
group by window_id
