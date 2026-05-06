# api/backend/app/schedulers/hardware.py
"""
Scheduled tasks to send metrics to LAMA Exchange every 5 minutes
Aggregates metrics from the last 5 minutes (min, max, avg, med) before sending
Integrates DC/DR physical servers, EC2 instances, and ECS Fargate
"""

import logging
import time
import asyncio
import random
from datetime import datetime, timedelta, timezone
from sqlalchemy import select, text
from app.db.db import engine
from app.utils.lama_exchange import (
    is_exchange_enabled,
    get_exchange_credentials,
    get_enabled_exchanges,
)
from app.utils.lama_token_cache import get_lama_exchange_token
from app.utils.lama_exchange_api import (
    send_metrics_to_lama_exchange,
    get_next_sequence_id,
    can_send_to_exchange,
    update_sequence_cache_after_704,
)
from app.utils.scheduler_logger import (
    log_scheduler_start,
    log_scheduler_end,
    log_metrics_sent,
    log_scheduler_event,
    log_704_retry,
    log_704_retry_result
)
from app.utils.lama_exchange_constants import APPLICATION_ID_EXCHANGE_CONNECTIVITY
from app.utils.nse_timestamp import get_nse_timestamp_ms

from app.collectors.mimir_collector import MimirCollector

logger = logging.getLogger(__name__)
from .common import *

def hardware_scheduler(environment: str = None, exchange_id: int = None):
    metric_type = "hardware"
    scheduler_name = "Hardware-Scheduler"
    if not environment:
        import os
        environment = os.getenv("ACTIVE_ENVIRONMENT", "uat").lower()
    else:
        environment = environment.lower()
    
    log_scheduler_start(scheduler_name, environment)
    env_start = time.time()
    
    try:
        if not is_exchange_enabled(environment):
            return

        _src = get_source_config(environment)

        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        with engine.connect() as conn:
            query = text("""
                SELECT s.id, s.name, s.ip, s.environment, s.cpu, s.memory, s.disk, s.os_type, s.location_id, s.external_id
                FROM server_status s
                INNER JOIN lama_exchange_server_selection less ON s.id = less.server_id AND s.environment = less.environment
                WHERE s.environment = :env 
                AND less.enabled = TRUE
                AND s.ip NOT IN ('aws', 'aws-ecs')
                AND (s.location_id != 3 OR s.last_seen >= (NOW() - INTERVAL '24 hours'))
                ORDER BY s.id
            """)
            env_servers = conn.execute(query, {"env": environment}).fetchall()

        async def fetch_server_metrics(s_data):
            s_id, s_name, s_ip, s_env, s_cpu, s_mem, s_disk, s_os, s_loc, s_ext_id = s_data
            raw = None
            try:
                target_mimir_url = None
                if s_loc in [1, 2]:
                    target_mimir_url = _src["onprem_prometheus"]
                elif s_loc == 3:
                    target_mimir_url = _src["cloud_mimir"]
                
                if target_mimir_url and s_ip and s_ip != "aws":
                    try:
                        local_mimir = MimirCollector(url=target_mimir_url)
                        lookup_key = s_name if s_os == 'ECS' else s_ip
                        raw = await asyncio.wait_for(local_mimir.collect_ec2_metrics(lookup_key, os_type=s_os), timeout=45.0)
                        await local_mimir.close()
                    except: pass

                if not raw:
                    zero = {"min": 0.0, "max": 0.0, "avg": 0.0, "med": 0.0, "points": [], "datasource": f"{target_mimir_url}-Zero"}
                    raw = {"cpu": zero, "memory": zero, "disk": zero, "uptime": zero}
                return (s_data, raw)
            except:
                return (s_data, None)

        async def fetch_all():
            return await asyncio.gather(*[fetch_server_metrics(s) for s in env_servers], return_exceptions=True)
        
        execution_results = loop.run_until_complete(fetch_all())

        metrics_by_location = {} 
        loc_servers = {}
        
        def init_loc(loc):
            if loc not in metrics_by_location:
                metrics_by_location[loc] = {"cpu": [], "memory": [], "disk": [], "uptime": []}
                loc_servers[loc] = []

        for item in execution_results:
            if not isinstance(item, tuple): continue
            s_data, raw = item
            if not raw: continue
            
            s_id, s_name, s_ip, s_env, s_cpu, s_mem, s_disk, s_os, s_loc, s_ext_id = s_data
            init_loc(s_loc)
            loc_servers[s_loc].append(s_name)
            
            server_ip_for_log = s_ip
            if s_loc == 3 and s_ext_id:
                server_ip_for_log = s_ext_id
            
            try:
                from app.utils.hot_store import update_server_hot_data
                update_server_hot_data(s_id, {
                    "cpu": raw.get("cpu", {}).get("avg", 0),
                    "memory": raw.get("memory", {}).get("avg", 0),
                    "disk": raw.get("disk", {}).get("avg", 0),
                    "status": "online",
                    "last_seen": datetime.utcnow().isoformat()
                }, category="hardware")
            except: pass

            # Write to ClickHouse for historical charts
            try:
                from app.utils.metrics_calculator import store_metric_value
                for k in ["cpu", "memory", "disk", "uptime"]:
                    avg_val = raw.get(k, {}).get("avg", 0)
                    if avg_val: store_metric_value(s_id, k, float(avg_val))
            except: pass

            # Check thresholds and trigger alerts
            try:
                from app.utils.alert_checker import check_and_create_alert
                for k in ["cpu", "memory", "disk", "uptime"]:
                    avg_val = raw.get(k, {}).get("avg", 0)
                    if avg_val: check_and_create_alert(s_id, "hardware", k, float(avg_val))
            except: pass

            for k in ["cpu", "memory", "disk", "uptime"]:
                if raw.get(k):
                    m = raw[k]
                    metrics_by_location[s_loc][k].append({
                        "min": round(float(m["min"]), 2), "max": round(float(m["max"]), 2), "avg": round(float(m["avg"]), 2), "med": round(float(m["med"]), 2),
                        "points": m.get("points", []),
                        "datasource": m.get("datasource") or raw.get("datasource", "Unknown"),
                        "name": k, "server_name": s_name, "server_ip": server_ip_for_log, "resource_category": "hardware"
                    })

        creds = get_exchange_credentials(environment)
        if not creds: return
        member_id = creds.get("member_id")
        enabled_exchanges = [exchange_id] if exchange_id else get_enabled_exchanges(environment)

        for loc_id, loc_raw_data in metrics_by_location.items():
            loc_final_metrics = []
            for key in ["cpu", "memory", "disk", "uptime"]:
                res = aggregate_worst_case(key, loc_raw_data.get(key, []))
                if res: loc_final_metrics.append(res)
            
            if not loc_final_metrics: continue

            loc_staging_id = stage_raw_metrics(
                environment=environment,
                metric_type=metric_type,
                member_id=member_id,
                raw_snapshot={"location_id": loc_id, "targets": loc_servers.get(loc_id, [])},
                source_meta={"location_id": loc_id},
                location_id=loc_id
            )
            
            if loc_staging_id:
                update_staged_results(
                    staging_id=loc_staging_id,
                    calculated_stats=loc_final_metrics,
                    individual_details=get_all_individual_metrics(loc_raw_data, category='hardware'),
                    status="calculated"
                )

            clean_metrics = []
            for m in loc_final_metrics:
                m_key = m.get("name")
                if m_key in PLAIN_VALUE_METRICS:
                    clean_metrics.append({"key": m_key, "value": int(m.get("value", 0))})
                else:
                    clean_metrics.append({
                        "key": m_key,
                        "value": {
                            "min": float(m.get("min", 0)), "max": float(m.get("max", 0)),
                            "avg": float(m.get("avg", 0)), "med": float(m.get("med", 0))
                        }
                    })
            
            batch_payload = [{"applicationId": -1, "metricData": clean_metrics}]

            for exch_id in enabled_exchanges:
                can_send, _ = can_send_to_exchange(environment, exch_id, metric_type, location_id=loc_id)
                if not can_send: continue

                token = get_lama_exchange_token(environment, exch_id, scheduler_name=scheduler_name)
                if not token: continue

                result = send_metrics_to_lama_exchange(
                    environment=environment, member_id=member_id, instance_id=f"loc_{loc_id}_hw", 
                    metrics=clean_metrics, auth_token=token, metric_type=metric_type, 
                    scheduler_name=scheduler_name, server_name=f"Combined-Hardware-{loc_id}",
                    server_ip="combined", exchange_id=exch_id, application_id=-1, 
                    sequence_id=None, sent_at=datetime.now(), 
                    nse_timestamp=get_nse_timestamp_ms(), skip_705_check=True, 
                    batched_payload=batch_payload,
                    stored_metrics=get_all_individual_metrics(loc_raw_data, category='hardware'),
                    location_id=loc_id
                )
                
                if result.get("success"): 
                    log_metrics_sent(scheduler_name, environment, exch_id, metric_type, len(loc_final_metrics))
                    if loc_staging_id: update_staged_results(loc_staging_id, loc_final_metrics, None, status="success")

        log_scheduler_end(scheduler_name, environment, int((time.time() - env_start) * 1000))

    except Exception as e:
        logger.error(f"[{scheduler_name}] Global error: {e}", exc_info=True)
