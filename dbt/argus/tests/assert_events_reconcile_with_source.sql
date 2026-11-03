-- Reconciliation: nothing is lost or duplicated between the raw table and the fact table.
select s.n as source_rows, f.n as fact_rows
from (select count(*) as n from {{ source('argus', 'events') }}) s,
     (select sum(events) as n from {{ ref('fact_hourly_events') }}) f
where s.n <> f.n
