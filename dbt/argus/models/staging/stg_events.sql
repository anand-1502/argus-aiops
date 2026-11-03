-- One typed row per log line. A view: it adds no storage, and downstream tables do the heavy work once.
select
    ts,
    date_trunc('hour', ts)            as hour_ts,
    pid,
    level,
    component,
    nullif(block_id, '')              as block_id,
    content,
    template
from {{ source('argus', 'events') }}
