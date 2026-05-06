# api/backend/app/schedulers/application.py
"""
Scheduled tasks to send Application metrics to LAMA Exchange every 5 minutes.
Handles Throughput, Latency, and Failures for ECS and Generic sources.
"""

import logging
import time
import asyncio
import statistics
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Dict, Any
from sqlalchemy import text
from app.db.db import engine
from app.utils.lama_exchange import (
    is_exchange_enabled, get_exchange_credentials, get_enabled_exchanges
)
from app.utils.lama_token_cache import get_lama_exchange_token
from app.utils.lama_exchange_api import (
    send_metrics_to_lama_exchange, get_next_sequence_id, 
    can_send_to_exchange, update_sequence_cache_after_704
)
from app.utils.scheduler_logger import (
    log_scheduler_start, log_scheduler_end, log_metrics_sent,
    log_704_retry, log_704_retry_result
)
from app.utils.nse_timestamp import get_nse_timestamp_ms
from app.collectors.mimir_collector import MimirCollector
from app.collectors.es_collector import ESCollector, _is_index_available, _zeros as es_zeros
from app.collectors.prometheus_collector import PrometheusCollector
from app.utils.aes_encryption import decrypt_password
from app.aggregators.metric_mapper import MetricMapper
from app.lama.sequence_manager import SequenceManager
from .common import (
    _to_lama_metric_data, stage_raw_metrics, update_staged_results
)

logger = logging.getLogger(__name__)

async def collect_application_metrics(environment: str) -> list:
    """
    Refactored Application Collector (LAMA V1.3 Compliance):
    1. Dynamic Discovery from DB
    2. Strict 6-point Audit Trail
    3. Source Isolation (DC/DR -> OnPrem, Cloud -> Mimir)
    4. Zero-Fallback Protocol
    """
    results = []
    mapper = MetricMapper()
    seq_mgr = SequenceManager()
    
    from app.schedulers.common import get_source_config
    _src = get_source_config(environment)
    onprem_prometheus = _src["onprem_prometheus"]
    cloud_mimir = _src["cloud_mimir"]

    try:
        with engine.connect() as conn:
            # 1. Fetch all enabled Application/ECS sources
            query = text("""
                SELECT ms.id, ms.name, ms.type, ms.config, ms.location_id
                FROM metric_sources ms
                WHERE ms.enabled = TRUE AND ms.environment = :env
                AND (ms.type = 'ecs' OR ms.type IN ('elasticsearch', 'mysql', 'postgresql', 'prometheus_app'))
            """)
            sources = conn.execute(query, {"env": environment}).fetchall()

            # 1b. Fetch all configured queries for ES/SQL sources
            queries_query = text("""
                SELECT source_id, metric_name, query_payload, index_name 
                FROM metric_queries 
                WHERE enabled = TRUE
            """)
            all_queries = conn.execute(queries_query).fetchall()
            queries_by_source = {}
            for q in all_queries:
                sid = q[0]
                if sid not in queries_by_source:
                    queries_by_source[sid] = []
                queries_by_source[sid].append(q)

            for src in sources:
                ms_id, ms_name, ms_type, config, loc_id = src
                loc_id = loc_id or 1
                service_name = config.get("service") or ms_name
                app_id = seq_mgr.get_next_application_id(service_name, environment=environment)

                # --- AUTOMATION: AUTO-ONBOARD TO DASHBOARD ---
                # Ensure this source exists in application_status so it shows in Application Monitoring UI
                try:
                    with engine.begin() as onboard_conn:
                        onboard_conn.execute(text("""
                            INSERT INTO application_status (name, environment, status, location_id, source_id)
                            SELECT :name, :env, 'online', :loc, :sid
                            WHERE NOT EXISTS (
                                SELECT 1 FROM application_status WHERE name = :name AND environment = :env
                            )
                        """), {"name": service_name, "env": environment, "loc": loc_id, "sid": ms_id})
                    # Refresh app_id after onboarding
                    if app_id <= 0:
                        app_id = seq_mgr.get_next_application_id(service_name, environment=environment)
                    if app_id > 0:
                        logger.info(f"✨ Ensured {service_name} exists in Application Monitoring (app_id={app_id}).")
                except Exception as e:
                    logger.error(f"Failed auto-onboarding for {service_name}: {e}")
                # ----------------------------------------------

                # V1.3 FIX: Ensure Odiin-Trading-Logs and other apps are ALWAYS enabled for exchange submission
                # and Resource Breakdown by defaulting to enabled=True for all direct application sources.
                send_to_exchange = config.get("send_application_metrics", True)
                if not send_to_exchange:
                    logger.info(f"⏭️ Skipping {ms_name} - explicitly disabled in config.")
                    continue

                # STRICT SOURCE MAPPING
                prometheus_url = cloud_mimir if loc_id == 3 else onprem_prometheus
                
                raw = None
                
                # Priority 0: Prometheus (LAMA Exporter)
                if ms_type == 'prometheus_app':
                    try:
                        p_url = config.get("url") or prometheus_url
                        instance = config.get("instance") or "localhost:8000"
                        prom = PrometheusCollector(url=p_url)
                        raw = await prom.collect_lama_app_metrics(instance=instance)
                        await prom.close()
                    except Exception as e:
                        logger.error(f"Prometheus LAMA collection failed for {ms_name}: {e}")

                # Priority 1: Elasticsearch (Native Audit - Pick & Pass)
                if not raw and ms_type == 'elasticsearch':
                    try:
                        available, current_index = _is_index_available()
                        if not available:
                            logger.info(f"ES index not available for {ms_name} (before 5 AM IST)")
                            raw = es_zeros()
                        else:
                            host = config.get("host")
                            port = config.get("port", 9200)
                            username = config.get("username")
                            enc_password = config.get("password")
                            password = decrypt_password(enc_password) if enc_password else None
                            
                            es = ESCollector(es_url=f"http://{host}:{port}", username=username, password=password)
                            src_queries = queries_by_source.get(ms_id, [])
                            
                            if not src_queries:
                                logger.warning(f"No queries configured for ES source {ms_name} (ID: {ms_id})")
                                raw = es_zeros()
                            else:
                                raw = es_zeros()
                                raw["data_available"] = True
                                import pytz
                                ist = pytz.timezone('Asia/Kolkata')
                                today_str = datetime.now(ist).strftime('%Y.%m.%d')
                                
                                for q in src_queries:
                                    m_name = q[1]
                                    q_payload = q[2].replace("{DATE}", today_str)
                                    q_index = (q[3] or current_index).replace("{DATE}", today_str)
                                    
                                    res = await es.collect_metric(q_index, m_name, q_payload)
                                    if res:
                                        m_name_lower = m_name.lower()
                                        if m_name_lower in ["throughput", "latency", "historicalthroughput", "historicallatency"]:
                                            # Normalize key to camelCase standard expected by mapper
                                            norm_key = "throughput" if m_name_lower == "throughput" else \
                                                      "latency" if m_name_lower == "latency" else \
                                                      "historicalThroughput" if m_name_lower == "historicalthroughput" else \
                                                      "historicalLatency"
                                            raw[norm_key] = res
                                        elif m_name_lower == "failuretradeapi":
                                            raw["failureTradeApi"] = res.get("value", 0)
                                        elif m_name_lower == "failureauthentication":
                                            raw["failureAuthentication"] = res.get("value", 0)
                                logger.info(f"Successfully collected ES metrics for {ms_name} from {host}")
                    except Exception as e:
                        logger.error(f"ES collection failed for {ms_name}: {e}")
                        raw = es_zeros()
                # =========================================================================

                # Priority 1: Mimir/Prometheus (Source Isolation)
                if not raw:
                    try:
                        # V1.3 FIX: Ensure onprem_prometheus is used for all loc_id=1 sources
                        target_url = config.get("url") or (cloud_mimir if loc_id == 3 else onprem_prometheus)
                        mimir = MimirCollector(url=target_url)
                        raw = await mimir.collect_application_metrics(service_name)
                        await mimir.close()
                        
                        # Validation: Check for points (Compliance Check)
                        if raw:
                            tp_pts = len(raw.get("throughput", {}).get("points", []))
                            if tp_pts < 1:
                                raw = None
                    except Exception as e:
                        target_url = config.get("url") or (cloud_mimir if loc_id == 3 else onprem_prometheus)
                        logger.debug(f"Source {target_url} failed for {service_name}: {e}")

                # Zero-Fallback Protocol: Report 0.0 if still no raw points found
                if not raw:
                    # ZERO-FILING: Provide 6 zero points for audit compliance
                    now_ts = int(datetime.utcnow().timestamp())
                    zero_pts = [[now_ts - (i * 60), 0.0] for i in range(6)]
                    zero_pts.reverse()
                    
                    target_url = config.get("url") or (cloud_mimir if loc_id == 3 else onprem_prometheus)
                    zero_stats = {
                        "min": 0.0, "max": 0.0, "avg": 0.0, "med": 0.0, 
                        "points": zero_pts, 
                        "datasource": f"{target_url}-Zero"
                    }
                    raw = {
                        "throughput": zero_stats,
                        "latency": zero_stats,
                        "historicalThroughput": zero_stats,
                        "historicalLatency": zero_stats,
                        "failureTradeApi": 0,
                        "failureAuthentication": 0,
                        "datasource": f"{target_url}-Zero"
                    }

                mapped = mapper.map_application(raw)
                res_id = f"loc{loc_id}:{service_name}"

                # Update application_status.last_seen so dashboard knows this app is alive
                try:
                    # Extract avg values for dashboard display
                    tp_val = raw.get('throughput', {})
                    lat_val = raw.get('latency', {})
                    tp_avg = tp_val.get('avg', 0) if isinstance(tp_val, dict) else float(tp_val or 0)
                    lat_avg = lat_val.get('avg', 0) if isinstance(lat_val, dict) else float(lat_val or 0)
                    ft_val = float(raw.get('failureTradeApi', 0))
                    fa_val = float(raw.get('failureAuthentication', 0))

                    with engine.begin() as upd_conn:
                        upd_conn.execute(text("""
                            UPDATE application_status 
                            SET last_seen = NOW(), status = 'online',
                                throughput = :tp, latency_ms = :lat,
                                failure_trade_api = :ft, failure_authentication = :fa
                            WHERE name = :name AND environment = :env
                        """), {"name": service_name, "env": environment,
                               "tp": tp_avg, "lat": lat_avg, "ft": ft_val, "fa": fa_val})

                    # Update Redis hot store for real-time dashboard (offset ID: 10000 + app_status_id)
                    from app.utils.hot_store import update_hot_store_server_status
                    with engine.connect() as id_conn:
                        row = id_conn.execute(text(
                            "SELECT id FROM application_status WHERE name = :name AND environment = :env"
                        ), {"name": service_name, "env": environment}).fetchone()
                    if row:
                        hot_id = 10000 + row[0]
                        update_hot_store_server_status(hot_id, {
                            "throughput": str(tp_avg), "latency": str(lat_avg),
                            "failureTradeApi": str(ft_val), "failureAuthentication": str(fa_val),
                            "status": "online", "last_seen": datetime.now().isoformat()
                        })

                        # Write to ClickHouse for Performance Metrics charts
                        try:
                            from app.utils.metrics_calculator import store_metrics_batch
                            store_metrics_batch(row[0], {
                                "app_throughput": tp_avg,
                                "app_latency": lat_avg,
                                "app_failure_trade_api": ft_val,
                                "app_failure_authentication": fa_val,
                            }, update_hot_store=False)
                        except Exception as ch_err:
                            logger.debug(f"ClickHouse write for {service_name}: {ch_err}")

                        # Check thresholds and trigger alerts (Slack/Email/Android)
                        try:
                            from app.utils.alert_checker import check_and_create_alert
                            check_and_create_alert(row[0], "application", "throughput", tp_avg)
                            check_and_create_alert(row[0], "application", "latency", lat_avg)
                            check_and_create_alert(row[0], "application", "failureTradeApi", ft_val)
                            check_and_create_alert(row[0], "application", "failureAuthentication", fa_val)
                        except Exception as alert_err:
                            logger.debug(f"Alert check for {service_name}: {alert_err}")
                except Exception as e:
                    logger.debug(f"Failed to update status for {service_name}: {e}")
                
                results.append({
                    "applicationId": app_id if app_id > 0 else 1,
                    "metricData": _to_lama_metric_data(mapped),
                    "serviceName": service_name,
                    "server_ip": res_id,
                    "resource_id": f"app:{ms_type}:{service_name}",
                    "source_id": ms_id,
                    "location_id": loc_id,
                    "muted": not config.get("send_application_metrics", True),
                    "data_available": True
                })
    except Exception as e:
        logger.error(f"Critical error in dynamic app discovery: {e}")

    return results

def aggregate_application_fleet(payload_list: List[dict]) -> dict:
    """
    Aggregates metrics across all enabled services into a single 'worst-case' fleet-wide metric set.
    """
    enabled_payloads = [p for p in payload_list if not p.get("muted", False)]
    
    if not enabled_payloads:
        return [
            {"key": "throughput", "value": {"min": 0.0, "max": 0.0, "avg": 0.0, "med": 0.0}},
            {"key": "latency", "value": {"min": 0.0, "max": 0.0, "avg": 0.0, "med": 0.0}},
            {"key": "historicalThroughput", "value": {"min": 0.0, "max": 0.0, "avg": 0.0, "med": 0.0}},
            {"key": "historicalLatency", "value": {"min": 0.0, "max": 0.0, "avg": 0.0, "med": 0.0}},
            {"key": "failureTradeApi", "value": 0},
            {"key": "failureAuthentication", "value": 0}
        ]

    # =========================================================================
    # CRITICAL: DO NOT TOUCH - APPLICATION METRIC AGGREGATION & HISTORICAL KEYS
    # This logic is mandatory for LAMA V1.3 Compliance.
    # 1. historicalThroughput/historicalLatency MUST be included in stats_metrics.
    # 2. Case-insensitive mapping (Normalized to camelCase) is mandatory for ES.
    # =========================================================================
    stats_metrics = ["throughput", "latency", "historicalThroughput", "historicalLatency"]
    plain_metrics = ["failureTradeApi", "failureAuthentication"]
    # =========================================================================
    
    raw_stats = {m: {"mins": [], "maxs": [], "avgs": [], "sources": []} for m in stats_metrics}
    raw_plain = {m: {"total": 0, "max_val": -1, "source": "N/A", "ds": "Unknown"} for m in plain_metrics}

    for svc in enabled_payloads:
        s_name = svc.get("serviceName", "Unknown")
        s_ip = svc.get("server_ip", "Unknown")
        
        for metric in svc.get("metricData", []):
            key = metric.get("key")
            val = metric.get("value")
            
            if key in stats_metrics:
                if isinstance(val, dict):
                    v_min = float(val.get("min", 0))
                    v_max = float(val.get("max", 0))
                    v_avg = float(val.get("avg", 0))
                    v_ds = val.get("datasource", "Unknown")
                else:
                    v_min = v_max = v_avg = float(val or 0)
                    v_ds = metric.get("datasource", "Unknown")

                raw_stats[key]["mins"].append(v_min)
                raw_stats[key]["maxs"].append(v_max)
                raw_stats[key]["avgs"].append(v_avg)
                raw_stats[key]["sources"].append({"peak": v_max, "name": s_name, "ip": s_ip, "ds": v_ds})
            elif key in plain_metrics:
                try:
                    v = int(val or 0)
                    raw_plain[key]["total"] += v
                    if v > raw_plain[key]["max_val"]:
                        raw_plain[key]["max_val"] = v
                        raw_plain[key]["source"] = f"{s_name} ({s_ip})"
                        raw_plain[key]["ds"] = metric.get("datasource", "Unknown")
                except: pass

    aggregated_metric_data = []
    for m_key, data in raw_stats.items():
        if not data["avgs"]: continue
        worst = max(data["sources"], key=lambda x: x["peak"]) if data["sources"] else {"name": "N/A", "ip": "N/A", "ds": "Unknown"}
        aggregated_metric_data.append({
            "key": m_key,
            "value": {
                "min": round(min(data["mins"]), 2),
                "max": round(max(data["maxs"]), 2),
                "avg": round(sum(data["avgs"]) / len(data["avgs"]), 2),
                "med": round(statistics.median(data["avgs"]), 2)
            },
            "worst_case_source": f"{worst['name']} ({worst['ip']})",
            "datasource": worst["ds"]
        })
    
    for m_key, pdata in raw_plain.items():
        aggregated_metric_data.append({
            "key": m_key, 
            "value": pdata["total"],
            "max_value": pdata["max_val"],
            "worst_case_source": pdata["source"],
            "datasource": pdata["ds"]
        })
    return aggregated_metric_data

def application_scheduler(environment: str = None):
    metric_type = "application"
    scheduler_name = "Application-Scheduler"
    
    if not environment:
        import os
        environment = os.getenv("ACTIVE_ENVIRONMENT", "uat").lower()
    else:
        environment = environment.lower()
    
    log_scheduler_start(scheduler_name, environment)
    start_time = time.time()
    
    try:
        if not is_exchange_enabled(environment):
            return

        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
        results = loop.run_until_complete(collect_application_metrics(environment))
        payload_list = results if results else []
        
        creds = get_exchange_credentials(environment)
        if not creds: return
        member_id = creds["member_id"]
        exchanges = get_enabled_exchanges(environment)

        # Group by location for V1.3 Compliance
        loc_payloads = {}
        for p in payload_list:
            lid = p.get("location_id") or 1
            if lid not in loc_payloads: loc_payloads[lid] = []
            loc_payloads[lid].append(p)

        # --- SUBMISSION LOOP (PER LOCATION) ---
        for loc_id, payloads in loc_payloads.items():
            metrics_for_log = []
            for svc in payloads:
                svc_name = svc["serviceName"]
                server_ip = svc.get("server_ip", "combined")
                for m in svc["metricData"]:
                    m_key = m["key"]
                    m_val = m["value"]
                    m_row = {
                        "name": m_key, "key": m_key, "value": m_val, 
                        "server_name": svc_name, "server_ip": server_ip, 
                        "applicationId": svc["applicationId"], 
                        "resource_category": "application"
                    }
                    if isinstance(m_val, dict):
                        m_row.update(m_val)
                        m_row["value"] = m_val.get("avg", 0)
                        m_row["points"] = m_val.get("points", [])
                        m_row["datasource"] = m_val.get("datasource", "Unknown")
                    else:
                        # Plain value metrics (failures, counts): inherit datasource from sibling stats metric
                        sibling_ds = "Unknown"
                        for sm in svc["metricData"]:
                            sv = sm.get("value")
                            if isinstance(sv, dict) and sv.get("datasource"):
                                sibling_ds = sv["datasource"]
                                break
                        m_row["datasource"] = sibling_ds
                    metrics_for_log.append(m_row)

            loc_fleet_metrics = aggregate_application_fleet(payloads)
            if not loc_fleet_metrics: continue

            loc_staging_id = stage_raw_metrics(
                environment=environment,
                metric_type=metric_type,
                member_id=member_id,
                raw_snapshot={"location_id": loc_id, "targets": [p["serviceName"] for p in payloads]},
                source_meta={"location_id": loc_id},
                location_id=loc_id
            )
            
            if loc_staging_id:
                update_staged_results(
                    staging_id=loc_staging_id, 
                    calculated_stats=loc_fleet_metrics, 
                    individual_details=metrics_for_log, 
                    status="calculated"
                )

            clean_metrics = [{"key": m["key"], "value": m["value"]} for m in loc_fleet_metrics]
            final_payload = [{"applicationId": -1, "metricData": clean_metrics}]

            for exch_id in exchanges:
                can_send, _ = can_send_to_exchange(environment, exch_id, metric_type, location_id=loc_id)
                if not can_send: continue

                token = get_lama_exchange_token(environment, exch_id, scheduler_name=scheduler_name)
                if not token: continue

                result = send_metrics_to_lama_exchange(
                    environment=environment, member_id=member_id, instance_id=f"loc_{loc_id}_fleet", 
                    metrics=clean_metrics, auth_token=token, metric_type=metric_type, 
                    scheduler_name=scheduler_name, server_name=f"Combined-Apps-{loc_id}", 
                    server_ip="combined", exchange_id=exch_id, application_id=-1, 
                    sequence_id=None, sent_at=datetime.now(),
                    nse_timestamp=get_nse_timestamp_ms(), skip_705_check=True, 
                    batched_payload=final_payload, stored_metrics=metrics_for_log, location_id=loc_id
                )
                
                if result.get("success"): 
                    log_metrics_sent(scheduler_name, environment, exch_id, metric_type, len(payloads))
                    if loc_staging_id: update_staged_results(loc_staging_id, loc_fleet_metrics, None, status="success")

        log_scheduler_end(scheduler_name, environment, int((time.time() - start_time) * 1000))
    except Exception as e:
        logger.error(f"Critical error in application_scheduler: {e}", exc_info=True)
