# Plan: Prometheus Application Metrics Integration

This plan transitions the application metrics collection from Elasticsearch to the new Prometheus data source (`http://10.215.33.196:9090`).

## Objective
Migrate "Odiin-Trading-Logs" and other application metrics to Prometheus with full LAMA V1.3 21-day audit compliance.

## Key Files & Context
- `api/backend/app/collectors/prometheus_collector.py`: For the new collection logic.
- `api/backend/app/schedulers/application.py`: To support the new `prometheus_app` source type.
- `api/backend/app/schedulers/historical_application.py`: For the 21-day historical calculations using PromQL.

## Implementation Steps

### 1. Enhance PrometheusCollector
Add two methods to `api/backend/app/collectors/prometheus_collector.py`:
- `fetch_metric_stats`: Generic helper to fetch a 5-minute window of points for a PromQL query.
- `collect_lama_app_metrics`: Specific method to fetch `lama_avg_value`, `lama_min_value`, etc., for throughput and latency.

### 2. Update Application Scheduler
Modify `api/backend/app/schedulers/application.py`:
- Add `prometheus_app` to the `SELECT` query for metric sources.
- Add a logic branch for `ms_type == 'prometheus_app'`.
- Use `PrometheusCollector.collect_lama_app_metrics(instance=config.get("instance"))` to fetch real-time data.

### 3. Implement 21-Day Historical Scheduler
Modify `api/backend/app/schedulers/historical_application.py`:
- Add `calculate_21d_prometheus_app_metrics(prom_url, instance)` function.
- Use PromQL `avg_over_time`, `max_over_time`, and `min_over_time` with a `[21d]` range on the `lama_avg_value`, `lama_max_value`, and `lama_min_value` metrics.
- Integrate this function into the main `historical_application_scheduler` loop for the `prometheus_app` source type.

## Verification & Testing
1. **Manual Check:** Run a test script to call `collect_lama_app_metrics` and verify the output structure.
2. **Real-time Test:** Trigger the `Application-Scheduler` and verify logs show successful collection from Prometheus.
3. **Historical Test:** Trigger the `Historical-App-Scheduler` for the new source and verify 21-day stats are calculated correctly.
