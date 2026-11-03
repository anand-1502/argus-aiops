-- Grain: hour x component x level. The event-to-block-label join happens here, once, and every mart below reuses it.
select
    e.hour_ts,
    e.component,
    e.level,
    count(*)                                                            as events,
    count(*) filter (where l.is_anomaly)                                as anomalous_events
from {{ ref('stg_events') }} e
left join {{ ref('stg_block_labels') }} l using (block_id)
group by 1, 2, 3
