-- Hour by hour anomaly rate with the window-function toolbox: running totals, moving average,
-- lag, z-score for spikes, ranking and quartiles.
with hourly as (
    select
        hour_ts,
        sum(events)                      as events,
        sum(anomalous_events)            as anomalous_events
    from {{ ref('fact_hourly_events') }}
    group by hour_ts
),
rated as (
    select *, anomalous_events::float8 / nullif(events, 0) as anomaly_rate from hourly
)
select
    hour_ts,
    events,
    anomalous_events,
    anomaly_rate,
    -- cumulative rate: the share of all events so far that belong to anomalous blocks
    (sum(anomalous_events) over w_all)::float8 / nullif(sum(events) over w_all, 0)            as cumulative_rate,
    avg(anomaly_rate) over (order by hour_ts rows between 2 preceding and current row)       as moving_avg_3h,
    anomaly_rate - lag(anomaly_rate) over (order by hour_ts)                                 as change_vs_prev_hour,
    (anomaly_rate - avg(anomaly_rate) over ()) / nullif(stddev_samp(anomaly_rate) over (), 0) as zscore,
    ((anomaly_rate - avg(anomaly_rate) over ()) / nullif(stddev_samp(anomaly_rate) over (), 0)) > 2 as is_spike,
    rank() over (order by anomaly_rate desc nulls last)                                      as worst_hour_rank,
    ntile(4) over (order by events)                                                          as volume_quartile
from rated
window w_all as (order by hour_ts rows between unbounded preceding and current row)
