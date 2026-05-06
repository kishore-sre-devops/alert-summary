"""
MimirCollector: SMC LAMA V2.0 Robust Implementation
Targets Mimir/Prometheus at http://10.236.26.167:9009/prometheus
"""
import os
import logging
import asyncio
import httpx
import re
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Optional, List
import statistics
from app.collectors.base import BaseCollector

logger = logging.getLogger(__name__)

class MimirCollector(BaseCollector):
    def __init__(self, url: str = None):
        base_url = (url or os.getenv("MIMIR_URL", "http://10.236.26.167:9009")).rstrip('/')
        # Ensure /prometheus suffix for Mimir
        if "prometheus" not in base_url and "9009" in base_url:
            base_url = f"{base_url}/prometheus"
        self.url = base_url
        self._async_client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._async_client is None or self._async_client.is_closed:
            self._async_client = httpx.AsyncClient(
                timeout=httpx.Timeout(15.0, connect=3.0)
            )
        return self._async_client

    async def fetch_metric_stats(self, query: str, window_minutes: int = 8) -> Optional[dict]:
        client = await self._get_client()
        # LAMA V2.0: Real-Time Dynamic Window
        # We look back 60 minutes to ensure we capture the latest data points 
        # even if there is an ingestion delay (e.g. RDS metrics arriving 30 mins late).
        now = datetime.now(timezone.utc)
        
        end_time = now
        # We use a 60-minute lookback to be robust against cloud delays
        start_time = end_time - timedelta(minutes=60)
        
        params = {
            "query": query,
            "start": start_time.isoformat(),
            "end": end_time.isoformat(),
            "step": "60s"
        }
        
        try:
            resp = await client.get(f"{self.url}/api/v1/query_range", params=params)
            if resp.status_code == 200:
                data = resp.json().get("data", {}).get("result", [])
                if data:
                    all_points = []
                    all_values = []
                    for series in data:
                        for v in series.get("values", []):
                            ts = int(v[0])
                            val = round(float(v[1]), 3)
                            all_points.append([ts, val])
                            all_values.append(val)
                    
                    # Sort by timestamp and take LATEST 5-6 points for the cycle
                    all_points.sort(key=lambda x: x[0])
                    # Per-minute data: we want roughly one point per minute in the window
                    final_points = all_points[-6:] if len(all_points) >= 6 else all_points
                    final_values = [p[1] for p in final_points]
                        
                    return {
                        "min": round(min(final_values), 3),
                        "max": round(max(final_values), 3),
                        "avg": round(statistics.mean(final_values), 3),
                        "med": round(statistics.median(final_values), 3),
                        "points": final_points,
                        "datasource": "Mimir/Prometheus (DC/DR)" if "10.215.33.196" in self.url else "Mimir/Prometheus (Cloud)"
                    }

        except Exception as e:
            logger.debug(f"Mimir fetch failed: {e}")
        return None

    def _get_patterns(self, target: str) -> List[str]:
        """Generate list of search patterns for the target ID"""
        if not target or target in ["aws", "Pending Discovery"]:
            return [".*"]
            
        patterns = [target]
        
        # 1. If it's a DNS name like ip-10-203-100-71.ap-south-1.compute.internal
        # Add the short version: ip-10-203-100-71
        if "ip-" in target and "." in target:
            short_dns = target.split('.')[0]
            patterns.append(short_dns)

        # 2. Extract digits to form IP and dashed IP
        ip_parts = re.findall(r'\d+', target)
        if len(ip_parts) >= 4:
            ip_base = ".".join(ip_parts[:4])
            dashed_base = "ip-" + "-".join(ip_parts[:4])
            # Add both the dotted IP and the dashed version
            patterns.extend([ip_base, dashed_base])
            
        # 3. EXTRACTION for Alloy/ECS Services (Senior Engineer Addition)
        # If target is like 'smc-pre-trade-dispatcher-api', add 'dispatcher'
        if 'dispatcher' in target.lower():
            patterns.append('dispatcher')
        elif 'algo' in target.lower():
            patterns.append('algo')
        elif 'munshi' in target.lower():
            patterns.append('munshi')
        elif 'sanjay' in target.lower():
            patterns.append('sanjay')
            
        return list(dict.fromkeys(patterns)) # Unique items only

    async def collect_ec2_metrics(self, ip: str, os_type: str = "linux", window_minutes: int = 5) -> dict:
        """Sequential discovery of telemetry across labels and patterns"""
        if not ip or ip == "aws" or ip == "Pending Discovery":
            zero = {"min": 0.0, "max": 0.0, "avg": 0.0, "med": 0.0}
            return {"cpu": zero, "memory": zero, "disk": zero, "uptime": zero}

        patterns = self._get_patterns(ip)
        # Added service_name and job labels for Alloy Agent compatibility
        labels = ["service_name", "ecs_service_name", "job", "instance", "instance_id", "nodename"]
        os_t = (os_type or "linux").lower()
        
        # SEQUENTIAL DISCOVERY: Find the first combination that works
        active_query_data = None
        for p in patterns:
            for l in labels:
                # Test with a simple CPU query to see if this combination (Label + Pattern) exists
                if os_t == "windows":
                    test_q = 'windows_cpu_time_total{%s=~".*%s.*"}' % (l, p)
                else:
                    test_q = 'node_cpu_seconds_total{%s=~".*%s.*"}' % (l, p)
                
                stats = await self.fetch_metric_stats(test_q, window_minutes)
                if stats:
                    # Found it! Now build full queries for all metrics using THIS label and pattern
                    active_query_data = (l, p)
                    break
            if active_query_data: break
            
        if not active_query_data:
            zero = {"min": 0.0, "max": 0.0, "avg": 0.0, "med": 0.0}
            return {"cpu": zero, "memory": zero, "disk": zero, "uptime": zero}

        l, p = active_query_data
        pattern = f".*{p}.*"
        
        if os_t == "windows":
            q_cpu = f'100 - (avg by ({l}) (rate(windows_cpu_time_total{{mode="idle", {l}=~"{pattern}"}}[1m])) * 100)'
            q_mem = f'(1 - (windows_os_physical_memory_free_bytes{{{l}=~"{pattern}"}} or windows_memory_physical_free_bytes{{{l}=~"{pattern}"}}) / (windows_cs_physical_memory_bytes{{{l}=~"{pattern}"}} or windows_memory_physical_total_bytes{{{l}=~"{pattern}"}})) * 100'
            q_disk = f'max((1 - windows_logical_disk_free_bytes{{volume!~"HarddiskVolume.*", {l}=~"{pattern}"}} / windows_logical_disk_size_bytes{{volume!~"HarddiskVolume.*", {l}=~"{pattern}"}})) * 100'
            q_uptime = f'(windows_os_system_up_time{{{l}=~"{pattern}"}} or (time() - windows_system_boot_time_timestamp{{{l}=~"{pattern}"}})) / 60'
        else:
            q_cpu = f'100 - (avg by ({l}) (rate(node_cpu_seconds_total{{mode="idle", {l}=~"{pattern}"}}[5m])) * 100)'
            q_mem = f'100 * (1 - (node_memory_MemAvailable_bytes{{{l}=~"{pattern}"}} / node_memory_MemTotal_bytes{{{l}=~"{pattern}"}}))'
            q_disk = f'max(100 * (1 - (node_filesystem_avail_bytes{{{l}=~"{pattern}", mountpoint!~"/boot.*|/snap.*|/run.*|/dev.*|/sys.*|/proc.*", fstype!~"tmpfs|ramfs|autofs|vfat|iso9660|overlay"}} / node_filesystem_size_bytes{{{l}=~"{pattern}", mountpoint!~"/boot.*|/snap.*|/run.*|/dev.*|/sys.*|/proc.*", fstype!~"tmpfs|ramfs|autofs|vfat|iso9660|overlay"}})))'
            q_uptime = f'(time() - node_boot_time_seconds{{{l}=~"{pattern}"}}) / 60'

        cpu, mem, disk, uptime = await asyncio.gather(
            self.fetch_metric_stats(q_cpu, window_minutes),
            self.fetch_metric_stats(q_mem, window_minutes),
            self.fetch_metric_stats(q_disk, window_minutes),
            self.fetch_metric_stats(q_uptime, window_minutes)
        )

        now_ts = int(datetime.utcnow().timestamp())
        zero_pts = [[now_ts - (i * 60), 0.0] for i in range(6)]
        zero_pts.reverse()
        zero = {"min": 0.0, "max": 0.0, "avg": 0.0, "med": 0.0, "points": zero_pts, "datasource": "Mimir/Prometheus (Zero-Filing)"}
        return {
            "cpu": cpu or zero,
            "memory": mem or zero,
            "disk": disk or zero,
            "uptime": uptime or zero,
            "datasource": "Mimir/Prometheus"
        }

    async def collect_application_metrics(self, service_name: str, window_minutes: int = 5) -> dict:
        """Collect application throughput and latency from Mimir"""
        # Search for metrics by service_name or job label
        pattern = f".*{service_name}.*"
        
        # Throughput: request count rate (req/s)
        q_tp = f'sum(rate(http_requests_total{{service=~"{pattern}"}}[5m])) or sum(rate(application_requests_total{{job=~"{pattern}"}}[5m]))'
        # Latency: p95 duration (ms)
        q_lat = f'histogram_quantile(0.95, sum by (le) (rate(http_request_duration_seconds_bucket{{service=~"{pattern}"}}[5m]))) * 1000'
        
        tp, lat = await asyncio.gather(
            self.fetch_metric_stats(q_tp, window_minutes),
            self.fetch_metric_stats(q_lat, window_minutes)
        )
        
        now_ts = int(datetime.utcnow().timestamp())
        zero_pts = [[now_ts - (i * 60), 0.0] for i in range(6)]
        zero_pts.reverse()
        zero = {"min": 0.0, "max": 0.0, "avg": 0.0, "med": 0.0, "points": zero_pts, "datasource": "Mimir/Prometheus (Zero-Filing)"}
        return {
            "throughput": tp or zero,
            "latency": lat or zero,
            "historicalThroughput": zero,
            "historicalLatency": zero,
            "failureTradeApi": 0,
            "failureAuthentication": 0,
            "datasource": "Mimir/Prometheus"
        }

    async def collect_database_metrics(self, db_identifier: str, window_minutes: int = 5) -> dict:
        """Collect RDS/DB metrics from Mimir (YACE RDS Exporter or On-Prem)"""
        clean_pattern = db_identifier.replace(".", "\\.")
        pattern = f".*{clean_pattern}.*"

        # AWS/YACE specific label
        is_rds = True # Assume RDS if using Mimir collector for database

        # PromQL: Use a single selector with | (OR) for label variants
        def _lbl(metric, pat):
            # Combined selector for AWS (dimension) and On-Prem (instance/name) labels
            return f'{metric}{{dimension_DBInstanceIdentifier=~"{pat}", db_instance_identifier=~"{pat}", instance=~"{pat}", name=~"{pat}"}}'

        # Status: replication health (using CPU as health check if no lag data)
        q_health = f'aws_rds_cpuutilization_average{{dimension_DBInstanceIdentifier=~"{pattern}"}} or node_cpu_seconds_total{{instance=~"{pattern}"}}'
        
        # qSize: Disk Queue Depth
        q_qs = f'aws_rds_disk_queue_depth_average{{dimension_DBInstanceIdentifier=~"{pattern}"}} or aws_rds_database_connections_average{{dimension_DBInstanceIdentifier=~"{pattern}"}} or mysql_global_status_threads_connected{{instance=~"{pattern}"}}'

        # bandwidth: Network Throughput
        q_bw = f'(aws_rds_network_receive_throughput_average{{dimension_DBInstanceIdentifier=~"{pattern}"}} + aws_rds_network_transmit_throughput_average{{dimension_DBInstanceIdentifier=~"{pattern}"}}) or rate(node_network_transmit_bytes_total{{instance=~"{pattern}"}}[5m])'

        # latency: Replica Lag
        q_lat = f'aws_rds_replica_lag_average{{dimension_DBInstanceIdentifier=~"{pattern}"}} or mysql_slave_status_seconds_behind_master{{instance=~"{pattern}"}}'

        health, qs, bw, lat = await asyncio.gather(
            self.fetch_metric_stats(q_health, window_minutes),
            self.fetch_metric_stats(q_qs, window_minutes),
            self.fetch_metric_stats(q_bw, window_minutes),
            self.fetch_metric_stats(q_lat, window_minutes)
        )

        # Resolve status: If we see CPU OR any other metric, the instance is Up (1.0)
        # This prevents status 0 if only CPU metrics are temporarily missing in Mimir.
        has_any_metric = (health and health.get("avg") is not None) or \
                         (qs and qs.get("avg") is not None) or \
                         (bw and bw.get("avg") is not None) or \
                         (lat and lat.get("avg") is not None)
        
        base_status = 1.0 if has_any_metric else 0.0

        now_ts = int(datetime.utcnow().timestamp())
        zero_pts = [[now_ts - (i * 60), 0.0] for i in range(6)]
        zero_pts.reverse()
        zero = {"min": 0.0, "max": 0.0, "avg": 0.0, "med": 0.0, "points": zero_pts, "datasource": "Mimir/Prometheus (Zero-Filing)"}
        
        return {
            "status": base_status,
            "qSize": qs or zero,
            "bandwidth": bw or zero,
            "latency": lat or zero,
            "datasource": "Mimir/Prometheus"
        }

    def collect(self, resource_id: str, window_minutes: int = 5) -> Dict[str, Any]:
        return {}

    def health_check(self) -> bool:
        return True

    async def close(self):
        if self._async_client:
            await self._async_client.aclose()
            self._async_client = None
