-- Components with the plane each belongs to (from the component_taxonomy seed); unknown ones land in 'Other'.
select
    md5(c.component)                       as component_key,
    c.component,
    coalesce(t.plane, 'Other')             as plane
from (select distinct component from {{ ref('stg_events') }}) c
left join {{ ref('component_taxonomy') }} t on t.component = c.component
