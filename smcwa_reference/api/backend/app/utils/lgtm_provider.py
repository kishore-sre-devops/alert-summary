import os
import logging
import asyncio
import httpx
from datetime import datetime, timedelta
from prometheus_api_client import PrometheusConnect
from prometheus_api_client.utils import parse_datetime
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)

# Configuration
# Support for multiple data sources
URL_ONPREM = os.getenv("LGTM_PROMETHEUS_URL_ONPREM")
URL_AWS = os.getenv("LGTM_PROMETHEUS_URL_AWS")
URL_MIMIR = os.getenv("MIMIR_URL", "http://10.236.26.167:9009/prometheus")
URL_DEFAULT = os.getenv("LGTM_PROMETHEUS_URL", "http://localhost:9090")
DISABLE_SSL = os.getenv("LGTM_DISABLE_SSL", "true").lower() == "true"

# Safety Kill-Switch for High-Resolution Mode
ENABLE_HIGH_RES_MODE = os.getenv("ENABLE_HIGH_RES_MODE", "true").lower() == "true"

# --- Predefined PromQL Queries ---
# Linux (node_exporter)
QUERY_CPU_LINUX = '100 - (avg by(instance) (irate(node_cpu_seconds_total{mode="idle", instance=~"{{IP}}(:.*)?"}[1m])) * 100)'
QUERY_MEMORY_TOTAL_LINUX = 'node_memory_MemTotal_bytes{instance=~"{{IP}}(:.*)?"}'
QUERY_MEMORY_USED_LINUX = 'node_memory_MemTotal_bytes{instance=~"{{IP}}(:.*)?"} - node_memory_MemAvailable_bytes{instance=~"{{IP}}(:.*)?"}'
# Compliance Fix: Calculate AGGREGATE utilization across all physical disks (Total Used / Total Size)
QUERY_DISK_LINUX = '(sum(node_filesystem_size_bytes{instance=~"{{IP}}(:.*)?", mountpoint!~"/boot.*|/snap.*|/run.*|/dev.*|/sys.*|/proc.*", fstype!~"tmpfs|ramfs|autofs|vfat|iso9660|overlay"} - node_filesystem_avail_bytes{instance=~"{{IP}}(:.*)?", mountpoint!~"/boot.*|/snap.*|/run.*|/dev.*|/sys.*|/proc.*", fstype!~"tmpfs|ramfs|autofs|vfat|iso9660|overlay"}) / sum(node_filesystem_size_bytes{instance=~"{{IP}}(:.*)?", mountpoint!~"/boot.*|/snap.*|/run.*|/dev.*|/sys.*|/proc.*", fstype!~"tmpfs|ramfs|autofs|vfat|iso9660|overlay"})) * 100'
QUERY_DISK_TOTAL_LINUX = 'sum(node_filesystem_size_bytes{instance=~"{{IP}}(:.*)?", mountpoint!~"/boot.*|/snap.*|/run.*|/dev.*|/sys.*|/proc.*", fstype!~"tmpfs|ramfs|autofs|vfat|iso9660|overlay"})'
QUERY_DISK_USED_LINUX = 'sum(node_filesystem_size_bytes{instance=~"{{IP}}(:.*)?", mountpoint!~"/boot.*|/snap.*|/run.*|/dev.*|/sys.*|/proc.*", fstype!~"tmpfs|ramfs|autofs|vfat|iso9660|overlay"} - node_filesystem_avail_bytes{instance=~"{{IP}}(:.*)?", mountpoint!~"/boot.*|/snap.*|/run.*|/dev.*|/sys.*|/proc.*", fstype!~"tmpfs|ramfs|autofs|vfat|iso9660|overlay"})'
QUERY_UPTIME_LINUX = 'time() - node_boot_time_seconds{instance=~"{{IP}}(:.*)?"}'

# Windows (windows_exporter)
QUERY_CPU_WINDOWS = '100 - (avg by(instance) (rate(windows_cpu_time_total{mode="idle", instance=~"{{IP}}(:.*)?"}[1m])) * 100)'
QUERY_MEMORY_WINDOWS = '(1 - (windows_memory_physical_free_bytes{instance=~"{{IP}}(:.*)?"} or windows_os_physical_memory_free_bytes{instance=~"{{IP}}(:.*)?"}) / (windows_memory_physical_total_bytes{instance=~"{{IP}}(:.*)?"} or windows_cs_physical_memory_bytes{instance=~"{{IP}}(:.*)?"})) * 100'
# Compliance Fix: Aggregate Windows utilization (Sum of Used / Sum of Size)
QUERY_DISK_WINDOWS = '(sum(windows_logical_disk_size_bytes{volume!~"HarddiskVolume.*",instance=~"{{IP}}(:.*)?"} - windows_logical_disk_free_bytes{volume!~"HarddiskVolume.*",instance=~"{{IP}}(:.*)?"}) / sum(windows_logical_disk_size_bytes{volume!~"HarddiskVolume.*",instance=~"{{IP}}(:.*)?"})) * 100'
QUERY_MEMORY_TOTAL_WINDOWS = '(windows_memory_physical_total_bytes{instance=~"{{IP}}(:.*)?"} or windows_cs_physical_memory_bytes{instance=~"{{IP}}(:.*)?"})'
QUERY_MEMORY_USED_WINDOWS = '(windows_memory_physical_total_bytes{instance=~"{{IP}}(:.*)?"} or windows_cs_physical_memory_bytes{instance=~"{{IP}}(:.*)?"}) - (windows_memory_physical_free_bytes{instance=~"{{IP}}(:.*)?"} or windows_os_physical_memory_free_bytes{instance=~"{{IP}}(:.*)?"})'
# Compliance Fix: Aggregate Total/Used for Windows
QUERY_DISK_TOTAL_WINDOWS = 'sum(windows_logical_disk_size_bytes{volume!~"HarddiskVolume.*",instance=~"{{IP}}(:.*)?"})'
QUERY_DISK_USED_WINDOWS = 'sum(windows_logical_disk_size_bytes{volume!~"HarddiskVolume.*",instance=~"{{IP}}(:.*)?"} - windows_logical_disk_free_bytes{volume!~"HarddiskVolume.*",instance=~"{{IP}}(:.*)?"})'
QUERY_UPTIME_WINDOWS = '(windows_os_system_up_time{instance=~"{{IP}}(:.*)?"}) or (time() - windows_system_boot_time_timestamp{instance=~"{{IP}}(:.*)?"}) or (time() - windows_system_system_up_time{instance=~"{{IP}}(:.*)?"})'

# Fallback/Legacy
QUERY_CPU = QUERY_CPU_LINUX
QUERY_MEMORY = '((1 - (node_memory_MemAvailable_bytes{instance=~"{{IP}}(:.*)?"} / node_memory_MemTotal_bytes{instance=~"{{IP}}(:.*)?"})) * 100)'
QUERY_DISK = QUERY_DISK_LINUX
QUERY_UPTIME = QUERY_UPTIME_LINUX

# Network
# Bandwidth Utilization %: (Current Bytes/sec / Max Capacity Bytes/sec) * 100
# Falls back to 10Gbps (1.25e9 bytes/s) if speed metric is missing.
QUERY_BANDWIDTH_LINUX = 'max by(instance) ((rate(node_network_receive_bytes_total{instance=~"{{IP}}(:.*)?", device!~"lo|docker.*|veth.*|tunnel.*"}[5m]) + rate(node_network_transmit_bytes_total{instance=~"{{IP}}(:.*)?", device!~"lo|docker.*|veth.*|tunnel.*"}[5m])) / (node_network_speed_bytes{instance=~"{{IP}}(:.*)?", device!~"lo|docker.*|veth.*|tunnel.*"} or vector(1.25e9)) * 100) or on(instance) (vector(0.01))'
QUERY_BANDWIDTH_WINDOWS = 'max by(instance) ((rate(windows_net_bytes_received_total{instance=~"{{IP}}(:.*)?"}[5m]) + rate(windows_net_bytes_sent_total{instance=~"{{IP}}(:.*)?"}[5m])) / (windows_net_current_bandwidth_bytes{instance=~"{{IP}}(:.*)?"} or vector(1.25e9)) * 100) or on(instance) (vector(0.01))'
QUERY_BANDWIDTH = QUERY_BANDWIDTH_LINUX  # Legacy alias
QUERY_LATENCY = 'avg_over_time(probe_duration_seconds{instance=~"{{IP}}(:.*)?"}[1m])'

# Network Latency: ICMP RTT as per LAMA V1.3: "Network Latency (in milliseconds) — delay in network communication"
QUERY_NETWORK_LATENCY = 'avg_over_time(probe_icmp_duration_seconds{phase="rtt",instance=~"{{IP}}(:.*)?"}[5m]) * 1000'

# DNS Lookup Failure Count as per LAMA V1.3: "DNS Lookup Failure Count"
QUERY_LOOKUP_COUNT = 'sum by(instance) (increase(probe_dns_lookup_time_seconds{instance=~"{{IP}}(:.*)?"}[5m]))'

# Packet Count: RECEIVED ERRORS ONLY as per LAMA definition: "packets received with errors"
QUERY_PACKET_COUNT = 'sum by(instance) (increase(node_network_receive_errs_total{instance=~"{{IP}}(:.*)?"}[5m]))'
QUERY_PACKET_COUNT_WINDOWS = 'sum by(instance) (increase(windows_net_packets_received_errors_total{instance=~"{{IP}}(:.*)?"}[5m]))'


# Database (Placeholder - requires specific DB exporter like mysqld_exporter or postgres_exporter)
QUERY_DB_STATUS = 'pg_up{instance=~"{{IP}}(:.*)?"}' # Example for Postgres
QUERY_DB_QSIZE = 'pg_stat_activity_count{instance=~"{{IP}}(:.*)?"}'

# Application (Placeholder - requires custom instrumentation)
QUERY_APP_THROUGHPUT = 'rate(http_requests_total{instance=~"{{IP}}(:.*)?"}[5m])'
QUERY_APP_LATENCY = 'rate(http_request_duration_seconds_sum{instance=~"{{IP}}(:.*)?"}[5m]) / rate(http_request_duration_seconds_count{instance=~"{{IP}}(:.*)?"}[5m])'

class LGTMProvider:
    def __init__(self):
        self.clients = []
        self.ip_source_cache = {}
        self.db_sources_loaded = False
        self._async_client: Optional[httpx.AsyncClient] = None
        self.reload_sources()

    async def get_async_client(self) -> httpx.AsyncClient:
        # Check if we have a client and if it's still valid for the current loop
        try:
            current_loop = asyncio.get_running_loop()
        except RuntimeError:
            current_loop = None

        recreate = False
        if self._async_client is None or self._async_client.is_closed:
            recreate = True
        elif hasattr(self, '_client_loop') and self._client_loop != current_loop:
            logger.debug("Recreating AsyncClient because event loop has changed")
            try:
                await self.close()
            except Exception as e:
                logger.debug(f"Error closing old AsyncClient: {e}")
            recreate = True
        
        if recreate:
            self._async_client = httpx.AsyncClient(
                verify=not DISABLE_SSL,
                timeout=httpx.Timeout(10.0, connect=2.0),
                limits=httpx.Limits(max_connections=1000, max_keepalive_connections=100)
            )
            self._client_loop = current_loop
            
        return self._async_client

    async def close(self):
        if self._async_client:
            await self._async_client.aclose()
            self._async_client = None

    def reload_sources(self):
        self.clients = []
        sources = []
        
        env_url = os.getenv("LGTM_PROMETHEUS_URL")
        if env_url: sources.append(("Mimir/Prometheus", env_url, "prometheus", 1))
        if URL_ONPREM: sources.append(("On-Prem/Prometheus", URL_ONPREM, "prometheus", 1))
        if URL_AWS: sources.append(("AWS/Prometheus", URL_AWS, "prometheus", 3))
        if URL_MIMIR: sources.append(("MIMIR", URL_MIMIR, "prometheus", 3))
            
        try:
            from app.db.db import engine, metric_sources_table
            from sqlalchemy import select
            with engine.connect() as conn:
                query = select(metric_sources_table).where(metric_sources_table.c.enabled == True)
                db_sources = conn.execute(query).fetchall()
                for src in db_sources:
                    # Use _mapping for safe column access
                    m = src._mapping
                    s_name, s_type, s_config = m['name'], m['type'].lower(), m['config']
                    s_location_id = m.get('location_id', 1)
                    s_id = m.get('id')
                    
                    if s_type in ['prometheus', 'mimir', 'lgtm']:
                        url = s_config.get('url')
                        if url: sources.append((s_name, url, "prometheus", s_location_id, s_id))
                    elif s_type == 'cloudwatch':
                        sources.append((s_name, s_config, "cloudwatch", s_location_id, s_id))
            self.db_sources_loaded = True
        except Exception as e:
            logger.warning(f"Could not load metric sources from DB: {e}")

        if not sources and URL_DEFAULT:
            sources.append(("DEFAULT", URL_DEFAULT, "prometheus", 1, None))
            
        for item in sources:
            name, config_or_url, src_type, loc_id = item[0], item[1], item[2], item[3]
            s_id = item[4] if len(item) > 4 else None
            try:
                if src_type == "prometheus":
                    url = config_or_url.rstrip('/')
                    if not url.startswith('http'): url = f"http://{url}"
                    client = PrometheusConnect(url=url, disable_ssl=DISABLE_SSL)
                    self.clients.append({
                        "name": name, 
                        "type": "prometheus", 
                        "client": client, 
                        "url": url,
                        "location_id": loc_id,
                        "source_id": s_id
                    })
                    logger.info(f"✅ Registered LGTM source: {name} ({url}) [Loc: {loc_id}]")
                elif src_type == "cloudwatch":
                    self.clients.append({
                        "name": name, 
                        "type": "cloudwatch", 
                        "config": config_or_url,
                        "location_id": loc_id,
                        "source_id": s_id
                    })
                    logger.info(f"✅ Registered CloudWatch source: {name} [Loc: {loc_id}]")
            except Exception as e:
                logger.error(f"❌ Failed to connect to source {name}: {e}")

    def _get_query_for_os(self, query_type: str, os_type: str = "Linux"):
        os_type = (os_type or "Linux").lower()
        queries = {
            "cpu": {"linux": QUERY_CPU_LINUX, "windows": QUERY_CPU_WINDOWS},
            "memory": {"linux": QUERY_MEMORY, "windows": QUERY_MEMORY_WINDOWS},
            "memory_total": {"linux": QUERY_MEMORY_TOTAL_LINUX, "windows": QUERY_MEMORY_TOTAL_WINDOWS},
            "memory_used": {"linux": QUERY_MEMORY_USED_LINUX, "windows": QUERY_MEMORY_USED_WINDOWS},
            "disk": {"linux": QUERY_DISK_LINUX, "windows": QUERY_DISK_WINDOWS},
            "disk_total": {"linux": QUERY_DISK_TOTAL_LINUX, "windows": QUERY_DISK_TOTAL_WINDOWS},
            "disk_used": {"linux": QUERY_DISK_USED_LINUX, "windows": QUERY_DISK_USED_WINDOWS},
            "uptime": {"linux": QUERY_UPTIME_LINUX, "windows": QUERY_UPTIME_WINDOWS},
            "network_throughput": {
                "linux": '(sum(irate(node_network_receive_bytes_total{instance=~"{{IP}}.*", device!="lo"}[1m]) + irate(node_network_transmit_bytes_total{instance=~"{{IP}}.*", device!="lo"}[1m])) by (instance)) * 8',
                "windows": '(sum(irate(windows_net_bytes_received_total{instance=~"{{IP}}.*"}[1m]) + irate(windows_net_bytes_sent_total{instance=~"{{IP}}.*"}[1m])) by (instance)) * 8'
            },
            "network_bandwidth": {"linux": QUERY_BANDWIDTH_LINUX, "windows": QUERY_BANDWIDTH_WINDOWS},
            "packet_count": {
                "linux": QUERY_PACKET_COUNT,
                "windows": QUERY_PACKET_COUNT_WINDOWS
            },
            "lookup_count": {
                "linux": QUERY_LOOKUP_COUNT,
                "windows": QUERY_LOOKUP_COUNT
            },
            "network_latency": {
                "linux": QUERY_NETWORK_LATENCY,
                "windows": QUERY_NETWORK_LATENCY
            },
            "latency": {
                "linux": QUERY_LATENCY,
                "windows": QUERY_LATENCY
            }
        }
        if query_type in queries:
            return queries[query_type].get(os_type, queries[query_type]["linux"])
        return query_type

    def _get_clients_prioritized(self, server_ip, location_id: int = None):
        if not self.clients: return []
        
        # Base list
        clients = list(self.clients)
        
        # 1. Prioritize by Location ID match
        if location_id is not None:
            # Sort clients: those matching location_id come first
            clients.sort(key=lambda x: 0 if x.get('location_id') == location_id else 1)
            
        # 2. Finally, bubble up the cached source for this specific IP if it exists
        if server_ip in self.ip_source_cache:
            idx_in_original = self.ip_source_cache[server_ip]
            if 0 <= idx_in_original < len(self.clients):
                cached_client = self.clients[idx_in_original]
                # Put cached client at the very front
                clients = [cached_client] + [c for c in clients if c != cached_client]
                
        return clients

    def _update_cache(self, server_ip, client_obj):
        try:
            idx = self.clients.index(client_obj)
            self.ip_source_cache[server_ip] = idx
        except: pass

    async def async_get_os_info(self, resource_id: str, os_type: str = "Linux") -> Optional[str]:
        """Attempt to resolve a descriptive OS name (e.g. 'Windows Server 2019', 'Ubuntu 22.04')"""
        if not self.clients: return None
        orig_os_type = (os_type or "Linux").lower()
        clients = self._get_clients_prioritized(resource_id)
        async_client = await self.get_async_client()

        # Try the expected OS type first, then fallback to the other one if no result
        # This handles cases where a server was manually added with the wrong OS type
        types_to_try = [orig_os_type, "windows" if orig_os_type != "windows" else "linux"]

        for try_type in types_to_try:
            if try_type == "windows":
                q = f'windows_os_info{{instance=~"{resource_id}.*"}}'
                label_keys = ["product", "version"]
            else:
                q = f'node_os_info{{instance=~"{resource_id}.*"}}'
                label_keys = ["pretty_name", "name"]

            for client_obj in clients:
                if client_obj["type"] == "prometheus":
                    try:
                        response = await async_client.get(f"{client_obj['url']}/api/v1/query", params={"query": q}, timeout=2.0)
                        if response.status_code == 200:
                            data = response.json()
                            results = data.get("data", {}).get("result", [])
                            if results:
                                metric = results[0].get("metric", {})
                                for k in label_keys:
                                    val = metric.get(k)
                                    if val and val.lower() != "unknown":
                                        return val
                    except Exception as e:
                        logger.debug(f"OS info resolution failed for {try_type} from {client_obj['name']}: {e}")
        return None

    async def async_get_hostname(self, resource_id: str, os_type: str = "Linux") -> Optional[str]:
        """Attempt to resolve a descriptive hostname from Prometheus metrics"""
        if not self.clients: return None
        os_type = (os_type or "Linux").lower()
        clients = self._get_clients_prioritized(resource_id)
        async_client = await self.get_async_client()

        # Queries to try based on OS
        if os_type == "windows":
            queries = [
                f'windows_cs_hostname{{instance=~"{resource_id}.*"}}',
                f'windows_os_info{{instance=~"{resource_id}.*"}}' # Falls back to job name in collector logic usually, but here we check labels
            ]
            label_keys = ["hostname", "fqdn", "job"]
        else:
            queries = [
                f'node_uname_info{{instance=~"{resource_id}.*"}}'
            ]
            label_keys = ["nodename", "job"]

        for client_obj in clients:
            if client_obj["type"] == "prometheus":
                for q in queries:
                    try:
                        response = await async_client.get(f"{client_obj['url']}/api/v1/query", params={"query": q}, timeout=2.0)
                        if response.status_code == 200:
                            data = response.json()
                            results = data.get("data", {}).get("result", [])
                            if results:
                                metric = results[0].get("metric", {})
                                for k in label_keys:
                                    val = metric.get(k)
                                    if val and val.lower() != "unknown" and val != resource_id:
                                        return val
                    except Exception as e:
                        logger.debug(f"Hostname resolution failed from {client_obj['name']} with query {q}: {e}")
        return None

    async def async_query_value(self, query: str, location_id: int = None):
        """Execute a raw PromQL query and return the latest scalar value."""
        if not self.clients: return None
        
        # Filter clients by location if provided
        target_clients = self.clients
        if location_id is not None:
            target_clients = [c for c in self.clients if c.get("location_id") == location_id or c.get("location_id") == 1]
            
        async_client = await self.get_async_client()
        for client_obj in target_clients:
            if client_obj['type'] == 'prometheus':
                try:
                    url = f"{client_obj['url']}/api/v1/query"
                    resp = await async_client.get(url, params={"query": query}, timeout=3.0)
                    if resp.status_code == 200:
                        data = resp.json().get("data", {}).get("result", [])
                        if data:
                            return float(data[0]['value'][1])
                except Exception as e:
                    logger.debug(f"Raw query failed from {client_obj['name']}: {e}")
        return 0.0

    async def async_get_latest_value(self, query_base: str, resource_id: str, source_preference: str = "auto", os_type: str = "Linux", location_id: int = None, server_ip: str = None, source_id: int = None):
        if not self.clients: 
            logger.debug(f"No clients registered in LGTMProvider for {resource_id}")
            return None
        
        # Identification priority: If server_ip is not provided, use resource_id as fallback
        prom_id = server_ip if server_ip else resource_id
        clients = self._get_clients_prioritized(prom_id, location_id=location_id)
        async_client = await self.get_async_client()

        # If source_preference is 'aws', we should prioritize cloudwatch clients
        if source_preference == 'aws':
            # Re-sort clients to put cloudwatch first
            clients = [c for c in clients if c['type'] == 'cloudwatch'] + [c for c in clients if c['type'] != 'cloudwatch']
            # If source_id is specified, pin to that exact source
            if source_id is not None:
                pinned = [c for c in clients if c.get('source_id') == source_id]
                if pinned:
                    clients = pinned
        elif source_preference in ['onprem', 'auto']:
            # STRICT FILTER: Never use CloudWatch for an IP address
            import re
            is_ip = bool(re.match(r'^\d{1,3}(\.\d{1,3}){3}(:\d+)?$', resource_id))
            if is_ip or source_preference == 'onprem':
                clients = [c for c in clients if c['type'] != 'cloudwatch']

        for client_obj in clients:
            if client_obj["type"] == "prometheus":
                query_tpl = self._get_query_for_os(query_base, os_type)
                # CRITICAL: Use prom_id (IP) for Prometheus queries, NOT the AWS Instance ID
                query = query_tpl.replace("{{IP}}", prom_id)
                try:
                    response = await async_client.get(f"{client_obj['url']}/api/v1/query", params={"query": query}, timeout=2.0)
                    if response.status_code == 200:
                        data = response.json()
                        result = data.get("data", {}).get("result", [])
                        if result:
                            val = float(result[0]['value'][1])
                            if source_preference == "auto": self._update_cache(prom_id, client_obj)
                            return val
                except Exception as e:
                    logger.debug(f"Async fetch failed from {client_obj['name']}: {e}")
            elif client_obj["type"] == "cloudwatch":
                logger.info(f"Attempting CloudWatch fetch for {resource_id} ({query_base}) via {client_obj['name']}")
                loop = asyncio.get_event_loop()
                val_obj = await loop.run_in_executor(None, self._fetch_cloudwatch_metric, client_obj["config"], query_base, resource_id)
                if val_obj is not None:
                    val = val_obj.get("avg")
                    logger.info(f"✅ CloudWatch fetch success for {resource_id} ({query_base}): {val}")
                    if source_preference == "auto": self._update_cache(resource_id, client_obj)
                    return val
        return None

    async def async_fetch_metric_stats(self, query_base: str, server_ip: str, time_window_minutes: int = 5, source_preference: str = "auto", os_type: str = "Linux", high_res: bool = False, prometheus_url: str = None):
        if not self.clients and not prometheus_url: return None
        
        # If prometheus_url is provided, we use it directly as a single-item list
        if prometheus_url:
            clients = [{"type": "prometheus", "url": prometheus_url, "name": "Custom-Source"}]
        else:
            clients = self._get_clients_prioritized(server_ip)
            
        async_client = await self.get_async_client()

        # Resolution Logic: Strictly 1-minute resolution (60s) as requested
        step = "60s"

        # STRICT FILTER: Never use CloudWatch for an IP address
        import re
        is_ip = bool(re.match(r'^\d{1,3}(\.\d{1,3}){3}(:\d+)?$', server_ip))
        if (is_ip or source_preference == 'onprem') and not prometheus_url:
            clients = [c for c in clients if c['type'] != 'cloudwatch']

        for client_obj in clients:
            if client_obj["type"] == "prometheus":
                query_tpl = self._get_query_for_os(query_base, os_type)
                query = query_tpl.replace("{{IP}}", server_ip)
                
                # COMPLIANCE FIX: Location-Aware Time Shifting
                # Loc 1 (DC) & Loc 2 (DR) -> Real-Time (No shift)
                # Loc 3 (Cloud) -> 4-minute shift to handle AWS/CloudWatch publishing delay
                loc_id = client_obj.get("location_id", 1) # Default to On-Prem if unknown
                if loc_id == 3:
                    end_time = datetime.utcnow() - timedelta(seconds=240)
                else:
                    end_time = datetime.utcnow()
                
                start_time = end_time - timedelta(minutes=10) # Window ensures we find 6 points
                
                try:
                    params = {
                        "query": query,
                        "start": start_time.isoformat() + "Z",
                        "end": end_time.isoformat() + "Z",
                        "step": step
                    }
                    response = await async_client.get(f"{client_obj['url']}/api/v1/query_range", params=params, timeout=5.0)
                    if response.status_code == 200:
                        data = response.json()
                        results = data.get("data", {}).get("result", [])
                        if results:
                            # Filter to find result with matching instance (skip fallback vectors)
                            target_result = None
                            for r in results:
                                inst = r.get("metric", {}).get("instance", "")
                                if inst and server_ip in inst:
                                    target_result = r
                                    break
                            # Fallback to first result with an instance label
                            if not target_result:
                                for r in results:
                                    if r.get("metric", {}).get("instance"):
                                        target_result = r
                                        break
                            # Last resort: first result
                            if not target_result:
                                target_result = results[0]
                            
                            # Extract the data points (v[1] is the value)
                            all_raw_pts = target_result.get("values", [])
                            # Sort by timestamp and take LATEST 6 points for the cycle
                            all_raw_pts.sort(key=lambda x: x[0])
                            final_points_raw = all_raw_pts[-6:] if len(all_raw_pts) >= 6 else all_raw_pts
                            
                            values = [float(v[1]) for v in final_points_raw]
                            
                            if values:
                                import statistics
                                if source_preference == "auto" and not prometheus_url: 
                                    self._update_cache(server_ip, client_obj)
                                
                                # Extract raw points with timestamps and round to 2 decimal places
                                points = [[int(v[0]), round(float(v[1]), 2)] for v in final_points_raw]
                                
                                # Calculate stats from the points and round to 2 decimal places
                                return {
                                    "min": round(min(values), 2),
                                    "max": round(max(values), 2),
                                    "avg": round(statistics.mean(values), 2),
                                    "med": round(statistics.median(values), 2),
                                    "points": points,
                                    "datasource": client_obj.get("name", "Mimir/Prometheus")
                                }
                        
                        # ZERO-FILING: If no results found, provide 6 zero points for the window
                        # This ensures audit compliance for metrics like packetCount (errors) which are often zero.
                        now_ts = int(datetime.utcnow().timestamp())
                        zero_points = [[now_ts - (i * 60), 0.0] for i in range(6)]
                        zero_points.reverse()
                        return {
                            "min": 0.0, "max": 0.0, "avg": 0.0, "med": 0.0,
                            "points": zero_points,
                            "datasource": f"{client_obj.get('name', 'Mimir/Prometheus')} (Zero-Filing)"
                        }
                except Exception as e:
                    logger.debug(f"Range fetch failed from {client_obj['name']}: {e}")
            elif client_obj["type"] == "cloudwatch":
                # For CloudWatch, we continue using the dedicated stats fetcher
                try:
                    loop = asyncio.get_event_loop()
                    stats = await loop.run_in_executor(
                        None, 
                        self._fetch_cloudwatch_metric_stats, 
                        client_obj["config"], 
                        query_base, 
                        server_ip, 
                        datetime.utcnow() - timedelta(minutes=time_window_minutes),
                        datetime.utcnow()
                    )
                    if stats: return stats
                except Exception as e:
                    logger.debug(f"CloudWatch stats fetch failed from {client_obj['name']}: {e}")
        return None

    def fetch_metric_stats(self, query_base: str, server_ip: str, time_window_minutes: int = 5, source_preference: str = "auto", os_type: str = "Linux", high_res: bool = False, prometheus_url: str = None):
        try:
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                
            if loop.is_running():
                import nest_asyncio
                nest_asyncio.apply()
                return loop.run_until_complete(self.async_fetch_metric_stats(query_base, server_ip, time_window_minutes, source_preference, os_type, high_res=high_res, prometheus_url=prometheus_url))
            else:
                return loop.run_until_complete(self.async_fetch_metric_stats(query_base, server_ip, time_window_minutes, source_preference, os_type, high_res=high_res, prometheus_url=prometheus_url))
        except Exception as e:
            logger.error(f"Error in fetch_metric_stats: {e}")
            return None

    async def async_get_disk_details(self, resource_id: str, os_type: str = "Linux", location_id: int = None, server_ip: str = None):
        if not self.clients: return []
        os_type = (os_type or "linux").lower()
        
        prom_id = server_ip if server_ip else resource_id
        clients = self._get_clients_prioritized(prom_id, location_id=location_id)
        async_client = await self.get_async_client()

        if os_type == "windows":
            q_size = f'windows_logical_disk_size_bytes{{instance=~"{prom_id}.*", volume=~"[C-Z]:"}}'
            q_free = f'windows_logical_disk_free_bytes{{instance=~"{prom_id}.*", volume=~"[C-Z]:"}}'
            label_key = "volume"
        else:
            q_size = f'node_filesystem_size_bytes{{instance=~"{prom_id}.*", mountpoint!~"/boot.*|/snap.*|/run.*|/dev.*|/sys.*|/proc.*", fstype!~"tmpfs|ramfs|autofs|vfat|iso9660|overlay"}}'
            q_free = f'node_filesystem_free_bytes{{instance=~"{prom_id}.*", mountpoint!~"/boot.*|/snap.*|/run.*|/dev.*|/sys.*|/proc.*", fstype!~"tmpfs|ramfs|autofs|vfat|iso9660|overlay"}}'
            label_key = "mountpoint"

        for client_obj in clients:
            if client_obj["type"] == "prometheus":
                try:
                    base_url = client_obj["url"]
                    res_size_task = async_client.get(f"{base_url}/api/v1/query", params={"query": q_size})
                    res_free_task = async_client.get(f"{base_url}/api/v1/query", params={"query": q_free})
                    res_size_resp, res_free_resp = await asyncio.gather(res_size_task, res_free_task)

                    if res_size_resp.status_code == 200 and res_free_resp.status_code == 200:
                        res_size = res_size_resp.json().get("data", {}).get("result", [])
                        res_free = res_free_resp.json().get("data", {}).get("result", [])
                        free_map = {item['metric'].get(label_key): float(item['value'][1]) for item in res_free if item['metric'].get(label_key)}
                        partitions = []
                        for item in res_size:
                            metric = item['metric']
                            name = metric.get(label_key)
                            if not name: continue
                            
                            # Attempt to find a descriptive label/name for the disk
                            display_name = name
                            
                            total_bytes = float(item['value'][1])
                            free_bytes = free_map.get(name, 0.0)
                            used_bytes = total_bytes - free_bytes
                            if total_bytes > 0:
                                partitions.append({
                                    "name": display_name,
                                    "total_gb": round(total_bytes / (1024**3), 2),
                                    "used_gb": round(used_bytes / (1024**3), 2),
                                    "free_gb": round(free_bytes / (1024**3), 2),
                                    "utilization": round(((total_bytes - free_bytes) / total_bytes) * 100, 2)
                                })
                        if partitions: return partitions
                except Exception as e:
                    logger.debug(f"Disk details async failed: {e}")
        return []

    async def async_get_network_details(self, resource_id: str, os_type: str = "Linux", location_id: int = None, server_ip: str = None):
        """Fetch per-interface network throughput and speed from Prometheus"""
        if not self.clients: return []
        os_type = (os_type or "linux").lower()
        
        prom_id = server_ip if server_ip else resource_id
        clients = self._get_clients_prioritized(prom_id, location_id=location_id)
        async_client = await self.get_async_client()

        if os_type == "windows":
            # Professional Update: Join with windows_net_nic_info to get the 'friendly_name' (e.g. "DR-LAN", "Odin-LAN")
            # Fallback: If nic_info join fails (empty result), return the raw metrics so we don't lose visibility
            q_throughput = f'((irate(windows_net_bytes_received_total{{instance=~"{prom_id}.*"}}[1m]) + irate(windows_net_bytes_sent_total{{instance=~"{prom_id}.*"}}[1m])) * 8) * on(instance, nic) group_left(friendly_name) (windows_net_nic_info{{instance=~"{prom_id}.*"}} == 1) or (irate(windows_net_bytes_received_total{{instance=~"{prom_id}.*"}}[1m]) + irate(windows_net_bytes_sent_total{{instance=~"{prom_id}.*"}}[1m])) * 8'
            q_speed = f'(windows_net_current_bandwidth_bytes{{instance=~"{prom_id}.*"}} * 8) * on(instance, nic) group_left(friendly_name) (windows_net_nic_info{{instance=~"{prom_id}.*"}} == 1) or (windows_net_current_bandwidth_bytes{{instance=~"{prom_id}.*"}} * 8)'
            label_key = "nic" # Use 'nic' label for Windows as it contains the adapter description
        else:
            q_throughput = f'(irate(node_network_receive_bytes_total{{instance=~"{prom_id}.*", device!="lo"}}[1m]) + irate(node_network_transmit_bytes_total{{instance=~"{prom_id}.*", device!="lo"}}[1m])) * 8'
            q_speed = f'node_network_speed_bytes{{instance=~"{prom_id}.*", device!="lo"}} * 8'
            label_key = "device"

        for client_obj in clients:
            if client_obj["type"] == "prometheus":
                try:
                    base_url = client_obj["url"]
                    res_throughput_task = async_client.get(f"{base_url}/api/v1/query", params={"query": q_throughput})
                    res_speed_task = async_client.get(f"{base_url}/api/v1/query", params={"query": q_speed})
                    res_throughput_resp, res_speed_resp = await asyncio.gather(res_throughput_task, res_speed_task)

                    if res_throughput_resp.status_code == 200 and res_speed_resp.status_code == 200:
                        res_throughput = res_throughput_resp.json().get("data", {}).get("result", [])
                        res_speed_data = res_speed_resp.json().get("data", {}).get("result", [])
                        speed_map = {item['metric'].get(label_key): float(item['value'][1]) for item in res_speed_data if item['metric'].get(label_key)}
                        
                        interfaces = []
                        for item in res_throughput:
                            metric = item['metric']
                            name = metric.get(label_key)
                            if not name: continue
                            
                            # For Linux, name is already descriptive enough (eth0, etc.)
                            # For Windows, use the 'friendly_name' from the join, fallback to 'nic' label
                            display_name = metric.get('friendly_name', name)
                            
                            throughput_bps = float(item['value'][1])
                            speed_bps = speed_map.get(name, 10_000_000_000.0) # Default to 10Gbps if speed not reported
                            if speed_bps <= 0: speed_bps = 10_000_000_000.0
                            
                            utilization = (throughput_bps / speed_bps) * 100
                            interfaces.append({
                                "name": display_name,
                                "throughput_bps": round(throughput_bps, 2),
                                "speed_bps": speed_bps,
                                "utilization": round(min(max(0.0, utilization), 100.0), 4)
                            })
                        if interfaces: return interfaces
                except Exception as e:
                    logger.debug(f"Network details async failed: {e}")
        return []

    def get_latest_value(self, query_base: str, server_ip: str, source_preference: str = "auto", os_type: str = "Linux"):
        try:
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                
            if loop.is_running():
                import nest_asyncio
                nest_asyncio.apply()
                return loop.run_until_complete(self.async_get_latest_value(query_base, server_ip, source_preference, os_type))
            else:
                return loop.run_until_complete(self.async_get_latest_value(query_base, server_ip, source_preference, os_type))
        except: return None

    def get_disk_details(self, server_ip: str, os_type: str = "Linux"):
        try:
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                
            if loop.is_running():
                import nest_asyncio
                nest_asyncio.apply()
                return loop.run_until_complete(self.async_get_disk_details(server_ip, os_type))
            else:
                return loop.run_until_complete(self.async_get_disk_details(server_ip, os_type))
        except: return []

    def get_network_details(self, server_ip: str, os_type: str = "Linux"):
        try:
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                
            if loop.is_running():
                import nest_asyncio
                nest_asyncio.apply()
                return loop.run_until_complete(self.async_get_network_details(server_ip, os_type))
            else:
                return loop.run_until_complete(self.async_get_network_details(server_ip, os_type))
        except: return []

    def _fetch_cloudwatch_metric(self, config, metric_type, resource_id):
        stats = self._fetch_cloudwatch_metric_stats(config, metric_type, resource_id, datetime.utcnow() - timedelta(minutes=10), datetime.utcnow())
        return stats # Return the dict {"min":..., "max":..., "avg":...}

    def _fetch_cloudwatch_metric_stats(self, config, metric_type, resource_id, start_time, end_time):
        try:
            from app.utils.aws_discovery import get_aws_client
            cw = get_aws_client('cloudwatch', config)
            
            # Default to EC2
            namespace, dimension_name, metric_name = 'AWS/EC2', 'InstanceId', 'CPUUtilization'
            
            # Identify resource type (Instance ID vs RDS ID vs ECS Service)
            is_ec2 = resource_id.startswith('i-')
            is_ecs = '/' in resource_id
            # RDS ID: Does not start with i-, no slash, usually has no dots (unlike IPs)
            is_rds = not is_ec2 and not is_ecs and '.' not in resource_id and len(resource_id) > 2
            
            logger.info(f"CloudWatch ID Match: {resource_id} -> EC2={is_ec2}, ECS={is_ecs}, RDS={is_rds}")

            if is_ec2:
                namespace, dimension_name = 'AWS/EC2', 'InstanceId'
                if metric_type == 'cpu': metric_name = 'CPUUtilization'
                elif metric_type in ['memory', 'memory_used', 'memory_total']: 
                    namespace, metric_name = 'CWAgent', 'mem_used_percent'
                elif metric_type in ['disk', 'disk_used', 'disk_total']: 
                    namespace, metric_name = 'CWAgent', 'disk_used_percent'
                elif metric_type == 'network_throughput':
                    # EC2: (NetworkIn + NetworkOut) bytes in 5 min -> Convert to bits/sec
                    ni = self._fetch_cloudwatch_metric_stats(config, 'NetworkIn', resource_id, start_time, end_time)
                    no = self._fetch_cloudwatch_metric_stats(config, 'NetworkOut', resource_id, start_time, end_time)
                    if ni or no:
                        total_bytes = (ni.get('avg', 0) if ni else 0) + (no.get('avg', 0) if no else 0)
                        bps = (total_bytes * 8) / 300 # Average bits per second over 5 min
                        return {"min": bps, "max": bps, "avg": bps}
                    return {"min": 0.0, "max": 0.0, "avg": 0.0}
                elif metric_type in ['packet_count', 'packetCount']:
                    pi = self._fetch_cloudwatch_metric_stats(config, 'NetworkPacketsIn', resource_id, start_time, end_time)
                    po = self._fetch_cloudwatch_metric_stats(config, 'NetworkPacketsOut', resource_id, start_time, end_time)
                    if pi or po:
                        total_p = (pi.get('avg', 0) if pi else 0) + (po.get('avg', 0) if po else 0)
                        return {"min": total_p, "max": total_p, "avg": total_p}
                    return {"min": 0.0, "max": 0.0, "avg": 0.0}
                elif metric_type in ['network_latency', 'latency']:
                    return {"min": 0.0, "max": 0.0, "avg": 0.0}
            elif is_ecs: # ECS Service (cluster/service or ARN)
                namespace, dimension_name = 'AWS/ECS', 'ServiceName'
                if resource_id.startswith('arn:'):
                    # Format: arn:aws:ecs:region:account:service/cluster-name/service-name
                    # Or: arn:aws:ecs:region:account:service/service-name (default cluster)
                    path = resource_id.split(':service/')[-1]
                    parts = path.split('/')
                    if len(parts) >= 2:
                        cluster_name = parts[0]
                        service_name = parts[1]
                    else:
                        cluster_name = 'default'
                        service_name = parts[0]
                else:
                    parts = resource_id.split('/')
                    service_name = parts[-1]
                    cluster_name = parts[0] if len(parts) > 1 else 'default'
                
                dimensions = [{'Name': 'ClusterName', 'Value': cluster_name}, {'Name': 'ServiceName', 'Value': service_name}]
                if metric_type == 'cpu': metric_name = 'CPUUtilization'
                elif metric_type in ['memory', 'memory_used', 'memory_total']: metric_name = 'MemoryUtilization'
                elif metric_type == 'throughput':
                    metric_name = 'RequestCount'
                    namespace = 'AWS/ApplicationELB' # Usually from ALB for ECS
                elif metric_type == 'latency':
                    # AWS TargetResponseTime is in Seconds, LAMA V1.3 requires Microseconds
                    res = self._fetch_cloudwatch_metric_stats(config, 'TargetResponseTime', resource_id, start_time, end_time)
                    if res:
                        val_us = res.get('avg', 0) * 1000000
                        return {"min": val_us, "max": val_us, "avg": val_us}
                    return {"min": 0.0, "max": 0.0, "avg": 0.0}
                elif metric_type == 'failureTradeApi':
                    metric_name = 'HTTPCode_Target_5XX_Count'
                    namespace = 'AWS/ApplicationELB'
                elif metric_type == 'failureAuthentication':
                    metric_name = 'HTTPCode_Target_4XX_Count'
                    namespace = 'AWS/ApplicationELB'
                elif metric_type in ['packet_count', 'network_latency', 'packetCount']:
                    return {"min": 0.0, "max": 0.0, "avg": 0.0}
                else: return None 
            elif is_rds: # RDS
                namespace, dimension_name = 'AWS/RDS', 'DBInstanceIdentifier'
                # RDS Dimensions must use DBInstanceIdentifier
                dimensions = [{'Name': 'DBInstanceIdentifier', 'Value': resource_id}]
                
                # PROFESSIONAL ARCHITECTURE: Map LAMA V1.3 RDS Metrics
                if metric_type in ['status', 'db_status']:
                    try:
                        rds = get_aws_client('rds', config)
                        db_res = rds.describe_db_instances(DBInstanceIdentifier=resource_id)
                        if db_res['DBInstances']:
                            db_status = db_res['DBInstances'][0].get('DBInstanceStatus')
                            val = 1.0 if db_status == 'available' else 0.0
                            return {"min": val, "max": val, "avg": val}
                    except: return {"min": 0.0, "max": 0.0, "avg": 0.0}
                
                elif metric_type in ['qSize', 'db_qsize']:
                    metric_name = 'ReplicationSlotDiskUsage'
                
                elif metric_type in ['bandwidth', 'db_bandwidth']:
                    try:
                        # Sum of Receive + Transmit Throughput
                        rx = self._fetch_cloudwatch_metric_stats(config, 'NetworkReceiveThroughput', resource_id, start_time, end_time)
                        tx = self._fetch_cloudwatch_metric_stats(config, 'NetworkTransmitThroughput', resource_id, start_time, end_time)
                        val = (rx.get('avg', 0) if rx else 0) + (tx.get('avg', 0) if tx else 0)
                        return {"min": val, "max": val, "avg": val}
                    except: return {"min": 0.0, "max": 0.0, "avg": 0.0}
                
                elif metric_type in ['latency', 'db_latency']:
                    # AWS ReplicaLag is in Seconds, LAMA V1.3 requires Microseconds
                    res = self._fetch_cloudwatch_metric_stats(config, 'ReplicaLag', resource_id, start_time, end_time)
                    if res:
                        val_us = res.get('avg', 0) * 1000000
                        return {"min": val_us, "max": val_us, "avg": val_us}
                    return {"min": 0.0, "max": 0.0, "avg": 0.0}

                # Standard Hardware mappings for RDS
                elif metric_type == 'cpu': metric_name = 'CPUUtilization'
                elif metric_type in ['memory', 'memory_used', 'memory_total']:
                    # Get FreeableMemory directly via CloudWatch API
                    from app.utils.aws_discovery import get_aws_client as _get_client
                    cw_mem = _get_client('cloudwatch', config)
                    freeable_bytes = 0
                    try:
                        resp = cw_mem.get_metric_statistics(
                            Namespace='AWS/RDS', MetricName='FreeableMemory',
                            Dimensions=[{'Name': 'DBInstanceIdentifier', 'Value': resource_id}],
                            StartTime=start_time, EndTime=end_time, Period=300, Statistics=['Average'])
                        dp = resp.get('Datapoints', [])
                        if dp:
                            freeable_bytes = sorted(dp, key=lambda x: x['Timestamp'])[-1]['Average']
                    except Exception as e:
                        logger.debug(f"Failed to get FreeableMemory for {resource_id}: {e}")
                    # Get total RAM from instance class
                    total_bytes = None
                    try:
                        rds = get_aws_client('rds', config)
                        inst_class = rds.describe_db_instances(DBInstanceIdentifier=resource_id)['DBInstances'][0]['DBInstanceClass']
                        _mem_gib = {'db.t4g.micro':1,'db.t4g.small':2,'db.t4g.medium':4,'db.t4g.large':8,
                                    'db.t4g.xlarge':16,'db.t4g.2xlarge':32,
                                    'db.t3.micro':1,'db.t3.small':2,'db.t3.medium':4,'db.t3.large':8,
                                    'db.t3.xlarge':16,'db.t3.2xlarge':32,
                                    'db.r6g.large':16,'db.r6g.xlarge':32,'db.r6g.2xlarge':64,
                                    'db.r5.large':16,'db.r5.xlarge':32,'db.r5.2xlarge':64,
                                    'db.m6g.large':8,'db.m6g.xlarge':16,'db.m6g.2xlarge':32,
                                    'db.m5.large':8,'db.m5.xlarge':16,'db.m5.2xlarge':32}
                        total_bytes = _mem_gib.get(inst_class, 8) * (1024**3)
                    except Exception as e:
                        logger.debug(f"Failed to get RDS instance class for {resource_id}: {e}")
                        total_bytes = 8 * (1024**3)
                    if metric_type == 'memory_total':
                        return {"min": total_bytes, "max": total_bytes, "avg": total_bytes}
                    elif metric_type == 'memory_used':
                        used = max(0, total_bytes - freeable_bytes)
                        return {"min": used, "max": used, "avg": used}
                    else:  # memory -> used percentage
                        used_pct = max(0.0, (total_bytes - freeable_bytes) / total_bytes * 100) if total_bytes > 0 else 0.0
                        return {"min": used_pct, "max": used_pct, "avg": used_pct}
                elif metric_type in ['disk', 'disk_used', 'disk_total']: 
                    metric_name = 'FreeStorageSpace' # Bytes
                elif metric_type == 'network_throughput':
                    # RDS: NetworkReceiveThroughput + NetworkTransmitThroughput (Bytes/Second) -> bits/sec
                    ni = self._fetch_cloudwatch_metric_stats(config, 'NetworkReceiveThroughput', resource_id, start_time, end_time)
                    no = self._fetch_cloudwatch_metric_stats(config, 'NetworkTransmitThroughput', resource_id, start_time, end_time)
                    if ni or no:
                        total_bps = ((ni.get('avg', 0) if ni else 0) + (no.get('avg', 0) if no else 0)) * 8
                        return {"min": total_bps, "max": total_bps, "avg": total_bps}
                    return {"min": 0.0, "max": 0.0, "avg": 0.0}
                elif metric_type in ['packet_count', 'network_latency', 'packetCount']:
                    return {"min": 0.0, "max": 0.0, "avg": 0.0}
                elif metric_type == 'uptime':
                    try:
                        rds = get_aws_client('rds', config)
                        db_res = rds.describe_db_instances(DBInstanceIdentifier=resource_id)
                        if db_res['DBInstances']:
                            create_time = db_res['DBInstances'][0]['InstanceCreateTime']
                            uptime_seconds = (datetime.now(create_time.tzinfo) - create_time).total_seconds()
                            # Return in minutes for LAMA standard
                            return {"min": uptime_seconds/60, "max": uptime_seconds/60, "avg": uptime_seconds/60}
                    except: return None
                else: return None
            else:
                # This is likely a local IP being passed incorrectly or an unsupported resource
                logger.debug(f"Resource {resource_id} does not match any CloudWatch pattern")
                return None

            if metric_type == 'uptime' and is_ec2:
                try:
                    ec2 = get_aws_client('ec2', config)
                    ec2_res = ec2.describe_instances(InstanceIds=[resource_id])
                    if ec2_res['Reservations']:
                        launch_time = ec2_res['Reservations'][0]['Instances'][0]['LaunchTime']
                        uptime_seconds = (datetime.now(launch_time.tzinfo) - launch_time).total_seconds()
                        return {"min": uptime_seconds/60, "max": uptime_seconds/60, "avg": uptime_seconds/60}
                except: return None

            if not is_ecs and not is_rds:
                dimensions = [{'Name': dimension_name, 'Value': resource_id}]
            
            logger.info(f"Querying CW: {namespace}/{metric_name} for {resource_id} with dimensions {dimensions}")
            response = cw.get_metric_statistics(
                Namespace=namespace,
                MetricName=metric_name,
                Dimensions=dimensions,
                StartTime=start_time,
                EndTime=end_time,
                Period=300,
                Statistics=['Average']
            )
            datapoints = response.get('Datapoints', [])
            
            # CRITICAL: If no datapoints found for this specific metric, return None
            # DO NOT fallback to other metrics like CPU
            if not datapoints: 
                logger.debug(f"No CW datapoints for {resource_id} {namespace}/{metric_name}")
                return None
                
            latest = sorted(datapoints, key=lambda x: x['Timestamp'])[-1]
            return {
                "min": latest['Average'], 
                "max": latest['Average'], 
                "avg": latest['Average'], 
                "med": latest['Average'],
                "datasource": f"AWS/CloudWatch ({config.get('name', 'Default')})"
            }
        except Exception as e:
            logger.debug(f"CW fetch failed for {resource_id} ({metric_type}): {e}")
            return None


lgtm_provider = LGTMProvider()