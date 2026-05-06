# SMC-LAMA Integration Service — Complete Technical Runbook

## 1. System Overview
### 1.1 What LAMA is
The **Log Analytics and Metrics Analyzer (LAMA)** is a regulatory mandate by the **National Stock Exchange of India (NSE)**. It requires all trading members to submit real-time infrastructure health metrics to the exchange to ensure system stability, capacity management, and early detection of systemic risks.

### 1.2 Service Purpose
The **SMC-LAMA Integration Service** is a dedicated middleware that automates the collection, normalization, and submission of infrastructure metrics from across SMC Global's heterogenous environment (On-Prem DC, On-Prem DR, and AWS Cloud) to the LAMA V1.3 API.

### 1.3 Compliance Requirements
*   **Frequency**: Every 5 minutes (standard cycle).
*   **Coverage**: 24/7, including all trading days and mock sessions.
*   **Latency**: Metrics must be submitted within the same 5-minute block they were collected.
*   **Success Criteria**: Only a **Response Code 601 (Success)** is considered compliant.

### 1.4 Supported Exchanges
| Exchange | ID | Purpose |
| :--- | :--- | :--- |
| **NSE** | 1 | National Stock Exchange |
| **BSE** | 2 | Bombay Stock Exchange |
| **MCX** | 4 | Multi Commodity Exchange |
| **NCDEX** | 5 | National Commodity & Derivatives Exchange |

### 1.5 Environment Matrix
| Environment | Base URL (Example) | Purpose |
| :--- | :--- | :--- |
| **UAT** | `https://lama.uat.nseindia.com/api/V1` | Testing and Compliance Validation |
| **PROD** | `https://lama.nseindia.com/api/V1` | Live Production Submission |

## 2. Architecture Overview
### 2.1 System Architecture
The system follows a 5-layer modular architecture:

1.  **LAYER 1: DATA SOURCES**: Physical Servers (On-prem), EC2 Instances, ECS Containers, Load Balancers (ALB/NLB), and RDS Databases.
2.  **LAYER 2: COLLECTORS**: specialized async modules that fetch raw data from CloudWatch APIs, Prometheus PromQL, and Direct DB queries.
3.  **LAYER 3: AGGREGATORS & MAPPERS**: Logic that processes raw "server-level" data into "fleet-level" statistical objects (min, max, average, median).
4.  **LAYER 4: SCHEDULERS**: APScheduler-based jobs that orchestrate the 5-minute push cycle, manage Sequence IDs, and handle Token Authentication.
5.  **LAYER 5: API & UI**: FastAPI-based management layer for monitoring transaction logs and manual overrides.

### 2.2 Technology Stack
*   **Backend**: Python 3.11 / FastAPI
*   **Database**: PostgreSQL 15 (Config) / ClickHouse (Metrics) / Redis (Cache)
*   **Infrastructure**: Docker / Docker Compose
*   **AWS SDK**: Boto3 (Cross-Account Role Assumption)

## 3. Infrastructure & Data Sources
### 3.1 Prometheus (On-Prem)
*   **URL**: `http://10.215.33.196:9090`
*   **Role**: Primary data source for 24 physical servers across DC and DR sites.
*   **Queries**:
    *   **CPU (Linux)**: `100 - (avg by(instance) (irate(node_cpu_seconds_total{mode="idle", instance=~"{{IP}}.*"}[1m])) * 100)`
    *   **Memory (Linux)**: `((1 - (node_memory_MemAvailable_bytes{instance=~"{{IP}}.*"} / node_memory_MemTotal_bytes{instance=~"{{IP}}.*"})) * 100)`
    *   **Disk (Linux)**: `max((node_filesystem_size_bytes{...} - node_filesystem_avail_bytes{...}) / node_filesystem_size_bytes{...} * 100)`

### 3.2 AWS CloudWatch via ARN
*   **Account**: `122610489939` (Central Observability Account)
*   **Role ARN**: `arn:aws:iam::396913716058:role/SMC-LAMA-CrossAccount-ReadOnly`
*   **External ID**: `SMC-LAMA-OBSERVABILITY`
*   **Services**: EC2 (System), ECS (Application/Hardware), ALB/NLB (Network), RDS (Database).

### 3.3 MySQL Direct Connection
*   **Role**: Used for on-prem MySQL database replication monitoring.
*   **Encryption**: Passwords decrypted at runtime using `app.routes.database_config.decrypt_password` (Fernet).
*   **Logic**: Uses `aiomysql` to run `SHOW REPLICA STATUS` and extracts `Seconds_Behind_Master` and Log Position diffs.

### 3.4 AWS RDS (PostgreSQL)
*   **Instances**: `smc-pre-trade-postgres` (Primary), `smc-pre-trade-postgres-replica-a` (Replica).
*   **Collection**: Uses CloudWatch `AWS/RDS` Namespace.
*   **Primary Metric**: `ReplicaLag` (Seconds).

## 4. Complete Metric Mapping Reference
### 4.1 Hardware Metrics (/metrics/hardware)
| LAMA Key | Unit | Source | Collection Method | Prometheus Query / CW Metric |
| :--- | :--- | :--- | :--- | :--- |
| **cpu** | % | OS | PromQL / CW | `irate(node_cpu_seconds_total)` / `CPUUtilization` |
| **memory** | % | OS | PromQL / CW | `node_memory_MemAvailable_bytes` / `MemoryUtilization` |
| **disk** | % | OS | PromQL / CW | `node_filesystem_avail_bytes` / `DiskSpaceUtilization` |
| **uptime** | Min | OS | PromQL / CW | `node_boot_time_seconds` / `LaunchTime` |

### 4.2 Network Metrics (/metrics/network)
| LAMA Key | Unit | Source | Collection Method | Notes |
| :--- | :--- | :--- | :--- | :--- |
| **bandwidth** | % | LB / NIC | CloudWatch / PromQL | Percentage of 1Gbps capacity |
| **latency** | ms | LB / ICMP | CloudWatch / PromQL | TargetResponseTime (ALB) |
| **packetCount** | Num | LB / NIC | CloudWatch / PromQL | Sum of packets in 5m window |
| **lookupCount** | Num | Route53 | [FUTURE] | Currently defaults to 0 |

### 4.3 Database Metrics (/metrics/database)
| LAMA Key | Unit | Source | Collection Method | Notes |
| :--- | :--- | :--- | :--- | :--- |
| **status** | 1/0 | DB Engine | Ping / Describe | 1=Available, 0=Down |
| **qSize** | Sec | Replica | `SHOW SLAVE STATUS` | Seconds_Behind_Master |
| **bandwidth** | % | Replica | Log Pos Diff | (Read - Exec) / 1GB |
| **latency** | ms | Replica | CloudWatch | ReplicaLag * 1000 |

### 4.4 Application Metrics (/metrics/application)
| Service Name | applicationId | Type | LB Type | Cluster |
| :--- | :---: | :--- | :--- | :--- |
| **sanjay-api** | 1 | ECS Fargate | ALB | smc-pre-trade-ecs-fargate |
| **research-tool** | 2 | ECS Fargate | ALB | smc-pre-trade-ecs-fargate |
| **algo-api** | 3 | ECS EC2 | NLB | smc-pre-trade-ecs-ec2 |
| **munshi-api** | 4 | ECS EC2 | NLB | smc-pre-trade-ecs-ec2 |
| **dispatcher** | 5 | ECS EC2 | NLB | smc-pre-trade-ecs-ec2 |
| **khabri** | -1 | ECS Fargate | BACKGROUND | smc-pre-trade-ecs-fargate |

## 5. Server & Location Registry
| Server Name | IP / Identifier | OS | Type | LocID | AppID |
| :--- | :--- | :--- | :--- | :---: | :---: |
| LAMA-Net Admin | 192.168.1.100 | Windows | Physical | 1 | -1 |
| DR-SMC-OC1-204 | 192.168.176.106 | Windows | Physical | 2 | -1 |
| sanjay-api | [ALB ARN] | Linux | ECS | 3 | 1 |
| munshi-api | [NLB ARN] | Linux | ECS | 3 | 4 |
| postgres-primary | [RDS Identifier] | Linux | RDS | 3 | -1 |
| postgres-replica | [RDS Identifier] | Linux | RDS | 3 | -1 |

**Location Legend**:
*   **Location 1**: DC On-Prem (15 servers)
*   **Location 2**: DR On-Prem (9 servers)
*   **Location 3**: AWS Cloud (13 servers)

## 6. Scheduler Deep Dive
### 6.1 Hardware Scheduler
*   **Trigger**: Every 5 minutes (Cron: `*/5`).
*   **Execution Flow**:
    1.  Assume AWS ReadOnly Role and collect ECS task metrics asynchronously.
    2.  Query `server_status` for all enabled physical servers.
    3.  Iterate through servers and fetch metrics from Prometheus or local cache.
    4.  Apply `aggregate_worst_case()` to find the fleet max/min/avg.
    5.  Obtain Sequence ID and Auth Token.
    6.  Submit batched JSON to `/metrics/hardware`.
*   **Batching**: Grouped by `locationId`. Max 5 records per batch as per LAMA spec.

### 6.2 Network Scheduler
*   **Trigger**: Every 5 minutes.
*   **Logic**: 
    *   For **AWS**: Fetches `TargetResponseTime` (latency) and `ActiveConnectionCount` from ALB/NLB.
    *   For **On-Prem**: Defaults to 0.0 unless network exporters are detected in Prometheus.
*   **ApplicationID**: Hardcoded to `4` (Exchange Connectivity) to satisfy LAMA validation.

### 6.3 Database Scheduler
*   **Trigger**: Every 5 minutes.
*   **Routing**:
    *   **PostgreSQL**: Routed to `AWSCollector.collect_rds_database_metrics` (via CloudWatch).
    *   **MySQL**: Routed to `MySQLCollector` (Direct connection using decrypted credentials).
*   **Metrics**: Collects Status, QSize, Bandwidth, and Latency (scaled from seconds to ms).

### 6.4 Application Scheduler
*   **Trigger**: Every 5 minutes.
*   **Services**: Maps 6 core ECS services to `applicationId` 1-5.
*   **Metrics**: Throughput, Latency, and Error Rates.

### 6.5 Daily Scheduler (Historical)
*   [DATA NOT AVAILABLE — Logic currently aggregates daily trends within the UI historical data route rather than a separate LAMA push job.]

## 7. LAMA Exchange Integration
### 7.1 Authentication
*   **Encryption**: AES-256 ECB with PKCS7 Padding.
*   **Secret Key**: `DOqWxmnwif2nHdxrW+gPO394LT6hcOu/0MlVOJOEuhw=`
*   **Token Validity**: 24 Hours.
*   **Implementation**:
```python
cipher = Cipher(algorithms.AES(key), modes.ECB(), backend)
encryptor = cipher.encryptor()
padder = padding.PKCS7(algorithms.AES.block_size).padder()
padded_data = padder.update(password_bytes) + padder.finalize()
```

### 7.2 Sequence ID Management
*   **Atomic ID**: Stored in `lama_sequence` table.
*   **Table Schema**: `(environment, member_id, exchange_id, metric_type, current_id)`.
*   **704 Resync**: If LAMA returns `704`, the service parses the `expectedSequenceId` from the error message and automatically retries with the correct ID.

### 7.3 NSE Epoch Timestamp
*   **Base Date**: 01-Jan-1980 00:00:00 UTC.
*   **Formula**: `current_time_ms - 315532800000`.
*   **Critical**: All timestamps sent to LAMA must be in this format.

### 7.4 API Endpoints Reference
| Endpoint | Method | Purpose |
| :--- | :--- | :--- |
| `/login` | POST | Authenticate and get Bearer Token |
| `/metrics/hardware` | POST | System health submission |
| `/metrics/network` | POST | Connectivity health submission |
| `/metrics/database` | POST | DB health submission |
| `/metrics/application` | POST | API performance submission |

## 8. Error Handling & Recovery
| Code | Meaning | Recovery Logic |
| :--- | :--- | :--- |
| **601** | Success | Log transaction and continue. |
| **704** | Invalid Sequence | Extract expected ID from LAMA description and retry immediately. |
| **801/802** | Token Issues | Logout, clear Redis cache, and re-login on next cycle. |
| **709** | Duplicate | Skip this record; typically occurs on service restarts. |
| **607** | Concurrent Limit | Wait 10 seconds and retry with exponential backoff. |
| **901** | Null Fields | Validation layer strips nulls before sending to avoid this. |

## 9. Database Schema
### 9.1 `server_status` (Infrastructure Registry)
*   **Purpose**: Stores the inventory of all physical and cloud assets.
*   **Key Columns**: `name`, `ip`, `environment`, `location_id`, `last_seen`.

### 9.2 `exchange_transactions` (Audit Trail)
*   **Purpose**: Permanent log of every API call made to LAMA.
*   **Key Columns**: `metric_type`, `metrics_sent` (JSON), `status_code`, `sent_at`.

### 9.3 `lama_sequence` (State Tracking)
*   **Purpose**: Maintains the strictly incremental counter required by LAMA.
*   **Key Columns**: `exchange_id`, `environment`, `current_seq`.

### 9.4 `database_config` (Credential Storage)
*   **Purpose**: Connection details for On-Prem MySQL monitoring.
*   **Note**: Passwords are **Fernet encrypted**.

## 10. Configuration Reference
### 10.1 Environment Variables
| Variable | Purpose | Example |
| :--- | :--- | :--- |
| `POSTGRES_DB` | Config DB Name | `lama_prod` |
| `LGTM_PROMETHEUS_URL` | On-Prem metrics source | `http://10.215.33.196:9090` |
| `AWS_ROLE_ARN` | Central observability role | `arn:aws:iam::396913716058:role/...` |
| `JWT_SECRET` | UI Token security | [HIDDEN] |

## 11. Deployment
### 11.1 Container Architecture
*   **lama_api**: Serving the frontend and transaction logs.
*   **lama_scheduler**: Background process running the 5-minute compliance jobs.
*   **lama_nginx**: Frontend server and load balancer.
*   **lama_postgres**: Relational database for system state.
*   **lama_clickhouse**: High-speed storage for server performance history.

## 12. Monitoring the Monitor
### 12.1 Compliance Audit Query
```sql
SELECT 
    scheduler_name, environment, status,
    MAX(created_at) as last_run
FROM scheduler_logs
WHERE created_at > NOW() - INTERVAL '30 minutes'
GROUP BY 1, 2, 3;
```
### 12.2 Exchange Success Query
```sql
SELECT exchange_id, metric_type, status_code, sent_at
FROM exchange_transactions
WHERE status_code = 601
ORDER BY sent_at DESC LIMIT 10;
```

## 13. Incident Runbook
### Scenario 1: Persistent 704 Errors
*   **Cause**: Sequence ID out of sync beyond automatic recovery.
*   **Action**: Manually update `lama_sequence` table with the `expectedSequenceId` provided in the LAMA error description.
*   **SQL**: `UPDATE lama_sequence SET current_seq = [EXPECTED_ID] WHERE exchange_id = [X] AND metric_type = '[TYPE]';`

### Scenario 2: On-Prem Metrics = 0.0
*   **Check**: Verify `node_exporter` or `windows_exporter` is running on the target server.
*   **Check**: Verify Prometheus Target Status at `http://10.215.33.196:9090/targets`.

## 14. Known Limitations
*   **CWAgent**: Not currently installed on EC2 instances (Memory/Disk metrics default to 0.0).
*   **Route53 Logs**: DNS LookupCount defaults to 0.0 as Resolver logging is not enabled.
*   **NLB Latency**: NLBs do not provide TargetResponseTime; latency defaults to 0.0.

## 15. Appendix
### A. LAMA API V1.3 Response Codes
| Code | Description |
| :--- | :--- |
| **601** | Success |
| **602** | Partial Success |
| **704** | Invalid Sequence ID |
| **705** | Push Window Violation (< 5 min) |
| **801** | Invalid Token |

### B. Useful Commands
*   **Check Logs**: `docker logs -f lama_scheduler`
*   **Force Manual Database Push**: `docker exec lama_api python3 /app/manual_db_submit.py`
*   **Restart Pipeline**: `docker compose -f smc-lama-config/docker-compose.yml restart api scheduler`
