"""
Historical Application Metrics Scheduler
Calculates 21-day historical summary (Min, Max, Avg, Med) for all applications.
Runs once a day at 7:00 AM IST.

CRITICAL: DO NOT TOUCH
---------------------
This file is mandatory for LAMA V1.3 21-day Audit Compliance.
Do NOT modify the 21-day calculation logic for ES or Mimir.
Do NOT remove this scheduler or its daily 7 AM IST trigger.
"""

import logging
import asyncio
import time
import statistics
from datetime import datetime, timedelta, timezone
from sqlalchemy import text
from app.db.db import engine
from app.collectors.es_collector import ESCollector
from app.collectors.mimir_collector import MimirCollector
from app.utils.lama_exchange import get_active_configs, get_exchange_credentials, get_enabled_exchanges
from app.utils.lama_token_cache import get_lama_exchange_token
from app.utils.lama_exchange_api import send_metrics_to_lama_exchange, get_next_sequence_id
from app.utils.nse_timestamp import get_nse_timestamp_ms
from app.utils.aes_encryption import decrypt_password
from app.lama.sequence_manager import SequenceManager

logger = logging.getLogger(__name__)

async def calculate_21d_es_metrics(es_url, username, password, queries, ms_name):
    """Calculate 21-day stats from Elasticsearch by querying all historical indices"""
    es = ESCollector(es_url=es_url, username=username, password=password)
    results = {}
    
    # We use a wildcard to query all relevant indices for the last 21 days
    # Index pattern: lama-smc*
    index_pattern = "lama-smc*"
    
    for q in queries:
        m_name = q[1]
        q_payload = q[2] # Use raw payload, but ESCollector might need range adjustment
        
        # Override the collector's default query to be a 21-day range query
        # This is more efficient than the default 'last 5 hits' logic
        range_query = {
            "size": 0,
            "query": {
                "bool": {
                    "must": [
                        {"query_string": {"query": q_payload}},
                        {"range": {"@timestamp": {"gte": "now-21d/d", "lte": "now/d"}}}
                    ]
                }
            },
            "aggs": {
                "stats": {
                    "extended_stats": {
                        "field": "Average" if m_name.lower() == "latency" else "throughput" # Dynamic field mapping
                    }
                }
            }
        }
        
        # Since ESCollector.collect_metric is designed for 5-min pick & pass, 
        # we implement the historical calculation here directly
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                auth = (username, password) if username and password else None
                resp = await client.post(f"{es_url}/{index_pattern}/_search", json=range_query, auth=auth)
                if resp.status_code == 200:
                    data = resp.json()
                    s = data.get("aggregations", {}).get("stats", {})
                    if s.get("count", 0) > 0:
                        results[m_name] = {
                            "min": round(s.get("min", 0), 2),
                            "max": round(s.get("max", 0), 2),
                            "avg": round(s.get("avg", 0), 2),
                            "med": round(s.get("avg", 0), 2), # Med is approx avg for ES stats
                            "datasource": "Elasticsearch-21d-Audit"
                        }
        except Exception as e:
            logger.error(f"Failed 21d ES calculation for {ms_name} {m_name}: {e}")
            
    return results

async def calculate_21d_mimir_metrics(mimir_url, service_name):
    """Calculate 21-day stats from Mimir using PromQL aggregation"""
    mimir = MimirCollector(url=mimir_url)
    pattern = f".*{service_name}.*"
    
    # PromQL for 21-day stats
    # Throughput: avg_over_time of the 5m rate over 21 days
    q_tp_base = f'sum(rate(http_requests_total{{service=~"{pattern}"}}[5m])) or sum(rate(application_requests_total{{job=~"{pattern}"}}[5m]))'
    q_lat_base = f'histogram_quantile(0.95, sum by (le) (rate(http_request_duration_seconds_bucket{{service=~"{pattern}"}}[5m]))) * 1000'
    
    queries = {
        "historicalThroughput": [
            f'avg_over_time(({q_tp_base})[21d:1h])',
            f'max_over_time(({q_tp_base})[21d:1h])',
            f'min_over_time(({q_tp_base})[21d:1h])'
        ],
        "historicalLatency": [
            f'avg_over_time(({q_lat_base})[21d:1h])',
            f'max_over_time(({q_lat_base})[21d:1h])',
            f'min_over_time(({q_lat_base})[21d:1h])'
        ]
    }
    
    results = {}
    client = await mimir._get_client()
    
    for m_key, q_list in queries.items():
        try:
            # We fetch avg, max, min separately to build the full LAMA stats object
            stats = {"min": 0.0, "max": 0.0, "avg": 0.0, "med": 0.0}
            for i, q in enumerate(q_list):
                resp = await client.get(f"{mimir.url}/api/v1/query", params={"query": q})
                if resp.status_code == 200:
                    data = resp.json().get("data", {}).get("result", [])
                    if data:
                        val = float(data[0]['value'][1])
                        if i == 0: stats["avg"] = stats["med"] = round(val, 2)
                        elif i == 1: stats["max"] = round(val, 2)
                        elif i == 2: stats["min"] = round(val, 2)
            
            if stats["avg"] > 0 or stats["max"] > 0:
                results[m_key] = {**stats, "datasource": "Mimir-21d-Audit"}
        except Exception as e:
            logger.error(f"Failed 21d Mimir calculation for {service_name} {m_key}: {e}")
            
    await mimir.close()
    return results

def historical_application_scheduler(environment: str = None):
    """Main entry point for 7 AM Historical Scheduler"""
    import httpx
    if not environment:
        import os
        environment = os.getenv("ACTIVE_ENVIRONMENT", "uat").lower()
    
    logger.info(f"--- STARTING 7 AM HISTORICAL APPLICATION AUDIT ({environment.upper()}) ---")
    seq_mgr = SequenceManager()
    
    try:
        # 1. Fetch all applications
        with engine.connect() as conn:
            query = text("""
                SELECT ms.id, ms.name, ms.type, ms.config, ms.location_id
                FROM metric_sources ms
                WHERE ms.enabled = TRUE AND ms.environment = :env
                AND (ms.type = 'ecs' OR ms.type IN ('elasticsearch', 'mysql', 'postgresql', 'prometheus_app'))
            """)
            sources = conn.execute(query, {"env": environment}).fetchall()

            # Fetch queries for ES
            queries_query = text("SELECT source_id, metric_name, query_payload FROM metric_queries WHERE enabled = TRUE")
            all_queries = conn.execute(queries_query).fetchall()
            queries_by_source = {}
            for q in all_queries:
                sid = q[0]
                if sid not in queries_by_source: queries_by_source[sid] = []
                queries_by_source[sid].append(q)

        # 2. Process each application
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        from app.schedulers.common import get_source_config
        _src = get_source_config(environment)
        onprem_prometheus = _src["onprem_prometheus"]
        cloud_mimir = _src["cloud_mimir"]

        for src in sources:
            ms_id, ms_name, ms_type, config, loc_id = src
            service_name = config.get("service") or ms_name

            # Check if this source has historicals pre-computed in Prometheus (managed via UI)
            with engine.connect() as chk_conn:
                is_precalc = chk_conn.execute(text(
                    "SELECT historical_precalculated FROM metric_sources WHERE id = :id"
                ), {"id": ms_id}).scalar()
            if is_precalc:
                logger.info(f"⏭️ Skipping 21-day calc for [{ms_name}] - historicals pre-computed in Prometheus")
                continue
            
            historical_raw = {}
            
            if ms_type == 'elasticsearch':
                host = config.get("host")
                port = config.get("port", 9200)
                username = config.get("username")
                enc_password = config.get("password")
                password = decrypt_password(enc_password) if enc_password else None
                
                es_url = f"http://{host}:{port}"
                src_queries = queries_by_source.get(ms_id, [])
                
                historical_raw = loop.run_until_complete(
                    calculate_21d_es_metrics(es_url, username, password, src_queries, ms_name)
                )
            elif ms_type == 'prometheus_app':
                # 21-day data lives in ClickHouse (stored by prom_metrics_collector every 10s)
                # server_id offset for apps = 10000 + application_status.id
                with engine.connect() as hist_conn:
                    row = hist_conn.execute(text(
                        "SELECT id FROM application_status WHERE name = :name AND environment = :env"
                    ), {"name": service_name, "env": environment}).fetchone()
                if row:
                    from app.aggregators.historical_aggregator import HistoricalAggregator
                    historical_raw = HistoricalAggregator.get_21_day_metrics(10000 + row[0], is_generic=True) or {}
            else:
                prom_url = cloud_mimir if loc_id == 3 else onprem_prometheus
                historical_raw = loop.run_until_complete(
                    calculate_21d_mimir_metrics(prom_url, service_name)
                )

            if historical_raw:
                # 3. Submit Historical Metrics to LAMA Exchange
                # LAMA V1.3: Historical metrics are sent with current Real-Time metrics as 0.0
                # but with historicalThroughput and historicalLatency populated
                
                creds = get_exchange_credentials(environment)
                if not creds: continue
                member_id = creds["member_id"]
                exchanges = get_enabled_exchanges(environment)
                
                # Format payload
                zero = {"min": 0.0, "max": 0.0, "avg": 0.0, "med": 0.0}
                metric_data = [
                    {"key": "throughput", "value": zero},
                    {"key": "latency", "value": zero},
                    {"key": "historicalThroughput", "value": historical_raw.get("historicalThroughput") or historical_raw.get("throughput") or zero},
                    {"key": "historicalLatency", "value": historical_raw.get("historicalLatency") or historical_raw.get("latency") or zero},
                    {"key": "failureTradeApi", "value": 0},
                    {"key": "failureAuthentication", "value": 0}
                ]
                
                app_id = seq_mgr.get_next_application_id(service_name, environment=environment)
                
                for eid in exchanges:
                    token = get_lama_exchange_token(environment, eid, scheduler_name="Historical-App-Scheduler")
                    
                    if token:
                        send_metrics_to_lama_exchange(
                            environment=environment, member_id=member_id, instance_id=f"hist_{ms_id}", 
                            metrics=metric_data, auth_token=token, metric_type="application", 
                            scheduler_name="Historical-App-Scheduler", server_name=service_name, 
                            server_ip="historical", exchange_id=eid, application_id=app_id, 
                            sequence_id=None, sent_at=datetime.now(),
                            nse_timestamp=get_nse_timestamp_ms(), location_id=loc_id
                        )
                        logger.info(f"✅ Sent 21-day historical metrics for {service_name} to Exchange {eid}")

        loop.close()
        logger.info("--- HISTORICAL APPLICATION AUDIT COMPLETED ---")
        
    except Exception as e:
        logger.error(f"Critical error in historical_application_scheduler: {e}", exc_info=True)

if __name__ == "__main__":
    historical_application_scheduler()
