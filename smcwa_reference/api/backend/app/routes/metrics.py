from fastapi import APIRouter, HTTPException, Depends
from app.utils.permissions import get_current_user
import clickhouse_connect
import redis
import os
import atexit
import logging

logger = logging.getLogger(__name__)
router = APIRouter(dependencies=[Depends(get_current_user)])

# ClickHouse connection
CLICKHOUSE_HOST = os.getenv("CLICKHOUSE_HOST", "lama_clickhouse")
CLICKHOUSE_PORT = int(os.getenv("CLICKHOUSE_PORT", "8123"))
CLICKHOUSE_USER = os.getenv("CLICKHOUSE_USER", "default")
CLICKHOUSE_PASSWORD = os.getenv("CLICKHOUSE_PASSWORD", "")

# Redis connection
REDIS_HOST = os.getenv("REDIS_HOST", "lama_redis")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_DB = int(os.getenv("REDIS_DB", "0"))
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", None)

import threading

# Thread-local storage for clients
_thread_local = threading.local()

def get_clickhouse_client():
    """Get or create a thread-local ClickHouse client"""
    if not hasattr(_thread_local, 'ch'):
        try:
            _thread_local.ch = clickhouse_connect.get_client(
                host=CLICKHOUSE_HOST,
                port=CLICKHOUSE_PORT,
                username=CLICKHOUSE_USER,
                password=CLICKHOUSE_PASSWORD
            )
        except Exception as e:
            logger.error(f"ClickHouse connection failed: {e}")
            return None
    return _thread_local.ch

def get_redis_client():
    """Get or create a thread-local Redis client"""
    if not hasattr(_thread_local, 'redis'):
        try:
            _thread_local.redis = redis.Redis(
                host=REDIS_HOST,
                port=REDIS_PORT,
                db=REDIS_DB,
                password=REDIS_PASSWORD,
                decode_responses=True
            )
        except Exception as e:
            logger.error(f"Redis connection failed: {e}")
            return None
    return _thread_local.redis

def cleanup_clients():
    """Close clients in current thread"""
    if hasattr(_thread_local, 'ch'):
        try:
            _thread_local.ch.close()
        except:
            pass
        delattr(_thread_local, 'ch')
    
    if hasattr(_thread_local, 'redis'):
        try:
            _thread_local.redis.close()
        except:
            pass
        delattr(_thread_local, 'redis')

@router.get("/stats")
def get_stats():
    client = get_clickhouse_client()
    if client is None:
        raise HTTPException(status_code=500, detail="ClickHouse not connected")

    try:
        result = client.query("SELECT now() AS server_time")
        return {"status": "ok", "server_time": result.result_rows[0][0]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
