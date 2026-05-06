# Application Scheduler — End-to-End Documentation

## Overview

The **Application Scheduler** collects Throughput, Latency, Error Rates, and Historical metrics from ECS services (via ALB/NLB/CloudWatch) and Elasticsearch, aggregates them into a fleet-wide payload, and submits to the LAMA Exchange API every 5 minutes.

**File:** `api/backend/app/schedulers/application.py`
**Scheduler Name:** `Application-Scheduler`
**Metric Type:** `application`
**Trigger:** Every 5 minutes (CronTrigger `*/5` IST) via `scheduler_main.py`

---

## End-to-End Flow

```
┌─────────────────────────────────────────────────────────────────────┐
│  scheduler_main.py → lama_exchange_sync_scheduler()                │
│  └─> ThreadPoolExecutor.submit(application_scheduler, env)         │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│  application_scheduler(environment="uat"|"prod")                   │
│                                                                     │
│  1. Validate exchange is enabled                                   │
│  2. collect_application_metrics(environment) [async]               │
│     a. Query metric_sources DB for ECS services (type='ecs')       │
│     b. Query metric_sources DB for generic sources (ES/MySQL/PG)   │
│     c. For each ECS service:                                       │
│        - Has ALB? → collect_alb_application_metrics()              │
│        - Has NLB? → collect_nlb_application_metrics()              │
│        - Neither? → collect_ecs_application_metrics_fallback()     │
│     d. For each ES source:                                         │
│        - ESCollector.collect_application_metrics()                  │
│     e. Legacy loop for hardcoded ECS_SERVICES                      │
│  3. aggregate_application_fleet(payload_list)                      │
│  4. For each enabled exchange:                                     │
│     a. Get token → Get sequence → Send payload                    │
│     b. Handle 704 retry                                            │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Metric Keys & How Each Is Fetched

### 1. Throughput (`throughput`)
**LAMA Format:** `{ "min": float, "max": float, "avg": float, "med": float }` (requests/second)

| Source Type | How It's Fetched | AWS API / Query |
|---|---|---|
| **ALB Service** | CloudWatch `AWS/ApplicationELB` → `RequestCount` (Sum) | `cw.get_metric_statistics(Namespace="AWS/ApplicationELB", MetricName="RequestCount", Dimensions=[LoadBalancer, TargetGroup], Statistics=["Sum"])`. **Note:** Uses TargetGroup dimension for accuracy on shared ALBs. |
| **NLB Service** | CloudWatch `AWS/NetworkELB` → `NewFlowCount` (Sum) | `NewFlowCount / 60.0` = new TCP connections per second. |
| **ECS Fallback** | `ECS/ContainerInsights` → `RunningTaskCount` × 10 | Heuristic: 1 running task ≈ 10 req/s baseline. |
| **Elasticsearch** | ES index `lama-smc<YYYY.MM.DD>` → topic `lamareqesttime` | Aggregation query on today's index, last 15 minutes, extracts `Minimum`, `Maximum`, `Average`, `Median` fields from latest document. |

**Calculation (ALB):**
```
# LAMA V2.0 Fix: Isolated traffic for shared ALBs
raw_values = CloudWatch RequestCount (Sum per 60s period) over 5 minutes 
             Filtered by: [LoadBalancer="...", TargetGroup="..."]
throughput_per_sec = [value / 60.0 for value in raw_values]
result = { min: min(throughput_per_sec), max: max(...), avg: mean(...), med: median(...) }
```

### 2. Latency (`latency`)
**LAMA Format:** `{ "min": float, "max": float, "avg": float, "med": float }` (milliseconds)

| Source Type | How It's Fetched | AWS API / Query |
|---|---|---|
| **ALB Service** | CloudWatch `AWS/ApplicationELB` → `TargetResponseTime` (Average) | Returns seconds → multiply by 1000 for ms. Dimensions: `[LoadBalancer, TargetGroup]`. |
| **NLB Service** | `ECS/ContainerInsights` → `CpuUtilized` as proxy | Heuristic: `max(cpu_pct * 10.0, 1.0)` ms (1% CPU ≈ 10ms processing). |
| **ECS Fallback** | `ECS/ContainerInsights` → `CpuUtilized` as proxy | Heuristic: `max(cpu_pct * 5.0, 1.0)` ms. |
| **Elasticsearch** | ES index → topic `lama_avgresponsetime` | Same aggregation pattern, extracts `Minimum`, `Maximum`, `Average` from latest doc. |

**Calculation (ALB):**
```
# Isolated latency for specific ECS service
raw_values = CloudWatch TargetResponseTime (Average, in seconds)
             Filtered by: [LoadBalancer="...", TargetGroup="..."]
latency_ms = [value * 1000.0 for value in raw_values]
result = aggregate(latency_ms)
```

### 3. Failure Trade API (`failureTradeApi`)
**LAMA Format:** `integer` (plain value, count of failures)

| Source Type | How It's Fetched | AWS API / Query |
|---|---|---|
| **ALB Service** | CloudWatch → `HTTPCode_Target_5XX_Count` (Sum) | `sum(all_5xx_datapoints)` over 5-minute window |
| **NLB Service** | CloudWatch → `TCP_Target_Reset_Count` (Sum) | TCP resets from target = connection failures |
| **ECS Fallback** | `DesiredTaskCount - RunningTaskCount` | Tasks that failed to start |
| **Elasticsearch** | ES index → topic `lama_apierrorcount` | `Sum` or `count` field from latest document |

### 4. Failure Authentication (`failureAuthentication`)
**LAMA Format:** `integer` (plain value, count of auth failures)

| Source Type | How It's Fetched | AWS API / Query |
|---|---|---|
| **ALB Service** | CloudWatch → `HTTPCode_Target_4XX_Count` (Sum) | `sum(all_4xx_datapoints)` — 4xx includes 401/403 auth errors |
| **NLB Service** | CloudWatch → `TCP_Client_Reset_Count` (Sum) | Client-side TCP resets |
| **ECS Fallback** | Always `0` | No auth metric available without LB |
| **Elasticsearch** | Always `0` | Not tracked in ES topics currently |

### 5. Historical Throughput (`historicalThroughput`)
**LAMA Format:** `{ "min": float, "max": float, "avg": float, "med": float }` (req/sec, 21-day window)

| Source Type | How It's Fetched |
|---|---|
| **ALB** | CloudWatch `RequestCount` (Sum) with 1-hour period over 21 days → `Sum / 3600` for req/sec |
| **NLB** | Same via `get_historical_metrics()` |
| **Elasticsearch** | ES wildcard `lama-smc*` → aggregation over 21 days on topic `lamareqesttime` → `min_val`, `max_val`, `avg_val` |

### 6. Historical Latency (`historicalLatency`)
**LAMA Format:** `{ "min": float, "max": float, "avg": float, "med": float }` (ms, 21-day window)

| Source Type | How It's Fetched |
|---|---|
| **ALB** | CloudWatch `TargetResponseTime` (Average/Min/Max) with 1-hour period over 21 days → seconds × 1000 |
| **Elasticsearch** | ES wildcard `lama-smc*` → aggregation over 21 days on topic `lama_avgresponsetime` |

---

## Data Collection Strategy

```
collect_application_metrics(environment):

  1. DYNAMIC DISCOVERY (metric_sources table):
     ├── type='ecs' → For each ECS service:
     │   ├── Has targetGroupArn + albArn? → collect_alb_application_metrics()
     │   ├── Has targetGroupArn + nlbArn? → collect_nlb_application_metrics()
     │   └── No LB? → collect_ecs_application_metrics_fallback()
     │
     └── type='elasticsearch' → For each ES source:
         └── ESCollector.collect_application_metrics(index_pattern, topics, client_name)

  2. LEGACY LOOP (ECS_SERVICES hardcoded list):
     └── type='ELASTICSEARCH' or 'BACKGROUND' → ESCollector or zeroed metrics

  3. Each result → MetricMapper.map_application(raw) → standardized format
```

---

## Aggregation Logic

`aggregate_application_fleet()` combines all per-service metrics into ONE fleet-wide record:

```python
# Statistical metrics (throughput, latency, historicalThroughput, historicalLatency):
for each metric:
    min = min(all_service_mins)
    max = max(all_service_maxs)
    avg = mean(all_service_avgs)
    med = median(all_service_avgs)

# Plain metrics (failureTradeApi, failureAuthentication):
    value = sum(all_service_values)  # Total failures across fleet
```

The final payload sent to LAMA Exchange wraps this in:
```json
[{ "applicationId": -1, "metricData": [aggregated_metrics] }]
```

---

## LAMA Exchange Submission

```json
{
  "memberId": "<member_id>",
  "exchangeId": 1,
  "applicationId": -1,
  "sequenceId": 55,
  "metricType": "application",
  "timestamp": 1710000000000,
  "metricData": [
    { "key": "throughput",    "value": { "min": 5.2, "max": 120.5, "avg": 45.3, "med": 42.0 } },
    { "key": "latency",       "value": { "min": 1.2, "max": 350.0, "avg": 45.0, "med": 38.5 } },
    { "key": "failureTradeApi",       "value": 3 },
    { "key": "failureAuthentication", "value": 0 },
    { "key": "historicalThroughput",  "value": { "min": 2.0, "max": 200.0, "avg": 50.0, "med": 48.0 } },
    { "key": "historicalLatency",     "value": { "min": 0.5, "max": 500.0, "avg": 60.0, "med": 55.0 } }
  ]
}
```

---

## Side Effects (DB + Cache Updates)

1. **Upserts `application_status` table:** For each service, updates `latency_ms`, `throughput`, `failure_trade_api`, `failure_authentication`, `status`, `last_seen`
2. **Updates Redis Hot Store:** `update_server_hot_data(app_status_id, metrics, category="application")`
3. **Logs to `exchange_transactions`:** Full payload + response recorded

---

## AWS IAM Requirements

Same cross-account role as Hardware, plus:
- `cloudwatch:GetMetricStatistics` (namespaces: `AWS/ApplicationELB`, `AWS/NetworkELB`, `ECS/ContainerInsights`)
- `elasticloadbalancingv2:DescribeLoadBalancers` (implicit for ARN resolution)

---

## Elasticsearch Requirements

- **Index Pattern:** `lama-smc<YYYY.MM.DD>` (daily rollover)
- **Required Topics:** `lamareqesttime`, `lama_apierrorcount`, `lama_avgresponsetime`
- **Required Fields:** `@timestamp`, `topic`, `clientname`, `Minimum`, `Maximum`, `Average`, `Median`, `Sum`, `count`
- **Query Window:** Last 15 minutes for real-time, last 21 days for historical
