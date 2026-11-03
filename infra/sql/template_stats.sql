-- distinct (template, block) pairs first; far cheaper than count(DISTINCT) over 11M rows
SET work_mem = '128MB';
DROP TABLE IF EXISTS template_stats;
CREATE TEMP TABLE pairs AS SELECT template, block_id FROM events WHERE block_id <> '' GROUP BY 1, 2;
CREATE TABLE template_stats AS
SELECT template, count(*) AS blocks,
       count(*)::float8 / (SELECT count(DISTINCT block_id) FROM pairs) AS frac_blocks
FROM pairs GROUP BY template;
CREATE UNIQUE INDEX template_stats_pk ON template_stats (template);
