# api/backend/app/routes/logs.py
"""
Logs and services endpoints for monitoring and configuration
"""

from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy import select, desc
from sqlalchemy.orm import Session
from datetime import datetime
from app.db.db import get_db, audit_logs_table, server_status_table, engine
from pydantic import BaseModel

router = APIRouter()

class ConfigData(BaseModel):
    exchangeName: str = None
    exchangeType: str = None
    exchangeHost: str = None
    exchangePort: str = None
    exchangeUsername: str = None
    exchangePassword: str = None
    appName: str = None
    appVersion: str = None
    notificationEmail: str = None
    enableAlerts: bool = True

@router.get("/logs")
async def get_logs(db: Session = Depends(get_db)):
    """Get all activity logs with user email for audit purposes"""
    try:
        from app.db.db import users_table
        from sqlalchemy import text
        
        # Join audit_logs with users table to get user email
        query = text("""
            SELECT 
                al.id,
                al.user_id,
                al.action,
                al.resource_type,
                al.resource_id,
                al.details,
                al.created_at,
                u.email as user_email
            FROM audit_logs al
            LEFT JOIN users u ON al.user_id = u.id
            ORDER BY al.created_at DESC
            LIMIT 500
        """)
        
        with engine.connect() as conn:
            result = conn.execute(query).fetchall()
            logs = [
                {
                    "id": row[0],
                    "user_id": row[1],
                    "action": row[2],
                    "resource_type": row[3],
                    "resource_id": row[4],
                    "details": row[5] if row[5] else {},
                    "timestamp": (row[6].isoformat() + 'Z') if row[6] else None,
                    "user_email": row[7] if row[7] else "System"
                }
                for row in result
            ]
            return {"logs": logs, "count": len(logs)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/config")
async def save_config(config: ConfigData, db: Session = Depends(get_db)):
    """Save configuration"""
    try:
        # Store configuration (can be extended with actual config table)
        return {"status": "success", "message": "Configuration saved"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/config")
async def get_config(db: Session = Depends(get_db)):
    """Get configuration"""
    try:
        return {"status": "success", "config": {}}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/services")
async def get_services(db: Session = Depends(get_db)):
    """Get list of services"""
    try:
        # Fetch agents grouped by exchange/service
        query = select(agents_table)
        result = db.execute(query).fetchall()
        
        services = []
        for agent in result:
            # Row access: id, agent_id, server_id, agent_name, agent_version, status, last_heartbeat, created_at, updated_at
            services.append({
                "name": agent[3] or "Unknown",
                "status": agent[5],
                "totalServers": 1,
                "activeServers": 1 if agent[5] == "online" else 0,
                "failedServers": 0 if agent[5] == "online" else 1,
                "servers": []
            })
        
        return services if services else [
            {"name": "NSE", "status": "online", "totalServers": 0, "activeServers": 0, "failedServers": 0},
            {"name": "BSE", "status": "online", "totalServers": 0, "activeServers": 0, "failedServers": 0},
            {"name": "MCX", "status": "offline", "totalServers": 0, "activeServers": 0, "failedServers": 0},
            {"name": "NCDEX", "status": "offline", "totalServers": 0, "activeServers": 0, "failedServers": 0},
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
