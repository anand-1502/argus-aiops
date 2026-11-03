-- One row per block: everything the events say about that block's life.
select
    block_id,
    count(*)                                                    as n_events,
    min(ts)                                                     as first_ts,
    max(ts)                                                     as last_ts,
    extract(epoch from max(ts) - min(ts))::float8               as duration_s,
    count(*) filter (where level = 'WARN')                      as n_warn,
    count(distinct component)                                   as n_components
from {{ ref('stg_events') }}
where block_id is not null
group by block_id
