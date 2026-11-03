-- Which components carry the anomalies? A Pareto: sorted by anomalous events with a running share.
with by_component as (
    select
        f.component,
        d.plane,
        sum(f.events)                    as events,
        sum(f.anomalous_events)          as anomalous_events
    from {{ ref('fact_hourly_events') }} f
    join {{ ref('dim_component') }} d using (component)
    group by 1, 2
)
select
    component,
    plane,
    events,
    anomalous_events,
    round(100.0 * events / sum(events) over (), 2)                                      as pct_of_events,
    round(100.0 * anomalous_events / nullif(sum(anomalous_events) over (), 0), 2)       as pct_of_anomalous_events,
    round(100.0 * sum(anomalous_events) over (order by anomalous_events desc rows between unbounded preceding and current row)
          / nullif(sum(anomalous_events) over (), 0), 2)                                as cumulative_pct,
    dense_rank() over (order by anomalous_events desc)                                  as anomaly_rank
from by_component
