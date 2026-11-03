-- Loghub publishes 16,838 anomalous blocks out of 575,061 (2.93%). Fail if the pipeline drifts from that.
select anomalous_blocks, total_blocks, anomaly_rate_pct
from {{ ref('mart_kpis') }}
where anomalous_blocks <> 16838 or total_blocks <> 575061 or anomaly_rate_pct <> 2.93
