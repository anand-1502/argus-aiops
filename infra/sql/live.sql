CREATE TABLE IF NOT EXISTS live_events (
    ts          timestamptz NOT NULL,
    pid         integer,
    level       text NOT NULL,
    component   text NOT NULL,
    block_id    text,
    content     text NOT NULL,
    template    text NOT NULL,
    batch       integer NOT NULL,
    ingested_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS live_events_batch_idx ON live_events (batch);
