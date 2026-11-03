DROP TABLE IF EXISTS service_metrics;
CREATE TABLE service_metrics (
    ts      timestamptz NOT NULL,
    service text NOT NULL,
    metric  text NOT NULL,
    value   double precision NOT NULL,
    source  text NOT NULL CHECK (source IN ('derived-from-logs', 'simulated'))
);
CREATE INDEX service_metrics_idx ON service_metrics (service, metric, ts);
