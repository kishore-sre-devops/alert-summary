# api/backend/app/utils/metrics_calculator.py
"""
Utility functions for calculating min, max, average, and median from historical metrics.
Uses local time (IST) for system-wide consistency.
"""

import statistics
from typing import List, Dict, Optional
from datetime import datetime, timedelta
from sqlalchemy import select, func, and_
from sqlalchemy import text
from app.db.db import engine, server_metrics_table
from app.utils.hot_store import update_hot_store_server_metrics
import logging
import os

logger = logging.getLogger(__name__)

# ClickHouse support
def store_metric_to_clickhouse(server_id: int, metric_name: str, value: float, interface_name: Optional[str] = None, ts: Optional[datetime] = None):
    """Store metric in ClickHouse using local time (IST)"""
    try:
        from app.routes.metrics import get_clickhouse_client
        client = get_clickhouse_client()
        if client:
            # Use provided ts or fall back to local now (IST)
            data_ts = ts if ts is not None else datetime.now()
            data = [[
                int(server_id),
                str(metric_name),
                round(float(value), 2),
                interface_name,
                data_ts
            ]]
            client.insert('lama.server_metrics', data, column_names=['server_id', 'metric_name', 'value', 'interface_name', 'ts'])
            return True
    except Exception as e:
        logger.warning(f"Failed to store metric in ClickHouse: {e}")
    return False


def store_metrics_batch(server_id: int, metrics: Dict[str, float], update_hot_store: bool = True) -> bool:
    """Store multiple metrics for a server in a single ClickHouse insert using local time (IST)"""
    try:
        from app.routes.metrics import get_clickhouse_client
        client = get_clickhouse_client()
        if client:
            ts = datetime.now()
            data = []
            for name, val in metrics.items():
                if val is not None:
                    data.append([
                        int(server_id),
                        str(name),
                        round(float(val), 2),
                        None, # interface_name
                        ts
                    ])
            
            if data:
                client.insert('lama.server_metrics', data, column_names=['server_id', 'metric_name', 'value', 'interface_name', 'ts'])
                
                # HOT-STORE: Also update Redis
                if update_hot_store:
                    update_hot_store_server_metrics(server_id, metrics)
                return True
    except Exception as e:
        logger.warning(f"Batch storage to ClickHouse failed for server {server_id}: {e}")
    return False

def store_raw_batch(server_id: int, data_points: List[Dict], update_hot_store: bool = False) -> bool:
    """
    Store a raw list of data points into ClickHouse in one go.
    data_points: list of {'metric': str, 'value': float, 'interface': str|None, 'ts': datetime}
    """
    try:
        from app.routes.metrics import get_clickhouse_client
        client = get_clickhouse_client()
        if client and data_points:
            data = []
            hot_store_update = {}
            
            for dp in data_points:
                val = round(float(dp['value']), 2)
                data.append([
                    int(server_id),
                    str(dp['metric']),
                    val,
                    dp.get('interface'),
                    dp['ts']
                ])
                
                if update_hot_store:
                    # Construct hot store key
                    key = dp['metric']
                    if dp.get('interface'):
                        key = f"{key}_{dp['interface']}"
                    hot_store_update[key] = val
            
            if data:
                # DEBUG: Log what we are inserting for partitions/interfaces
                interfaces = [row[3] for row in data if row[3] is not None]
                if interfaces:
                    logger.info(f"DB INSERT Server {server_id}: {len(data)} rows. Interfaces: {interfaces}")

                client.insert('lama.server_metrics', data, column_names=['server_id', 'metric_name', 'value', 'interface_name', 'ts'])
                
                if update_hot_store and hot_store_update:
                    update_hot_store_server_metrics(server_id, hot_store_update)
                return True
    except Exception as e:
        logger.warning(f"Raw batch storage failed for server {server_id}: {e}")
    return False


def calculate_metric_stats(
    server_id: int,
    metric_name: str,
    current_value: float,
    time_window_minutes: int = 15,
    prefer_clickhouse: bool = True
) -> Dict[str, float]:
    """
    Calculate min, max, average, and median for a metric from historical data.
    Optimized: Uses ClickHouse native aggregation functions for high performance.
    """
    if prefer_clickhouse:
        try:
            from app.routes.metrics import get_clickhouse_client
            client = get_clickhouse_client()
            if client:
                # PERFORMANCE: Calculate everything in one DB pass
                # CRITICAL: Use conditional aggregation to filter monitoring glitches (noise)
                # If a server has AT LEAST ONE value > 0, we treat any 0 as noise and ignore it.
                # If a server is CONSISTENTLY 0 for the whole window, we report it as genuinely down.
                
                is_noisy_metric = any(m in metric_name.lower() for m in ['uptime', 'latency', 'historical'])
                
                if is_noisy_metric:
                    query = f"""
                        SELECT 
                            countIf(value > 0) as up_count,
                            minIf(value, value > 0), 
                            maxIf(value, value > 0), 
                            avgIf(value, value > 0), 
                            medianIf(value, value > 0),
                            groupArray(5)(tuple(toUnixTimestamp(ts), value)) as points
                        FROM (
                            SELECT ts, value 
                            FROM lama.server_metrics 
                            WHERE server_id = {int(server_id)} 
                            AND metric_name = '{metric_name}' 
                            AND ts >= now() - INTERVAL {int(time_window_minutes)} MINUTE
                            ORDER BY ts DESC
                        )
                    """
                else:
                    query = f"""
                        SELECT 
                            count(value),
                            min(value), 
                            max(value), 
                            avg(value), 
                            median(value),
                            groupArray(5)(tuple(toUnixTimestamp(ts), value)) as points
                        FROM (
                            SELECT ts, value 
                            FROM lama.server_metrics 
                            WHERE server_id = {int(server_id)} 
                            AND metric_name = '{metric_name}' 
                            AND ts >= now() - INTERVAL {int(time_window_minutes)} MINUTE
                            ORDER BY ts DESC
                        )
                    """
                
                ch_result = client.query(query)
                if ch_result.result_rows:
                    row = ch_result.result_rows[0]
                    up_count = row[0]
                    
                    # LOGIC: If up_count > 0, use filtered stats. If up_count == 0, return None to avoid polluting aggregates
                    if up_count > 0:
                        # Format points: [[ts, val], [ts, val], ...]
                        raw_points = row[5] if len(row) > 5 else []
                        formatted_points = [[int(p[0]), round(float(p[1]), 2)] for p in raw_points]
                        # Sort points by timestamp ascending
                        formatted_points.sort(key=lambda x: x[0])

                        return {
                            "min": round(float(row[1]), 2) if row[1] is not None else 0.0,
                            "max": round(float(row[2]), 2) if row[2] is not None else 0.0,
                            "avg": round(float(row[3]), 2) if row[3] is not None else 0.0,
                            "med": round(float(row[4]), 2) if row[4] is not None else 0.0,
                            "points": formatted_points
                        }
                    else:
                        # No data found in ClickHouse window
                        return None
        except Exception as e:
            logger.warning(f"ClickHouse stats calculation failed: {e}")

    # Fallback: Return None if all else fails to prevent 0.0 polluting averages
    return None


def store_metric_value(
    server_id: int,
    metric_name: str,
    value: float,
    update_hot_store: bool = True,
    ts: Optional[datetime] = None
) -> bool:
    """Store a metric value using local time (IST)"""
    success = store_metric_to_clickhouse(server_id, metric_name, value, ts=ts)
    if update_hot_store:
        update_hot_store_server_metrics(server_id, {metric_name: value})
    return success

def store_metric_value_with_interface(
    server_id: int,
    metric_name: str,
    value: float,
    interface_name: str,
    update_hot_store: bool = True,
    ts: Optional[datetime] = None
) -> bool:
    """Store a metric value with interface name using local time (IST)"""
    success = store_metric_to_clickhouse(server_id, metric_name, value, interface_name, ts=ts)
    if update_hot_store:
        hot_key = f"{metric_name}_{interface_name}"
        update_hot_store_server_metrics(server_id, {hot_key: value})
    return success
