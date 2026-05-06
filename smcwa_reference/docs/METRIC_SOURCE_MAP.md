# LAMA Metric Source Map (Definitive Reference)

## Data Sources (ONLY 2 allowed)

### Source 1: OnPrem-LGTM (Prometheus)
- **URL:** `http://10.215.33.196:9090`
- **Locations:** DC (Location 1), DR (Location 2)

| Exporter | Instance | Metrics Provided |
|---|---|---|
| Windows Exporter / Node Exporter | `<server_ip>:9182` / `:9100` | **Hardware**: cpu, memory, disk, uptime |
| Windows Exporter / Node Exporter | `<server_ip>:9182` / `:9100` | **Network**: bandwidth, latency, packetCount, lookupCount |
| Blackbox Exporter | various targets | **Network**: latency (ICMP RTT), lookupCount (DNS) |
| Odin-Web-Logs Exporter | `localhost:8000` | **Application**: throughput, latency, failureTradeApi, failureAuthentication, historicalThroughput, historicalLatency |
| XTS DB+App Exporter | `localhost:8001` (DC) | **Database**: db_status, db_qsize_*, db_bandwidth_*, db_latency_* |
| XTS DB+App Exporter | `localhost:8001` (DC) | **Application**: throughput_*, latency_*, failuretradeapi, failureauthentication, historicalthroughput_*, historicallatency_* |
| XTS DB+App Exporter | `localhost:8021` (DR) | **Database**: db_status, db_qsize_*, db_bandwidth_*, db_latency_* |
| XTS DB+App Exporter | `localhost:8021` (DR) | **Application**: throughput_*, latency_*, failuretradeapi, failureauthentication, historicalthroughput_*, historicallatency_* |

### Source 2: Cloud-LGTM-Mimir
- **URL:** `http://10.236.26.167:9009/prometheus`
- **Locations:** Cloud (Location 3)

| Exporter | Label Format | Metrics Provided |
|---|---|---|
| Alloy (node_exporter) | `instance="<ip>:9100"` | **Hardware**: cpu, memory, disk, uptime |
| Alloy (node_exporter) | `instance="<ip>:9100"` | **Network**: bandwidth, packetCount |
| YACE (CloudWatch scraper) | `name="arn:aws:rds:..."` | **Database (RDS)**: aws_rds_disk_queue_depth_average, aws_rds_network_*_throughput_average, aws_rds_replica_lag_average, aws_rds_read/write_latency_average |
| *(Future)* | TBD | **Application**: Not available yet — zero-fill |

## LAMA V1.3 Key Mapping

### Hardware (all locations from exporters)
| LAMA Key | Source |
|---|---|
| `cpu` | windows_exporter / node_exporter |
| `memory` | windows_exporter / node_exporter |
| `disk` | windows_exporter / node_exporter |
| `uptime` | windows_exporter / node_exporter |

### Network (all locations from exporters)
| LAMA Key | Source |
|---|---|
| `bandwidth` | windows_exporter / node_exporter |
| `latency` | blackbox ICMP RTT (DC/DR only, zero-fill Cloud) |
| `packetCount` | windows_exporter / node_exporter |
| `lookupCount` | blackbox DNS (DC/DR only, zero-fill Cloud) |

### Database
| LAMA Key | DC/DR (localhost:8001/8021) | Cloud (Mimir YACE) |
|---|---|---|
| `status` | `db_status` | Derived from aws_rds data existence |
| `qSize` | `db_qsize_min/max/avg/median` | `aws_rds_disk_queue_depth_average` |
| `bandwidth` | `db_bandwidth_min/max/avg/median` | `aws_rds_network_receive + transmit_throughput_average` |
| `latency` | `db_latency_min/max/avg/median` | `aws_rds_replica_lag_average * 1000` (ms) |

### Application
| LAMA Key | DC/DR (localhost:8000/8001/8021) | Cloud (Mimir) |
|---|---|---|
| `throughput` | `throughput_min/max/avg/median` | Zero-fill (future) |
| `latency` | `latency_min/max/avg/median` | Zero-fill (future) |
| `historicalThroughput` | `historicalthroughput_min/max/avg/median` | Zero-fill (future) |
| `historicalLatency` | `historicallatency_min/max/avg/median` | Zero-fill (future) |
| `failureTradeApi` | `failuretradeapi` | Zero-fill (future) |
| `failureAuthentication` | `failureauthentication` | Zero-fill (future) |

## Rules
1. NO other data sources allowed (no AWS CloudWatch direct, no MySQL direct)
2. If data not available from these 2 sources → send as 0 (zero-fill)
3. Metric keys must exactly match LAMA V1.3 spec
4. Pre-calculated data from exporters: PICK and PASS — no derivation/override
