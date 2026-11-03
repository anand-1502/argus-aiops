-- A calendar of every hour in the capture, so charts have no gaps and hours can be grouped by day or time of day.
with bounds as (
    select min(hour_ts) as lo, max(hour_ts) as hi from {{ ref('stg_events') }}
)
select
    h                                                as hour_ts,
    h::date                                          as day,
    extract(hour from h)::int                        as hour_of_day,
    to_char(h, 'Dy')                                 as day_name,
    extract(hour from h) between 8 and 19            as is_business_hours
from bounds, generate_series(lo, hi, interval '1 hour') as h
