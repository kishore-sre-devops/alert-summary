from fastapi import APIRouter, Depends, HTTPException, status, Response, Request, Query
from sqlalchemy import select, update, delete, desc, and_, text, or_, func
from sqlalchemy.dialects.postgresql import insert
from app.db.db import (
    get_db, users_table, alerts_table, alert_config_table, 
    server_status_table, engine, audit_logs_table
)
from app.models.mobile import (
    mobile_devices_table, mobile_alerts_table, 
    escalation_policies_table, active_escalations_table,
    incident_audit_trail_table
)
from app.routes.auth import get_current_user_token, create_jwt_token, users_table, get_user_groups
from app.services.push import send_push_notification
from jose import jwt, JWTError
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
import secrets
import string
import bcrypt
import logging
import pytz
from typing import List, Optional
from pydantic import BaseModel

logger = logging.getLogger(__name__)
router = APIRouter()

# --- GOOGLE LOGIN (MOBILE COMPATIBILITY) ---
class GoogleMobileRequest(BaseModel):
    idToken: str

@router.post("/auth/google")
async def google_login_mobile(data: GoogleMobileRequest, db: Session = Depends(get_db)):
    """Authenticate mobile user via Google Identity Services"""
    try:
        # Same Client ID as auth.py
        CLIENT_ID = "655248995621-mf0gp9tb3omc7dfjr71kft8qr30ucjr2.apps.googleusercontent.com"
        
        id_info = id_token.verify_oauth2_token(
            data.idToken, 
            google_requests.Request(), 
            CLIENT_ID
        )

        email = id_info.get('email')
        if not email:
            raise HTTPException(status_code=400, detail="Google token does not contain email")
        
        # RESTRICTION REMOVED: Allow all Gmail/Google domains
        
        if not id_info.get('email_verified'):
            raise HTTPException(status_code=400, detail="Google email not verified")

        # Check if user exists in DB
        query = select(users_table).where(users_table.c.email == email)
        result = db.execute(query).fetchone()
        
        user_id = None
        role = "user"
        
        if result:
            user_id = result[0]
            role = result[5]
        else:
            # Create new user
            logger.info(f"Creating new mobile user from Google Login: {email}")
            alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
            password = ''.join(secrets.choice(alphabet) for i in range(20))
            hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
            full_name = id_info.get('name') or email.split('@')[0]
            
            insert_query = users_table.insert().values(
                email=email,
                password=hashed_password,
                full_name=full_name,
                role="user",
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
                is_active=True
            )
            db.execute(insert_query)
            db.commit()
            
            # Fetch the newly created user
            new_user = db.execute(select(users_table).where(users_table.c.email == email)).fetchone()
            user_id = new_user[0]
            role = new_user[5]

        # Generate JWT Token
        token = create_jwt_token(user_id, email, role)
        
        return {
            "token": token,
            "user_email": email,
            "user_id": user_id,
            "role": role,
            "group_name": get_user_groups(user_id),
            "status": "ok"
        }

    except Exception as e:
        logger.error(f"Google Mobile Login Error: {e}")
        raise HTTPException(status_code=401, detail=f"Google authentication failed: {str(e)}")

def to_ist_str(dt):
    if not dt: return None
    ist = pytz.timezone('Asia/Kolkata')
    # If naive, assume UTC
    if dt.tzinfo is None:
        dt = pytz.utc.localize(dt)
    return dt.astimezone(ist).strftime("%d/%m/%y, %I:%M:%S %p")

def format_metric_with_unit(metric_raw: str, value: float) -> str:
    """Helper to format numeric metrics with units for mobile UI"""
    if value is None: return "-"

    METRIC_UNIT_MAP = {
        'application.failureAuthentication': '',
        'application.failureTradeApi': '',
        'application.historicalLatency': 'ms',
        'application.historicalThroughput': ' Req/s',
        'application.latency': 'ms',
        'application.throughput': ' Req/s',
        'database.bandwidth': '%',
        'database.latency': 'ms',
        'database.qSize': '',
        'hardware.cpu': '%',
        'hardware.disk': '%',
        'hardware.memory': '%',
        'hardware.uptime': 'm',
        'network.bandwidth': '%',
        'network.packetCount': ' errors',
        'network.latency': 'ms'
    }

    unit = METRIC_UNIT_MAP.get(metric_raw, "")

    # Professional formatting: 1 decimal place if float, else plain
    display_val = f"{float(value):.1f}" if float(value) % 1 != 0 else str(int(value))
    return f"{display_val}{unit}"

def update_device_activity(db: Session, user_id: int):
    """Updates the last_active_at timestamp for a user's mobile device"""
    try:
        db.execute(update(mobile_devices_table).where(
            mobile_devices_table.c.user_id == user_id
        ).values(
            last_active_at=datetime.utcnow(),
            is_logged_in=True # Ensure they are marked logged in if active
        ))
        db.commit()
    except Exception as e:
        logger.error(f"Error updating device activity: {e}")
        db.rollback()

@router.get("/alerts")
async def get_alerts(filter: str = "active", skip: int = 0, limit: int = 50, db: Session = Depends(get_db), auth = Depends(get_current_user_token)):
    """
    Get alerts for the mobile app/UI history - FETCH DIRECTLY FROM PRIMARY ALERTS TABLE
    Ensures absolute sync between Dashboard and Mobile with all details.
    """
    _, u = auth
    user_id = u['user_id']
    update_device_activity(db, user_id)
    try:
        # We query the primary alerts table and join with metadata tables
        q = select(
            alerts_table.c.id, 
            alerts_table.c.alert_type.label("title"),
            alerts_table.c.message.label("body"), 
            alerts_table.c.severity, 
            alerts_table.c.is_resolved, 
            alerts_table.c.created_at, 
            alerts_table.c.resolved_at, 
            alerts_table.c.metric_value,
            alerts_table.c.threshold_value,
            server_status_table.c.name.label("server_name"),
            server_status_table.c.ip.label("server_ip"),
            escalation_policies_table.c.name.label("group_name"),
            func.max(mobile_alerts_table.c.status).label("mobile_status"),
            func.max(mobile_alerts_table.c.acknowledged_at).label("acknowledged_at"),
            func.max(users_table.c.full_name).label("ack_user_name"),
            func.max(users_table.c.email).label("ack_user_email"),
            func.max(mobile_alerts_table.c.ert_at).label("ert_at"),
            func.max(mobile_alerts_table.c.ert_justification).label("ert_justification")
        ).select_from(
            alerts_table.outerjoin(server_status_table)
            .outerjoin(active_escalations_table)
            .outerjoin(escalation_policies_table)
            .outerjoin(mobile_alerts_table)
            .outerjoin(users_table, mobile_alerts_table.c.acknowledged_by == users_table.c.id)
        )
        
        if filter == "active": 
            q = q.where(alerts_table.c.is_resolved == False)
        else: 
            q = q.where(alerts_table.c.is_resolved == True)
            
        res = db.execute(
            q.group_by(
                alerts_table.c.id, 
                server_status_table.c.name, 
                server_status_table.c.ip,
                escalation_policies_table.c.name
            ).order_by(desc(alerts_table.c.created_at)).offset(skip).limit(limit)
        ).fetchall()
        
        alerts = []
        for r in res:
            metric_raw = r.title or ""
            hardware_details = "N/A"
            if "." in metric_raw:
                parts = metric_raw.split(".")
                if len(parts) >= 3:
                    hardware_details = parts[2]
                elif parts[0] == 'hardware' and len(parts) >= 2:
                    hardware_details = "System"

            alerts.append({
                "id": r.id, 
                "alert_type": r.title,
                "title": r.title,
                "message": r.body,
                "body": r.body,
                "severity": "critical" if (r.severity or "").lower() == "error" else (r.severity or "info").lower(),
                "server_name": r.server_name or "System",
                "site_name": r.server_name or "System",
                "server_ip": r.server_ip or "",
                "hardware_details": hardware_details,
                "group_name": r.group_name or "SRE",
                "metric_value": format_metric_with_unit(r.title, r.metric_value),
                "threshold_value": format_metric_with_unit(r.title, r.threshold_value),
                "created_at": to_ist_str(r.created_at), 
                "resolved_at": to_ist_str(r.resolved_at),
                "is_resolved": r.is_resolved,
                "status": "resolved" if r.is_resolved else (r.mobile_status or "pending"),
                "mobile_status": r.mobile_status or "pending",
                "acknowledged_at": to_ist_str(r.acknowledged_at),
                "acknowledged_by_name": r.ack_user_name or r.ack_user_email or (r.acknowledged_at and "System") or "-",
                "ert_at": to_ist_str(r.ert_at),
                "ert_justification": r.ert_justification,
                "can_acknowledge": not r.is_resolved
            })
        return alerts
    except Exception as e:
        logger.error(f"Mobile API Alerts Error: {e}", exc_info=True)
        return []

@router.get("/active-alerts")
async def get_active_alerts_ui(skip: int = 0, limit: int = 50, db: Session = Depends(get_db)):
    """
    Get active alerts for Dashboard UI - ALIGNED WITH COMPLIANCE
    """
    try:
        since = datetime.utcnow() - timedelta(days=7)
        q = select(
            alerts_table.c.id, alerts_table.c.alert_type.label("title"), alerts_table.c.message.label("body"),
            alerts_table.c.severity, alerts_table.c.created_at, escalation_policies_table.c.name.label("group_name"),
            alerts_table.c.metric_value, alerts_table.c.threshold_value,
            func.max(mobile_alerts_table.c.status).label("mobile_status"), func.max(mobile_alerts_table.c.acknowledged_at).label("acknowledged_at"),
            func.max(users_table.c.full_name).label("ack_user_name"), func.max(users_table.c.email).label("ack_user_email"),
            func.max(mobile_alerts_table.c.ert_justification).label("ert_justification"),
            func.max(mobile_alerts_table.c.ert_at).label("ert_at"),
            server_status_table.c.name.label("server_name"), server_status_table.c.ip.label("server_ip")
        ).select_from(alerts_table.outerjoin(active_escalations_table).outerjoin(escalation_policies_table).outerjoin(mobile_alerts_table).outerjoin(users_table, mobile_alerts_table.c.acknowledged_by == users_table.c.id).outerjoin(server_status_table)) \
         .where(and_(alerts_table.c.is_resolved == False, alerts_table.c.created_at >= since)) \
         .group_by(alerts_table.c.id, escalation_policies_table.c.name, server_status_table.c.name, server_status_table.c.ip, alerts_table.c.metric_value, alerts_table.c.threshold_value) \
         .order_by(desc(alerts_table.c.created_at)).offset(skip).limit(limit)
        
        res = db.execute(q).fetchall()
        return [{
            "id": r.id, "title": r.title, "body": r.body, 
            "severity": "critical" if (r.severity or "").lower() == "error" else (r.severity or "info").lower(),
            "server_name": r.server_name or "System", "server_ip": r.server_ip or "",
            "group_name": r.group_name or "SRE", "status": r.mobile_status or "pending",
            "metric_value": format_metric_with_unit(r.title, r.metric_value),
            "threshold_value": format_metric_with_unit(r.title, r.threshold_value),
            "created_at": to_ist_str(r.created_at),
            "acknowledged_at": to_ist_str(r.acknowledged_at),
            "acknowledged_by_name": r.ack_user_name or r.ack_user_email or (r.acknowledged_at and "System") or "-",
            "ert_justification": r.ert_justification,
            "ert_at": to_ist_str(r.ert_at)
        } for r in res]
    except Exception as e:
        logger.error(f"Active Alerts UI Error: {e}")
        raise HTTPException(500, "Internal Error")

class AlertAckRequest(BaseModel):
    ert_minutes: int = 2 # Default 2 minutes
    justification: Optional[str] = None

@router.post("/alerts/{alert_id}/ack")
async def acknowledge_alert(alert_id: str, req: AlertAckRequest, db: Session = Depends(get_db), auth = Depends(get_current_user_token)):
    """
    Acknowledge an alert from mobile or web. 
    Handles both numeric DB IDs and string 'test_' IDs.
    """
    _, u = auth
    user_id = u['user_id']
    user_email = u['email']
    update_device_activity(db, user_id)

    try:
        # Handle 'test_' string IDs (Legacy/Direct)
        if str(alert_id).startswith("test_") or str(alert_id).lower() == "nan":
            logger.info(f"Test or NaN alert {alert_id} acknowledged by {user_email}")
            return {"status": "ok", "message": "Test alert acknowledged"}

        numeric_alert_id = int(alert_id)
        
        # 0. Check if this is a real alert in our DB
        alert_q = select(alerts_table).where(alerts_table.c.id == numeric_alert_id)
        alert_exists = db.execute(alert_q).fetchone()
        
        if not alert_exists:
            # If it's a number but NOT in our alerts table, it's a Test Alert (Timestamp ID)
            logger.info(f"Integer test alert {numeric_alert_id} acknowledged by {user_email}")
            db.execute(insert(audit_logs_table).values(
                user_id=user_id,
                action="Test Alert Acknowledged",
                resource_type="Mobile",
                details={"alert_id": numeric_alert_id, "user_email": user_email}
            ))
            db.commit()
            return {"status": "ok", "message": "Test alert acknowledged"}

        # Get alert details for mobile_alerts record
        alert_data = dict(alert_exists._mapping)
        title = f"Alert: {alert_data.get('alert_type', 'System')}"
        body = alert_data.get('message', 'No message provided')
        severity = alert_data.get('severity', 'info')

        # 1. Update/Create mobile_alerts entry (REAL ALERT)
        stmt = insert(mobile_alerts_table).values(
            alert_id=numeric_alert_id,
            user_id=user_id,
            title=title,
            body=body,
            severity=severity,
            status="acknowledged",
            acknowledged_by=user_id,
            acknowledged_at=datetime.utcnow(),
            ert_at=datetime.utcnow() + timedelta(minutes=req.ert_minutes),
            ert_justification=req.justification
        ).on_conflict_do_update(
            index_elements=['alert_id', 'user_id'],
            set_={
                "status": "acknowledged",
                "acknowledged_by": user_id,
                "acknowledged_at": datetime.utcnow(),
                "ert_at": datetime.utcnow() + timedelta(minutes=req.ert_minutes),
                "ert_justification": req.justification,
                "title": title,
                "body": body
            }
        )
        db.execute(stmt)
        
        # 2. Log to Audit Trail (detailed incident audit)
        audit_stmt = insert(incident_audit_trail_table).values(
            alert_id=numeric_alert_id,
            user_id=user_id,
            action="Acknowledge",
            details={
                "ert_minutes": req.ert_minutes, 
                "justification": req.justification,
                "user_name": user_email
            }
        )
        db.execute(audit_stmt)
        
        # 3. Update Escalation State
        db.execute(update(active_escalations_table).where(active_escalations_table.c.alert_id == numeric_alert_id).values(
            status="acknowledged",
            ert_at=datetime.utcnow() + timedelta(minutes=req.ert_minutes),
            ert_justification=req.justification,
            updated_at=datetime.utcnow()
        ))
        
        db.commit()
        
        # 4. Broadcast STOP RINGING to all mobile apps
        try:
            from app.utils.ws_broadcast import broadcast_ui_update
            broadcast_ui_update("alert_acknowledged", {"alert_id": numeric_alert_id, "user": user_email})
        except: pass
        
        return {"status": "ok"}
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid alert ID format: {alert_id}")
    except Exception as e:
        logger.error(f"Ack Error: {e}", exc_info=True)
        db.rollback()
        raise HTTPException(500, str(e))

@router.post("/logout")
async def logout_device(db: Session = Depends(get_db), auth = Depends(get_current_user_token)):
    """
    Logout: Marks the device as logged out and CLEARS the push token 
    so it no longer receives push notifications and shows Offline in Dashboard.
    """
    _, u = auth
    user_id = u['user_id']
    try:
        # Update device status and NULLify token to be 100% sure no more pushes go out (Ref: 020e9fd)
        db.execute(update(mobile_devices_table).where(mobile_devices_table.c.user_id == user_id).values(
            is_logged_in=False,
            push_token=None, 
            last_active_at=datetime.utcnow()
        ))
        
        # Audit Log
        db.execute(insert(audit_logs_table).values(
            user_id=user_id,
            action="Mobile App Logout",
            resource_type="Mobile",
            details={"email": u['email'], "status": "Offline"}
        ))
        
        db.commit()
        return {"status": "ok"}
    except Exception as e:
        db.rollback()
        logger.error(f"Logout Error: {e}")
        raise HTTPException(500, "Logout failed")

@router.get("/alerts/{alert_id}/call-flow")
async def get_alert_call_flow(alert_id: int, db: Session = Depends(get_db)):
    """
    Get the full lifecycle/audit trail of an alert
    """
    q = select(
        incident_audit_trail_table.c.id,
        incident_audit_trail_table.c.action,
        incident_audit_trail_table.c.details,
        incident_audit_trail_table.c.created_at,
        users_table.c.full_name.label("user_name"),
        users_table.c.email.label("user_email")
    ).select_from(incident_audit_trail_table.outerjoin(users_table)).where(incident_audit_trail_table.c.alert_id == alert_id).order_by(incident_audit_trail_table.c.created_at.asc())
    
    res = db.execute(q).fetchall()
    return [{
        "id": r.id,
        "action": r.action,
        "details": r.details,
        "timestamp": to_ist_str(r.created_at),
        "user": r.user_name or r.user_email or "System"
    } for r in res]

@router.get("/history")
async def get_alert_history(limit: int = 100, db: Session = Depends(get_db)):
    # Legacy support, redirect to /alerts?filter=resolved
    return await get_alerts(filter="resolved", limit=limit, db=db)

# Registration and other mobile routes follow...
@router.post("/register")
async def register_device(req: dict, db: Session = Depends(get_db), auth = Depends(get_current_user_token)):
    _, u = auth
    user_id = u['user_id']
    push_token = req.get("push_token")
    device_os = req.get("device_os", "android")
    device_name = req.get("device_name", "Unknown")
    app_version = req.get("app_version", "1.0.0")

    try:
        # 1. Check if device already exists for this user
        existing = db.execute(select(mobile_devices_table).where(mobile_devices_table.c.user_id == user_id)).fetchone()
        
        if existing:
            # Update
            db.execute(update(mobile_devices_table).where(mobile_devices_table.c.user_id == user_id).values(
                push_token=push_token,
                device_os=device_os,
                device_name=device_name,
                app_version=app_version,
                is_logged_in=True,
                last_active_at=datetime.utcnow()
            ))
        else:
            # Insert
            db.execute(insert(mobile_devices_table).values(
                user_id=user_id,
                push_token=push_token,
                device_os=device_os,
                device_name=device_name,
                app_version=app_version,
                is_logged_in=True,
                last_active_at=datetime.utcnow(),
                created_at=datetime.utcnow()
            ))
        
        # Audit Log
        db.execute(insert(audit_logs_table).values(
            user_id=user_id,
            action="Mobile Device Registered",
            resource_type="Mobile",
            details={
                "push_token": push_token,
                "device_os": device_os,
                "device_name": device_name,
                "app_version": app_version
            }
        ))
        
        db.commit()
        return {"status": "ok"}
    except Exception as e:
        db.rollback()
        logger.error(f"Device Registration Error: {e}", exc_info=True)
        raise HTTPException(500, str(e))

@router.post("/test-push")
async def test_push(db: Session = Depends(get_db), auth = Depends(get_current_user_token)):
    _, u = auth
    # FIXED: Use pure integer ID so parseInt() on mobile app works (Ref: 020e9fd logic)
    test_id = int(datetime.utcnow().timestamp())
    success = await send_push_notification(
        user_ids=[u['user_id']],
        title="🚨 TEST CRITICAL ALERT",
        body=f"This is a test critical alert for {u['email']} to verify Nokia ringtone and voice.",
        data={
            "type": "call", 
            "alert_id": str(test_id),
            "site_name": "TEST-DEVICE",
            "server_ip": "192.168.1.100",
            "alert_type": "Connectivity Test",
            "hardware_details": "Eth0 / Interface",
            "message": f"This is a test critical alert from SMC LAMA to verify Nokia ringtone and voice. Triggered by {u['email']}.",
            "voice_alert": f"Attention Required: Test Device 192 dot 168 dot 1 dot 100. Connectivity Test of Interface Eth 0 is down and is in critical state, kindly check and resolve.",
            "alert_time": to_ist_str(datetime.utcnow())
        },
        severity="critical"
    )
    
    # Audit Log
    db.execute(insert(audit_logs_table).values(
        user_id=u['user_id'],
        action="Test Push Attempted",
        resource_type="Mobile",
        details={
            "status": "success" if success else "failed",
            "targets": [u['user_id']],
            "title": "Test Alert",
            "severity": "critical",
            "test_id": test_id
        }
    ))
    db.commit()
    
    return {"status": "ok" if success else "failed"}

@router.post("/test-push/{user_id}")
async def test_push_for_user(user_id: int, db: Session = Depends(get_db), auth = Depends(get_current_user_token)):
    _, u = auth
    if u['role'] != "admin": raise HTTPException(403)
    
    # FIXED: Use pure integer ID so parseInt() on mobile app works
    test_id = int(datetime.utcnow().timestamp())
    success = await send_push_notification(
        user_ids=[user_id],
        title="🚨 TEST VOICE ALERT",
        body=f"This is a manual test voice alert triggered by {u['email']}.",
        data={
            "type": "call", 
            "alert_id": str(test_id),
            "site_name": "TEST-SERVER",
            "server_ip": "172.16.0.50",
            "alert_type": "Manual Test",
            "hardware_details": "/dev/sda1 (Root)",
            "message": f"This is a manual test voice alert from SMC LAMA. Triggered by {u['email']}.",
            "voice_alert": f"Attention Required: Test Server 172 dot 16 dot 0 dot 50. Manual Test of Drive Dev Sda 1 is critical and is in critical state, kindly check and resolve.",
            "alert_time": to_ist_str(datetime.utcnow())
        },
        severity="critical"
    )
    
    # Audit Log
    db.execute(insert(audit_logs_table).values(
        user_id=u['user_id'],
        action="Manual Test Push Attempted",
        resource_type="Mobile",
        details={
            "status": "success" if success else "failed",
            "target_user_id": user_id,
            "title": "Test Alert",
            "severity": "critical",
            "test_id": test_id
        }
    ))
    db.commit()
    
    return {"status": "ok" if success else "failed"}

@router.get("/groups")
async def get_groups(db: Session = Depends(get_db)):
    try:
        res = db.execute(select(escalation_policies_table)).fetchall()
        output = []
        for r in res:
            d = dict(r._mapping)
            # Map 'steps' from DB to 'escalation_chain' for frontend
            d['escalation_chain'] = d.get('steps', [])
            output.append(d)
        return output
    except Exception as e:
        logger.error(f"Get Groups Error: {e}")
        return []

@router.post("/groups")
async def create_group(group: dict, db: Session = Depends(get_db), auth = Depends(get_current_user_token)):
    _, u = auth
    if u['role'] != "admin": raise HTTPException(403)
    try:
        # Map 'escalation_chain' from frontend to 'steps' for backend
        steps = group.get('escalation_chain', group.get('steps', []))
        stmt = insert(escalation_policies_table).values(
            name=group['name'],
            steps=steps,
            enabled=group.get('enabled', True)
        )
        db.execute(stmt)
        db.commit()
        return {"status": "ok"}
    except Exception as e:
        logger.error(f"Create Group Error: {e}")
        db.rollback()
        raise HTTPException(500, str(e))

@router.put("/groups/{group_id}")
async def update_group(group_id: int, group: dict, db: Session = Depends(get_db), auth = Depends(get_current_user_token)):
    _, u = auth
    if u['role'] != "admin": raise HTTPException(403)
    try:
        steps = group.get('escalation_chain', group.get('steps', []))
        stmt = update(escalation_policies_table).where(escalation_policies_table.c.id == group_id).values(
            name=group['name'],
            steps=steps,
            enabled=group.get('enabled', True),
            updated_at=datetime.utcnow()
        )
        db.execute(stmt)
        db.commit()
        return {"status": "ok"}
    except Exception as e:
        logger.error(f"Update Group Error: {e}")
        db.rollback()
        raise HTTPException(500, str(e))

@router.delete("/groups/{group_id}")
async def delete_group(group_id: int, db: Session = Depends(get_db), auth = Depends(get_current_user_token)):
    _, u = auth
    if u['role'] != "admin": raise HTTPException(403)
    try:
        db.execute(delete(escalation_policies_table).where(escalation_policies_table.c.id == group_id))
        db.commit()
        return {"status": "ok"}
    except Exception as e:
        logger.error(f"Delete Group Error: {e}")
        db.rollback()
        raise HTTPException(500, str(e))

@router.get("/contacts")
async def get_contacts(db: Session = Depends(get_db)):
    try:
        # 1. Fetch all users and their devices
        q = select(
            users_table.c.id, 
            users_table.c.full_name, 
            users_table.c.email, 
            users_table.c.role,
            mobile_devices_table.c.device_os, 
            mobile_devices_table.c.id.label("device_id"),
            mobile_devices_table.c.is_logged_in, 
            mobile_devices_table.c.last_active_at
        ).select_from(users_table.outerjoin(mobile_devices_table, users_table.c.id == mobile_devices_table.c.user_id))
        
        user_results = db.execute(q).fetchall()
        
        # 2. Fetch all escalation policies to map users to groups (e.g., SRE)
        policies = db.execute(select(escalation_policies_table)).fetchall()
        user_to_groups = {}
        for p in policies:
            policy_data = dict(p._mapping)
            group_name = policy_data.get("name", "Unknown")
            steps = policy_data.get("steps", [])
            
            # Robust JSON handling: Convert string to list if necessary
            if isinstance(steps, str):
                try:
                    import json
                    steps = json.loads(steps)
                except:
                    steps = []

            # Extract all user_ids mentioned in any step of this policy
            if isinstance(steps, list):
                for step in steps:
                    if isinstance(step, dict):
                        notify_list = step.get("notify", [])
                        for uid in notify_list:
                            # Ensure uid is an integer for matching
                            try:
                                uid_int = int(uid)
                                if uid_int not in user_to_groups: user_to_groups[uid_int] = []
                                if group_name not in user_to_groups[uid_int]:
                                    user_to_groups[uid_int].append(group_name)
                            except: pass

        output = []
        now = datetime.utcnow()
        for row in user_results:
            uid = row[0]
            groups = user_to_groups.get(uid, [])
            group_str = f"Group {', '.join(groups)}" if groups else None
            
            # ONLINE LOGIC: must be is_logged_in AND active within last 15 minutes
            is_logged_in_flag = bool(row[6]) if row[6] is not None else False
            last_active = row[7]
            
            # Determine Online status strictly
            is_online = False
            if is_logged_in_flag and last_active:
                diff = (now - last_active).total_seconds() / 60
                if diff <= 15: # 15 minute threshold for heartbeat/activity
                    is_online = True

            d = {
                "id": uid,
                "full_name": row[1],
                "email": row[2],
                "role": row[3],
                "device_os": row[4],
                "device_id": row[5],
                "is_logged_in": is_logged_in_flag,
                "is_online": is_online, # New calculated field for UI
                "last_active_at": to_ist_str(last_active) if last_active else None,
                "group_name": group_str
            }
            output.append(d)
        
        return output
    except Exception as e:
        logger.error(f"Get Contacts Error: {e}", exc_info=True)
        return []

@router.get("/settings")
async def get_settings(db: Session = Depends(get_db)):
    try:
        res = db.execute(select(alert_config_table).where(alert_config_table.c.alert_channel == "mobile")).fetchone()
        if res:
            return dict(res._mapping)
        return {"enabled": False}
    except Exception as e:
        logger.error(f"Get Settings Error: {e}")
        return {"enabled": False}

@router.post("/settings")
async def update_settings(s: dict, db: Session = Depends(get_db), auth = Depends(get_current_user_token)):
    _, u = auth
    if u['role'] != "admin": raise HTTPException(403)
    db.execute(update(alert_config_table).where(alert_config_table.c.alert_channel == "mobile").values(enabled=s.enabled))
    db.commit()
    return {"status": "ok"}
