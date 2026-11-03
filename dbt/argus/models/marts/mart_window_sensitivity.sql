-- How many incident windows would there be for each choice of gap? Publishing the curve keeps the headline honest.
with gaps as (
    select unnest(array[1, 5, 15, 30, 60, 300]) as gap_seconds
),
anomalous as (
    select first_ts from {{ ref('dim_block') }} where is_anomaly
),
with_prev as (
    select
        g.gap_seconds,
        a.first_ts,
        lag(a.first_ts) over (partition by g.gap_seconds order by a.first_ts) as prev_ts
    from gaps g cross join anomalous a
)
select
    gap_seconds,
    count(*) filter (where prev_ts is null or first_ts - prev_ts > make_interval(secs => gap_seconds)) as windows,
    count(*)                                                                                           as anomalous_blocks,
    round(100.0 * (1 - (count(*) filter (where prev_ts is null or first_ts - prev_ts > make_interval(secs => gap_seconds)))::numeric
                      / count(*)), 1)                                                                  as reduction_pct
from with_prev
group by gap_seconds
order by gap_seconds
