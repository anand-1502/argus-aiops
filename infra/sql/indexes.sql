CREATE INDEX IF NOT EXISTS events_block_id_idx ON events (block_id);
CREATE INDEX IF NOT EXISTS events_ts_idx ON events (ts);
CREATE INDEX IF NOT EXISTS events_component_idx ON events (component);
ANALYZE events;
