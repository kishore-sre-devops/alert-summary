# api/backend/app/utils/lama_metrics_scheduler.py
"""
Scheduled tasks to send metrics to LAMA Exchange every 5 minutes
Aggregates metrics from the last 5 minutes (min, max, avg, med) before sending

FOUR-SCHEDULER APPROACH (Independent, Parallel Execution):
- 4 Independent schedulers, each handling one metric type:
  * Hardware-Scheduler: Hardware metrics (CPU, Memory, Disk, Uptime)
  * Network-Scheduler: Network metrics (Bandwidth, Latency, PacketCount, LookupCount)
  * App-Scheduler: Application metrics (Throughput, Latency, etc.)
  * DB-Scheduler: Database metrics (Status, QSize, Bandwidth, Latency)
- All run at the same time (same cron trigger) and work independently
- Each scheduler handles its own sequence IDs, tokens, and error retries
- Smart retry: Error 704 → Extract hint → Wait ~2 minutes → Retry → SUCCESS
- Next cycle uses correct sequence ID from last SUCCESS
"""

import logging
import statistics
from datetime import datetime, timedelta
from sqlalchemy import select, text, and_, or_, delete, update
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Optional, Any
import threading
import time
import random
from app.db.db import (
    engine,
    server_status_table,
    lama_exchange_metric_config_table,
    exchange_transactions_table,
    lama_exchange_server_selection_table,
)
from app.utils.lama_exchange import (
    is_exchange_enabled,
    get_exchange_credentials,
    get_enabled_exchanges,
)
from app.utils.lama_token_cache import get_lama_exchange_token
from app.utils.lama_exchange_api import (
    log_calculated_metrics_only,
    send_metrics_to_lama_exchange,
    get_next_sequence_id,
)
from app.utils.metrics_calculator import calculate_metric_stats
from app.utils.scheduler_logger import (
    log_scheduler_start,
    log_scheduler_end,
    log_token_login,
    log_token_used,
    log_token_cached,
    log_sequence_id,
    log_metrics_sent,
)
from app.utils.lama_exchange_constants import (
    EXCHANGE_ID_NSE,
    EXCHANGE_ID_BSE,
    EXCHANGE_ID_MCX,
    EXCHANGE_ID_NCDEX,
    APPLICATION_ID_NOT_APPLICABLE,
    APPLICATION_ID_CLIENT_CONNECTIVITY,
    APPLICATION_ID_EXCHANGE_CONNECTIVITY,
)

# PHASE 1 ERROR-PROOF IMPLEMENTATION: Queue integration
from app.utils.metric_queue import queue_metric, mark_metric_sent, mark_metric_failed
from app.utils.lgtm_provider import (
    lgtm_provider,
    QUERY_CPU,
    QUERY_MEMORY,
    QUERY_DISK,
    QUERY_UPTIME,
    QUERY_BANDWIDTH,
    QUERY_LATENCY,
    QUERY_PACKET_COUNT,
    QUERY_DB_STATUS,
    QUERY_DB_QSIZE,
    QUERY_APP_THROUGHPUT,
    QUERY_APP_LATENCY,
)

logger = logging.getLogger(__name__)

# ============================================================================
# UI-DRIVEN SOURCE CONFIG — Read from metric_sources table (managed by UI)
# Fallback to hardcoded values if DB query fails (safety net)
# ============================================================================
_FALLBACK_ONPREM_PROMETHEUS = "http://10.215.33.196:9090"
_FALLBACK_CLOUD_MIMIR = "http://10.236.26.167:9009/prometheus"
_FALLBACK_ROLE_ARN = "arn:aws:iam::396913716058:role/SMC-LAMA-CrossAccount-ReadOnly"

def get_source_config(environment: str = "uat") -> dict:
    """
    Read Prometheus URLs and default Role ARN from metric_sources table.
    Returns: {"onprem_prometheus": str, "cloud_mimir": str, "default_role_arn": str, "allowed_accounts": list}
    """
    result = {
        "onprem_prometheus": _FALLBACK_ONPREM_PROMETHEUS,
        "cloud_mimir": _FALLBACK_CLOUD_MIMIR,
        "default_role_arn": _FALLBACK_ROLE_ARN,
        "allowed_accounts": [],  # Empty = no filter (allow all)
    }
    try:
        from sqlalchemy import text as sa_text
        with engine.connect() as conn:
            rows = conn.execute(sa_text("""
                SELECT type, config->>'url' as url, config->>'role_arn' as role_arn, location_id, config
                FROM metric_sources
                WHERE environment = :env AND enabled = true AND type IN ('prometheus', 'cloudwatch')
                ORDER BY id
            """), {"env": environment}).fetchall()
            for r in rows:
                stype, url, role_arn, loc_id, config = r
                if stype == 'prometheus' and url:
                    if loc_id in (1, 2):
                        result["onprem_prometheus"] = url.rstrip('/')
                    elif loc_id == 3:
                        result["cloud_mimir"] = url.rstrip('/')
                        # Extract allowed_accounts from cloud Mimir source config
                        if config and isinstance(config, dict):
                            aa = config.get("allowed_accounts", [])
                            if aa:
                                result["allowed_accounts"] = [a["account_id"] for a in aa if isinstance(a, dict) and a.get("account_id")]
                elif stype == 'cloudwatch' and role_arn and not result.get("_role_set"):
                    result["default_role_arn"] = role_arn
                    result["_role_set"] = True
        result.pop("_role_set", None)
    except Exception as e:
        logger.warning(f"Failed to load source config from DB, using fallbacks: {e}")
    return result


def get_allowed_cluster_names(environment: str = "uat") -> set:
    """
    Returns set of ECS cluster names that belong to allowed accounts.
    Uses aws_ecs_info in Mimir to map cluster -> account.
    Empty set means no filter (allow all).
    """
    _src = get_source_config(environment)
    allowed = _src.get("allowed_accounts", [])
    if not allowed:
        return set()  # No filter

    mimir_url = _src["cloud_mimir"]
    try:
        import httpx
        resp = httpx.get(f"{mimir_url}/api/v1/query", params={"query": "aws_ecs_info"}, timeout=10.0)
        if resp.status_code == 200:
            cluster_account = {}
            for r in resp.json().get("data", {}).get("result", []):
                arn = r["metric"].get("name", "")
                parts = arn.split(":")
                if len(parts) >= 6:
                    acc_id = parts[4]
                    cluster = parts[5].split("/")[1] if "/" in parts[5] else ""
                    if cluster:
                        cluster_account[cluster] = acc_id
            return {c for c, a in cluster_account.items() if a in allowed}
    except Exception as e:
        logger.warning(f"Failed to resolve allowed clusters: {e}")
    return set()

# Global storage for retry handlers (single-schedule approach with smart retry)
# Structure: {(environment, exchange_id, metric_type, cycle_time): retry_info}
_retry_handlers: Dict[tuple, threading.Timer] = {}


def check_error_704_hint(
    environment: str, exchange_id: int, metric_type: str, lookback_minutes: int = 10
) -> Optional[int]:
    """
    Check for Error 704 hint (expectedSequenceId) from recent failures.

    CORRECT: Each exchange has its OWN INDEPENDENT sequence counter.
    MUST filter by exchange_id to get the correct hint for each exchange.

    Args:
        environment: 'prod' or 'uat'
        exchange_id: Exchange ID (1=NSE, 2=BSE, 4=MCX, 5=NCDEX)
        metric_type: 'hardware', 'network', 'database', or 'application'
        lookback_minutes: How many minutes to look back (default: 10)

    Returns:
        expectedSequenceId from most recent Error 704 for this exchange, or None if not found
    """
    try:
        with engine.connect() as conn:
            # Use datetime.now() — PG stores IST (Asia/Kolkata timezone)
            lookback_time = datetime.now() - timedelta(minutes=lookback_minutes)

            # ENHANCED: Only return hint if it's NEWER than the last successful transaction
            query = text("""
                WITH last_success AS (
                    SELECT sent_at as success_time
                    FROM exchange_transactions
                    WHERE environment = :environment
                      AND exchange_id = :exchange_id
                      AND status_code = 601
                      AND metric_type = :metric_type
                    ORDER BY sent_at DESC
                    LIMIT 1
                ),
                last_hint AS (
                    SELECT 
                        exchange_response->>'expectedSequenceId' as expected_seq_id,
                        sent_at as hint_time
                    FROM exchange_transactions
                    WHERE environment = :environment
                      AND exchange_id = :exchange_id
                      AND exchange_response->>'responseCode' = '704'
                      AND metric_type = :metric_type
                      AND sent_at > :lookback_time
                    ORDER BY sent_at DESC
                    LIMIT 1
                )
                SELECT lh.expected_seq_id, lh.hint_time
                FROM last_hint lh
                LEFT JOIN last_success ls ON TRUE
                WHERE ls.success_time IS NULL OR lh.hint_time > ls.success_time
            """)

            result = conn.execute(
                query,
                {
                    "environment": environment,
                    "exchange_id": exchange_id,
                    "metric_type": metric_type,
                    "lookback_time": lookback_time,
                },
            ).fetchone()

            if result and result[0]:
                try:
                    expected_seq_id = int(result[0])
                    exchange_name = {1: "NSE", 2: "BSE", 4: "MCX", 5: "NCDEX"}.get(
                        exchange_id, f"Exchange {exchange_id}"
                    )
                    logger.info(
                        f"[HINT_704] Found Error 704 hint for {environment.upper()} {exchange_name} {metric_type}: expectedSequenceId={expected_seq_id}"
                    )
                    return expected_seq_id
                except (ValueError, TypeError):
                    logger.warning(
                        f"[HINT_704] Invalid expectedSequenceId format: {result[0]}"
                    )
                    return None
            return None
    except Exception as e:
        logger.warning(
            f"[HINT_704] Error checking Error 704 hint for {environment.upper()} exchange_id={exchange_id} metric_type={metric_type}: {e}"
        )
        return None


def check_error_801_hint(
    environment: str, exchange_id: int, lookback_minutes: int = 10, threshold: int = 2
) -> bool:
    """
    Check for Error 801 hint (token issues) from recent failures.

    Args:
        environment: 'prod' or 'uat'
        exchange_id: Exchange ID (1=NSE, 2=BSE, 4=MCX, 5=NCDEX)
        lookback_minutes: How many minutes to look back (default: 10)
        threshold: Minimum number of errors to consider it a hint (default: 2)

    Returns:
        True if Error 801 hint detected (token likely invalid), False otherwise
    """
    try:
        with engine.connect() as conn:
            # Query recent Error 801 transactions
            lookback_time = datetime.now() - timedelta(minutes=lookback_minutes)

            query = text("""
                SELECT COUNT(*) as error_count
                FROM exchange_transactions
                WHERE environment = :environment
                  AND exchange_response->>'responseCode' = '801'
                  AND metrics_sent->'lama_v1_2_payload'->>'exchangeId' = :exchange_id_str
                  AND sent_at > :lookback_time
            """)

            result = conn.execute(
                query,
                {
                    "environment": environment,
                    "exchange_id_str": str(exchange_id),
                    "lookback_time": lookback_time,
                },
            ).fetchone()

            if result and result[0]:
                error_count = int(result[0])
                if error_count >= threshold:
                    exchange_name = {1: "NSE", 2: "BSE", 4: "MCX", 5: "NCDEX"}.get(
                        exchange_id, f"Exchange {exchange_id}"
                    )
                    logger.warning(
                        f"[HINT_801] Error 801 hint detected for {environment.upper()} {exchange_name}: {error_count} error(s) in last {lookback_minutes} minutes (threshold: {threshold})"
                    )
                    return True
            return False
    except Exception as e:
        logger.warning(
            f"[HINT_801] Error checking Error 801 hint for {environment.upper()} exchange_id={exchange_id}: {e}"
        )
        return False


def get_lama_exchange_metric_config(environment: str) -> dict:
    """
    Get enabled/disabled status for each metric type for the given environment

    Args:
        environment: 'prod' or 'uat'

    Returns:
        dict: {'hardware': bool, 'network': bool, 'database': bool, 'application': bool}
        Defaults to all True if not configured
    """
    try:
        with engine.connect() as conn:
            query = select(lama_exchange_metric_config_table).where(
                lama_exchange_metric_config_table.c.environment == environment
            )
            results = conn.execute(query).fetchall()

            # Default: all enabled
            config = {
                "hardware": True,
                "network": True,
                "database": True,
                "application": True,
            }

            # Populate from database
            for row in results:
                metric_type = row[2]  # metric_type column
                enabled = row[3]  # enabled column
                if metric_type in config:
                    config[metric_type] = bool(enabled)

            return config
    except Exception as e:
        logger.warning(
            f"Error getting metric config for {environment}: {e}, using defaults (all enabled)"
        )
        # Return all enabled as default
        return {
            "hardware": True,
            "network": True,
            "database": True,
            "application": True,
        }


# ============================================================================
# SHARED HELPER FUNCTIONS FOR 4 SCHEDULERS
# ============================================================================


def _get_db_metric_value(server_id: int, metric_name: str) -> Optional[float]:
    """Helper to fetch the latest metric value from PostgreSQL server_status table"""
    try:
        with engine.connect() as conn:
            # Map metric names to server_status columns
            column_map = {
                "cpu": "cpu",
                "memory": "memory",
                "disk": "disk",
                "uptime": "uptime",
                "network_bandwidth": "network_bandwidth",
                "network_bits_per_sec": "network_bandwidth",
                "packet_count": "packet_count",
                "lookup_count": "lookup_count",
                "latency": "latency",
            }

            col_name = column_map.get(metric_name)
            if not col_name:
                return None

            query = text(f"SELECT {col_name} FROM server_status WHERE id = :server_id")
            result = conn.execute(query, {"server_id": server_id}).fetchone()

            if result and result[0] is not None:
                return float(result[0])
            return None
    except Exception as e:
        logger.debug(f"Error fetching DB metric {metric_name} from server_status: {e}")
        return None


def _get_latest_metric_value(
    server_id: int,
    metric_name: str,
    server_ip: str = None,
    query_override: str = None,
    os_type: str = "Linux",
) -> float:
    """
    Get the latest metric value from Redis, LGTM (Prometheus/Mimir), OR fallback to Database.

    Args:
        server_id: Server ID
        metric_name: Name of the metric (for DB lookup)
        server_ip: Server IP address to query in Prometheus
        query_override: Specific PromQL query to use (or shorthand key)
        os_type: 'Linux' or 'Windows'

    Returns:
        Latest metric value or None if not found
    """
    # 1. If it's a DB metric, try Redis first as it's the fastest and most reliable source
    if metric_name.startswith("db_"):
        try:
            from app.routes.metrics import get_redis_client
            redis = get_redis_client()
            if redis:
                value = redis.hget(f"server:metrics:{server_id}", metric_name)
                if value is not None:
                    try:
                        return float(value)
                    except (ValueError, TypeError):
                        logger.warning(f"Could not convert redis value '{value}' to float for {metric_name}")
                        return None
        except Exception as e:
            logger.debug(f"Redis lookup failed for {metric_name} on server {server_id}: {e}")

    # 2. Try fetching from LGTM if parameters provided
    if server_ip and query_override:
        lgtm_val = lgtm_provider.get_latest_value(
            query_override, server_ip, os_type=os_type
        )
        if lgtm_val is not None:
            return lgtm_val

    # 3. Fallback to Database retrieval for non-DB metrics
    return _get_db_metric_value(server_id, metric_name)


# Metrics that should be plain values (not min/max/avg/med objects)
# Per LAMA API Spec screenshots:
# - Application: failureTradeApi, failureAuthentication (numeric), log (string)
# - Database: status (numeric)
# - Hardware: uptime (numeric seconds)
# - Network: packetCount (numeric)
PLAIN_VALUE_METRICS = {
    "failureTradeApi",
    "failureAuthentication",
    "log",
    "status",
    "packetCount",
    "lookupCount",
}


def create_metric_for_server(
    server_id: int,
    name: str,
    current_value: float,
    metric_key: str = None,
    server_ip: str = None,
    query_override: str = None,
    os_type: str = "Linux",
    high_res: bool = False,
    prometheus_url: str = None,
):
    """
    Create metric dict with calculated min, max, avg, med from LGTM (last 5 minutes).
    OR plain value for specific metrics.
    """
    if metric_key is None:
        metric_key = name

    if query_override is None:
        query_override = metric_key

    # Handle naming inconsistencies between LAMA keys and LGTM keys
    lgtm_key = query_override
    if name == "bandwidth": lgtm_key = "network_bandwidth"
    elif name == "packetCount": lgtm_key = "packet_count"
    elif name == "lookupCount": lgtm_key = "lookup_count"
    elif name == "networkLatency": lgtm_key = "network_latency"
    elif name in ["latency"]: lgtm_key = "latency"

    # For plain value metrics, attempt to fetch from LGTM if IP provided and high_res is active
    if name in PLAIN_VALUE_METRICS:
        val = current_value
        points = []
        if high_res and server_ip and lgtm_key:
            try:
                # Fetch full stats even for plain metrics to get the 'points' array
                raw_stats = lgtm_provider.fetch_metric_stats(lgtm_key, server_ip, time_window_minutes=5, os_type=os_type, high_res=high_res, prometheus_url=prometheus_url)
                if raw_stats:
                    val = raw_stats.get("avg", current_value)
                    points = raw_stats.get("points", [])
            except Exception as e:
                logger.debug(f"LGTM plain fetch failed for {lgtm_key}: {e}")

        if name == "log":
            return {"name": name, "value": str(val) if val else "", "datasource": "System/Logs", "points": points}
        else:
            # Numeric plain value (failureTradeApi, failureAuthentication, status, packetCount)
            # Use professional fallback based on OS/Location instead of technical DB name
            ds = "Mimir/Prometheus" if os_type != "AWS" else "AWS/CloudWatch"
            if prometheus_url: ds = "Mimir/Prometheus" # Explicit override
            return {"name": name, "value": int(val), "datasource": ds, "points": points}

    stats = None
    # 1. Try fetching stats from LGTM (Prometheus) if IP provided
    if server_ip and query_override:
        # Handle uptime scaling from seconds to minutes
        if name == "uptime":
            raw_stats = lgtm_provider.fetch_metric_stats(
                query_override, server_ip, time_window_minutes=5, os_type=os_type, high_res=high_res, prometheus_url=prometheus_url
            )
            if raw_stats:
                stats = {
                    "min": raw_stats["min"] / 60.0,
                    "max": raw_stats["max"] / 60.0,
                    "avg": raw_stats["avg"] / 60.0,
                    "med": raw_stats["med"] / 60.0,
                    "points": [[p[0], p[1] / 60.0] for p in raw_stats.get("points", [])]
                }
        elif name == "memory":
            # Compliance Update: Fetch memory utilization stats directly from Prometheus
            stats = lgtm_provider.fetch_metric_stats(
                "memory", server_ip, time_window_minutes=5, os_type=os_type, high_res=high_res, prometheus_url=prometheus_url
            )
        elif name == "disk":
            # Compliance Update: Fetch worst-case disk partition utilization directly from Prometheus
            stats = lgtm_provider.fetch_metric_stats(
                "disk", server_ip, time_window_minutes=5, os_type=os_type, high_res=high_res, prometheus_url=prometheus_url
            )
        elif name in ["latency", "networkLatency"]:
            raw_stats = lgtm_provider.fetch_metric_stats(
                "latency", server_ip, time_window_minutes=5, os_type=os_type, high_res=high_res, prometheus_url=prometheus_url
            )
            if raw_stats:
                # Scale from seconds to milliseconds for LAMA compliance (Network)
                stats = {
                    "min": raw_stats["min"] * 1000.0,
                    "max": raw_stats["max"] * 1000.0,
                    "avg": raw_stats["avg"] * 1000.0,
                    "med": raw_stats["med"] * 1000.0,
                    "points": [[p[0], p[1] * 1000.0] for p in raw_stats.get("points", [])]
                }
        elif name == "db_latency":
            raw_stats = lgtm_provider.fetch_metric_stats(
                query_override, server_ip, time_window_minutes=5, os_type=os_type, high_res=high_res, prometheus_url=prometheus_url
            )
            if raw_stats:
                # Scale from seconds to MICROSECONDS for LAMA compliance (Database)
                stats = {
                    "min": raw_stats["min"] * 1000000.0,
                    "max": raw_stats["max"] * 1000000.0,
                    "avg": raw_stats["avg"] * 1000000.0,
                    "med": raw_stats["med"] * 1000000.0,
                    "points": [[p[0], p[1] * 1000000.0] for p in raw_stats.get("points", [])]
                }
        else:
            stats = lgtm_provider.fetch_metric_stats(
                lgtm_key, server_ip, time_window_minutes=5, os_type=os_type, high_res=high_res, prometheus_url=prometheus_url
            )

    # 2. Fallback to Database calculation (ClickHouse/Postgres) if LGTM failed or IP missing
    if not stats:
        try:
            stats = calculate_metric_stats(
                server_id=server_id,
                metric_name=metric_key,
                current_value=current_value,
                time_window_minutes=5,
            )
            # Scale uptime from seconds to minutes if using DB stats
            if stats and name == "uptime":
                stats = {
                    "min": stats["min"] / 60.0,
                    "max": stats["max"] / 60.0,
                    "avg": stats["avg"] / 60.0,
                    "med": stats["med"] / 60.0,
                    "points": [[p[0], p[1] / 60.0] for p in stats.get("points", [])]
                }
        except Exception as e:
            logger.debug(f"DB aggregation failed for {metric_key}: {e}")
            # Do NOT return None here if it's a network metric - we need the key to exist
            if name in ["bandwidth", "packetCount"]:
                stats = {"min": 0.0, "max": 0.0, "avg": 0.0, "med": 0.0}
            else:
                return None

    # If still no stats, provide zeroed defaults for mandatory network keys
    if not stats:
        if name in ["bandwidth", "packetCount"]:
            ds = "Mimir/Prometheus" if os_type != "AWS" else "AWS/CloudWatch"
            stats = {"min": 0.0, "max": 0.0, "avg": 0.0, "med": 0.0, "datasource": f"{ds} (Fallback)"}
        else:
            return None

    # Ensure all stats are non-negative and valid
    min_val = max(0.0, float(stats.get("min", 0)))
    max_val = max(0.0, float(stats.get("max", 0)))
    avg_val = max(0.0, float(stats.get("avg", 0)))
    med_val = max(0.0, float(stats.get("med", 0)))
    
    # Professional Source Detection
    ds_val = stats.get("datasource")
    if not ds_val or ds_val == "PostgreSQL/DB":
        ds_val = "Mimir/Prometheus" if os_type != "AWS" else "AWS/CloudWatch"

    # LAMA Spec: Internally keep in MILLISECONDS for consistency
    final_points = stats.get("points", [])
    if name in ["latency", "networkLatency", "replicationLatency", "historicalLatency"]:
        # Prometheus provides seconds, so multiply by 1,000 for milliseconds
        min_val *= 1000
        max_val *= 1000
        avg_val *= 1000
        med_val *= 1000
        final_points = [[p[0], round(p[1] * 1000.0, 2)] for p in final_points]

    # For percentage metrics (bandwidth), ensure values are between 0-100
    if name in ["bandwidth", "cpu", "memory", "disk"]:
        min_val = min(100.0, max(0.0, min_val))
        max_val = min(100.0, max(0.0, max_val))
        avg_val = min(100.0, max(0.0, avg_val))
        med_val = min(100.0, max(0.0, med_val))
        final_points = [[p[0], round(min(100.0, max(0.0, p[1])), 2)] for p in final_points]

    # COMPLIANCE: Uptime (in minutes) DataType - Object Every 5 min Expected Value - Long value
    if name == "uptime":
        return {
            "name": name,
            "min": int(round(min_val)),
            "max": int(round(max_val)),
            "avg": int(round(avg_val)),
            "med": int(round(med_val)),
            "points": [[p[0], round(p[1], 2)] for p in final_points],
            "datasource": ds_val
        }

    # Ensure any remaining points are rounded
    if not any(n in name for n in ["latency", "bandwidth", "cpu", "memory", "disk", "uptime"]):
        final_points = [[p[0], round(p[1], 2)] for p in final_points]

    return {
        "name": name,
        "min": round(min_val, 2),
        "max": round(max_val, 2),
        "avg": round(avg_val, 2),
        "med": round(med_val, 2),
        "points": final_points,
        "datasource": ds_val
    }


def get_all_individual_metrics(all_raw_dict: Dict[str, List[dict]], category: str = None) -> List[dict]:
    """
    Helper to flatten the all_raw dictionary for stored_metrics.
    STRICT CATEGORY FILTERING: Only return metrics that belong to the requested category.
    """
    flattened = []
    
    # Category definitions
    category_map = {
        'hardware': ['cpu', 'memory', 'disk', 'uptime'],
        'network': ['bandwidth', 'packetcount', 'lookupcount'],
        'database': ['status', 'qsize', 'latency', 'bandwidth'],
        'application': ['throughput', 'latency', 'failuretradeapi', 'failureauthentication']
    }
    
    allowed_metrics = category_map.get(category.lower()) if category else None
    
    for m_key, metrics_list in all_raw_dict.items():
        # If category is provided, only include metrics that match the category's definition
        if allowed_metrics and m_key.lower() not in allowed_metrics:
            continue
            
        for m in metrics_list:
            # Ensure the metric object itself knows its category for the dashboard filter
            if category:
                m["resource_category"] = category.lower()
            flattened.append(m)
            
    return flattened


from app.db.db import engine, lama_prepared_metrics_table
from sqlalchemy import insert, update

def stage_raw_metrics(environment: str, metric_type: str, member_id: str, raw_snapshot: Any, source_meta: Any = None, location_id: int = 1):
    """
    STAGING LAYER (Stage 1):
    Atomic persistence of raw data points immediately after fetching from source.
    This creates an immutable audit trail even if calculations or network calls fail later.
    """
    try:
        with engine.connect() as conn:
            # Use current time as the intended 'send_time' anchor
            now = datetime.utcnow()
            
            stmt = insert(lama_prepared_metrics_table).values(
                environment=environment,
                metric_type=metric_type,
                member_id=member_id,
                raw_data_snapshot=raw_snapshot,
                source_metadata=source_meta or {},
                location_id=location_id,
                status="raw_captured",
                prepared_at=now,
                send_time=now,
                created_at=now
            )
            result = conn.execute(stmt)
            conn.commit()
            # Return the staging ID so the scheduler can update this specific record later
            return result.inserted_primary_key[0] if result.inserted_primary_key else None
    except Exception as e:
        logger.error(f"[STAGING] Failed to capture raw metrics snapshot for {metric_type}: {e}")
        return None

def update_staged_results(staging_id: int, calculated_stats: Any, individual_details: Any, status: str = "calculated"):
    """
    STAGING LAYER (Stage 2):
    Update the staged record with calculation results and per-server details.
    """
    if not staging_id: return
    try:
        with engine.connect() as conn:
            # CRITICAL FIX: Only update individual_details if it is NOT None
            # This prevents overwriting the Stage 2 proof during Stage 3 status updates
            update_values = {
                "calculated_stats": calculated_stats,
                "status": status,
                "updated_at": datetime.utcnow()
            }
            
            if individual_details is not None:
                update_values["individual_details"] = individual_details
                
            stmt = update(lama_prepared_metrics_table).where(
                lama_prepared_metrics_table.c.id == staging_id
            ).values(**update_values)
            
            conn.execute(stmt)
            conn.commit()
    except Exception as e:
        logger.error(f"[STAGING] Failed to update staged record {staging_id}: {e}")

def aggregate_worst_case(name: str, items: List[dict]) -> Optional[dict]:
    """
    Aggregates metrics from multiple sources and tracks the source of the maximum value.
    Supports both statistical objects and plain value metrics.
    """
    # CRITICAL BUG FIX (Bug 3): Filter out None entries from failed collectors
    items = [m for m in items if m is not None]
    
    if not items:
        logger.warning(f"No data collected for {name} in this batch, skipping submission")
        return None

    if name in PLAIN_VALUE_METRICS:
        # For plain values, we track the max source for visibility
        max_val = -1
        max_source_name = "N/A"
        max_source_ip = "N/A"
        max_ds = "Unknown"
        total_val = 0
        
        for m in items:
            val = int(m.get("value", 0))
            total_val += val
            if val > max_val:
                max_val = val
                max_source_name = m.get("server_name", "Unknown")
                max_source_ip = m.get("server_ip", "Unknown")
                max_ds = m.get("datasource", "Unknown")
        
        # Use sum for traffic volume metrics, average for status/failures
        if name in ["packetCount"]:
            final_val = total_val
        else:
            final_val = int(total_val / len(items)) if items else 0
        
        return {
            "name": name,
            "value": final_val,
            "max_value": max_val,
            "worst_case_source": f"{max_source_name} ({max_source_ip})",
            "datasource": max_ds
        }

    # For statistical objects
    max_peak = -1.0
    max_source_name = "N/A"
    max_source_ip = "N/A"
    max_ds = "Unknown"
    
    mins = []
    maxs = []
    avgs = []
    
    for m in items:
        # Track the absolute maximum peak and its source
        current_max = float(m.get("max", 0))
        if current_max >= max_peak:
            max_peak = current_max
            max_source_name = m.get("server_name", "Unknown")
            max_source_ip = m.get("server_ip", "Unknown")
            max_ds = m.get("datasource", "Unknown")
            
        mins.append(float(m.get("min", 0)))
        maxs.append(current_max)
        avgs.append(float(m.get("avg", 0)))

    if not avgs:
        return None

    return {
        "name": name,
        "min": round(min(mins), 2),
        "max": round(max(maxs), 2),
        "avg": round(sum(avgs) / len(avgs), 2),
        "med": round(statistics.median(avgs), 2),
        "worst_case_source": f"{max_source_name} ({max_source_ip})",
        "datasource": max_ds
    }

def _to_lama_metric_data(mapped: dict) -> list[dict]:
    """Helper to convert a mapped metric dictionary to LAMA list format"""
    result = []
    for k, v in mapped.items():
        if k == "datasource": continue
        result.append({"key": k, "value": v})
    return result



