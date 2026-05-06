# api/backend/app/schedulers/network.py
"""
Scheduled tasks to send Network metrics to LAMA Exchange every 5 minutes
Handles Bandwidth, Latency, PacketCount, LookupCount
Integrates DC/DR physical servers with AWS Cloud Load Balancers
"""

import logging
import time
import asyncio
import statistics
from datetime import datetime, timezone
from sqlalchemy import text
from concurrent.futures import ThreadPoolExecutor, as_completed
from app.db.db import engine
from app.utils.lama_exchange import (
    is_exchange_enabled, get_exchange_credentials, get_enabled_exchanges
)
from app.utils.lama_token_cache import get_lama_exchange_token
from app.utils.lama_exchange_api import (
    log_calculated_metrics_only, send_metrics_to_lama_exchange, get_next_sequence_id, 
    can_send_to_exchange, update_sequence_cache_after_704
)
from app.utils.scheduler_logger import (
    log_scheduler_start, log_scheduler_end, log_metrics_sent, log_scheduler_event,
    log_704_retry, log_704_retry_result
)
from app.utils.lama_exchange_constants import APPLICATION_ID_EXCHANGE_CONNECTIVITY
from app.utils.nse_timestamp import get_nse_timestamp_ms

from app.aggregators.metric_mapper import MetricMapper
from .common import (
    create_metric_for_server, PLAIN_VALUE_METRICS, aggregate_worst_case,
    stage_raw_metrics, update_staged_results, get_source_config
)

logger = logging.getLogger(__name__)

def network_scheduler(environment: str = None, exchange_id: int = None):
    metric_type = "network"
    scheduler_name = "Network-Scheduler"

    if not environment:
        import os
        environment = os.getenv("ACTIVE_ENVIRONMENT", "uat").lower()
    else:
        environment = environment.lower()
    
    log_scheduler_start(scheduler_name, environment)

    try:
        if not is_exchange_enabled(environment):
            return

        # Fetch all selected servers
        with engine.connect() as conn:
            query = text("""
                SELECT s.id, s.name, s.ip, s.environment, s.os_type, s.location_id
                FROM server_status s
                INNER JOIN lama_exchange_server_selection less ON s.id = less.server_id AND s.environment = less.environment
                WHERE s.environment = :env AND less.enabled = TRUE
            """)
            servers = conn.execute(query, {"env": environment}).fetchall()

        servers_by_loc = {}
        for s in servers:
            loc = s[5] or 1
            if loc not in servers_by_loc: servers_by_loc[loc] = []
            servers_by_loc[loc].append(s)

        creds = get_exchange_credentials(environment)
        member_id = creds["member_id"] if creds else "unknown"
        
        _src = get_source_config(environment)
        
        locations_to_process = []

        # Process ALL locations (DC=1, DR=2, Cloud=3) — Prometheus/Mimir only
        for loc_id in [1, 2, 3]:
            env_servers = servers_by_loc.get(loc_id, [])
            promo_url = _src["cloud_mimir"] if loc_id == 3 else _src["onprem_prometheus"]
            
            all_raw = {"bandwidth": [], "latency": [], "packetCount": [], "lookupCount": []}

            def fetch_net_strict(s):
                sid, sname, sip, senv, sos, sloc = s
                res_list = []
                zero_obj = {"min": 0.0, "max": 0.0, "avg": 0.0, "med": 0.0, "points": [], "datasource": f"{promo_url}-Zero"}
                try:
                    m_bw = create_metric_for_server(sid, "bandwidth", 0, "bandwidth", server_ip=sip, os_type=sos, high_res=True, prometheus_url=promo_url)
                    if not m_bw or len(m_bw.get("points", [])) < 1: m_bw = {**zero_obj}
                    res_list.append(("bandwidth", {**m_bw, "server_id": sid, "server_name": sname, "server_ip": sip}))

                    m_lat = create_metric_for_server(sid, "networkLatency", 0, "network_latency", server_ip=sip, os_type=sos, high_res=True, prometheus_url=promo_url)
                    if not m_lat or len(m_lat.get("points", [])) < 1: m_lat = {**zero_obj}
                    res_list.append(("latency", {**m_lat, "server_id": sid, "server_name": sname, "server_ip": sip}))

                    m_pc = create_metric_for_server(sid, "packetCount", 0, "packet_count", server_ip=sip, os_type=sos, high_res=True, prometheus_url=promo_url)
                    if not m_pc or len(m_pc.get("points", [])) < 1: m_pc = {**zero_obj}
                    res_list.append(("packetCount", {**m_pc, "server_id": sid, "server_name": sname, "server_ip": sip}))

                    m_lc = create_metric_for_server(sid, "lookupCount", 0, "lookup_count", server_ip=sip, os_type=sos, high_res=True, prometheus_url=promo_url)
                    if not m_lc or len(m_lc.get("points", [])) < 1: m_lc = {**zero_obj}
                    res_list.append(("lookupCount", {**m_lc, "server_id": sid, "server_name": sname, "server_ip": sip}))

                    try:
                        from app.utils.metrics_calculator import store_metric_value
                        from app.utils.hot_store import update_server_hot_data
                        bw_val = float(m_bw.get("avg", 0))
                        pc_val = float(m_pc.get("avg", 0))
                        if bw_val: store_metric_value(sid, "network_bandwidth", bw_val)
                        store_metric_value(sid, "packet_count", pc_val)
                        update_server_hot_data(sid, {"network_bandwidth": bw_val, "packet_count": pc_val}, category="network")
                    except: pass

                    return sname, res_list
                except Exception as e:
                    logger.error(f"Error in strict network fetch for {sname}: {e}")
                    return sname, []

            if env_servers:
                with ThreadPoolExecutor(max_workers=5) as exe:
                    futures = {exe.submit(fetch_net_strict, s): s for s in env_servers}
                    for f in as_completed(futures):
                        _, results = f.result()
                        for cat, obj in results:
                            all_raw[cat].append(obj)

            final_metrics = []
            detailed_metrics = []
            for k in ["bandwidth", "latency", "packetCount", "lookupCount"]:
                res = aggregate_worst_case(k, all_raw.get(k, []))
                if not res: res = {"name": k, "avg": 0.0, "max": 0.0, "min": 0.0, "med": 0.0}
                final_metrics.append(res)
                for item in all_raw.get(k, []):
                    detailed_metrics.append(item)

            locations_to_process.append({
                "loc_id": loc_id,
                "metrics": final_metrics,
                "detailed": detailed_metrics,
                "name": f"PHYSICAL_LOC_{loc_id}_NETWORK"
            })

        # --- SUBMISSION LOOP (PER LOCATION) ---
        env_start = time.time()
        creds = get_exchange_credentials(environment)
        if not creds: return
        member_id = creds["member_id"]
        enabled_exchanges = [exchange_id] if exchange_id else get_enabled_exchanges(environment)
        sent_at = datetime.now()
        nse_ts = get_nse_timestamp_ms()

        for loc in locations_to_process:
            loc_id = loc["loc_id"]
            loc_metrics = loc["metrics"]
            loc_detailed = loc["detailed"]
            
            # 1. Stage this location's data
            loc_staging_id = stage_raw_metrics(
                environment=environment,
                metric_type=metric_type,
                member_id=member_id,
                raw_snapshot={"location_id": loc_id, "metrics": loc_detailed},
                source_meta={"location_id": loc_id, "name": loc["name"]},
                location_id=loc_id
            )
            
            if loc_staging_id:
                update_staged_results(
                    staging_id=loc_staging_id,
                    calculated_stats=loc_metrics,
                    individual_details=loc_detailed,
                    status="calculated"
                )

            # 2. Submit to all enabled exchanges
            # CRITICAL FIX (LAMA V1.3 Consistency):
            # Wrap network metrics in a batched_payload list with applicationId: -1
            clean_metrics = []
            for m in loc_metrics:
                m_key = m.get("name")
                if m_key in PLAIN_VALUE_METRICS:
                    clean_metrics.append({"key": m_key, "value": int(m.get("value", 0))})
                else:
                    clean_metrics.append({
                        "key": m_key,
                        "value": {
                            "min": float(m.get("min", 0)),
                            "max": float(m.get("max", 0)),
                            "avg": float(m.get("avg", 0)),
                            "med": float(m.get("med", 0))
                        }
                    })
            
            batch_payload = [{"applicationId": -1, "metricData": clean_metrics}]

            for eid in enabled_exchanges:
                can_send, _ = can_send_to_exchange(environment, eid, metric_type, location_id=loc_id)
                if not can_send: continue

                token = get_lama_exchange_token(environment, eid, scheduler_name=scheduler_name)
                if not token: continue

                result = send_metrics_to_lama_exchange(
                    environment, member_id, f"loc_{loc_id}_net", clean_metrics, token, metric_type, 
                    scheduler_name, f"Combined-{loc['name']}", "combined", eid, -1, None, sent_at, nse_ts, 
                    skip_705_check=True, batched_payload=batch_payload,
                    stored_metrics=loc_detailed, location_id=loc_id
                )

                if result.get("success"):
                    log_metrics_sent(scheduler_name, environment, eid, metric_type, len(loc_metrics))
                    if loc_staging_id: update_staged_results(loc_staging_id, loc_metrics, None, status="success")

        log_scheduler_end(scheduler_name, environment, int((time.time() - env_start) * 1000))

    except Exception as e:
        logger.error(f"Critical error in network_scheduler: {e}", exc_info=True)