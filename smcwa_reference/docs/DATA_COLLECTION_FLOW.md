# Data Collection Flow

## Overview

LAMA collects metrics from three source types — DC physical servers, DR physical servers, and AWS ECS containers. Data flows through Prometheus/Mimir (for physical) and CloudWatch/boto3 (for AWS) into the LAMA Scheduler, which stores everything in ClickHouse.

---

## Flow Diagram

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  DC SERVERS     │     │  DR SERVERS     │     │  AWS ECS        │
│  (Windows/Linux)│     │  (Windows/Linux)│     │  (Containers)   │
└────────┬────────┘     └────────┬────────┘     └────────┬────────┘
         │                       │                       │
         │ node_exporter         │ node_exporter         │ CloudWatch
         │ windows_exporter      │ windows_exporter      │ ContainerInsights
         ▼                       ▼                       ▼
┌─────────────────────────────────────────┐     ┌─────────────────┐
│         PROMETHEUS / MIMIR              │     │   AWS APIs      │
│       (Metrics Aggregation)             │     │   (boto3)       │
└────────────────────┬────────────────────┘     └────────┬────────┘
                     │                                   │
                     │ PromQL Queries                    │ CloudWatch API
                     ▼                                   ▼
┌─────────────────────────────────────────────────────────────────┐
│                      LAMA SCHEDULER                              │
│                                                                   │
│  Jobs (Every 1-5 minutes):                                       │
│  • collect_prom_metrics()     → Prometheus scrape (every 10s)    │
│  • collect_database_metrics() → DB status polling (every 6s)     │
│  • collect_ecs_app_metrics()  → ECS application data (every 1m)  │
│  • server_down_monitor()      → Server health check (every 2m)   │
│  • lama_exchange_sync()       → 4 parallel schedulers (every 5m) │
│    ├── Hardware:  CPU, Memory, Disk, Uptime                      │
│    ├── Application: Throughput, Latency, Errors                  │
│    ├── Database: Status, QSize, Bandwidth, Latency               │
│    └── Network: Bandwidth, PacketCount                           │
└────────────────────────────┬────────────────────────────────────┘
                             │
              ┌──────────────┼──────────────┐
              ▼              ▼              ▼
       ┌──────────┐  ┌──────────────┐  ┌────────┐
       │ClickHouse│  │  PostgreSQL  │  │ Redis  │
       │          │  │              │  │        │
       │Raw metrics│ │server_status │  │Hot Store│
       │Hourly agg│  │exchange_txns │  │Sessions │
       │Alert hist│  │scheduler_logs│  │Cache    │
       └──────────┘  └──────────────┘  └────────┘
```

---

## Collection Intervals

| Job | Interval | What It Does |
|---|---|---|
| Prometheus Metrics Collection | Every 10 seconds | Scrapes node_exporter/windows_exporter metrics from DC/DR servers via Mimir |
| Database Metrics Collection | Every 6 seconds | Polls database_config entries for connectivity and replication status |
| ECS Application Metrics | Every 1 minute | Fetches CloudWatch metrics for ECS services (CPU, memory, task count) |
| Server Down Monitor | Every 2 minutes | Checks `last_seen` timestamps, marks servers offline if stale |
| LAMA Exchange Sync | Every 5 minutes | Runs 4 parallel schedulers (Hardware, App, DB, Network) → submits to exchanges |

---

## Data Sources by Server Type

| Server Type | Exporter | Metrics Pipeline |
|---|---|---|
| **Linux DC/DR** | `node_exporter` (port 9100) | → Prometheus/Mimir → PromQL → LAMA Scheduler |
| **Windows DC/DR** | `windows_exporter` (port 9182) | → Prometheus/Mimir → PromQL → LAMA Scheduler |
| **AWS EC2** | CloudWatch Agent (`CWAgent`) | → CloudWatch API → boto3 → LAMA Scheduler |
| **AWS ECS Fargate** | ContainerInsights (auto) | → CloudWatch API → boto3 → LAMA Scheduler |
| **AWS ECS EC2** | ContainerInsights + `AWS/ECS` | → CloudWatch API → boto3 → LAMA Scheduler |
| **AWS RDS** | Built-in CloudWatch metrics | → CloudWatch API → boto3 → LAMA Scheduler |
| **MySQL** | Direct connection (aiomysql) | → SHOW REPLICA STATUS → LAMA Scheduler |
| **Elasticsearch** | ES REST API | → cluster.health() + cat.thread_pool → LAMA Scheduler |

---

## Storage Strategy

- **ClickHouse `server_metrics`**: Raw datapoints every 6-10 seconds, auto-expires after 30 days
- **ClickHouse `server_metrics_hourly`**: Materialized view auto-aggregates to hourly min/max/sum/count, kept for 2 years
- **PostgreSQL `server_status`**: Latest snapshot values (cpu, memory, disk, status, last_seen)
- **Redis Hot Store**: `server:metrics:{id}` hash with latest values for sub-second dashboard reads
