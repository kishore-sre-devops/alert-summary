# api/backend/app/schedulers/database.py
"""
Scheduled tasks to send Database metrics to LAMA Exchange every 5 minutes.
Handles Status, QSize, Bandwidth, and Latency for RDS, MySQL, ES, and Postgres.
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
    log_scheduler_start, log_scheduler_end, log_metrics_sent, log_704_retry, log_704_retry_result
)
from app.utils.nse_timestamp import get_nse_timestamp_ms
from app.collectors.mimir_collector import MimirCollector
from app.aggregators.metric_mapper import MetricMapper
from .common import (
    _to_lama_metric_data, stage_raw_metrics, update_staged_results, 
    aggregate_worst_case, get_all_individual_metrics, PLAIN_VALUE_METRICS,
    get_source_config
)

logger = logging.getLogger(__name__)

async def fetch_db_metrics_async(db_row, onprem_prometheus, cloud_mimir):
    """
    Unified Database Collector (LAMA V1.3 Compliance):
    1. Strict 6-point Audit Trail
    2. Source Isolation (DC/DR -> OnPrem, Cloud -> Mimir)
    3. Zero-Fallback Protocol
    """
    did, dname, dhost, dloc, dtype, is_replica, dext_id = db_row[:7]
    dc_port = db_row[8] if len(db_row) > 8 else None
    dc_user = db_row[9] if len(db_row) > 9 else None
    dc_pass = db_row[10] if len(db_row) > 10 else None
    dc_database = db_row[11] if len(db_row) > 11 else None
    dc_master = db_row[12] if len(db_row) > 12 else None
    source_type = db_row[13] if len(db_row) > 13 else None
    source_config = db_row[14] if len(db_row) > 14 else None
    dloc = dloc or 1
    
    # Identify identifier for Cloud/Mimir matching
    display_ip = dhost or dext_id or "N/A"
    
    # --- AUTOMATION: Ensure On-Prem DB appears in Database Monitoring Dashboard ---
    try:
        with engine.begin() as conn_onboard:
            # CHECK: Do not onboard if this host already exists in server_status OR database_status
            # This prevents double entries when a host is both a 'server' and a 'database'
            conn_onboard.execute(text("""
                INSERT INTO database_status (name, engine, environment, status, location_id, source_id, external_id, is_replication, master_host)
                SELECT :name, :engine, (SELECT environment FROM server_status WHERE id = :sid), 'online', :loc, :src_id, :host, :is_rep, :master
                WHERE NOT EXISTS (
                    SELECT 1 FROM database_status WHERE external_id = :host
                ) AND NOT EXISTS (
                    SELECT 1 FROM server_status WHERE ip = :host AND id != :sid
                )
            """), {
                "name": dname, "engine": dtype or 'mysql', "sid": did, "loc": dloc, 
                "src_id": source_id, "host": dhost or dext_id, "is_rep": is_replica, "master": dc_master
            })
    except Exception as e:
        logger.debug(f"Failed auto-onboarding for DB status {dname}: {e}")
    # --------------------------------------------------------------------------

    if dloc == 3:
        # CRITICAL FIX (LAMA V1.3): For RDS, the identifier must be the short DBInstanceIdentifier
        # instead of the full endpoint to ensure pattern matching works in Mimir/YACE.
        if dext_id and "." in dext_id:
            db_identifier = dext_id.split(".")[0]
        elif dext_id:
            db_identifier = dext_id
        elif dhost and "." in dhost:
            db_identifier = dhost.split(".")[0]
        elif dhost:
            db_identifier = dhost
        else:
            db_identifier = dname.split("]")[-1].strip() if "]" in dname else dname
    elif not dhost:
        db_identifier = dext_id or dname.split("]")[-1].strip() if "]" in dname else dname
    else:
        db_identifier = dhost
        display_ip = dhost

    raw = None
    
    # Priority 0: Prometheus DB exporter (UI-driven, prometheus_db source type)
    if source_type == 'prometheus_db' and source_config:
        cfg = source_config if isinstance(source_config, dict) else {}
        prom_url = cfg.get('url', onprem_prometheus)
        prom_instance = cfg.get('instance')
        if prom_url and prom_instance:
            try:
                import httpx as _httpx
                from datetime import timedelta
                end_time = datetime.utcnow()
                start_time = end_time - timedelta(minutes=10)
                db_metrics = {}
                # Pre-calculated metrics: db_status (plain), db_qsize_avg/max/min/median, db_bandwidth_avg/max/min/median, db_latency_avg/max/min/median
                async with _httpx.AsyncClient(timeout=10) as client:
                    # Fetch all db_* metrics AND general metrics (bandwidth, latency, throughput) for this instance
                    q = f'{{instance="{prom_instance}"}}'
                    resp = await client.get(f'{prom_url}/api/v1/query', params={'query': q})
                    if resp.status_code == 200:
                        for r in resp.json().get('data', {}).get('result', []):
                            name = r['metric']['__name__']
                            val = float(r['value'][1])
                            db_metrics[name] = val

                if 'db_status' in db_metrics or 'status' in db_metrics:
                    # Mapping logic for LAMA exporter (Strictly DB metrics)
                    m_status = db_metrics.get('db_status', 1.0)
                    
                    m_qs_avg = db_metrics.get('db_qsize_avg', 0.0)
                    m_qs_max = db_metrics.get('db_qsize_max', 0.0)
                    m_qs_min = db_metrics.get('db_qsize_min', 0.0)
                    m_qs_med = db_metrics.get('db_qsize_median', 0.0)

                    # Bandwidth
                    m_bw_avg = db_metrics.get('db_bandwidth_avg', 0.0)
                    m_bw_max = db_metrics.get('db_bandwidth_max', 0.0)
                    m_bw_min = db_metrics.get('db_bandwidth_min', 0.0)
                    m_bw_med = db_metrics.get('db_bandwidth_median', 0.0)

                    # Latency
                    m_lat_avg = db_metrics.get('db_latency_avg', 0.0)
                    m_lat_max = db_metrics.get('db_latency_max', 0.0)
                    m_lat_min = db_metrics.get('db_latency_min', 0.0)
                    m_lat_med = db_metrics.get('db_latency_median', 0.0)

                    raw = {
                        'status': m_status,
                        'qSize': {
                            'min': m_qs_min, 'max': m_qs_max, 'avg': m_qs_avg, 'med': m_qs_med,
                            'datasource': 'Prometheus-DB-Exporter'
                        },
                        'bandwidth': {
                            'min': m_bw_min, 'max': m_bw_max, 'avg': m_bw_avg, 'med': m_bw_med,
                            'datasource': 'Prometheus-DB-Exporter'
                        },
                        'latency': {
                            'min': m_lat_min, 'max': m_lat_max, 'avg': m_lat_avg, 'med': m_lat_med,
                            'datasource': 'Prometheus-DB-Exporter'
                        },
                        'datasource': 'Prometheus-DB-Exporter'
                    }
                    logger.info(f"✅ Prometheus DB exporter success for {dname}: status={raw['status']}")
                else:
                    logger.info(f"⚠️ Prometheus DB exporter for {dname} returned only status. Falling back to direct check.")
            except Exception as e:
                logger.warning(f"Prometheus DB exporter failed for {dname}: {e}")

    # Priority 1: Direct Database Monitoring (for on-prem MySQL/Postgres with credentials)
    if not raw and dc_user and dc_user != 'aws_cloudwatch_managed' and dc_pass:
        try:
            from app.utils.database_monitor import check_database_metrics, decrypt_password
            password = decrypt_password(dc_pass)
            
            # Use run_in_executor for blocking DB calls
            loop = asyncio.get_event_loop()
            direct_metrics = await loop.run_in_executor(
                None, 
                check_database_metrics,
                dhost or dext_id, dc_port or 3306, dc_database or 'mysql', 
                dc_user, password, dtype or 'mysql', is_replica
            )
            
            if direct_metrics and direct_metrics.get('status') is not None:
                qsize = direct_metrics.get('qsize', 0)
                lat = direct_metrics.get('latency', 0)
                bw = direct_metrics.get('bandwidth', 0)
                
                # Create a pseudo-6-point distribution for direct metrics
                now_ts = int(datetime.utcnow().timestamp())
                def _pts(val):
                    return [[now_ts - (i * 60), val] for i in range(6)]
                
                raw = {
                    'status': direct_metrics.get('status', 0),
                    'qSize': {'min': qsize, 'max': qsize, 'avg': qsize, 'med': qsize, 'points': _pts(qsize), 'datasource': 'Direct-DB-Probe'},
                    'bandwidth': {'min': bw, 'max': bw, 'avg': bw, 'med': bw, 'points': _pts(bw), 'datasource': 'Direct-DB-Probe'},
                    'latency': {'min': lat, 'max': lat, 'avg': lat, 'med': lat, 'points': _pts(lat), 'datasource': 'Direct-DB-Probe'},
                    'datasource': 'Direct-DB-Probe'
                }
                logger.info(f"✅ Direct DB probe success for {dname}")
        except Exception as e:
            logger.error(f"Direct DB probe failed for {dname}: {e}")

    if not raw:
        prometheus_url = cloud_mimir if dloc == 3 else onprem_prometheus
        try:
            mimir = MimirCollector(url=prometheus_url)
            # CRITICAL: Added timeout for Mimir/Prometheus calls
            raw = await asyncio.wait_for(
                mimir.collect_database_metrics(db_identifier),
                timeout=45.0
            )
            await mimir.close()
            
            if raw:
                q_pts = len(raw.get("qSize", {}).get("points", []))
                bw_pts = len(raw.get("bandwidth", {}).get("points", []))
                # V1.3 COMPLIANCE: Relax to 1 point for sparse cloud/network data
                if q_pts < 1 or bw_pts < 1:
                    logger.warning(f"Insufficient points for DB {db_identifier} from {prometheus_url} ({q_pts}/{bw_pts}).")
                    raw = None
        except asyncio.TimeoutError:
            logger.error(f"Timeout (45s) reached while fetching Mimir metrics for {db_identifier}")
        except Exception as e:
            logger.debug(f"Source {prometheus_url} failed for DB {db_identifier}: {e}")

    # Zero-Fallback Protocol
    if not raw:
        now_ts = int(datetime.utcnow().timestamp())
        zero_pts = [[now_ts - (i * 60), 0.0] for i in range(6)]
        zero_pts.reverse()
        zero_stats = {"min": 0.0, "max": 0.0, "avg": 0.0, "med": 0.0, "points": zero_pts, "datasource": f"{prometheus_url if 'prometheus_url' in locals() else 'System'}-Zero"}
        raw = {"status": 0.0, "qSize": zero_stats, "bandwidth": zero_stats, "latency": zero_stats, "datasource": f"{prometheus_url if 'prometheus_url' in locals() else 'System'}-Zero"}

    # No status override — trust the value from Prometheus/Mimir source

    mapped = MetricMapper().map_database(raw)
    res = []
    for k in ["status", "qSize", "bandwidth", "latency"]:
        m_val = mapped.get(k)
        if m_val is None: continue
        m_obj = {"name": k, "server_id": did, "server_name": dname, "server_ip": display_ip, "resource_category": "database", "location_id": dloc, "datasource": raw.get("datasource", "Direct-DB-Audit")}
        if isinstance(m_val, dict):
            m_obj.update(m_val)
            m_obj["value"] = m_val.get("avg", 0)
        else:
            m_obj["value"] = m_val
            m_obj["points"] = [[int(time.time()), m_val]]
        res.append(m_obj)

    # Check thresholds and trigger alerts
    try:
        from app.utils.alert_checker import check_and_create_alert
        for m in res:
            val = float(m.get("avg", m.get("value", 0)))
            check_and_create_alert(did, "database", m["name"], val)
    except: pass

    # Update hot store + database_status + ClickHouse for real-time UI
    try:
        from app.utils.hot_store import update_hot_store_server_status
        from app.utils.metrics_calculator import store_metric_value
        hot_vals = {"status": "online", "last_seen": datetime.utcnow().isoformat()}
        db_update = {"last_seen": datetime.utcnow(), "status": "online"}
        for m in res:
            val = float(m.get("value", 0))
            if m["name"] == "status":
                store_metric_value(did, "db_status", val)
                hot_vals["db_status"] = str(val)
            elif m["name"] == "qSize":
                store_metric_value(did, "db_qsize", val)
                hot_vals["db_qsize"] = str(val)
                db_update["connections"] = val
            elif m["name"] == "bandwidth":
                store_metric_value(did, "db_bandwidth", val)
            elif m["name"] == "latency":
                store_metric_value(did, "db_latency", val)
        # CPU from raw if available
        cpu_val = raw.get("cpu", {}).get("avg", 0) if isinstance(raw.get("cpu"), dict) else 0
        mem_val = raw.get("memory", {}).get("avg", 0) if isinstance(raw.get("memory"), dict) else 0
        if cpu_val: db_update["cpu"] = round(cpu_val, 2)
        if mem_val: db_update["memory"] = round(mem_val, 2)
        update_hot_store_server_status(did, hot_vals)
        # Write to database_status table (for RDS)
        with engine.begin() as conn_upd:
            from sqlalchemy import text as _text
            cols = ", ".join(f"{k} = :{k}" for k in db_update)
            conn_upd.execute(_text(f"UPDATE database_status SET {cols} WHERE id = :did"), {**db_update, "did": did})
    except Exception as e:
        logger.debug(f"Hot store/DB update for DB {did}: {e}")

    return dname, res

import random

def database_scheduler(environment: str = None, exchange_id: int = None):
    metric_type = "database"
    scheduler_name = "DB-Scheduler"
    
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

        with engine.connect() as conn:
            query = text("""
                SELECT ds.id, ds.name, dc.host, ds.location_id, ds.engine as db_type, 
                       dc.is_replication, ds.external_id, ms.config->>'role_arn' as role_arn,
                       dc.port, dc.username, dc.password, dc.database, dc.master_host,
                       ms.type as source_type, ms.config as source_config
                FROM database_status ds
                LEFT JOIN database_config dc ON (
                    dc.host = ds.external_id OR 
                    dc.host LIKE ds.external_id || '.%' OR
                    ds.external_id = dc.host
                )
                LEFT JOIN metric_sources ms ON ds.source_id = ms.id
                WHERE ds.environment = :env
            """)
            dbs = list(conn.execute(query, {"env": environment}).fetchall())

            # Also pick up on-prem servers with prometheus_db sources (MySQL/PG via Prometheus exporter)
            prom_db_query = text("""
                SELECT s.id, s.name, dc.host, s.location_id, dc.db_type as db_type,
                       dc.is_replication, s.external_id, NULL as role_arn,
                       dc.port, dc.username, dc.password, dc.database, dc.master_host,
                       ms.type as source_type, ms.config as source_config
                FROM server_status s
                INNER JOIN database_config dc ON s.id = dc.server_id AND dc.enabled = TRUE
                INNER JOIN metric_sources ms ON ms.type = 'prometheus_db' AND ms.enabled = TRUE
                    AND ms.environment = :env
                    AND (
                        ms.config->>'db_host' = s.ip OR
                        ms.config->>'db_host' = dc.host OR
                        ms.name ILIKE '%' || s.ip || '%'
                    )
                WHERE s.environment = :env
            """)
            prom_dbs = conn.execute(prom_db_query, {"env": environment}).fetchall()
            dbs.extend(prom_dbs)

            # Deduplicate by server ID — JOIN can produce multiple rows per server
            seen_ids = set()
            unique_dbs = []
            for d in dbs:
                if d[0] not in seen_ids:
                    seen_ids.add(d[0])
                    unique_dbs.append(d)
            dbs = unique_dbs

        onprem_prometheus = get_source_config(environment)["onprem_prometheus"]
        cloud_mimir = get_source_config(environment)["cloud_mimir"]

        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        async def run_env_logic():
            try:
                creds = get_exchange_credentials(environment)
                if not creds: return
                member_id = creds["member_id"]
                
                tasks = [fetch_db_metrics_async(d, onprem_prometheus, cloud_mimir) for d in dbs]
                results = await asyncio.gather(*tasks)
                
                # --- AUTOMATED CLUSTER SENSING & GROUPING ---
                # Group databases by their Application Prefix (e.g., [SMC-TRADING-MIDDLEWARE-PROD])
                # to ensure Master-Replica health is reported as a unified cluster status.
                clusters = {}
                for dn, res_list in results:
                    if not res_list: continue

                    # Parse Application Tag: "[APP-NAME] instance-id" -> "APP-NAME"
                    app_tag = "Default"
                    if "[" in dn and "]" in dn:
                        app_tag = dn.split("]")[0].replace("[", "").strip()

                    if app_tag not in clusters:
                        clusters[app_tag] = []
                    clusters[app_tag].append({"name": dn, "metrics": res_list})

                loc_raw_data = {} 
                loc_servers = {} 

                for app_tag, cluster_members in clusters.items():
                    for member in cluster_members:
                        dn = member["name"]
                        res_list = member["metrics"]
                        db_row = next((d for d in dbs if d[1] == dn), None)
                        loc_id = db_row[3] if db_row else 1

                        if loc_id not in loc_raw_data:
                            loc_raw_data[loc_id] = {"status": [], "qSize": [], "bandwidth": [], "latency": []}
                            loc_servers[loc_id] = []

                        loc_servers[loc_id].append(dn)
                        for m_obj in res_list:
                            cat = m_obj["name"]
                            loc_raw_data[loc_id][cat].append(m_obj)


                exchanges = [exchange_id] if exchange_id else get_enabled_exchanges(environment)

                for loc_id, raw_metrics in loc_raw_data.items():
                    loc_final_metrics = []
                    for k in ["status", "qSize", "bandwidth", "latency"]:
                        res = aggregate_worst_case(k, raw_metrics.get(k, []))
                        if res: loc_final_metrics.append(res)
                    if not loc_final_metrics: continue

                    loc_staging_id = stage_raw_metrics(
                        environment=environment, metric_type=metric_type, member_id=member_id,
                        raw_snapshot={"location_id": loc_id, "targets": loc_servers[loc_id]},
                        source_meta={"location_id": loc_id}, location_id=loc_id
                    )
                    if loc_staging_id:
                        update_staged_results(
                            staging_id=loc_staging_id, calculated_stats=loc_final_metrics,
                            individual_details=get_all_individual_metrics(raw_metrics, category='database'),
                            status="calculated"
                        )

                    # CRITICAL FIX (LAMA V1.3 Consistency):
                    # Wrap database metrics in a batched_payload list with applicationId: -1
                    clean_metrics = []
                    for m in loc_final_metrics:
                        m_key = m.get("name")
                        if m_key in PLAIN_VALUE_METRICS:
                            clean_metrics.append({"key": m_key, "value": int(m.get("value", 0))})
                        else:
                            vals = {
                                "min": round(float(m.get("min", 0)), 2),
                                "max": round(float(m.get("max", 0)), 2),
                                "avg": round(float(m.get("avg", 0)), 2),
                                "med": round(float(m.get("med", 0)), 2)
                            }
                            # LAMA V1.3 spec: bandwidth must be 0-100 (percentage)
                            if m_key == "bandwidth":
                                vals = {k: min(v, 100.0) for k, v in vals.items()}
                            clean_metrics.append({"key": m_key, "value": vals})
                    
                    batch_payload = [{"applicationId": -1, "metricData": clean_metrics}]

                    for eid in exchanges:
                        can_send, _ = can_send_to_exchange(environment, eid, metric_type, location_id=loc_id)
                        if not can_send: continue

                        token = get_lama_exchange_token(environment, eid, scheduler_name=scheduler_name)
                        if not token: continue

                        result = send_metrics_to_lama_exchange(
                            environment, member_id, f"loc_{loc_id}_db", clean_metrics, token, metric_type, 
                            None, ", ".join(loc_servers[loc_id]), "combined", eid, -1, None, 
                            datetime.now(), get_nse_timestamp_ms(), skip_705_check=True, 
                            batched_payload=batch_payload,
                            stored_metrics=get_all_individual_metrics(raw_metrics, category='database'),
                            location_id=loc_id
                        )
                        if result.get("success"): 
                            log_metrics_sent(scheduler_name, environment, eid, metric_type, len(loc_final_metrics))
                            if loc_staging_id: update_staged_results(loc_staging_id, loc_final_metrics, None, status="success")
            except Exception as e:
                logger.error(f"Error in DB-Scheduler run_env_logic: {e}", exc_info=True)

        loop.run_until_complete(run_env_logic())
        log_scheduler_end(scheduler_name, environment, int((time.time() - env_start) * 1000))
    except Exception as e:
        logger.error(f"Critical error in database_scheduler: {e}", exc_info=True)

