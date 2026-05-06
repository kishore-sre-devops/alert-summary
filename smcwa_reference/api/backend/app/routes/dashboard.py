from fastapi import APIRouter, HTTPException, Depends, Request, Query
from sqlalchemy import text, select, update
from sqlalchemy.orm import Session
from pydantic import BaseModel
from app.db.db import engine, get_db, exchange_transactions_table, metric_sources_table
from app.utils.hot_store import get_all_servers_hot_data
from app.utils.environment import get_active_environment
from datetime import datetime, timedelta
import math
import logging
from typing import Optional

logger = logging.getLogger(__name__)
router = APIRouter()

@router.get("/summary")
def get_summary(environment: str = Depends(get_active_environment)):
    """Combined summary for all entities using server_status, application_status, and database_status"""
    try:
        threshold = datetime.utcnow() - timedelta(minutes=10)
        env = environment
        
        with engine.connect() as conn:
            query = text("""
                WITH combined_heartbeats AS (
                    SELECT last_seen FROM server_status s WHERE s.environment = :env
                    UNION ALL
                    SELECT last_seen FROM application_status a WHERE a.environment = :env
                    UNION ALL
                    SELECT last_seen FROM database_status d WHERE d.environment = :env
                )
                SELECT 
                    COUNT(*) as total,
                    COUNT(*) FILTER (
                        WHERE last_seen IS NOT NULL AND last_seen > :threshold
                    ) as online_count
                FROM combined_heartbeats
            """)
            result = conn.execute(query, {"env": env, "threshold": threshold}).fetchone()
            
            total = result[0] if result else 0
            online = result[1] if result else 0
            return {
                "total": total,
                "online": online,
                "offline": (total - online)
            }
    except Exception as e:
        logger.error(f"Error in get_summary: {e}")
        return {"total": 0, "online": 0, "offline": 0}

@router.get("/raw-metrics-trace")
def get_raw_metrics_trace(
    metric_type: Optional[str] = Query(None, description="Filter by hardware, network, database, application"),
    environment: str = Depends(get_active_environment),
    db: Session = Depends(get_db)
):
    """
    Fetches the latest cycle of metrics containing the 5-point raw trace and datasource info.
    Used for the Raw Metrics Dashboard / QA Verification.
    """
    try:
        with engine.connect() as conn:
            # OPTIMIZATION: Only query the specific metric type if requested
            base_query = """
                SELECT DISTINCT ON (metric_type)
                    id, metric_type, metrics_sent, sent_at
                FROM exchange_transactions
                WHERE environment = :env
                  AND status = 'success'
                  AND metrics_sent IS NOT NULL
                  AND (metrics_sent->'original_metrics') IS NOT NULL
            """
            
            params = {"env": environment}
            if metric_type:
                base_query += " AND metric_type = :m_type "
                params["m_type"] = metric_type.lower()
            
            base_query += " ORDER BY metric_type, sent_at DESC"
            
            rows = conn.execute(text(base_query), params).fetchall()
            
            trace_data = []
            # Updated, comprehensive lists
            hardware_metrics = ['cpu', 'memory', 'disk', 'uptime']
            network_metrics = ['bandwidth', 'packetcount', 'lookupcount', 'latency', 'packetloss']
            database_metrics = ['status', 'qsize', 'latency', 'bandwidth']
            application_metrics = ['throughput', 'latency', 'failuretradeapi', 'failureauthentication', 'historicalthroughput', 'historicallatency']
            
            # IMPROVED QUERY: Show latest trace per Server/Metric, not just one per type
            base_query = """
                WITH latest_tx AS (
                    SELECT id, metric_type, metrics_sent, sent_at
                    FROM (
                        SELECT id, metric_type, metrics_sent, sent_at,
                               ROW_NUMBER() OVER (PARTITION BY metric_type ORDER BY sent_at DESC) as rank
                        FROM exchange_transactions
                        WHERE environment = :env
                          AND status = 'success'
                          AND metrics_sent IS NOT NULL
                          AND (metrics_sent->'original_metrics') IS NOT NULL
                    ) sub
                    WHERE rank <= 5  -- Get last 5 cycles to ensure we see all servers
                )
                SELECT id, metric_type, metrics_sent, sent_at FROM latest_tx
                ORDER BY metric_type, sent_at DESC
            """
            
            params = {"env": environment}
            rows = conn.execute(text(base_query), params).fetchall()
            
            seen_entries = set() # To avoid duplicates
            
            for row in rows:
                m_type = row[1]
                metrics_sent = row[2]
                sent_at = row[3]
                
                original_metrics = metrics_sent.get("original_metrics", [])
                
                # Check if it's a list of individual metrics OR a list of services (containing metrics)
                for item in original_metrics:
                    # Case A: item is an individual metric object (e.g. from Hardware/Network)
                    # Case B: item is a service object (e.g. from older Application transactions)
                    
                    if not isinstance(item, dict): continue
                    
                    # Try to extract metrics from the item
                    metrics_to_process = []
                    
                    # If it has a 'name' or 'key' and a 'value', it's Case A
                    if ("name" in item or "key" in item) and ("value" in item or "avg" in item):
                        metrics_to_process.append(item)
                    else:
                        # Case B: It's a service dictionary, metrics are inside keys
                        for k, v in item.items():
                            if k.lower() in application_metrics + hardware_metrics + network_metrics + database_metrics:
                                # Wrap it like Case A for uniform processing
                                metrics_to_process.append({
                                    **item, # keep service name/ip
                                    "name": k,
                                    "value": v,
                                    "from_service_dict": True
                                })
                
                    for m in metrics_to_process:
                        m_name_raw = m.get("name") or m.get("key") or ""
                        metric_name = m_name_raw.lower()
                        
                        # HARD ENFORCEMENT: Only show metrics belonging to the specific transaction category
                        is_valid = False
                        if m_type == 'hardware' and metric_name in hardware_metrics: is_valid = True
                        if m_type == 'network' and metric_name in network_metrics: is_valid = True
                        if m_type == 'database' and metric_name in database_metrics: is_valid = True
                        if m_type == 'application' and metric_name in application_metrics: is_valid = True
                        
                        if not is_valid: continue
                        
                        # If user requested a specific tab, strictly enforce it
                        if metric_type:
                            if metric_type.lower() != m_type: continue
                        
                        m_source = m.get("server_name") or m.get("serviceName") or "Unknown"
                        m_id = str(m.get("server_ip") or m.get("applicationId") or m.get("ip") or "Unknown")
                        
                        # Unique key for "Fleet View" deduplication
                        entry_key = f"{m_type}_{m_source}_{metric_name}"
                        if entry_key in seen_entries: continue
                        seen_entries.add(entry_key)
                        
                        # EXTRACT: Handle dictionary metrics vs long metrics
                        m_val = m.get("value")
                        m_ds = m.get("datasource")
                        
                        min_val = m.get("min")
                        max_val = m.get("max")
                        avg_val = m.get("avg")
                        med_val = m.get("med")
                        points = m.get("points", [])
                        
                        if isinstance(m_val, dict):
                            m_ds = m_val.get("datasource") or m_ds
                            min_val = m_val.get("min", min_val)
                            max_val = m_val.get("max", max_val)
                            avg_val = m_val.get("avg", avg_val)
                            med_val = m_val.get("med", med_val)
                            points = m_val.get("points", points)
                            m_val = avg_val or m_val.get("value", 0)
                        
                        trace_data.append({
                            "id": f"{row[0]}_{m_source}_{m_name_raw}",
                            "cycle_time": sent_at.isoformat(),
                            "metric_type": m_type,
                            "source": m_source,
                            "identifier": m_id,
                            "metric": m_name_raw,
                            "points": points,
                            "min": min_val,
                            "max": max_val,
                            "avg": avg_val,
                            "med": med_val,
                            "value": m_val,
                            "datasource": m_ds or "Unknown"
                        })
            
            return {
                "count": len(trace_data),
                "environment": environment,
                "data": trace_data
            }
    except Exception as e:
        logger.error(f"Error in get_raw_metrics_trace: {e}")
        return {"count": 0, "data": [], "error": str(e)}

@router.get("/data-sanity")
def get_data_sanity(
    environment: str = Depends(get_active_environment),
    exchange_id: Optional[int] = Query(None),
    metric_type: Optional[str] = Query(None),
    limit: int = Query(5),
    db: Session = Depends(get_db)
):
    """
    Fetches the last {limit} successful submissions per metric_type per exchange.
    Parses the metrics_sent JSON to extract the actual LAMA payload values.
    Used for the Data Sanity Dashboard / QA Verification.
    """
    try:
        # Helper for exchange names
        exchange_names = {1: "NSE", 2: "BSE", 4: "MCX", 5: "NCDEX"}
        
        with engine.connect() as conn:
            # Main query to get ranked submissions
            query = """
                SELECT 
                    metric_type, exchange_id, sequence_id, status_code, sent_at, metrics_sent
                FROM (
                    SELECT *,
                    ROW_NUMBER() OVER (
                        PARTITION BY metric_type, exchange_id 
                        ORDER BY sent_at DESC
                    ) as rn
                    FROM exchange_transactions
                    WHERE status_code = 601
                      AND environment = :env
            """
            
            params = {"env": environment, "limit": limit}
            
            if exchange_id:
                query += " AND exchange_id = :exch_id "
                params["exch_id"] = exchange_id
                
            if metric_type:
                query += " AND metric_type = :m_type "
                params["m_type"] = metric_type.lower()
                
            query += """
                ) ranked
                WHERE rn <= :limit
                ORDER BY metric_type, exchange_id, sent_at DESC
            """
            
            rows = conn.execute(text(query), params).fetchall()
            
            # Format results into the requested nested structure
            # result[metric_type][exchange_name] = [submissions]
            results = {
                "hardware": {},
                "network": {},
                "database": {},
                "application": {}
            }
            
            for row in rows:
                m_type = row[0]
                exch_id = row[1]
                seq_id = row[2]
                status_code = row[3]
                sent_at = row[4]
                metrics_sent = row[5]
                
                if m_type not in results:
                    results[m_type] = {}
                    
                exch_name = exchange_names.get(exch_id, f"Exch_{exch_id}")
                if exch_name not in results[m_type]:
                    results[m_type][exch_name] = []
                    
                # Parse metrics_sent to extract the LAMA payload
                records = []
                if isinstance(metrics_sent, dict):
                    payload_data = metrics_sent.get("lama_v1_2_payload", {}).get("payload", [])
                    for p in payload_data:
                        record = {
                            "applicationId": p.get("applicationId"),
                            "locationId": p.get("locationId", 1), # Default to 1 if missing
                            "metrics": {}
                        }
                        
                        # Extract metrics from metricData array
                        metric_data = p.get("metricData", [])
                        for m in metric_data:
                            key = m.get("key")
                            val = m.get("value")
                            record["metrics"][key] = val
                            
                        records.append(record)
                
                results[m_type][exch_name].append({
                    "sequence_id": seq_id,
                    "sent_at": sent_at.strftime("%Y-%m-%d %H:%M:%S"),
                    "status_code": status_code,
                    "records": records
                })
                
            return results

    except Exception as e:
        logger.error(f"Error in get_data_sanity: {e}")
        return {"error": str(e)}

@router.get("/data-sanity/export")
def export_data_sanity(
    environment: str = Depends(get_active_environment),
    db: Session = Depends(get_db)
):
    """
    Generates a CSV export of the last 5 submissions per type/exchange.
    """
    try:
        from fastapi.responses import StreamingResponse
        import io
        import csv
        
        # Reuse existing logic to get data
        data = get_data_sanity(environment=environment, limit=5, db=db)
        
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Headers
        writer.writerow(["Sequence ID", "Exchange", "Sent At", "Status", "applicationId", "locationId", "Key", "Min", "Max", "Avg", "Med"])
        
        for m_type in data:
            if m_type == "error": continue
            for exch in data[m_type]:
                for sub in data[m_type][exch]:
                    for rec in sub["records"]:
                        for key, val in rec["metrics"].items():
                            row = [
                                sub["sequence_id"],
                                exch,
                                sub["sent_at"],
                                sub["status_code"],
                                rec["applicationId"],
                                rec["locationId"],
                                key
                            ]
                            if isinstance(val, dict):
                                row.extend([val.get("min"), val.get("max"), val.get("avg"), val.get("med")])
                            else:
                                row.extend([val, val, val, val])
                            writer.writerow(row)
        
        output.seek(0)
        return StreamingResponse(
            io.BytesIO(output.getvalue().encode()),
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename=LAMA_Data_Sanity_{environment}.csv"}
        )
    except Exception as e:
        logger.error(f"Error in export_data_sanity: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/database-monitoring")
def get_database_monitoring(
    environment: str = Depends(get_active_environment), 
    page: int = Query(1), 
    size: int = Query(20)
):
    """Database monitoring real-time status"""
    try:
        with engine.connect() as conn:
            # 1. Get legacy on-prem servers that have database configurations
            query = text("""
                SELECT DISTINCT
                    s.id, s.name, s.ip, s.environment,
                    to_char(s.last_seen, 'YYYY-MM-DD HH24:MI:SS') as last_seen,
                    dc.is_replication, dc.master_host, dc.host
                FROM server_status s
                INNER JOIN database_config dc ON s.id = dc.server_id
                WHERE dc.enabled = TRUE
                    AND s.environment = :environment
                ORDER BY s.name
            """)
            params = {"environment": environment}
            result = conn.execute(query, params)
            rows = result.fetchall()
            
            servers = []
            
            # 2. Also fetch from the new database_status table
            q_rds = text("""
                SELECT id, name, environment, status, to_char(last_seen, 'YYYY-MM-DD HH24:MI:SS') as last_seen, engine, cpu, memory, connections, external_id, is_replication, master_host
                FROM database_status
                WHERE environment = :environment
            """)
            rds_rows = conn.execute(q_rds, params).fetchall()
            
            # Combine all IDs for hot data fetch
            server_ids = [r[0] for r in rows]
            rds_ids = [20000 + r[0] for r in rds_rows]
            hot_data_map = get_all_servers_hot_data(server_ids + rds_ids) if (server_ids + rds_ids) else {}
            
            # Process Legacy Servers
            for r in rows:
                sid, name, ip, env, ls_str, is_rep, m_host, d_host = r
                hot_data = hot_data_map.get(sid, {})
                db_status = float(hot_data.get('db_status', 0.0))
                
                servers.append({
                    "id": sid, "name": name, "ip": ip, "environment": env,
                    "replication_status": "Online" if db_status == 1.0 else "Offline",
                    "replication_queue_size": float(hot_data.get('db_qsize', 0.0)),
                    "replication_bandwidth": float(hot_data.get('db_bandwidth', 0.0)),
                    "replication_latency": float(hot_data.get('db_latency', 0.0)),
                    "is_inactive": ls_str is None,
                    "last_seen": ls_str.replace(' ', 'T') + 'Z' if ls_str else None,
                    "db_role": "slave" if is_rep else "master",
                    "master_host": m_host if is_rep else None,
                    "db_host": d_host
                })

            # Process RDS
            for r in rds_rows:
                m = r._mapping
                sid = 20000 + m['id']
                hot_data = hot_data_map.get(sid, {})
                is_online = m['status'] == 'online'
                ext_id = m.get('external_id') or ''
                
                # Heuristic to detect replication based on AWS naming pattern or database_status columns
                is_replica = bool(m.get('is_replication')) or '-replica' in ext_id.lower() or 'replica' in m['name'].lower()
                master_host = m.get('master_host') or None
                if not master_host and is_replica and '-replica' in ext_id.lower():
                    master_host = ext_id.lower().split('-replica')[0]
                
                ip_val = ext_id if ext_id else "aws.amazon.com/rds"
                
                servers.append({
                    "id": sid, "name": m['name'], "ip": ip_val, "environment": m['environment'],
                    "replication_status": "Online" if is_online else "Offline",
                    "replication_queue_size": float(hot_data.get('db_qsize', 0.0)),
                    "replication_bandwidth": float(hot_data.get('db_bandwidth', 0.0)),
                    "replication_latency": float(hot_data.get('db_latency', 0.0)),
                    "is_inactive": not is_online,
                    "last_seen": m['last_seen'].replace(' ', 'T') + 'Z' if m['last_seen'] else None,
                    "db_role": "slave" if is_replica else "master",
                    "master_host": master_host, 
                    "db_host": ip_val
                })

            # Group slaves under their respective master
            # NEW: Deduplicate by IP/Host to prevent same server appearing twice (Legacy vs RDS)
            dedup_servers = []
            seen_identifiers = set()
            for s in servers:
                # Normalizing identifiers: Use IP and Host
                id1 = s.get('ip')
                id2 = s.get('db_host')
                
                # Skip if we've seen this identifier already
                if (id1 and id1 in seen_identifiers) or (id2 and id2 in seen_identifiers):
                    continue
                
                if id1: seen_identifiers.add(id1)
                if id2: seen_identifiers.add(id2)
                dedup_servers.append(s)
            
            servers = dedup_servers
            
            masters = [s for s in servers if s['db_role'] == 'master']
            slaves = [s for s in servers if s['db_role'] == 'slave']
            
            # Sort masters by name
            masters.sort(key=lambda x: x['name'])
            
            ordered_servers = []
            assigned_ids = set() # Safety: Ensure no server ID appears twice in the list
            
            for m in masters:
                if m['id'] in assigned_ids: continue
                assigned_ids.add(m['id'])
                ordered_servers.append(m)
                
                # Find slaves for this master
                master_key = m['db_host'] or m['ip']
                m_slaves = [s for s in slaves if s['master_host'] == master_key]
                # If no direct match, try matching by name prefix (for RDS)
                if not m_slaves and m['master_host'] is None:
                    m_slaves = [s for s in slaves if s.get('master_host') == m.get('external_id', m['name'])]
                
                # Sort slaves by name
                m_slaves.sort(key=lambda x: x['name'])
                for slave in m_slaves:
                    if slave['id'] not in assigned_ids:
                        assigned_ids.add(slave['id'])
                        ordered_servers.append(slave)
                
            # Add any orphaned slaves at the end
            orphan_slaves = [s for s in slaves if s['id'] not in assigned_ids]
            orphan_slaves.sort(key=lambda x: x['name'])
            ordered_servers.extend(orphan_slaves)
            
            servers = ordered_servers

            total_count = len(servers)
            offset = (page - 1) * size
            paginated = servers[offset:offset + size]
            total_pages = math.ceil(total_count / size) if size > 0 else 0
            return {
                "items": paginated,
                "total_count": total_count,
                "page": page, "size": size, "total_pages": total_pages
            }
    except Exception as e:
        logger.error(f"Error in get_database_monitoring: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/database-monitoring-history")
def get_database_monitoring_history(
    environment: str = Depends(get_active_environment), 
    hours: int = Query(24), 
    page: int = Query(1), 
    size: int = Query(20)
):
    """Database monitoring historical data"""
    try:
        with engine.connect() as conn:
            query = text("""
                SELECT id, environment, metric_type, metrics_sent, status, sent_at
                FROM exchange_transactions
                WHERE metric_type = 'database'
                    AND environment = :env
                    AND sent_at >= NOW() - INTERVAL '1 hour' * :hours
                ORDER BY sent_at DESC
            """)
            params = {"env": environment, "hours": hours}
            result = conn.execute(query, params).fetchall()
            
            history = []
            summary = {
                "qSize": {"min": 0, "max": 0, "avg": 0},
                "bandwidth": {"min": 0, "max": 0, "avg": 0},
                "latency": {"min": 0, "max": 0, "avg": 0},
                "total_sends": 0,
                "successful_sends": 0,
                "failed_sends": 0
            }
            
            total_qsize = 0
            total_bw = 0
            total_lat = 0
            count = 0
            
            for r in result:
                m = r._mapping
                metrics = m['metrics_sent'] or {}
                
                # Extract servers data if available
                servers_data = metrics.get('servers', [])
                
                history.append({
                    "id": m['id'],
                    "environment": m['environment'],
                    "sent_at": m['sent_at'].isoformat() + 'Z' if m['sent_at'] else None,
                    "status": m['status'],
                    "server_count": len(servers_data),
                    "servers": servers_data
                })
                
                summary["total_sends"] += 1
                if m['status'] == 'success':
                    summary["successful_sends"] += 1
                else:
                    summary["failed_sends"] += 1
                    
                # Aggregate metrics for summary
                for s in servers_data:
                    q = float(s.get('qSize', {}).get('avg', 0))
                    b = float(s.get('bandwidth', {}).get('avg', 0))
                    l = float(s.get('latency', {}).get('avg', 0))
                    
                    total_qsize += q
                    total_bw += b
                    total_lat += l
                    count += 1
                    
                    if count == 1:
                        summary["qSize"] = {"min": q, "max": q, "avg": q}
                        summary["bandwidth"] = {"min": b, "max": b, "avg": b}
                        summary["latency"] = {"min": l, "max": l, "avg": l}
                    else:
                        summary["qSize"]["min"] = min(summary["qSize"]["min"], q)
                        summary["qSize"]["max"] = max(summary["qSize"]["max"], q)
                        summary["bandwidth"]["min"] = min(summary["bandwidth"]["min"], b)
                        summary["bandwidth"]["max"] = max(summary["bandwidth"]["max"], b)
                        summary["latency"]["min"] = min(summary["latency"]["min"], l)
                        summary["latency"]["max"] = max(summary["latency"]["max"], l)

            if count > 0:
                summary["qSize"]["avg"] = total_qsize / count
                summary["bandwidth"]["avg"] = total_bw / count
                summary["latency"]["avg"] = total_lat / count
                
            total_count = len(history)
            offset = (page - 1) * size
            paginated = history[offset:offset + size]
            
            return {
                "history": paginated,
                "summary": summary,
                "total_count": total_count,
                "page": page,
                "size": size
            }
    except Exception as e:
        logger.error(f"Error in get_database_monitoring_history: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/application-monitoring")
def get_application_monitoring(
    environment: str = Depends(get_active_environment), 
    page: int = Query(1), 
    size: int = Query(20)
):
    """Application monitoring real-time status"""
    try:
        with engine.connect() as conn:
            q_apps = text("""
                SELECT a.id, a.name, a.environment, to_char(a.last_seen, 'YYYY-MM-DD HH24:MI:SS') as last_seen, 
                       a.ip, a.cpu, a.memory, a.latency_ms, a.throughput, a.failure_trade_api, a.failure_authentication
                FROM application_status a
                LEFT JOIN metric_sources ms ON a.source_id = ms.id
                WHERE a.environment = :env
                AND (ms.id IS NULL OR COALESCE((ms.config->>'send_application_metrics')::boolean, true) = true)
            """)
            params = {"env": environment}
            rows_apps = conn.execute(q_apps, params).fetchall()
            
            found_servers = {}
            for r in rows_apps:
                m = r._mapping
                found_servers[m['id']] = {
                    "id": m['id'], "name": m['name'], "ip": m['ip'] or "aws.amazon.com",
                    "environment": m['environment'], "last_seen": m['last_seen'],
                    "latency": float(m['latency_ms'] or 0.0), "throughput": float(m['throughput'] or 0.0),
                    "failure_trade": float(m['failure_trade_api'] or 0.0), "failure_auth": float(m['failure_authentication'] or 0.0),
                    "cpu": float(m['cpu'] or 0.0), "memory": float(m['memory'] or 0.0)
                }
            
            # Combine all IDs for hot data fetch
            # prom_metrics_collector stores app data under offset ID (10000 + app_id)
            hot_fetch_ids = [10000 + sid for sid in found_servers.keys()]
                
            raw_hot_data_map = get_all_servers_hot_data(hot_fetch_ids)
            # Re-map back to original app IDs for lookup below
            hot_data_map = {sid - 10000: v for sid, v in raw_hot_data_map.items()}
                
            servers_list = []
            now = datetime.utcnow()
            for sid, sinfo in found_servers.items():
                hot_data = hot_data_map.get(sid, {})
                app_latency = float(hot_data.get('app_latency', hot_data.get('latency', sinfo.get('latency', 0.0))))
                app_throughput = float(hot_data.get('app_throughput', hot_data.get('throughput', sinfo.get('throughput', 0.0))))
                app_hist_throughput = float(hot_data.get('app_historicalThroughput', 0.0))
                app_hist_latency = float(hot_data.get('app_historicalLatency', 0.0))
                app_failure_auth = float(hot_data.get('app_failure_authentication', hot_data.get('failureAuthentication', sinfo.get('failure_auth', 0.0))))
                app_failure_trade = float(hot_data.get('app_failure_trade_api', hot_data.get('failureTradeApi', sinfo.get('failure_trade', 0.0))))
                
                last_seen_dt = None
                if sinfo['last_seen']:
                    try: last_seen_dt = datetime.strptime(sinfo['last_seen'], '%Y-%m-%d %H:%M:%S')
                    except: pass
                
                is_inactive = False
                if last_seen_dt: is_inactive = (now - last_seen_dt).total_seconds() > 600
                elif not hot_data: is_inactive = True
                
                if is_inactive: app_latency = app_throughput = app_failure_auth = app_failure_trade = 0.0
                
                servers_list.append({
                    "id": sid, "name": sinfo['name'], "ip": sinfo['ip'], "environment": sinfo['environment'],
                    "latency": app_latency, "throughput": app_throughput, 
                    "historicalThroughput": app_hist_throughput, "historicalLatency": app_hist_latency,
                    "failure_auth": app_failure_auth,
                    "failure_trade": app_failure_trade, "is_inactive": is_inactive,
                    "cpu": float(hot_data.get('cpu', sinfo.get('cpu', 0.0))),
                    "memory": float(hot_data.get('memory', sinfo.get('memory', 0.0))),
                    "last_seen": (sinfo['last_seen'].replace(' ', 'T') + 'Z') if sinfo['last_seen'] else None
                })
                
            servers_list.sort(key=lambda x: x['name'])
            total_count = len(servers_list)
            offset = (page - 1) * size
            paginated = servers_list[offset:offset + size]
            total_pages = math.ceil(total_count / size) if size > 0 else 0
            return {"items": paginated, "total_count": total_count, "page": page, "size": size, "total_pages": total_pages}
    except Exception as e:
        logger.error(f"Error in get_application_monitoring: {e}")
        raise HTTPException(status_code=500, detail=str(e))

class _MoveEnvReq(BaseModel):
    environment: str

@router.put("/application-monitoring/{app_id}/move")
def move_application_put(app_id: int, data: _MoveEnvReq, request: Request):
    from app.utils.permissions import require_admin
    require_admin(request)
    return _move_app(app_id, data.environment)

@router.put("/database-monitoring/{db_id}/move")
def move_database_put(db_id: int, data: _MoveEnvReq, request: Request):
    from app.utils.permissions import require_admin
    require_admin(request)
    return _move_db(db_id, data.environment)

def _move_app(app_id: int, target_env: str):
    from app.db.db import application_status_table, lama_exchange_server_selection_table, metric_sources_table
    target_env = target_env.lower()
    if target_env not in ('uat', 'prod'):
        raise HTTPException(status_code=400, detail="Environment must be 'uat' or 'prod'")
    with engine.begin() as conn:
        app = conn.execute(select(application_status_table).where(application_status_table.c.id == app_id)).fetchone()
        if not app: raise HTTPException(status_code=404, detail="Application not found")
        old_env = app._mapping['environment']
        if old_env == target_env:
            return {"message": f"Already in {target_env}"}
        # Move application_status
        conn.execute(update(application_status_table).where(application_status_table.c.id == app_id).values(environment=target_env))
        # Move exchange_selection
        conn.execute(text("DELETE FROM lama_exchange_server_selection WHERE server_id = :sid AND environment = :old AND metric_source = 'application'"), {"sid": app_id, "old": old_env})
        conn.execute(text("INSERT INTO lama_exchange_server_selection (environment, server_id, enabled, metric_source, created_at, updated_at) VALUES (:env, :sid, true, 'application', NOW(), NOW()) ON CONFLICT ON CONSTRAINT unique_env_server DO UPDATE SET environment = :env, enabled = true"), {"env": target_env, "sid": app_id})
        # Move linked metric_sources
        app_name = app._mapping['name']
        conn.execute(update(metric_sources_table).where(
            (metric_sources_table.c.type == 'ecs') &
            ((metric_sources_table.c.name == app_name) | (metric_sources_table.c.config.op('->>')('service') == app_name)) &
            (metric_sources_table.c.environment == old_env)
        ).values(environment=target_env))
    return {"message": f"Application moved to {target_env}"}

def _move_db(db_id: int, target_env: str):
    from app.db.db import database_status_table, database_config_table
    target_env = target_env.lower()
    if target_env not in ('uat', 'prod'):
        raise HTTPException(status_code=400, detail="Environment must be 'uat' or 'prod'")
    with engine.begin() as conn:
        db_row = conn.execute(select(database_status_table).where(database_status_table.c.id == db_id)).fetchone()
        if not db_row: raise HTTPException(status_code=404, detail="Database not found")
        old_env = db_row._mapping['environment']
        if old_env == target_env:
            return {"message": f"Already in {target_env}"}
        conn.execute(update(database_status_table).where(database_status_table.c.id == db_id).values(environment=target_env))
        # Move linked database_config
        host = db_row._mapping.get('external_id') or db_row._mapping.get('name')
        if host:
            conn.execute(text("UPDATE database_config SET environment = :env WHERE host = :host AND environment = :old"), {"env": target_env, "host": host, "old": old_env})
    return {"message": f"Database moved to {target_env}"}

@router.delete("/application-monitoring/{app_id}")
def delete_application_status(app_id: int, request: Request):
    """Surgical Deletion: Removes an app from dashboard, selection, and prevents re-discovery"""
    from app.utils.permissions import require_admin
    from app.db.db import application_status_table, lama_exchange_server_selection_table, aws_ignore_list_table, metric_sources_table
    from sqlalchemy import delete
    
    require_admin(request)
    with engine.begin() as conn:
        # 1. Fetch info before deletion for ignore-list
        app_q = select(application_status_table).where(application_status_table.c.id == app_id)
        app = conn.execute(app_q).fetchone()
        if not app:
            raise HTTPException(status_code=404, detail="Application not found")
        
        # 2. Add to ignore list if it's an AWS resource
        if app.external_id and app.external_id.startswith('arn:aws:'):
            try:
                conn.execute(text("""
                    INSERT INTO aws_ignore_list (external_id, resource_type, environment)
                    VALUES (:ext_id, 'ecs', :env)
                    ON CONFLICT (external_id) DO NOTHING
                """), {"ext_id": app.external_id, "env": app.environment})
                logger.info(f"Added {app.external_id} to AWS ignore list")
            except Exception as e:
                logger.warning(f"Failed to add to ignore list: {e}")

        # 3. Cascading delete from selection table
        conn.execute(delete(lama_exchange_server_selection_table).where(
            (lama_exchange_server_selection_table.c.server_id == app_id) &
            (lama_exchange_server_selection_table.c.metric_source == 'application')
        ))
        
        # 4. Delete linked metric_sources entry (ECS service config used by schedulers)
        app_name = app.name
        conn.execute(delete(metric_sources_table).where(
            (metric_sources_table.c.type == 'ecs') &
            ((metric_sources_table.c.name == app_name) |
             (metric_sources_table.c.config.op('->>')('service') == app_name))
        ))

        # 5. Delete from status table
        conn.execute(delete(application_status_table).where(application_status_table.c.id == app_id))
        
        return {"success": True, "message": "Application removed successfully and added to ignore list."}

@router.delete("/database-monitoring/{db_id}")
def delete_database_status(db_id: int, request: Request):
    """Surgical Deletion: Removes a database from dashboard and prevents re-discovery"""
    from app.utils.permissions import require_admin
    from app.db.db import database_status_table, aws_ignore_list_table
    from sqlalchemy import delete
    
    require_admin(request)
    with engine.begin() as conn:
        # 1. Fetch info
        db_q = select(database_status_table).where(database_status_table.c.id == db_id)
        db_row = conn.execute(db_q).fetchone()
        if not db_row:
            raise HTTPException(status_code=404, detail="Database not found")
        
        # 2. Add to ignore list
        if db_row.external_id:
            try:
                conn.execute(text("""
                    INSERT INTO aws_ignore_list (external_id, resource_type, environment)
                    VALUES (:ext_id, 'rds', :env)
                    ON CONFLICT (external_id) DO NOTHING
                """), {"ext_id": db_row.external_id, "env": db_row.environment})
            except Exception as e:
                logger.warning(f"Failed to add to ignore list: {e}")

        # 3. Delete linked database_config entry
        if db_row.external_id:
            conn.execute(text("DELETE FROM database_config WHERE host = :host OR host LIKE :host_like"), 
                         {"host": db_row.external_id, "host_like": f"{db_row.external_id}.%"})

        # 4. Delete from status table
        conn.execute(delete(database_status_table).where(database_status_table.c.id == db_id))
        
        return {"success": True, "message": "Database removed successfully."}

@router.get("/application-monitoring-history")
def get_application_monitoring_history(
    environment: str = Depends(get_active_environment), 
    hours: int = Query(24), 
    page: int = Query(1), 
    size: int = Query(20)
):
    """Application monitoring historical data"""
    try:
        with engine.connect() as conn:
            query = text("""
                SELECT id, environment, metric_type, metrics_sent, status, sent_at, sequence_id
                FROM exchange_transactions
                WHERE metric_type = 'application'
                    AND environment = :env
                    AND sent_at >= NOW() - INTERVAL '1 hour' * :hours
                ORDER BY sent_at DESC
            """)
            params = {"env": environment, "hours": hours}
            result = conn.execute(query, params).fetchall()
            
            history = []
            summary = {
                "throughput": {"min": 0, "max": 0, "avg": 0},
                "latency": {"min": 0, "max": 0, "avg": 0},
                "historicalThroughput": {"min": 0, "max": 0, "avg": 0},
                "historicalLatency": {"min": 0, "max": 0, "avg": 0},
                "failureAuthentication": {"min": 0, "max": 0, "avg": 0},
                "failureTradeApi": {"min": 0, "max": 0, "avg": 0}
            }
            
            totals = {"throughput": 0, "latency": 0, "h_throughput": 0, "h_latency": 0, "f_auth": 0, "f_api": 0}
            count = 0
            
            for r in result:
                m = r._mapping
                metrics = m['metrics_sent'] or {}
                
                # Flatten metrics for history table
                entry = {
                    "id": m['id'],
                    "environment": m['environment'],
                    "sent_at": m['sent_at'].isoformat() + 'Z' if m['sent_at'] else None,
                    "status": m['status'],
                    "sequence_id": m['sequence_id'],
                    "throughput": {"avg": float(metrics.get('throughput', 0))},
                    "latency": {"avg": float(metrics.get('latency', 0))},
                    "historicalThroughput": {"avg": float(metrics.get('historicalThroughput', 0))},
                    "historicalLatency": {"avg": float(metrics.get('historicalLatency', 0))},
                    "failureAuthentication": {"avg": float(metrics.get('failureAuthentication', 0))},
                    "failureTradeApi": {"avg": float(metrics.get('failureTradeApi', 0))}
                }
                history.append(entry)
                
                # Aggregate for summary
                for key in totals.keys():
                    val = float(metrics.get(key.replace('h_', 'historical').replace('f_auth', 'failureAuthentication').replace('f_api', 'failureTradeApi'), 0))
                    # Simplified aggregation logic
                    pass # Summary logic can be expanded
                
            total_count = len(history)
            offset = (page - 1) * size
            paginated = history[offset:offset + size]
            
            return {
                "history": paginated,
                "summary": summary,
                "total_count": total_count,
                "page": page,
                "size": size
            }
    except Exception as e:
        logger.error(f"Error in get_application_monitoring_history: {e}")
        raise HTTPException(status_code=500, detail=str(e))
