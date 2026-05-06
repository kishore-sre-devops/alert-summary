# Hardware Scheduler — End-to-End Documentation

## Overview

The **Hardware Scheduler** collects CPU, Memory, Disk, and Uptime metrics from all registered servers (DC/DR physical + AWS EC2 + ECS Fargate), aggregates them into a single worst-case payload, and submits to the LAMA Exchange API every 5 minutes.

**File:** `api/backend/app/schedulers/hardware.py`
**Scheduler Name:** `Hardware-Scheduler`
**Metric Type:** `hardware`
**Trigger:** Every 5 minutes (CronTrigger `*/5` IST) via `scheduler_main.py`

---

## End-to-End Flow

```
┌─────────────────────────────────────────────────────────────────────┐
│  scheduler_main.py (APScheduler CronTrigger */5 IST)               │
│  └─> lama_exchange_sync_scheduler()                                │
│       └─> ThreadPoolExecutor.submit(hardware_scheduler, env)       │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│  hardware_scheduler(environment="uat"|"prod")                      │
│                                                                     │
│  1. Validate exchange is enabled for this environment              │
│  2. Fetch Mimir URL from metric_sources (if configured)            │
│  3. Collect AWS ECS metrics (async) → collect_aws_hardware_metrics │
│  4. Fetch server list from DB (server_status + server_selection)   │
│  5. For each server:                                               │
│     a. Try Mimir (Prometheus) → MimirCollector                     │
│     b. Fallback to CloudWatch → AWSCollector                       │
│     c. Fallback to DB static values                                │
│  6. Update server_status DB + Redis Hot Store                      │
│  7. Aggregate all servers → aggregate_worst_case() per metric      │
│  8. For each enabled exchange (NSE/BSE/MCX/NCDEX):                 │
│     a. Get auth token (cached JWT)                                 │
│     b. Get next sequence ID                                        │
│     c. Send to LAMA Exchange API                                   │
│     d. Handle 704 retry if sequence mismatch                       │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Metric Keys & How Each Is Fetched

### 1. CPU (`cpu`)
**LAMA Format:** `{ "min": float, "max": float, "avg": float, "med": float }` (percentage 0–100)

| Source Type | How It's Fetched | AWS API / Query |
|---|---|---|
| **EC2 Instance** | CloudWatch `AWS/EC2` → `CPUUtilization` | `cw.get_metric_statistics(Namespace="AWS/EC2", MetricName="CPUUtilization", Dimensions=[InstanceId], Period=60, Statistics=["Average"])` |
| **ECS Fargate** | CloudWatch `ECS/ContainerInsights` → `CpuUtilized / CpuReserved × 100` | Two calls: `CpuUtilized` (Average) and `CpuReserved` (Average), then `(utilized/reserved)*100` |
| **ECS EC2-based** | Same as Fargate, fallback to `AWS/ECS` → `CPUUtilization` | If ContainerInsights returns empty, uses `AWS/ECS` namespace directly |
| **Physical DC/DR** | Prometheus/Mimir via `lgtm_provider.fetch_metric_stats("cpu", server_ip)` | PromQL: `100 - (avg(rate(node_cpu_seconds_total{mode="idle",instance=~"IP.*"}[5m])) * 100)` |
| **Fallback** | PostgreSQL `server_status.cpu` column | `SELECT cpu FROM server_status WHERE id = :sid` |

**Calculation:**
- CloudWatch: 5-minute window, 60s period → get all datapoints → `min(values)`, `max(values)`, `mean(values)`, `median(values)`
- Mimir: `fetch_metric_stats()` queries last 5 minutes of scrape data, computes min/max/avg/med
- Values clamped to 0–100 range

### 2. Memory (`memory`)
**LAMA Format:** `{ "min": float, "max": float, "avg": float, "med": float }` (percentage 0–100)

| Source Type | How It's Fetched | AWS API / Query |
|---|---|---|
| **EC2 Instance** | CloudWatch `CWAgent` → `mem_used_percent` | `cw.get_metric_statistics(Namespace="CWAgent", MetricName="mem_used_percent", Dimensions=[InstanceId])` |
| **ECS Fargate** | `ECS/ContainerInsights` → `MemoryUtilized / MemoryReserved × 100` | Same pattern as CPU |
| **Physical DC/DR** | Mimir → `memory` query | PromQL: `(1 - node_memory_MemAvailable_bytes/node_memory_MemTotal_bytes) * 100` |
| **Fallback** | PostgreSQL `server_status.memory` | Direct DB read |

**Note:** EC2 requires CloudWatch Agent installed. If `CWAgent` namespace returns empty, value defaults to 0.

### 3. Disk (`disk`)
**LAMA Format:** `{ "min": float, "max": float, "avg": float, "med": float }` (percentage 0–100)

| Source Type | How It's Fetched | AWS API / Query |
|---|---|---|
| **EC2 Instance** | CloudWatch `CWAgent` → `disk_used_percent` | `cw.get_metric_statistics(Namespace="CWAgent", MetricName="disk_used_percent", Dimensions=[InstanceId])` |
| **ECS Fargate** | `ECS/ContainerInsights` → `EphemeralStorageUtilized / EphemeralStorageReserved × 100` | Two calls, percentage calculation |
| **Physical DC/DR** | Mimir → `disk` query | PromQL: worst-case partition `max(node_filesystem_size_bytes - node_filesystem_avail_bytes) / node_filesystem_size_bytes * 100` |
| **Fallback** | PostgreSQL `server_status.disk` | Direct DB read |

### 4. Uptime (`uptime`)
**LAMA Format:** `{ "min": int, "max": int, "avg": int, "med": int }` (minutes, rounded to integer)

| Source Type | How It's Fetched | AWS API / Query |
|---|---|---|
| **EC2 Instance** | `ec2.describe_instances(InstanceIds=[id])` → `LaunchTime` | `(now_utc - LaunchTime).total_seconds() / 60.0` |
| **ECS Fargate/EC2** | `ecs.list_tasks()` → `ecs.describe_tasks()` → `startedAt` | `(now_utc - startedAt).total_seconds() / 60.0` |
| **Physical DC/DR** | Mimir → `uptime` query (returns seconds) | PromQL: `node_time_seconds - node_boot_time_seconds`, then `/60` for minutes |
| **Fallback** | `calculate_metric_stats()` from ClickHouse/Postgres | Historical aggregation |

**Calculation:** Raw seconds from Prometheus are divided by 60 to convert to minutes. All stats values are `int(round(val))`.

---

## Data Collection Strategy (Priority Order)

```
For each server:
  1. Is it AWS (location_id=3)?
     ├── YES → Try Mimir first (if mimir_url configured)
     │         ├── Got data? → Use it
     │         └── No data? → Try CloudWatch (AWSCollector)
     │                        ├── EC2? → collect_ec2_hardware_metrics(instance_id)
     │                        └── ECS? → collect_ecs_hardware_metrics(cluster, service)
     └── NO (Physical DC/DR) →
         ├── Try Mimir/Prometheus via lgtm_provider
         └── Fallback to server_status DB values
```

---

## Aggregation Logic

After collecting metrics from ALL servers, the scheduler calls `aggregate_worst_case()` for each metric key:

```python
# For statistical metrics (cpu, memory, disk, uptime):
result = {
    "name": "cpu",
    "min": min(all_server_mins),        # Best case across fleet
    "max": max(all_server_maxs),        # Worst case across fleet
    "avg": mean(all_server_avgs),       # Fleet average
    "med": median(all_server_avgs),     # Fleet median
    "worst_case_source": "server-name (ip)"  # Which server had the peak
}
```

This produces exactly 4 metric objects: `cpu`, `memory`, `disk`, `uptime`.

---

## LAMA Exchange Submission

For each enabled exchange (NSE=1, BSE=2, MCX=4, NCDEX=5):

1. **Auth Token:** `get_lama_exchange_token(env, exchange_id)` — cached JWT, auto-refreshes
2. **Sequence ID:** `get_next_sequence_id(env, member_id, exchange_id, "hardware")` — monotonically increasing per exchange per metric type
3. **API Call:** `send_metrics_to_lama_exchange()` with payload:

```json
{
  "memberId": "<member_id>",
  "exchangeId": 1,
  "applicationId": -1,
  "sequenceId": 42,
  "metricType": "hardware",
  "timestamp": 1710000000000,
  "metricData": [
    { "key": "cpu",    "value": { "min": 12.5, "max": 89.3, "avg": 45.2, "med": 43.1 } },
    { "key": "memory", "value": { "min": 30.0, "max": 78.5, "avg": 55.0, "med": 54.2 } },
    { "key": "disk",   "value": { "min": 20.0, "max": 65.0, "avg": 42.0, "med": 41.0 } },
    { "key": "uptime", "value": { "min": 1440, "max": 43200, "avg": 22320, "med": 21600 } }
  ]
}
```

4. **Error 704 Retry:** If exchange returns `responseCode: 704` (sequence mismatch), extract `expectedSequenceId` from response and retry immediately with the hinted sequence.

---

## AWS IAM Requirements

- **Role ARN:** `arn:aws:iam::396913716058:role/SMC-LAMA-CrossAccount-ReadOnly`
- **External ID:** `SMC-LAMA-OBSERVABILITY`
- **Required Permissions:**
  - `cloudwatch:GetMetricStatistics` (namespaces: `AWS/EC2`, `CWAgent`, `ECS/ContainerInsights`, `AWS/ECS`)
  - `ec2:DescribeInstances` (for uptime/LaunchTime)
  - `ecs:DescribeServices`, `ecs:ListTasks`, `ecs:DescribeTasks` (for ECS uptime)

---

## Side Effects (DB + Cache Updates)

During collection, the scheduler also:
1. **Updates `server_status` table:** Sets `cpu`, `memory`, `disk`, `status='online'`, `last_seen=now` for each server with live data
2. **Updates Redis Hot Store:** `update_server_hot_data(server_id, metrics, category="hardware")` for near-zero latency dashboard reads
3. **Logs to `exchange_transactions`:** Every submission (success or failure) is recorded with full payload and response
