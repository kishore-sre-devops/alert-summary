import json
import logging
from app.routes.metrics import get_redis_client

logger = logging.getLogger(__name__)

def broadcast_ui_update(update_type: str, data: dict = None):
    """
    Publishes a message to Redis 'server_updates' channel.
    This is picked up by the WebSocket listener and broadcast to all connected clients.
    """
    try:
        redis = get_redis_client()
        if not redis:
            return
            
        payload = {
            "type": update_type,
            "data": data or {},
            "timestamp": str(int(__import__('time').time()))
        }
        
        redis.publish("server_updates", json.dumps(payload))
        logger.debug(f"📡 Broadcast UI Update: {update_type}")
    except Exception as e:
        logger.error(f"Failed to broadcast UI update: {e}")
