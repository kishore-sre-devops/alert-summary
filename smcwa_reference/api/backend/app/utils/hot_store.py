"""
Hot-Store (Redis) implementation for SMC-LAMA
Stores the latest 'Now' status of all servers for near-zero latency UI updates.
Uses local time (IST) strings without 'Z' suffix.
"""
import json
import logging
from datetime import datetime
from app.routes.metrics import get_redis_client

logger = logging.getLogger(__name__)

# Key prefixes
KEY_SERVER_LATEST = "server:latest:{server_id}"
KEY_SERVER_METRICS = "server:metrics:{server_id}"
CHANNEL_SERVER_UPDATES = "server_updates"

def update_hot_store_server_metrics(server_id: int, metrics: dict):
    """
    Updates the Hot-Store with the latest hardware metrics for a server.
    """
    if not metrics:
        return True
        
    try:
        redis = get_redis_client()
        if not redis:
            return False
            
        key = KEY_SERVER_METRICS.format(server_id=server_id)
        
        # LAMA V2.0 PRO: Sanitize None values to prevent Redis errors
        safe_metrics = {k: (v if v is not None else 0.0) for k, v in metrics.items()}
        
        # Add timestamp to metrics (IST ISO format)
        safe_metrics['last_updated'] = datetime.now().isoformat()
        
        # Store as hash
        redis.hset(key, mapping=safe_metrics)
        redis.expire(key, 3600)
        
        # BROADCAST: Notify WebSocket clients
        broadcast_data = {"server_id": server_id, "type": "metrics", "data": safe_metrics}
        redis.publish(CHANNEL_SERVER_UPDATES, json.dumps(broadcast_data))
        
        return True
    except Exception as e:
        logger.warning(f"Failed to update Hot-Store for server {server_id}: {e}")
        return False

def update_hot_store_server_status(server_id: int, status_data: dict):
    """
    Updates the Hot-Store with the latest status (online/offline) and basic info.
    """
    if not status_data:
        return True
        
    try:
        redis = get_redis_client()
        if not redis:
            return False
            
        key = KEY_SERVER_LATEST.format(server_id=server_id)
        
        # LAMA V2.0 PRO: Sanitize None values
        safe_status = {k: (v if v is not None else "") for k, v in status_data.items()}
        
        # Add timestamp if missing (IST)
        if 'last_seen' not in safe_status:
            safe_status['last_seen'] = datetime.now().isoformat()
        
        logger.info(f"🔥 Updating Hot-Store status for server {server_id}: {safe_status}")
        
        redis.hset(key, mapping=safe_status)
        redis.expire(key, 3600)
        
        # BROADCAST: Notify WebSocket clients
        broadcast_data = {"server_id": server_id, "type": "status", "data": safe_status}
        redis.publish(CHANNEL_SERVER_UPDATES, json.dumps(broadcast_data))
        
        return True
    except Exception as e:
        logger.warning(f"Failed to update Hot-Store status for server {server_id}: {e}")
        return False

def update_server_hot_data(server_id: int, data: dict, category: str = "hardware"):
    """
    Generic entry point to update hot store data for hardware, application, or database metrics.
    Handles field mapping and broadcasts to web sockets.
    """
    if category == "hardware":
        return update_hot_store_server_metrics(server_id, data)
    elif category == "application" or category == "database":
        # For applications and databases, we update the status hash with real-time performance metrics
        return update_hot_store_server_status(server_id, data)
    return False

def get_hot_store_server_data(server_id: int) -> dict:
    """
    Retrieves all latest data for a server from Redis.
    """
    try:
        redis = get_redis_client()
        if not redis:
            return {}
            
        status_key = KEY_SERVER_LATEST.format(server_id=server_id)
        metrics_key = KEY_SERVER_METRICS.format(server_id=server_id)
        
        status_data = redis.hgetall(status_key)
        metrics_data = redis.hgetall(metrics_key)
        
        combined = {**status_data, **metrics_data}
        
        for k, v in combined.items():
            try:
                if '.' in v: combined[k] = float(v)
                else: combined[k] = int(v)
            except: pass
                
        return combined
    except Exception as e:
        logger.warning(f"Failed to fetch Hot-Store data: {e}")
        return {}

def get_all_servers_hot_data(server_ids: list) -> dict:
    """Retrieves hot data for multiple servers in one go"""
    if not server_ids: return {}
    try:
        redis = get_redis_client()
        if not redis: return {}
        pipe = redis.pipeline()
        for sid in server_ids:
            pipe.hgetall(KEY_SERVER_LATEST.format(server_id=sid))
            pipe.hgetall(KEY_SERVER_METRICS.format(server_id=sid))
        raw_results = pipe.execute()
        results = {}
        for i, sid in enumerate(server_ids):
            status_data = raw_results[i * 2]
            metrics_data = raw_results[i * 2 + 1]
            if status_data or metrics_data:
                combined = {**status_data, **metrics_data}
                processed = {}
                for k, v in combined.items():
                    try:
                        if '.' in v: processed[k] = float(v)
                        else: processed[k] = int(v)
                    except: processed[k] = v
                if processed: results[sid] = processed
        return results
    except Exception as e:
        logger.warning(f"Failed to batch fetch Hot-Store data: {e}")
        return {}
