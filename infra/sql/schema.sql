DROP TABLE IF EXISTS events;
CREATE TABLE events (
    ts        timestamptz NOT NULL,
    pid       integer,
    level     text NOT NULL,
    component text NOT NULL,
    block_id  text,
    content   text NOT NULL,
    template  text NOT NULL
);

CREATE TABLE IF NOT EXISTS block_labels (
    block_id text PRIMARY KEY,
    label    text NOT NULL CHECK (label IN ('Normal', 'Anomaly'))
);
