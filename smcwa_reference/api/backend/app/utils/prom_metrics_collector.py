"""
Prometheus metrics collector - periodically fetches hardware metrics from Prometheus/Mimir
for servers that don't have agents or prefer Prometheus as a data source.
Optimized for 1-second real-time resolution with IST support.
"""

import asyncio
import logging
from datetime import datetime
from sqlalchemy import update, text
from app.db.db import server_status_table, application_status_table, database_status_table, engine
from app.utils.lgtm_provider import lgtm_provider
from app.utils.metrics_calculator import store_metrics_batch, store_metric_value_with_interface, store_raw_batch
from app.utils.alert_checker import check_and_create_alert, check_and_create_alert_with_interface
from app.utils.alert_sender import send_alert
from app.utils.hot_store import update_hot_store_server_status

logger = logging.getLogger(__name__)

async def process_all_servers_async(servers):
    """Process all servers in parallel using a global task pool for maximum throughput"""
    if not servers: return

    # STEP 1: Batch fetch 'up' status for ALL servers in one query
    up_map = {}
    try:
        async_client = await lgtm_provider.get_async_client()
        if lgtm_provider.clients:
            primary_client = lgtm_provider.clients[0]
            if primary_client['type'] == 'prometheus':
                up_url = f"{primary_client['url']}/api/v1/query"
                # Filter out AWS sources from batch UP check (they use CloudWatch/Separate Mimir)
                # s[2] is ip, s[4] is metric_source, s[7] is external_id
                # Logic: Only check 'up' for servers that are NOT AWS/Cloud
                # Note: We need the location_id here, but let's use external_id as a proxy for now
                ips = [s[2] for s in servers if (s[4] or 'auto') != 'aws' and not s[7]]
                if not ips:
                    up_map = {}
                else:
                    ip_regex = "|".join([f"{ip}.*" for ip in ips])
                    up_query = f'up{{instance=~"{ip_regex}"}}'

                
                try:
                    up_res = await async_client.get(up_url, params={"query": up_query}, timeout=3.0)
                    if up_res.status_code == 200:
                        results = up_res.json().get("data", {}).get("result", [])
                        for r in results:
                            instance = r['metric'].get('instance', '')
                            val = float(r['value'][1])
                            ip = instance.split(':')[0]
                            up_map[ip] = (val == 1)
                except Exception as e:
                    logger.debug(f"Batch UP check failed: {e}")
    except Exception as e:
        logger.error(f"Error preparing batch Prometheus collection: {e}")

    # STEP 2: Launch parallel collection for each server (Batched to prevent Prometheus overload)
    sem = asyncio.Semaphore(5)  # Max 5 concurrent server polls

    async def _bound_worker(server):
        async with sem:
            return await asyncio.wait_for(process_single_server_async(server, up_map.get(server[2])), timeout=30.0)

    tasks = [_bound_worker(server) for server in servers]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    for i, r in enumerate(results):
        if isinstance(r, asyncio.TimeoutError):
            logger.warning(f"Timeout processing server {servers[i][1]} ({servers[i][2]})")
        elif isinstance(r, Exception):
            logger.warning(f"Error processing server {servers[i][1]}: {r}")

async def process_single_server_async(server_data, is_server_up_cached=None):
    """Worker function to process a single server asynchronously"""
    # SELECT s.id, s.name, s.ip, s.environment, COALESCE(less.metric_source, 'auto'), s.os_type, s.os_name, s.external_id, s.location_id[, source_id]
    source_id = None
    if len(server_data) == 10:
        server_id, server_name, server_ip, environment, metric_source, os_type, current_os_name, external_id, location_id, source_id = server_data
    else:
        server_id, server_name, server_ip, environment, metric_source, os_type, current_os_name, external_id, location_id = server_data
    metric_source = metric_source or "auto"
    os_type = (os_type or "Linux").lower()

    try:
        loop = asyncio.get_event_loop()
        is_server_up = is_server_up_cached

        # Fallback if cache missing
        if is_server_up is None and metric_source != 'aws' and not external_id:
            async_client = await lgtm_provider.get_async_client()
            up_query = f'up{{instance=~"{server_ip}.*"}}'
            prioritized_clients = lgtm_provider._get_clients_prioritized(server_ip, location_id=location_id)
            if prioritized_clients:
                try:
                    up_url = f"{prioritized_clients[0]['url']}/api/v1/query"
                    up_res = await async_client.get(up_url, params={"query": up_query}, timeout=1.5)
                    if up_res.status_code == 200:
                        up_data = up_res.json().get("data", {}).get("result", [])
                        if up_data:
                            is_server_up = (float(up_data[0]['value'][1]) == 1)
                except: pass

        # For AWS/Cloud sources, we assume online and let the metric fetch determine status
        if metric_source == 'aws' or external_id:
            is_server_up = True

        if is_server_up is False:
            # Optimization: skip processing if we explicitly know server is down from heartbeat check
            down_values = {"status": "offline", "cpu": 0.0, "memory": 0.0, "disk": 0.0, "updated_at": datetime.now()}
            await loop.run_in_executor(None, self_update_status, server_id, down_values)
            return

        # Prepare final values for DB and ClickHouse
        # COMPLIANCE: Consolidate into one final update to prevent race conditions
        now_ist = datetime.now()
        update_values = {"last_seen": now_ist, "updated_at": now_ist, "status": "online"}

        # Parallel metric fetch
        fetch_keys = ["cpu", "memory", "memory_total", "memory_used", "disk", "disk_total", "disk_used", "uptime", "network_throughput", "packet_count", "network_latency", "throughput", "latency", "failureTradeApi", "failureAuthentication"]
        
        # resource_id is InstanceId or IP
        resource_id = external_id if external_id else (server_name if metric_source == 'aws' or (server_name and server_name.startswith('i-')) else server_ip)

        # 1. Fetch Metrics
        fetch_tasks = []
        for k in fetch_keys:
            # SMART DISPATCHER: Route logic based on the actual Metric Source Type
            # This ensures 'ecs' sources use CloudWatch and 'prometheus_app' uses LAMA logic.
            
            if metric_source == 'prometheus_app' and k in ["throughput", "latency", "failureTradeApi", "failureAuthentication"]:
                # Pick & Pass: Query flat metric names from the LAMA exporter
                # Resolve the Prometheus instance label from metric_sources config
                if not hasattr(process_single_server_async, '_prom_instance_cache'):
                    process_single_server_async._prom_instance_cache = {}
                cache = process_single_server_async._prom_instance_cache
                if server_id not in cache:
                    try:
                        with engine.connect() as _c:
                            _r = _c.execute(text("SELECT ms.config->>'instance' FROM application_status a JOIN metric_sources ms ON a.source_id = ms.id WHERE a.id = :aid"), {"aid": server_id - 10000}).fetchone()
                            cache[server_id] = _r[0] if _r and _r[0] else "localhost:8000"
                    except:
                        cache[server_id] = "localhost:8000"
                prom_instance = cache[server_id]
                # Map: throughput->throughput_avg, latency->latency_avg, failures->single gauge
                prom_metric = f'{k}_avg' if k in ["throughput", "latency"] else k
                custom_q = f'{prom_metric}{{instance="{prom_instance}"}}'
                fetch_tasks.append(lgtm_provider.async_query_value(custom_q, location_id=location_id))
            
            elif metric_source == 'ecs' or metric_source == 'aws':
                # FUZZY FIX: If external_id is missing, fallback to the application name for lookup
                aws_res_id = external_id if external_id else server_name
                fetch_tasks.append(lgtm_provider.async_get_latest_value(k, aws_res_id, source_preference='aws', os_type=os_type, location_id=location_id, server_ip=server_ip, source_id=source_id))
            
            else:
                # Standard Prometheus/Generic logic
                fetch_tasks.append(lgtm_provider.async_get_latest_value(k, resource_id, source_preference=metric_source, os_type=os_type, location_id=location_id, server_ip=server_ip))

        # 2. Fetch Info
        info_tasks = []
        info_tasks.append(lgtm_provider.async_get_hostname(resource_id, os_type=os_type))
        if not current_os_name or current_os_name == os_type:
            info_tasks.append(lgtm_provider.async_get_os_info(resource_id, os_type=os_type))
        else:
            info_tasks.append(asyncio.sleep(0)) # Minimal sleep as placeholder

        # 3. Fetch Details
        detail_tasks = []
        detail_tasks.append(lgtm_provider.async_get_disk_details(resource_id, os_type=os_type, location_id=location_id))
        detail_tasks.append(lgtm_provider.async_get_network_details(resource_id, os_type=os_type, location_id=location_id))

        # Combine and Await
        all_tasks = fetch_tasks + info_tasks + detail_tasks
        all_results = await asyncio.gather(*all_tasks, return_exceptions=True)
        
        # Split results back
        res_metrics = all_results[:len(fetch_keys)]
        res_info = all_results[len(fetch_keys):len(fetch_keys)+2]
        res_details = all_results[len(fetch_keys)+2:]

        res_map = dict(zip(fetch_keys, res_metrics))
        res_map["partitions"] = res_details[0]
        res_map["interfaces"] = res_details[1]
        
        # Clean up exceptions and log failures
        for k in res_map:
            if isinstance(res_map[k], Exception):
                logger.debug(f"Task failed for {k} on {server_name}: {res_map[k]}")
                res_map[k] = None

        # SYNC HOSTNAME: If we got a hostname, update the server name in DB
        resolved_hostname = res_info[0] if not isinstance(res_info[0], Exception) else None
        if resolved_hostname and resolved_hostname != server_ip:
            new_name = str(resolved_hostname)
            if new_name and new_name.lower() != "unknown" and new_name != server_name:
                logger.info(f"🏷️ Updating server name for {server_id}: {server_name} -> {new_name}")
                update_values["name"] = new_name
                server_name = new_name # Keep local variable in sync

        # SYNC OS NAME
        resolved_os = res_info[1] if len(res_info) > 1 and not isinstance(res_info[1], Exception) else None
        if resolved_os:
            update_values["os_name"] = str(resolved_os)

        clickhouse_metrics = {}
        batch_points = [] # For storing raw points with interface names
        alert_ids = []
        
        # CPU
        if res_map.get("cpu") is not None:
            val = min(max(0.0, float(res_map["cpu"])), 100.0)
            update_values["cpu"] = val
            clickhouse_metrics["cpu"] = val
            alert_id = check_and_create_alert(server_id, "hardware", "cpu", val)
            if alert_id: alert_ids.append(alert_id)
            
        # Memory
        mem_used = res_map.get("memory_used")
        mem_total = res_map.get("memory_total")
        mem_pct = None
        
        if mem_used is not None and mem_total is not None and mem_total > 0:
            mem_pct = (float(mem_used) / float(mem_total)) * 100
            update_values["memory"] = mem_pct
            clickhouse_metrics["memory"] = mem_pct
            clickhouse_metrics["memory_total_bytes"] = mem_total
            clickhouse_metrics["memory_used_bytes"] = mem_used
        elif res_map.get("memory") is not None:
            val = float(res_map["memory"])
            # RDS HEURISTIC: If val > 100, it's likely Bytes (FreeableMemory)
            if val > 1000:
                # Assume 16GB total memory for these RDS instances if not specified
                # (FreeableMemory is Bytes, we want Used %)
                total_mem = 16 * (1024**3)
                used_mem = total_mem - val
                mem_pct = min(max(0.0, (used_mem / total_mem) * 100), 100.0)
            else:
                mem_pct = min(max(0.0, val), 100.0)
            
            update_values["memory"] = mem_pct
            clickhouse_metrics["memory"] = mem_pct
            clickhouse_metrics["memory_used_bytes"] = (mem_pct / 100) * 16 * (1024**3) if val > 1000 else None

        # Alert Check for Memory
        if mem_pct is not None:
            alert_id = check_and_create_alert(server_id, "hardware", "memory", mem_pct)
            if alert_id: alert_ids.append(alert_id)

        # Disk (Aggregated + Detailed)
        max_disk_util = None
        agg_disk_total = 0.0
        agg_disk_used = 0.0
        if res_map.get("partitions"):
            max_disk_util = 0.0
            for p in res_map["partitions"]:
                util = float(p['utilization'])
                total_gb = float(p['total_gb'])
                used_gb = float(p['used_gb'])
                
                # Standardize to bytes for consistent internal storage
                total_bytes = total_gb * (1024**3)
                used_bytes = used_gb * (1024**3)
                
                # ALERT LOGIC: Keep max_disk_util as the highest utilization found (LAMA API Sync compatible)
                max_disk_util = max(max_disk_util, util)
                
                # AUDIT LOGIC: Aggregate totals for the main graph
                agg_disk_total += total_bytes
                agg_disk_used += used_bytes
                
                p_name = p['name'].rstrip('/\\') or '/'
                # Store per-partition in Batch (History)
                batch_points.append({'metric': 'disk', 'value': util, 'interface': p_name, 'ts': now_ist})
                batch_points.append({'metric': 'disk_total_gb', 'value': total_gb, 'interface': p_name, 'ts': now_ist})
                batch_points.append({'metric': 'disk_used_gb', 'value': used_gb, 'interface': p_name, 'ts': now_ist})
                
                # WebSocket Payload (Real-time Sync)
                clickhouse_metrics[f"disk_partition_{p_name}"] = util
                clickhouse_metrics[f"disk_part_used_bytes_{p_name}"] = used_bytes
                clickhouse_metrics[f"disk_part_total_bytes_{p_name}"] = total_bytes
                
                # Alert Check for each Disk partition
                alert_id = check_and_create_alert_with_interface(server_id, "hardware", "disk", util, p_name)
                if alert_id: alert_ids.append(alert_id)
            
            update_values["disk"] = max_disk_util
            clickhouse_metrics["disk"] = max_disk_util
            clickhouse_metrics["disk_total_bytes"] = agg_disk_total
            clickhouse_metrics["disk_used_bytes"] = agg_disk_used
            # Aggregate percentage for display context
            clickhouse_metrics["disk_pct"] = (agg_disk_used / agg_disk_total * 100) if agg_disk_total > 0 else 0
        elif res_map.get("disk") is not None:
            val = float(res_map["disk"])
            # RDS HEURISTIC: If val > 100, it's likely Bytes (FreeStorageSpace)
            if val > 1000:
                # Assume 100GB total disk for these RDS instances if not specified
                # (FreeStorageSpace is Bytes, we want Used %)
                total_disk = 100 * (1024**3)
                used_disk = total_disk - val
                max_disk_util = min(max(0.0, (used_disk / total_disk) * 100), 100.0)
            else:
                max_disk_util = min(max(0.0, val), 100.0)
            
            update_values["disk"] = max_disk_util
            clickhouse_metrics["disk"] = max_disk_util
            # Alert Check for Disk without interface
            alert_id = check_and_create_alert(server_id, "hardware", "disk", max_disk_util)
            if alert_id: alert_ids.append(alert_id)

        # Network (Aggregated + Detailed)
        max_net_util = None
        total_throughput = 0.0
        has_network_data = False
        
        if res_map.get("interfaces"):
            max_net_util = 0.0
            total_throughput = 0.0
            max_link_speed = 0.0
            has_network_data = True
            for iface in res_map["interfaces"]:
                if any(x in iface['name'].lower() for x in ['loopback', 'lo0', 'tunnel', 'docker', 'veth']): continue
                util = float(iface['utilization'])
                throughput = float(iface['throughput_bps'])
                speed = float(iface.get('speed_bps', 0.0))
                
                # SUM of all physical/active interfaces for total server throughput
                total_throughput += throughput
                
                # MAX of all interfaces for utilization % and speed capacity
                if util > max_net_util:
                    max_net_util = util
                if speed > max_link_speed:
                    max_link_speed = speed
                
                # ... rest of interface storage code ...
                
                # Store per-interface in Batch (IST)
                iface_name = iface['name']
                batch_points.append({
                    'metric': 'network_bandwidth', 
                    'value': util, 
                    'interface': iface_name, 
                    'ts': now_ist
                })
                # SYNC FIX: Also store throughput per interface so it shows in details page
                batch_points.append({
                    'metric': 'network_bits_per_sec', 
                    'value': throughput, 
                    'interface': iface_name, 
                    'ts': now_ist
                })
                
                clickhouse_metrics[f"network_bandwidth_{iface_name}"] = util
                clickhouse_metrics[f"network_bits_per_sec_{iface_name}"] = throughput
                
                # Alert Check for each Network interface
                alert_id = check_and_create_alert_with_interface(server_id, "network", "bandwidth", util, iface_name)
                if alert_id: alert_ids.append(alert_id)

            update_values["network_bandwidth"] = max_net_util
            # Add network_bits_per_sec to update_values for real-time status updates (card on server page)
            # SYNC FIX: Also include in update_values so it goes to Hot-Store status
            update_values["network_bits_per_sec"] = total_throughput
            update_values["network_speed"] = max_link_speed
            
            clickhouse_metrics["network_bandwidth"] = max_net_util
            clickhouse_metrics["network_bits_per_sec"] = total_throughput
            clickhouse_metrics["network_speed"] = max_link_speed
        elif res_map.get("network_throughput") is not None:
            # Fallback if no details
            val = float(res_map["network_throughput"])
            total_throughput = val
            # COMPLIANCE: Do not update network_bandwidth if it was None (prevents 0.0)
            clickhouse_metrics["network_bits_per_sec"] = val
            update_values["network_bits_per_sec"] = val
            has_network_data = True

        # Uptime
        if res_map.get("uptime") is not None:
            val = float(res_map["uptime"])
            update_values["uptime"] = val
            clickhouse_metrics["uptime"] = val
            # Alert check for Uptime (Low is Bad)
            alert_id = check_and_create_alert(server_id, "hardware", "uptime", val)
            if alert_id: alert_ids.append(alert_id)

        if res_map.get("packet_count") is not None:
            val = float(res_map["packet_count"])
            update_values["packet_count"] = val
            clickhouse_metrics["packet_count"] = val
            # Alert check for Packet Count
            alert_id = check_and_create_alert(server_id, "network", "packetCount", val)
            if alert_id: alert_ids.append(alert_id)

        if res_map.get("network_latency") is not None:
            val = float(res_map["network_latency"]) * 1000 # Convert Seconds to ms
            # update_values["network_latency"] # Not in model usually
            # Alert check for Network Latency
            alert_id = check_and_create_alert(server_id, "network", "latency", val)
            if alert_id: alert_ids.append(alert_id)

        # Application Metrics (only for prometheus_app sources — ECS app metrics come from application_scheduler via CloudWatch)
        if metric_source == 'prometheus_app':
            if res_map.get("throughput") is not None:
                update_values["throughput"] = float(res_map["throughput"])
                clickhouse_metrics["throughput"] = float(res_map["throughput"])
            if res_map.get("latency") is not None:
                update_values["latency"] = float(res_map["latency"])
                clickhouse_metrics["latency"] = float(res_map["latency"])
            if res_map.get("failureTradeApi") is not None:
                update_values["failureTradeApi"] = float(res_map["failureTradeApi"])
                clickhouse_metrics["failureTradeApi"] = float(res_map["failureTradeApi"])
            if res_map.get("failureAuthentication") is not None:
                update_values["failureAuthentication"] = float(res_map["failureAuthentication"])
                clickhouse_metrics["failureAuthentication"] = float(res_map["failureAuthentication"])

        # Store Batch (triggers WebSocket with metrics type)
        if clickhouse_metrics:
            await loop.run_in_executor(None, store_metrics_batch, server_id, clickhouse_metrics, True)
            
        # Store Raw Batch (Partitions/Interfaces)
        if batch_points:
            await loop.run_in_executor(None, store_raw_batch, server_id, batch_points, False)

        # Update server_status in Postgres - FINAL CONSOLIDATED UPDATE
        await loop.run_in_executor(None, self_update_status, server_id, update_values)
        
        for alert_id in alert_ids:
            await loop.run_in_executor(None, send_alert, alert_id)
            
    except Exception as e:
        logger.warning(f"Error collecting for {server_name}: {e}")

def self_update_status(server_id, values):
    """Sync DB helper - Optimized to reduce Postgres Write Pressure"""
    try:
        from app.routes.metrics import get_redis_client
        redis = get_redis_client()
        
        # 1. ALWAYS Update Redis (Hot Store) for real-time UI
        redis_values = {k: str(v) for k, v in values.items() if k not in ['last_seen', 'updated_at']}
        if 'last_seen' in values:
            ts = values['last_seen']
            if hasattr(ts, 'isoformat'): redis_values['last_seen'] = ts.isoformat()
        
        update_hot_store_server_status(server_id, redis_values)
        
        # 2. DECIDE if we should sync to PostgreSQL (30s throttling)
        should_sync = values.get("status") == "offline"
        
        if not should_sync and redis:
            last_sync_key = f"server:last_db_sync:{server_id}"
            last_sync = redis.get(last_sync_key)
            now = datetime.now()
            
            if not last_sync:
                should_sync = True
            else:
                try:
                    val = last_sync.decode() if isinstance(last_sync, bytes) else last_sync
                    last_sync_dt = datetime.fromisoformat(val)
                    if (now - last_sync_dt).total_seconds() >= 30:
                        should_sync = True
                except:
                    should_sync = True
            
            if should_sync:
                redis.set(last_sync_key, now.isoformat())
        elif not redis:
            should_sync = True

        if should_sync:
            # logger.info(f"Syncing resource {server_id} metrics to Postgres: {values}")
            with engine.begin() as conn:
                if server_id >= 20000:
                    # Database Table
                    real_db_id = server_id - 20000
                    # Map generic metrics to DB table columns
                    db_values = {k: v for k, v in values.items() if k in ['status', 'last_seen', 'updated_at', 'cpu', 'memory', 'disk']}
                    if 'memory' in values: db_values['connections'] = int(values['memory'] / 1000000) # Simple bytes to count proxy
                    stmt = update(database_status_table).where(database_status_table.c.id == real_db_id).values(**db_values)
                    conn.execute(stmt)
                elif server_id >= 10000:
                    # Application Table
                    real_app_id = server_id - 10000
                    app_values = {k: v for k, v in values.items() if k in ['status', 'last_seen', 'updated_at', 'cpu', 'memory', 'uptime_seconds']}
                    # Map special app metrics
                    if 'latency' in values: app_values['latency_ms'] = values['latency']
                    if 'throughput' in values: app_values['throughput'] = values['throughput']
                    if 'failureTradeApi' in values: app_values['failure_trade_api'] = values['failureTradeApi']
                    if 'failureAuthentication' in values: app_values['failure_authentication'] = values['failureAuthentication']
                    stmt = update(application_status_table).where(application_status_table.c.id == real_app_id).values(**app_values)
                    conn.execute(stmt)
                else:
                    # Server Table - Filter values to match existing columns in server_status_table
                    server_cols = [c.name for c in server_status_table.columns]
                    filtered_values = {k: v for k, v in values.items() if k in server_cols}
                    stmt = update(server_status_table).where(server_status_table.c.id == server_id).values(**filtered_values)
                    conn.execute(stmt)
                
    except Exception as e:
        logger.error(f"DB update failed for server {server_id}: {e}")

def collect_prom_metrics(env: str = None):
    """Main scheduler entry point"""
    from app.utils.scheduler_logger import log_scheduler_start, log_scheduler_end
    import time
    start_time = time.time()
    try:
        log_scheduler_start("Prometheus Metrics Collection", "all")
        
        # Reload sources to pick up any new ones added to DB
        lgtm_provider.reload_sources()
        
        with engine.connect() as conn:
            where_sql = "(COALESCE(less.metric_source, 'auto') IN ('onprem', 'aws', 'auto') AND (less.enabled = true OR less.enabled IS NULL))"
            if env:
                where_sql += f" AND s.environment = '{env}'"
                
            query = text(f"""
                SELECT s.id, s.name, s.ip, s.environment, COALESCE(less.metric_source, 'auto'), s.os_type, s.os_name, s.external_id, s.location_id
                FROM server_status s
                LEFT JOIN lama_exchange_server_selection less ON s.id = less.server_id
                WHERE {where_sql}
            """)
            servers = conn.execute(query).fetchall()
            
            # PROFESSIONAL ARCHITECTURE: Fetch Applications and Databases from segregated tables
            # Join with metric_sources to get the actual source type (e.g., 'prometheus_app', 'ecs')
            q_apps = text("""
                SELECT a.id, a.name, COALESCE(a.ip, 'aws.amazon.com') as ip, a.environment, 
                       COALESCE(ms.type, 'aws') as metric_source, 'ECS' as os_type, 'Fargate' as os_name, 
                       a.external_id, a.location_id 
                FROM application_status a
                LEFT JOIN metric_sources ms ON a.source_id = ms.id
                WHERE a.status != 'deleted'
            """)
            q_dbs = text("""
                SELECT d.id, d.name, 'aws.amazon.com' as ip, d.environment, 
                       'aws' as metric_source, 'Database' as os_type, d.engine as os_name, 
                       d.external_id, d.location_id, d.source_id
                FROM database_status d
                WHERE d.status = 'online'
            """)
            
            apps = conn.execute(q_apps).fetchall()
            dbs = conn.execute(q_dbs).fetchall()
            
            # Normalize IDs to prevent collisions in the collector logic (using offsets)
            # Apps: +10000, Databases: +20000
            all_targets = list(servers)
            for a in apps:
                m = a._mapping
                all_targets.append((10000 + m['id'], m['name'], m['ip'], m['environment'], m['metric_source'], 'ECS', 'Fargate', m['external_id'], m['location_id']))
            for d in dbs:
                m = d._mapping
                all_targets.append((20000 + m['id'], m['name'], m['ip'], m['environment'], 'aws', 'Database', m['os_name'], m['external_id'], m['location_id'], m.get('source_id')))

            if all_targets:
                logger.info(f"Starting parallel collection for {len(all_targets)} resources ({len(servers)} servers, {len(apps)} apps, {len(dbs)} databases)")
                asyncio.run(process_all_servers_async(all_targets))
            else:
                logger.warning("No resources found for Prometheus/CloudWatch collection")
        log_scheduler_end("Prometheus Metrics Collection", "all", int((time.time() - start_time) * 1000))
    except Exception as e:
        logger.error(f"Collector error: {e}")


