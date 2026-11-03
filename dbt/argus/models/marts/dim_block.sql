select
    s.block_id,
    l.label,
    l.is_anomaly,
    s.first_ts,
    s.last_ts,
    s.duration_s,
    case
        when s.duration_s < 1        then 'under 1s'
        when s.duration_s < 60       then '1s to 1min'
        when s.duration_s < 3600     then '1min to 1h'
        else 'over 1h'
    end                              as duration_bucket,
    s.n_events,
    s.n_warn,
    s.n_components
from {{ ref('int_block_sessions') }} s
join {{ ref('stg_block_labels') }} l using (block_id)
