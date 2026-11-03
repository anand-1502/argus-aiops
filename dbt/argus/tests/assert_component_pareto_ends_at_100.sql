select max(cumulative_pct) as top from {{ ref('mart_component_health') }} having max(cumulative_pct) not between 99.9 and 100.1
