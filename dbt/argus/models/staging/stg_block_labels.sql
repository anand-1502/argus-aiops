select
    block_id,
    label,
    (label = 'Anomaly') as is_anomaly
from {{ source('argus', 'block_labels') }}
