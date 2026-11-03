-- Every labelled block must appear in dim_block exactly once (575,061 in the full load).
select l.n as labelled, d.n as in_dim
from (select count(*) as n from {{ source('argus', 'block_labels') }}) l,
     (select count(*) as n from {{ ref('dim_block') }}) d
where l.n <> d.n
