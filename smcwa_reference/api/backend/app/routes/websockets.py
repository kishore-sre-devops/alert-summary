from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends
import asyncio
import json
import logging
from app.routes.metrics import get_redis_client
from app.utils.permissions import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter()

class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"New WebSocket connection. Total: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            logger.info(f"WebSocket disconnected. Total: {len(self.active_connections)}")

    async def broadcast(self, message: str):
        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except Exception as e:
                logger.debug(f"Failed to send WS message: {e}")
                # We'll handle cleanup in the disconnect logic

manager = ConnectionManager()

@router.websocket("/ws/updates")
async def websocket_endpoint(websocket: WebSocket, user: dict = Depends(get_current_user)):
    await manager.connect(websocket)
    try:
        while True:
            # Just keep the connection open, we don't expect messages from client
            # but we need this loop to detect disconnection
            data = await websocket.receive_text()
            # If client sends "ping", we can "pong"
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        manager.disconnect(websocket)

# Background task to listen to Redis and broadcast to WebSockets
async def redis_listener():
    """Listens to Redis 'server_updates' channel and broadcasts to all connected WS clients"""
    logger.info("Starting Redis WebSocket listener background task...")
    redis = get_redis_client()
    if not redis:
        logger.error("Redis client not available for WebSocket listener")
        return

    pubsub = redis.pubsub()
    pubsub.subscribe("server_updates")

    try:
        while True:
            # check_msg() is non-blocking
            message = pubsub.get_message(ignore_subscribe_messages=True)
            if message:
                data = message['data']
                if isinstance(data, bytes):
                    data = data.decode('utf-8')
                await manager.broadcast(data)
            
            # Short sleep to prevent CPU spinning
            await asyncio.sleep(0.1)
    except Exception as e:
        logger.error(f"Redis listener error: {e}")
        await asyncio.sleep(5)
        # Re-start logic if needed or let the main loop handle it
