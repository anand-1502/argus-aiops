-- The headline must be reproducible from the published curve.
select k.incident_windows, s.windows
from {{ ref('mart_kpis') }} k
left join {{ ref('mart_window_sensitivity') }} s on s.gap_seconds = {{ var('incident_gap_seconds') }}
where s.windows is distinct from k.incident_windows
