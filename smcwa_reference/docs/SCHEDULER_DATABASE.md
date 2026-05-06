# Database Scheduler — End-to-End Documentation

## Overview

The **Database Scheduler** collects Status, Queue Size, Bandwidth, and Latency metrics from all configured databases (RDS PostgreSQL and MySQL), aggregates them into a worst-case fleet payload, and submits to the LAMA Exchange API every 5 minutes.

**File:** `api/backend/app/schedulers/database.py`  
**Scheduler Name:** `DB-Scheduler`  
**Metric Type:** `database`  
**Trigger:** Every 5 minutes (CronTrigger `*/5` IST) via `scheduler_main.py`

> **Note:** Elasticsearch is handled by the **Application Scheduler** for application-level metrics (throughput, latency, errors). The Database Scheduler focuses on RDS PostgreSQL and MySQL only.

---

## End-to-End Flow

```
┌─────────────────────────────────────────────────────────────────────┐
│  scheduler_main.py → lama_exchange_sync_scheduler()                │
│  └─> ThreadPoolExecutor.submit(db_scheduler, env)                  │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│  database_scheduler(environment="uat"|"prod")                      │
│                                                                     │
│  1. Validate exchange is enabled                                   │
│  2. Query database_config table for all enabled DBs                │
│  3. For each DB (parallel via asyncio.gather):                     │
│     └─> fetch_db_metrics_async(db, aws_collector)                  │
│         ├── PostgreSQL → AWSCollector.collect_rds_database_metrics()│
│         └── MySQL      → MySQLCollector.collect() (direct connect) │
│  4. MetricMapper.map_database(raw) → standardized format           │
│  5. aggregate_worst_case() for each metric key                     │
│  6. For each enabled exchange:                                     │
│     a. Get token → Get sequence → Send payload                    │
│     b. Handle 704 retry                                            │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Metric Keys & How Each Is Fetched

### 1. Status (`status`)
**LAMA Format:** `integer` (plain value: `1` = Up, `0` = Down)

| DB Type | How It's Determined |
|---|---|
| **RDS PostgreSQL** | `rds.describe_db_instances(DBInstanceIdentifier=id)` → `DBInstanceStatus == "available"` → 1, else 0 |
| **MySQL Primary** | `SELECT 1` ping query succeeds → 1, fails → 0 |
| **MySQL Replica** | `SHOW REPLICA STATUS` → `Replica_IO_Running == "Yes" AND Replica_SQL_Running == "Yes"` → 1, else 0 |

**Aggregation:** `aggregate_worst_case("status", items)` → averages all status values (if any DB is down, fleet average drops below 1)

### 2. Queue Size (`qSize`)
**LAMA Format:** `{ "min": float, "max": float, "avg": float, "med": float }`

| DB Type | What It Measures | How It's Fetched |
|---|---|---|
| **RDS PostgreSQL (Primary)** | Active database connections | CloudWatch `AWS/RDS` → `DatabaseConnections` (Average) |
| **RDS PostgreSQL (Replica)** | Replication lag in seconds | CloudWatch `AWS/RDS` → `ReplicaLag` (Average) — seconds behind master |
| **MySQL Replica** | Seconds behind master | `SHOW REPLICA STATUS` → `Seconds_Behind_Master` |
| **MySQL Primary** | Always 0 | No queue concept on primary |

**Calculation (RDS Replica):**
```
raw_values = CloudWatch ReplicaLag (Average, in seconds) over 5 minutes
qSize = aggregate(raw_values)  # min/max/avg/med of lag values
```

**Calculation (MySQL Replica):**
```
seconds_behind = SHOW REPLICA STATUS → Seconds_Behind_Master
qSize = { min: seconds_behind, max: seconds_behind, avg: seconds_behind, med: seconds_behind }
```

### 3. Bandwidth (`bandwidth`)
**LAMA Format:** `{ "min": float, "max": float, "avg": float, "med": float }` (percentage 0–100)

| DB Type | What It Measures | How It's Fetched |
|---|---|---|
| **RDS PostgreSQL** | CPU utilization as load proxy | CloudWatch `AWS/RDS` → `CPUUtilization` (Average) |
| **MySQL Replica** | Replication log position diff as % | `(Read_Master_Log_Pos - Exec_Master_Log_Pos) / 1GB × 100` |
| **MySQL Primary** | Always 0% | No replication bandwidth on primary |

**Calculation (RDS):**
```
raw_values = CloudWatch CPUUtilization (Average) over 5 minutes
bandwidth = aggregate(raw_values)  # Already in percentage
```

**Calculation (MySQL Replica):**
```
read_pos = Read_Source_Log_Pos
exec_pos = Exec_Source_Log_Pos
log_diff = max(0, read_pos - exec_pos)
bandwidth_pct = min(100.0, (log_diff / 1,073,741,824) * 100)  # 1GB normalization
```

### 4. Latency (`latency`)
**LAMA Format:** `{ "min": float, "max": float, "avg": float, "med": float }` (milliseconds)

| DB Type | What It Measures | How It's Fetched |
|---|---|---|
| **RDS PostgreSQL (Primary)** | Disk queue depth (I/O wait proxy) | CloudWatch `AWS/RDS` → `DiskQueueDepth` (Average) |
| **RDS PostgreSQL (Replica)** | Replication lag in milliseconds | CloudWatch `ReplicaLag` (seconds) × 1000 |
| **MySQL Replica** | Replication lag in milliseconds | `Seconds_Behind_Master × 1000` |
| **MySQL Primary** | Always 0 | No replication latency |

**Calculation (RDS Replica):**
```
raw_values = CloudWatch ReplicaLag (Average, in seconds)
latency_ms = [value * 1000.0 for value in raw_values]
result = { min: min(latency_ms), max: max(latency_ms), avg: mean(latency_ms), med: median(latency_ms) }
```

---

## Data Collection Strategy

```
fetch_db_metrics_async(db_row, aws_collector):

  1. Read full config from database_config table
  2. Branch by db_type:

     PostgreSQL:
       ├── Identify db_identifier from host (e.g., "mydb" from "mydb.xxx.rds.amazonaws.com")
       ├── Check metric_sources for custom role_arn (cross-account)
       └── AWSCollector.collect_rds_database_metrics(db_identifier)
           ├── rds.describe_db_instances() → status + is_replica detection
           ├── If replica: ReplicaLag → qSize + latency
           ├── If primary: DatabaseConnections → qSize, DiskQueueDepth → latency
           └── CPUUtilization → bandwidth

     MySQL:
       ├── Decrypt password from database_config
       ├── MySQLCollector(host, port, user, pass, db, is_replication, master_host)
       └── collector.collect()
           ├── If is_replication=True → _collect_replica_metrics()
           │   └── SHOW REPLICA STATUS (MySQL 8+) or SHOW SLAVE STATUS (5.x)
           └── If is_replication=False → _collect_primary_metrics()
               └── SELECT 1 (ping only, zeros for replication metrics)

  3. MetricMapper.map_database(raw) → standardized keys
  4. Update Redis Hot Store for dashboard visibility
```

---

## RDS Primary vs Replica — Metric Mapping Summary

| Metric Key | RDS Primary Source | RDS Replica Source |
|---|---|---|
| `status` | `DBInstanceStatus == "available"` | `DBInstanceStatus == "available"` |
| `qSize` | `DatabaseConnections` (count) | `ReplicaLag` (seconds) |
| `bandwidth` | `CPUUtilization` (%) | `CPUUtilization` (%) |
| `latency` | `DiskQueueDepth` (I/O depth) | `ReplicaLag × 1000` (ms) |

The replica detection is automatic: `"ReadReplicaSourceDBInstanceIdentifier" in db_instance` → is_replica = True.

---

## Aggregation Logic

`aggregate_worst_case()` per metric key across ALL databases:

```python
# For "status" (plain value):
final_status = int(sum(all_status_values) / count)  # Average (0 or 1)

# For "qSize", "bandwidth", "latency" (statistical):
result = {
    "name": "qSize",
    "min": min(all_db_mins),
    "max": max(all_db_maxs),
    "avg": mean(all_db_avgs),
    "med": median(all_db_avgs),
    "worst_case_source": "db-name (host)"
}
```

Produces 4 metric objects: `status`, `qSize`, `bandwidth`, `latency`.

---

## LAMA Exchange Submission

```json
{
  "memberId": "<member_id>",
  "exchangeId": 1,
  "applicationId": -1,
  "sequenceId": 78,
  "metricType": "database",
  "timestamp": 1710000000000,
  "metricData": [
    { "key": "status",    "value": 1 },
    { "key": "qSize",     "value": { "min": 0.0, "max": 5.2, "avg": 1.8, "med": 1.5 } },
    { "key": "bandwidth", "value": { "min": 10.0, "max": 45.0, "avg": 28.0, "med": 27.0 } },
    { "key": "latency",   "value": { "min": 0.5, "max": 120.0, "avg": 15.0, "med": 12.0 } }
  ]
}
```

---

## Database Config Table Schema

The scheduler reads from `database_config`:

| Column | Purpose |
|---|---|
| `id` | Primary key |
| `database` | Display name |
| `host` | Connection host |
| `port` | Connection port |
| `username` | DB username |
| `password` | AES-encrypted password |
| `db_type` | `postgresql` or `mysql` |
| `is_replication` | Boolean — determines replica vs primary collection logic |
| `master_host` | Master host for MySQL replicas |
| `location_id` | 1=DC, 2=DR, 3=Cloud |
| `server_id` | FK to server_status |
| `enabled` | Boolean — only enabled DBs are collected |

---

## AWS IAM Requirements

Same cross-account role as Hardware, plus:
- `cloudwatch:GetMetricStatistics` (namespace: `AWS/RDS`)
- `rds:DescribeDBInstances` (for status + replica detection)

---

## MySQL Direct Connection Requirements

- Network connectivity from LAMA backend to MySQL host:port
- MySQL user with `REPLICATION CLIENT` privilege (for `SHOW REPLICA STATUS`)
- Supports MySQL 5.x (`SHOW SLAVE STATUS`) and 8+ (`SHOW REPLICA STATUS`)
- Connection timeout: 30 seconds, 3 retry attempts with 2s delay
- Uses `aiomysql` for async non-blocking connections

---

## Side Effects

1. **Updates Redis Hot Store:** `update_server_hot_data(db_status_id, metrics, category="database")` with status, qSize, bandwidth, latency
2. **Logs to `exchange_transactions`:** Full payload + response recorded
