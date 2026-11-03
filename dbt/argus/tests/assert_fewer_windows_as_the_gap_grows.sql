-- A wider gap can only merge windows, never split them: the count must not increase with the gap.
select a.gap_seconds, a.windows, b.gap_seconds as larger_gap, b.windows as larger_gap_windows
from {{ ref('mart_window_sensitivity') }} a
join {{ ref('mart_window_sensitivity') }} b on b.gap_seconds > a.gap_seconds
where b.windows > a.windows
