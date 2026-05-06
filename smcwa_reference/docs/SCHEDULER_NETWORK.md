# Network Scheduler — End-to-End Documentation

## Overview

The **Network Scheduler** collects Bandwidth and Packet Count metrics from AWS Load Balancers (ALB/NLB) and physical DC/DR servers, aggregates them into a single fleet-wide worst-case payload, and submits to the LAMA Exchange API every 5 minutes.

**File:** `api/backend/app/schedulers/network.py`  
**Scheduler Name:** `Network-Scheduler`  
**Metric Type:** `network`  
**Trigger:** Every 5 minutes (CronTrigger `*/5` IST) via `scheduler_main.py`

---

## End-to-End Flow

```
┌─────────────────────────────────────────────────────────────────────┐
│  scheduler_main.py → lama_exchange_sync_scheduler()                │
│  └─> ThreadPoolExecutor.submit(network_scheduler, env)             │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│  network_scheduler(environment="uat"|"prod")                       │
│                                                                     │
│  1. Validate exchange is enabled                                   │
│  2. Collect AWS LB metrics (async) → collect_aws_network_metrics() │
│     ├── For each ALB in ECS_SERVICES → collect_alb_network_metrics │
│     └── For each NLB in ECS_SERVICES → collect_nlb_network_metrics │
│  3. Aggregate AWS results per metric key                           │
│  4. Fetch physical servers from DB (server_status + selection)     │
│  5. For each physical server (ThreadPoolExecutor):                 │
│     └── create_metric_for_server() via Prometheus/Mimir/DB         │
│  6. Combine ALL locations into fleet-wide aggregation              │
│  7. For each enabled exchange:                                     │
│     a. Log calculated metrics                                      │
│     b. Get token → Get sequence → Send payload                    │
│     c. Handle 704 retry                                            │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Metric Keys & How Each Is Fetched

### 1. Bandwidth (`bandwidth`)
**LAMA Format:** `{ "min": float, "max": float, "avg": float, "med": float }` (percentage 0–100)

| Source Type | What It Measures | How It's Fetched |
|---|---|---|
| **ALB** | Load balancer capacity usage | CloudWatch `AWS/ApplicationELB` → `ConsumedLCUs` (Average), capped at 100 |
| **NLB** | Network throughput as % of 1 Gbps | CloudWatch `AWS/NetworkELB` → `ProcessedBytes` (Sum) → `((bytes/60) / 125,000,000) × 100` |
| **Physical DC/DR** | Network interface utilization | Prometheus/Mimir → `network_bandwidth` query via `lgtm_provider.fetch_metric_stats()` |
| **Fallback** | Zero | `create_metric_for_server()` returns `{min:0, max:0, avg:0, med:0}` |

**Calculation (ALB — ConsumedLCUs):**
```
raw_values = CloudWatch ConsumedLCUs (Average) over 5 minutes, 60s period
bw_values = [min(value, 100.0) for value in raw_values]  # Cap at 100%
bandwidth = { min: min(bw_values), max: max(bw_values), avg: mean(bw_values), med: median(bw_values) }
```

**Calculation (NLB — ProcessedBytes):**
```
raw_values = CloudWatch ProcessedBytes (Sum) over 5 minutes, 60s period
# Convert bytes/minute to % of 1 Gbps (125,000,000 bytes/sec)
bw_pct = [min(((value / 60.0) / 125_000_000) * 100.0, 100.0) for value in raw_values]
bandwidth = aggregate(bw_pct)
```

**Calculation (Physical — Prometheus):**
```
lgtm_provider.fetch_metric_stats("network_bandwidth", server_ip, time_window_minutes=5)
# Returns { min, max, avg, med } already in percentage
# Values clamped to 0–100 range
```

### 2. Packet Count (`packetCount`)
**LAMA Format:** `integer` (plain value — total error/anomaly packet count)

| Source Type | What It Measures | How It's Fetched |
|---|---|---|
| **ALB** | HTTP error responses | CloudWatch → `HTTPCode_ELB_5XX_Count` (Sum) + `HTTPCode_ELB_4XX_Count` (Sum) |
| **NLB** | TCP connection anomalies | CloudWatch → `TCP_Client_Reset_Count` (Sum) + `TCP_Target_Reset_Count` (Sum) + `UnHealthyHostCount` (Sum) |
| **Physical DC/DR** | Packet count from agent | Prometheus/Mimir → `packet_count` query via `lgtm_provider` |
| **Fallback** | Zero | `create_metric_for_server()` returns `{"value": 0}` |

**Calculation (ALB):**
```
err_5xx = sum(CloudWatch HTTPCode_ELB_5XX_Count over 5 min)
err_4xx = sum(CloudWatch HTTPCode_ELB_4XX_Count over 5 min)
packetCount = int(err_5xx + err_4xx)
```

**Calculation (NLB):**
```
rst_client = sum(TCP_Client_Reset_Count)
rst_target = sum(TCP_Target_Reset_Count)
unhealthy  = sum(UnHealthyHostCount)
packetCount = int(rst_client + rst_target + unhealthy)
```

**Aggregation for packetCount (plain value):**
```python
# packetCount uses SUM across all sources (total error packets fleet-wide)
final_packetCount = sum(all_source_values)
```

---

## Data Collection Strategy

```
network_scheduler(environment):

  PHASE 1 — AWS Cloud (collect_aws_network_metrics):
    For each service in ECS_SERVICES (hardcoded config):
      ├── type="ALB" → collect_alb_network_metrics(alb_arn)
      │   ├── ConsumedLCUs → bandwidth
      │   └── HTTPCode_ELB_5XX + 4XX → packetCount
      │
      └── type="NLB" → collect_nlb_network_metrics(nlb_arn)
          ├── ProcessedBytes → bandwidth (% of 1Gbps)
          └── TCP Resets + UnHealthy → packetCount

    Aggregate AWS results → aws_metrics (one bandwidth + one packetCount)

  PHASE 2 — Physical DC/DR Servers:
    Query server_status + lama_exchange_server_selection
    Filter: enabled=TRUE, last_seen within 15 minutes
    Group by location_id

    For each location group (ThreadPoolExecutor, 5 workers):
      For each server:
        ├── create_metric_for_server("bandwidth", ...) → Prometheus/Mimir/DB
        └── create_metric_for_server("packetCount", ...) → Prometheus/Mimir/DB

    Aggregate per location → location_metrics

  PHASE 3 — Fleet Aggregation:
    Combine AWS + all physical locations
    aggregate_worst_case() per metric key across ALL locations
    → fleet_metrics (one bandwidth + one packetCount)
```

---

## Multi-Location Aggregation

The Network Scheduler is unique in that it aggregates across multiple locations:

```
Location 3 (AWS Cloud):     bandwidth={min:5, max:30, avg:18}, packetCount=12
Location 1 (DC Physical):   bandwidth={min:10, max:45, avg:25}, packetCount=3
Location 2 (DR Physical):   bandwidth={min:8, max:35, avg:20}, packetCount=1

Fleet Aggregate:
  bandwidth = { min: 5, max: 45, avg: 21, med: 20 }   ← worst-case across all
  packetCount = 16                                       ← sum across all
```

---

## LAMA Exchange Submission

```json
{
  "memberId": "<member_id>",
  "exchangeId": 1,
  "applicationId": -1,
  "sequenceId": 63,
  "metricType": "network",
  "timestamp": 1710000000000,
  "metricData": [
    { "key": "bandwidth",   "value": { "min": 5.0, "max": 45.0, "avg": 21.0, "med": 20.0 } },
    { "key": "packetCount", "value": 16 }
  ]
}
```

---

## AWS IAM Requirements

Same cross-account role, plus:
- `cloudwatch:GetMetricStatistics` (namespaces: `AWS/ApplicationELB`, `AWS/NetworkELB`)
- Metrics used:
  - ALB: `ConsumedLCUs`, `HTTPCode_ELB_5XX_Count`, `HTTPCode_ELB_4XX_Count`
  - NLB: `ProcessedBytes`, `TCP_Client_Reset_Count`, `TCP_Target_Reset_Count`, `UnHealthyHostCount`

---

## Physical Server Requirements

- Prometheus/Mimir agent running on each server, exposing `node_exporter` metrics
- LGTM provider configured with Mimir URL in `metric_sources` table
- Servers must have `last_seen` within 15 minutes to be included (stale servers are excluded)

---

## Side Effects

1. **Logs calculated metrics:** `log_calculated_metrics_only()` records the fleet-wide + per-server breakdown before submission
2. **Logs to `exchange_transactions`:** Full payload + response recorded
3. **No DB/Hot Store update:** Unlike Hardware and Application schedulers, Network does not update `server_status` or Redis Hot Store during collection
