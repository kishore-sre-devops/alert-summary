CREATE DATABASE IF NOT EXISTS lama;

CREATE TABLE IF NOT EXISTS lama.server_metrics
(
    server_id UInt32,
    metric_name String,
    value Float64,
    interface_name Nullable(String),
    ts DateTime DEFAULT now()
)
ENGINE = ReplacingMergeTree
PARTITION BY toYYYYMM(ts)
ORDER BY (server_id, metric_name, interface_name, ts)
TTL ts + toIntervalDay(30)
SETTINGS allow_nullable_key = 1;

CREATE TABLE IF NOT EXISTS lama.server_metrics_hourly
(
    server_id UInt32,
    metric_name String,
    interface_name Nullable(String),
    ts DateTime,
    min_value SimpleAggregateFunction(min, Float64),
    max_value SimpleAggregateFunction(max, Float64),
    sum_value SimpleAggregateFunction(sum, Float64),
    count SimpleAggregateFunction(sum, UInt64)
)
ENGINE = AggregatingMergeTree
PARTITION BY toYYYYMM(ts)
ORDER BY (server_id, metric_name, interface_name, ts)
TTL ts + toIntervalDay(730)
SETTINGS allow_nullable_key = 1;

CREATE MATERIALIZED VIEW IF NOT EXISTS lama.server_metrics_hourly_mv
TO lama.server_metrics_hourly
AS SELECT
    server_id,
    metric_name,
    interface_name,
    toStartOfHour(ts) AS ts,
    min(value) AS min_value,
    max(value) AS max_value,
    sum(value) AS sum_value,
    count(*) AS count
FROM lama.server_metrics
GROUP BY server_id, metric_name, interface_name, ts;
