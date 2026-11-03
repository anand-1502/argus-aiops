-- The gaps-and-islands grouping must neither drop nor double count a block.
select w.n as in_windows, b.n as anomalous
from (select sum(anomalous_blocks) as n from {{ ref('mart_incident_windows') }}) w,
     (select count(*) as n from {{ ref('dim_block') }} where is_anomaly) b
where w.n <> b.n
