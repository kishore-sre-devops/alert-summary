# Metrics Display Flow

## Overview

When a user views server details in the LAMA dashboard, the UI queries the FastAPI backend which fetches real-time metrics from Prometheus/Mimir and historical data from ClickHouse, then renders interactive Chart.js graphs with auto-refresh.

---

## Flow Diagram

```
┌──────────────────┐
│  User clicks on  │
│  Server Details  │
└────────┬─────────┘
         │
         │  1. GET /api/v1/servers/{id}/metrics?range=1h
         ▼
┌────────────────────────────────────────────────────────┐
│                   FASTAPI BACKEND                       │
│                                                         │
│  lgtm_provider.py — Metrics Provider                   │
│                                                         │
│  1. Check server type (Windows / Linux / AWS)          │
│  2. Build appropriate PromQL query                     │
│  3. Query Prometheus/Mimir                             │
│  4. Transform response to standard format              │
└──────────────────────────┬─────────────────────────────┘
                           │
                           │  2. Return metrics JSON
                           ▼
┌────────────────────────────────────────────────────────┐
│                     REACT UI                            │
│                                                         │
│  ServerDetails.jsx / MetricChartCard.jsx               │
│                                                         │
│  • Parse timestamp (handle ts/timestamp fields)        │
│  • Render Chart.js line/area charts                    │
│  • Show "No data available" if empty                   │
│  • Auto-refresh every 30 seconds                       │
└────────────────────────────────────────────────────────┘
```

---

## Query Strategy by Server Type

| Server Type | Metrics Provider | Query Method |
|---|---|---|
| **Linux** | Prometheus/Mimir | PromQL: `node_cpu_seconds_total`, `node_memory_MemAvailable_bytes`, `node_filesystem_avail_bytes` |
| **Windows** | Prometheus/Mimir | PromQL: `windows_cpu_time_total`, `windows_os_physical_memory_free_bytes`, `windows_logical_disk_free_bytes` |
| **AWS EC2** | Mimir first, fallback CloudWatch | Mimir PromQL or CloudWatch `AWS/EC2`, `CWAgent` namespaces |
| **AWS ECS** | CloudWatch | `ECS/ContainerInsights`: CpuUtilized, MemoryUtilized |

---

## Data Flow for Different Time Ranges

| Range | Data Source | Resolution |
|---|---|---|
| Last 1 hour | Prometheus/Mimir (live) | ~10 second intervals |
| Last 6 hours | Prometheus/Mimir (live) | ~10 second intervals |
| Last 24 hours | ClickHouse `server_metrics` | Raw datapoints (every 6-10s) |
| Last 7 days | ClickHouse `server_metrics_hourly` | Hourly aggregated (min/max/avg) |
| Last 30 days | ClickHouse `server_metrics_hourly` | Hourly aggregated (min/max/avg) |

---

## UI Components

| Component | File | Role |
|---|---|---|
| Server Details Page | `ServerDetails.jsx` | Full server view with all metric charts |
| Metric Chart Card | `MetricChartCard.jsx` | Individual chart widget (Chart.js line/area) |
| Dashboard | `Servers.jsx` | Overview grid with status badges and sparklines |
| Historical Data | `HistoricalData.jsx` | Date-range picker with exportable charts |

---

## Auto-Refresh Behavior

- Dashboard server list: refreshes every **30 seconds**
- Server detail charts: refreshes every **30 seconds**
- Redis Hot Store provides sub-second reads for dashboard status badges
- ClickHouse queries are used for chart rendering (heavier but detailed)
