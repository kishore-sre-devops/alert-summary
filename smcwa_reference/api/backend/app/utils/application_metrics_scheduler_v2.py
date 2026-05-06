"""
Application Metrics Scheduler V2
Runs every 5 minutes to query Elasticsearch, calculate metrics, and send to LAMA Exchange
Supports all 7 LAMA metrics (6 numeric + 1 log) with DC/DR failover
"""

import logging
import time
import os
import json
import statistics
import threading
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

from app.db.db import engine, metric_sources_table, metric_queries_table
from sqlalchemy import select, text
from app.utils.lama_exchange import get_active_configs, get_exchange_credentials, is_exchange_enabled, get_enabled_exchanges
from app.utils.lama_token_cache import get_lama_exchange_token
from app.utils.lama_exchange_api import send_metrics_to_lama_exchange, get_next_sequence_id, update_sequence_cache_after_704, can_send_to_exchange
from app.utils.scheduler_logger import log_scheduler_start, log_scheduler_end, log_scheduler_event
from app.connectors.elasticsearch import ElasticsearchConnector
from app.connectors.factory import ConnectorFactory
from app.config.exchange_config import ECS_SERVICES, AWS_ASSUME_ROLE_EXTERNAL_ID
from app.collectors.aws_collector import AWSCollector
from app.aggregators.metric_mapper import MetricMapper

logger = logging.getLogger(__name__)

def extract_value_from_elasticsearch_result(result: dict, metric_name: str) -> Optional[float]:
    """Extract numeric value from ES result based on field names"""
    if not result: return None
    
    # Priority fields
    priority_fields = ['Average', 'lamareqesttime', 'reqesttime', 'request_time', 'throughput', 'latency', 'Sum', 'count', 'total']
    for field in priority_fields:
        if field in result and isinstance(result[field], (int, float)):
            return float(result[field])
            
    # Fallback to any numeric field
    for key, value in result.items():
        if isinstance(value, (int, float)):
            return float(value)
    return None

def inject_time_range_to_query(query: str, metric_name: str) -> dict:
    """Inject IST-aligned time range into ES query and return as dict"""
    lookback = "21d" if metric_name.lower().startswith("historical") else "5m"
    time_filter = {"range": {"@timestamp": {"gte": f"now-{lookback}", "lte": "now"}}}

    try:
        query_dict = json.loads(query)
    except:
        # It's a raw string query (Lucene)
        query_dict = {
            "query": {
                "bool": {
                    "must": [{"query_string": {"query": query}}]
                }
            }
        }

    if "query" not in query_dict: query_dict["query"] = {"bool": {"filter": []}}
    if "bool" not in query_dict["query"]: query_dict["query"] = {"bool": {"filter": []}}
    if "filter" not in query_dict["query"]["bool"]: query_dict["query"]["bool"]["filter"] = []
    
    if isinstance(query_dict["query"]["bool"]["filter"], list):
        query_dict["query"]["bool"]["filter"].append(time_filter)
    else:
        # Convert to list if it was a dict
        query_dict["query"]["bool"]["filter"] = [query_dict["query"]["bool"]["filter"], time_filter]
        
    return query_dict

def process_metric_source(source: dict, environment: str) -> List[dict]:
    """Fetch metrics from a single source (ES or ECS)"""
    results = []
    try:
        source_dict = dict(source)
        source_type_val = source_dict.get('type')
        source_type = str(source_type_val).lower() if isinstance(source_type_val, str) else ''
        source_name = source_dict.get('name', 'Unknown')

        if source_type == 'elasticsearch':
            connector = ConnectorFactory.get_connector(source_type, source_dict.get('config', {}))
            if not connector: return []            
            # Fetch queries for this source
            with engine.connect() as conn:
                queries = conn.execute(
                    select(metric_queries_table).where(metric_queries_table.c.source_id == source_dict.get('id'))
                ).fetchall()
                
                for q_row in queries:
                    q = q_row._mapping
                    metric_name = q['metric_name']
                    
                    # Process {DATE} placeholder for IST daily indices
                    ist_date = (datetime.now(timezone.utc) + timedelta(hours=5, minutes=30)).strftime("%Y.%m.%d")
                    raw_query = q['query_payload'].replace("{DATE}", ist_date)
                    query_obj = inject_time_range_to_query(raw_query, metric_name)
                    
                    try:
                        res = connector.execute_query(index=q['index_name'].replace("{DATE}", ist_date), query=query_obj)
                        hits = res.get('hits', {}).get('hits', [])
                        if hits:
                            val = extract_value_from_elasticsearch_result(hits[0]['_source'], metric_name)
                            if val is not None:
                                results.append({
                                    "key": metric_name,
                                    "value": val,
                                    "source": source_name
                                })
                    except Exception as e:
                        logger.error(f"ES Query Failed for {metric_name} on {source_name}: {e}")
                        
        elif source_type == 'ecs':
            # ECS collection logic (simplified proxy to AWSCollector)
            pass # Hardware scheduler already handles ECS mostly
            
    except Exception as e:
        import traceback
        logger.error(f"Error processing source {source_dict.get('name', 'Unknown')}: {e}\n{traceback.format_exc()}")
    return results

def run_application_metrics_scheduler(environment: str = None, exchange_id: int = None):
    """Main Application Metrics Scheduler - Runs every 5 minutes"""
    scheduler_name = "Application-Scheduler"
    if not environment:
        environment = os.getenv("ACTIVE_ENVIRONMENT", "uat").lower()
    
    env = environment.lower()
    log_scheduler_start(scheduler_name, env)
    env_start_time = datetime.utcnow()
    
    try:
        if not is_exchange_enabled(env):
            logger.info(f"[{scheduler_name}] LAMA Disabled for {env.upper()}")
            return

        # 1. Fetch enabled sources for this environment
        with engine.connect() as conn:
            sources = conn.execute(
                select(metric_sources_table).where(
                    metric_sources_table.c.environment == env,
                    metric_sources_table.c.enabled == True
                )
            ).fetchall()
            enabled_sources = [s._mapping for s in sources]

        if not enabled_sources:
            logger.warning(f"[{scheduler_name}] No enabled sources for {env.upper()}")
            return

        # 2. Fetch metrics in parallel (capped to 5 threads for stability)
        all_metrics = []
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = {executor.submit(process_metric_source, s, env): s for s in enabled_sources}
            for future in as_completed(futures):
                try:
                    res = future.result()
                    if res: all_metrics.extend(res)
                except Exception as e:
                    logger.error(f"Source processing failed: {e}")

        if not all_metrics:
            logger.warning(f"[{scheduler_name}] No metrics collected for {env.upper()}")
            return

        # 3. Group and aggregate metrics for LAMA payload
        # Standard LAMA keys: throughput, latency, failureTradeApi, failureAuthentication, log
        aggregated = {}
        for m in all_metrics:
            key = m['key']
            if key not in aggregated: aggregated[key] = []
            aggregated[key].append(m['value'])
            
        payload_list = []
        for key, vals in aggregated.items():
            if not vals: continue
            if key in ['throughput', 'latency', 'historicalThroughput', 'historicalLatency']:
                payload_list.append({
                    "name": key,
                    "value": {
                        "min": round(min(vals), 2),
                        "max": round(max(vals), 2),
                        "avg": round(sum(vals) / len(vals), 2),
                        "med": round(statistics.median(vals), 2)
                    }
                })
            else:
                # Sum for counters
                payload_list.append({"name": key, "value": int(sum(vals))})

        # 4. Prepare stored_metrics for UI Resource Breakdown
        stored_metrics = []
        for m in all_metrics:
            key = m['key']
            val = m['value']
            source = m['source']
            if key in ['throughput', 'latency', 'historicalThroughput', 'historicalLatency']:
                stored_metrics.append({
                    "name": key,
                    "server_name": source,
                    "server_ip": source,
                    "min": round(val, 2), "max": round(val, 2), "avg": round(val, 2), "med": round(val, 2),
                    "resource_category": "application"
                })
            else:
                stored_metrics.append({
                    "name": key,
                    "server_name": source,
                    "server_ip": source,
                    "value": int(val),
                    "resource_category": "application"
                })

        # 5. Submit to Exchanges
        creds = get_exchange_credentials(env)
        if not creds: return
        member_id = creds['member_id']
        
        if exchange_id:
            enabled_exchanges = [exchange_id]
        else:
            enabled_exchanges = get_enabled_exchanges(env)

        def send_to_exchange(exchange_id, retry_count=0, expected_seq_hint=None):
            exchange_name = {1: "NSE", 2: "BSE", 4: "MCX", 5: "NCDEX"}.get(exchange_id, f"Exch-{exchange_id}")
            try:
                token = get_lama_exchange_token(env, exchange_id=exchange_id, scheduler_name=scheduler_name)
                if not token: return False
                
                seq = get_next_sequence_id(env, member_id, exchange_id, "application", expected_seq_id_hint=expected_seq_hint)
                
                res = send_metrics_to_lama_exchange(
                    environment=env, member_id=member_id, instance_id="App-Fleet",
                    metrics=payload_list, auth_token=token, metric_type="application",
                    scheduler_name=scheduler_name, server_name="Combined-Apps", server_ip="combined",
                    exchange_id=exchange_id, application_id=1, sequence_id=seq,
                    sent_at=datetime.now(timezone.utc), skip_705_check=True, stored_metrics=stored_metrics
                )
                
                if res.get("success"):
                    logger.info(f"✅ [{env.upper()}] {scheduler_name}: Sent to {exchange_name}")
                    return True
                
                # Retry for 704
                if str(res.get("response_code")) == "704" and retry_count == 0:
                    hint = res.get("exchange_response", {}).get("expectedSequenceId")
                    if hint:
                        logger.warning(f"🔄 [{scheduler_name}] 704 for {exchange_name}, retrying with {hint}")
                        return send_to_exchange(exchange_id, retry_count=1, expected_seq_hint=int(hint))
                return False
            except Exception as e:
                logger.error(f"Error sending to {exchange_name}: {e}")
                return False

        success_count = 0
        for exch_id in enabled_exchanges:
            if send_to_exchange(exch_id):
                success_count += 1
        
        duration = int((datetime.utcnow() - env_start_time).total_seconds() * 1000)
        log_scheduler_end(scheduler_name, env, duration)
        logger.info(f"[{env.upper()}] {scheduler_name} finished: {success_count}/{len(enabled_exchanges)} successful")

    except Exception as e:
        logger.error(f"CRITICAL: {scheduler_name} Error: {e}", exc_info=True)
        log_scheduler_event(scheduler_name, env, "error", "scheduler_error", f"Critical failure: {e}", "application", "failed")

if __name__ == "__main__":
    run_application_metrics_scheduler()
