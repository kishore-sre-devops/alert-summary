from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import os
import asyncio
import httpx

# Fix SSL verification for Firebase Admin SDK in environments with SSL inspection (Fortinet)
os.environ['REQUESTS_CA_BUNDLE'] = '/etc/ssl/certs/ca-certificates.crt'
os.environ['HTTPLIB2_CA_CERTS'] = '/etc/ssl/certs/ca-certificates.crt'

from sqlalchemy.orm import Session
from sqlalchemy import func, case, or_
from pydantic import BaseModel, Field
from typing import List, Optional, Union
from database import engine, get_db, Base
from models import (
    Alert, Comment, User, UserGroup, SilenceRule, DeviceToken, Setting,
    PrometheusServer, AlertGroupConfig, AlertRule, AlertState, PrometheusTarget
)
from datetime import datetime, timedelta
import re
import firebase_admin
from firebase_admin import credentials, messaging as fcm_messaging

# Initialize Firebase
try:
    cred = credentials.Certificate("firebase-key.json")
    firebase_admin.initialize_app(cred)
    print("Firebase Admin initialized successfully")
except Exception as e:
    print(f"Error initializing Firebase: {e}")

# Create tables
Base.metadata.create_all(bind=engine)

from fastapi.staticfiles import StaticFiles
import os

# Create static directory if it doesn't exist
if not os.path.exists("static"):
    os.makedirs("static")

app = FastAPI(title="SMC Alert Summary Dashboard API")

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Pydantic models for request/response
class UserCreate(BaseModel):
    name: str
    email: str

class UserLogin(BaseModel):
    email: str

class UserGroupOut(BaseModel):
    id: int
    group_name: str
    class Config:
        orm_mode = True

class UserOut(BaseModel):
    id: int
    name: str
    email: str
    device_name: Optional[str] = None
    os_version: Optional[str] = None
    groups: List[UserGroupOut] = []
    class Config:
        orm_mode = True

class GroupUpdate(BaseModel):
    groups: List[str]

class SettingUpdate(BaseModel):
    key: str
    value: str

class SilenceRuleCreate(BaseModel):
    instance: Optional[str] = None
    alertname: Optional[str] = None
    company: Optional[str] = None
    group1: Optional[str] = None
    start_time: datetime
    end_time: datetime

class SilenceRuleOut(BaseModel):
    id: int
    instance: Optional[str]
    alertname: Optional[str]
    company: Optional[str]
    group1: Optional[str]
    start_time: datetime
    end_time: datetime
    created_at: datetime
    is_active: int
    class Config:
        orm_mode = True

class DeviceTokenCreate(BaseModel):
    token: str
    user_id: Optional[int] = None
    device_name: Optional[str] = None
    os_version: Optional[str] = None

class AlertCreate(BaseModel):
    time: Optional[datetime] = None
    received_at: Optional[datetime] = None
    timestamp: Optional[datetime] = None
    status: Optional[str] = "firing"
    startsAt: Optional[datetime] = None
    endsAt: Optional[datetime] = None
    AlertName: Optional[str] = None
    alertname: Optional[str] = None
    Instance: Optional[str] = None
    instance: Optional[str] = None
    job_name: Optional[str] = None
    job: Optional[str] = None
    Group: Optional[str] = None
    group: Optional[str] = None
    group1: Optional[str] = ""
    Company: Optional[str] = None
    company: Optional[str] = None
    Asset: Optional[str] = None
    asset: Optional[str] = None
    volume_mountpoint: Optional[str] = None
    disk_info: Optional[str] = None
    disk_info_script: Optional[str] = Field(None, alias="Volume / MountPoint")
    cluster: Optional[str] = None
    Severity: Optional[str] = None
    severity: Optional[str] = None
    fingerprint: Optional[str] = None
    summary: Optional[str] = None
    description: Optional[str] = None

class CommentCreate(BaseModel):
    content: str

class CommentOut(BaseModel):
    id: int
    alert_id: int
    content: str
    created_at: datetime

    class Config:
        orm_mode = True

class PrometheusServerCreate(BaseModel):
    name: str
    url: str
    is_active: Optional[int] = 1

class PrometheusServerOut(BaseModel):
    id: int
    name: str
    url: str
    is_active: int
    status: Optional[str]
    last_checked: Optional[datetime]
    class Config:
        orm_mode = True

class AlertGroupConfigCreate(BaseModel):
    name: str
    emails: Optional[str] = None
    slack_webhook: Optional[str] = None
    voice_enabled: Optional[int] = 0

class AlertGroupConfigOut(BaseModel):
    id: int
    name: str
    emails: Optional[str]
    slack_webhook: Optional[str]
    voice_enabled: int
    class Config:
        orm_mode = True

class AlertRuleCreate(BaseModel):
    name: str
    promql: str
    severity: str
    summary: Optional[str] = None
    description: Optional[str] = None
    group_id: Optional[int] = None # Keeping for backward compatibility
    group_ids: Optional[List[int]] = [] # For multiple groups
    duration: str
    is_active: Optional[int] = 1

class AlertRuleOut(BaseModel):
    id: int
    name: str
    promql: str
    severity: str
    summary: Optional[str]
    description: Optional[str]
    group_id: Optional[int]
    duration: str
    is_active: int
    group: Optional[AlertGroupConfigOut]
    notification_groups: List[AlertGroupConfigOut] = []
    class Config:
        orm_mode = True

class PrometheusTargetOut(BaseModel):
    id: int
    instance: str
    job: Optional[str]
    group_name: Optional[str]
    group1: Optional[str]
    company: Optional[str]
    asset: Optional[str]
    server_id: int
    last_seen: datetime
    class Config:
        orm_mode = True

class AlertStateOut(BaseModel):
    id: int
    rule_id: Optional[int]
    alert_name: str
    instance: str
    cluster: str
    group_name: Optional[str]
    team: Optional[str]
    status: str
    severity: str
    starts_at: datetime
    ends_at: Optional[datetime]
    last_notified_at: Optional[datetime]
    fingerprint: str
    acknowledged_by_user: Optional[UserOut] = None
    comments: List[CommentOut] = []
    alert_id: Optional[int] = None
    class Config:
        orm_mode = True

class AlertOut(BaseModel):
    id: int
    received_at: datetime
    alertname: str
    instance: str
    job: Optional[str]
    company: Optional[str]
    group_name: Optional[str]
    group1: Optional[str]
    asset: Optional[str]
    disk_info: Optional[str]
    cluster: Optional[str]
    status: str
    severity: Optional[str]
    starts_at: Optional[datetime]
    ends_at: Optional[datetime]
    fingerprint: str
    created_at: datetime
    updated_at: datetime
    is_silenced: int = 0
    acknowledged_by_id: Optional[int]
    acknowledged_at: Optional[datetime]
    acknowledged_by_user: Optional[UserOut]
    comments: List[CommentOut] = []
    
    # Optional improvement: Duration calculation
    duration_seconds: Optional[float] = None

    @classmethod
    def from_orm(cls, obj):
        # Calculate duration if both starts_at and ends_at are present
        if obj.starts_at and obj.ends_at:
            duration = (obj.ends_at - obj.starts_at).total_seconds()
            setattr(obj, 'duration_seconds', duration)
        return super().from_orm(obj)

    class Config:
        orm_mode = True

def send_push_notifications(alert: Alert, db: Session):
    try:
        # Filter tokens: Only send to users who belong to the alert's group OR the "All" group
        # If the alert has no group, we fallback to all users in the "All" group
        target_group = alert.group_name or "Unknown"

        tokens_query = db.query(DeviceToken.token).join(User, DeviceToken.user_id == User.id).join(UserGroup, User.id == UserGroup.user_id)

        # Filter logic: User group matches Alert group OR User is in "All" group
        tokens_data = tokens_query.filter(
            or_(
                UserGroup.group_name == target_group,
                UserGroup.group_name == "All"
            )
        ).distinct().all()

        tokens = [t[0] for t in tokens_data]

        if not tokens:
            print(f"ℹ️ No mobile users subscribed to group '{target_group}'. Notification skipped.")
            return

        spoken_msg = f"SMC Alert! {alert.severity or 'CRITICAL'} Alert! {alert.alertname} on {alert.instance}."

        for token in tokens:
            try:
                message = fcm_messaging.Message(
                    token=token,
                    data={
                        "severity": (alert.severity or "critical").lower(),
                        "title": f"🚨 {alert.alertname}",
                        "message": f"{alert.severity or 'CRITICAL'}: {alert.alertname} on {alert.instance}",
                        "body": f"{alert.severity or 'CRITICAL'}: {alert.alertname} on {alert.instance}",
                        "site_name": alert.instance,
                        "alert_type": alert.alertname,
                        "voice_alert": spoken_msg,
                        "status": alert.status,
                        "alert_id": str(alert.id)
                    },
                    android=fcm_messaging.AndroidConfig(
                        priority='high'
                    )
                )
                response = fcm_messaging.send(message)
                print(f"Successfully sent notification to {token}: {response}")
            except Exception as token_err:
                print(f"Failed to send notification to {token}: {token_err}")
    except Exception as e:
        print(f"Error in send_push_notifications: {e}")

# Global memory to store instance metadata
INSTANCE_MEMORY = {}

def update_instance_memory(instance, job, group, group1, company, asset, db: Session):
    if not instance or instance == "UnknownInstance": return
    
    # Try to load from global memory first
    if instance not in INSTANCE_MEMORY:
        # Initial load for this instance from database if not in memory
        last_meta = db.query(Alert).filter(Alert.instance == instance).order_by(Alert.received_at.desc()).first()
        if last_meta:
            INSTANCE_MEMORY[instance] = {
                "job": last_meta.job,
                "group": last_meta.group_name,
                "group1": last_meta.group1,
                "company": last_meta.company,
                "asset": last_meta.asset
            }
        else:
            INSTANCE_MEMORY[instance] = {"job": None, "group": None, "group1": None, "company": None, "asset": None}

    # Update memory with NEW non-empty values
    mem = INSTANCE_MEMORY[instance]
    if job: mem["job"] = job
    if group: mem["group"] = group
    if group1: mem["group1"] = group1
    if company: mem["company"] = company
    if asset: mem["asset"] = asset

@app.get("/")
def read_root():
    return {"status": "Healthy"}

@app.post("/api/alerts")
def create_alerts(alert_data: Union[List[dict], dict, AlertCreate], db: Session = Depends(get_db)):
    # Normalize input to a list of AlertCreate objects
    alerts_to_process = []
    
    if isinstance(alert_data, list):
        for item in alert_data:
            if isinstance(item, dict):
                alerts_to_process.append(AlertCreate(**item))
            else:
                alerts_to_process.append(item)
    elif isinstance(alert_data, dict) and "alerts" in alert_data:
        # Handle Alertmanager payload
        am_alerts = alert_data["alerts"]
        for am_alert in am_alerts:
            if hasattr(am_alert, "get"):
                labels = am_alert.get("labels", {})
                annotations = am_alert.get("annotations", {})
                status_val = am_alert.get("status", "firing")
                starts_at = am_alert.get("startsAt")
                ends_at = am_alert.get("endsAt")
                fingerprint = am_alert.get("fingerprint")
            else:
                labels = getattr(am_alert, "labels", {})
                annotations = getattr(am_alert, "annotations", {})
                status_val = getattr(am_alert, "status", "firing")
                starts_at = getattr(am_alert, "startsAt", None)
                ends_at = getattr(am_alert, "endsAt", None)
                fingerprint = getattr(am_alert, "fingerprint", None)

            flat_alert = AlertCreate(
                status=status_val,
                startsAt=starts_at,
                endsAt=ends_at,
                alertname=labels.get("alertname"),
                instance=labels.get("instance"),
                job=labels.get("job"),
                severity=labels.get("severity"),
                group=labels.get("group"),
                company=labels.get("company"),
                fingerprint=fingerprint
            )
            alerts_to_process.append(flat_alert)
    elif isinstance(alert_data, AlertCreate):
        alerts_to_process = [alert_data]
    elif isinstance(alert_data, dict):
        alerts_to_process = [AlertCreate(**alert_data)]
    else:
        return {"message": "Invalid alert format"}, 422

    processed_alerts = []
    for alert_item in alerts_to_process:
        # Normalize incoming data from script keys to standard internal names
        if alert_item.time and not alert_item.received_at: alert_item.received_at = alert_item.time
        if alert_item.AlertName and not alert_item.alertname: alert_item.alertname = alert_item.AlertName
        if alert_item.Instance and not alert_item.instance: alert_item.instance = alert_item.Instance
        if alert_item.job_name and not alert_item.job: alert_item.job = alert_item.job_name
        if alert_item.Group and not alert_item.group: alert_item.group = alert_item.Group
        if alert_item.Company and not alert_item.company: alert_item.company = alert_item.Company
        if alert_item.Asset and not alert_item.asset: alert_item.asset = alert_item.Asset
        if alert_item.volume_mountpoint and not alert_item.disk_info: alert_item.disk_info = alert_item.volume_mountpoint
        if alert_item.disk_info_script and not alert_item.disk_info: alert_item.disk_info = alert_item.disk_info_script
        if alert_item.Severity and not alert_item.severity: alert_item.severity = alert_item.Severity

        # Convert "unknown" to blank string
        for field in ['alertname', 'instance', 'job', 'company', 'group', 'asset', 'disk_info', 'severity', 'cluster']:
            val = getattr(alert_item, field, None)
            if isinstance(val, str) and val.lower() == "unknown":
                setattr(alert_item, field, "")

        # SMART EXTRACTION: If fields are empty but description is present, try to parse them
        if alert_item.description:
            import re
            desc = alert_item.description
            
            def extract(pattern, current_val):
                if current_val: return current_val # Keep existing
                # Use a non-greedy match that stops at space or closing bracket
                match = re.search(pattern, desc, re.IGNORECASE)
                if match:
                    val = match.group(1).strip()
                    # If it's part of a map[...], stop at next field or ]
                    # Look for the first space that is followed by a word and a colon (key of next field)
                    # or the closing bracket
                    end_match = re.search(r" |\]", val)
                    if end_match:
                        # Re-run with more restrictive match
                        match = re.search(pattern.replace("(.*)", "([^ \\]]*)"), desc, re.IGNORECASE)
                        return match.group(1).strip() if match else val
                    return val
                return current_val

            alert_item.job = extract(r"Job:\s*(.*)", alert_item.job)
            alert_item.group = extract(r"Group:\s*(.*)", alert_item.group)
            alert_item.group1 = extract(r"Group1:\s*(.*)", alert_item.group1)
            alert_item.company = extract(r"Company:\s*(.*)", alert_item.company)
            alert_item.asset = extract(r"Asset:\s*(.*)", alert_item.asset)
            alert_item.instance = extract(r"Instance:\s*(.*)", alert_item.instance)

        # INSTANCE MEMORY: Fill in blanks from last known data for this IP
        update_instance_memory(alert_item.instance, alert_item.job, alert_item.group, alert_item.group1, alert_item.company, alert_item.asset, db)
        
        mem = INSTANCE_MEMORY.get(alert_item.instance)
        if mem:
            if not alert_item.job: alert_item.job = mem["job"]
            if not alert_item.group: alert_item.group = mem["group"]
            if not alert_item.group1: alert_item.group1 = mem["group1"]
            if not alert_item.company: alert_item.company = mem["company"]
            if not alert_item.asset: alert_item.asset = mem["asset"]

        # Fallback for missing essential fields
        if not alert_item.alertname: alert_item.alertname = "UnknownAlert"
        if not alert_item.instance: alert_item.instance = "UnknownInstance"

        fingerprint_val = alert_item.fingerprint
        if not fingerprint_val:
            fingerprint_val = f"{alert_item.company or 'unknown'}_{alert_item.job or 'unknown'}_{alert_item.group or 'unknown'}_{alert_item.alertname}_{alert_item.instance}"

        # Check for matching silence rules
        now = datetime.utcnow()
        active_rules = db.query(SilenceRule).filter(
            SilenceRule.start_time <= now,
            SilenceRule.end_time >= now,
            SilenceRule.is_active == 1
        ).all()
        
        is_silenced_val = 0
        for rule in active_rules:
            match = True
            if rule.instance and rule.instance.lower() not in (alert_item.instance or "").lower():
                match = False
            if rule.alertname and rule.alertname.lower() not in (alert_item.alertname or "").lower():
                match = False
            if rule.company and rule.company.lower() not in (alert_item.company or "").lower():
                match = False
            if rule.group1 and rule.group1.lower() not in (alert_item.group1 or "").lower():
                match = False
            
            if match:
                is_silenced_val = 1
                break

        # DEDUPLICATION LOGIC: Check if same alert at same time exists
        received_at_val = alert_item.received_at or alert_item.timestamp or datetime.utcnow()
        
        # Check if already in DB
        existing_alert = db.query(Alert).filter(
            Alert.received_at == received_at_val,
            Alert.alertname == alert_item.alertname,
            Alert.instance == alert_item.instance
        ).first()

        if existing_alert:
            processed_alerts.append(existing_alert)
            continue

        # Check if already processed in this batch (to handle duplicates within the same request)
        is_duplicate_in_batch = False
        for a in processed_alerts:
            if (a.received_at == received_at_val and 
                a.alertname == alert_item.alertname and 
                a.instance == alert_item.instance):
                is_duplicate_in_batch = True
                break
        
        if is_duplicate_in_batch:
            continue

        # Always INSERT new row
        db_alert = Alert(
            received_at=received_at_val,
            alertname=alert_item.alertname,
            instance=alert_item.instance,
            job=alert_item.job,
            company=alert_item.company,
            group_name=alert_item.group,
            group1=alert_item.group1 or "",
            asset=alert_item.asset,
            disk_info=alert_item.disk_info,
            status=alert_item.status,
            severity=alert_item.severity,
            starts_at=alert_item.startsAt,
            ends_at=alert_item.endsAt,
            fingerprint=f"{fingerprint_val}_{datetime.utcnow().timestamp()}", # Make fingerprint unique to allow repeat
            is_silenced=is_silenced_val
        )
        db.add(db_alert)
        
        processed_alerts.append(db_alert)

    db.commit()
    for a in processed_alerts:
        db.refresh(a)
        # Send push notification for firing alerts
        if a.status == "firing" and (a.is_silenced == 0 or a.is_silenced is None):
            send_push_notifications(a, db)
    
    if len(processed_alerts) == 1:
        return processed_alerts[0]
    return {"message": f"Processed {len(processed_alerts)} alerts"}

def apply_alert_filters(query, start_date, end_date, alertname, instance, job, group, disk_info, asset, status, severity, include_silenced=False, company=None, group1=None):
    from sqlalchemy import and_, not_, or_
    
    if not include_silenced:
        query = query.filter(or_(Alert.is_silenced == 0, Alert.is_silenced == None))
    
    # Global Filter Logic: Hide Warning and Info except for LAMA group
    # 1. Hide alerts if Severity is Warning/Info
    # 2. UNLESS Group name contains "LAMA"
    
    # Simple logic: (Severity NOT LIKE Warning AND Severity NOT LIKE Info) OR (Group LIKE LAMA)
    # We also handle NULLs by considering them NOT Warning/Info
    query = query.filter(
        or_(
            and_(
                or_(Alert.severity == None, not_(Alert.severity.ilike("%warning%"))),
                or_(Alert.severity == None, not_(Alert.severity.ilike("%info%")))
            ),
            Alert.group_name.ilike("%lama%")
        )
    )

    if start_date: query = query.filter(Alert.received_at >= start_date)
    if end_date: query = query.filter(Alert.received_at <= end_date)
    if alertname: query = query.filter(Alert.alertname.ilike(f"%{alertname}%"))
    if instance: query = query.filter(Alert.instance.ilike(f"%{instance}%"))
    if job: query = query.filter(Alert.job.ilike(f"%{job}%"))
    if group: query = query.filter(Alert.group_name.ilike(f"%{group}%"))
    if group1: query = query.filter(Alert.group1.ilike(f"%{group1}%"))
    if company: query = query.filter(Alert.company.ilike(f"%{company}%"))
    if disk_info: query = query.filter(Alert.disk_info.ilike(f"%{disk_info}%"))
    if asset: query = query.filter(Alert.asset.ilike(f"%{asset}%"))
    if status and status != 'all': query = query.filter(Alert.status.ilike(f"%{status}%"))
    if severity: query = query.filter(Alert.severity.ilike(f"%{severity}%"))
    return query

@app.get("/api/metrics")
def get_metrics(
    start_date: Optional[datetime] = None, 
    end_date: Optional[datetime] = None, 
    alertname: Optional[str] = None,
    instance: Optional[str] = None,
    job: Optional[str] = None,
    group: Optional[str] = None,
    group1: Optional[str] = None,
    company: Optional[str] = None,
    disk_info: Optional[str] = None,
    asset: Optional[str] = None,
    status: Optional[str] = None,
    severity: Optional[str] = None,
    include_silenced: bool = False,
    db: Session = Depends(get_db)
):
    from sqlalchemy.orm import joinedload
    
    # Base query for counts
    base_query = db.query(Alert)
    base_query = apply_alert_filters(base_query, start_date, end_date, alertname, instance, job, group, disk_info, asset, None, severity, include_silenced, company, group1)
    
    firing_count = base_query.filter(Alert.status == "firing").count()
    resolved_count = base_query.filter(Alert.status == "resolved").count()
    
    recent_query = db.query(Alert).options(joinedload(Alert.comments), joinedload(Alert.acknowledged_by_user))
    recent_query = apply_alert_filters(recent_query, start_date, end_date, alertname, instance, job, group, disk_info, asset, status, severity, include_silenced, company, group1)
    recent_alerts = recent_query.order_by(Alert.received_at.desc()).limit(500).all()
    
    return {
        "firing": firing_count,
        "resolved": resolved_count,
        "recent_alerts": recent_alerts
    }

@app.get("/api/alerts/history")
def get_alert_history(
    days: int = 7,
    db: Session = Depends(get_db)
):
    from sqlalchemy import func, cast, Date
    start_date = datetime.utcnow() - timedelta(days=days)
    
    # Query for daily counts
    query = db.query(
        func.date(Alert.received_at).label('date'),
        Alert.status,
        func.count(Alert.id).label('count')
    ).filter(Alert.received_at >= start_date)
    
    # Apply global filters if needed, but for history we might want the full picture
    # However, let's stay consistent with other filters if applicable
    query = apply_alert_filters(query, start_date, None, None, None, None, None, None, None, None, None, False, None, None)
    
    results = query.group_by(func.date(Alert.received_at), Alert.status).all()
    
    # Format data for frontend (e.g., recharts)
    history_map = {}
    for r in results:
        date_str = r.date.strftime("%Y-%m-%d") if r.date else "Unknown"
        if date_str not in history_map:
            history_map[date_str] = {"date": date_str, "firing": 0, "resolved": 0}
        
        if r.status == "firing":
            history_map[date_str]["firing"] = r.count
        elif r.status == "resolved":
            history_map[date_str]["resolved"] = r.count
            
    # Convert to sorted list
    history_list = sorted(history_map.values(), key=lambda x: x["date"])
    return history_list

@app.post("/api/login", response_model=UserOut)
def login(login_data: UserLogin, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == login_data.email).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user

@app.post("/api/google-login", response_model=UserOut)
def google_login(data: dict, db: Session = Depends(get_db)):
    from google.oauth2 import id_token
    from google.auth.transport import requests as google_requests

    token = data.get("token")
    if not token:
        raise HTTPException(status_code=400, detail="Token is required")

    try:
        CLIENT_ID = "655248995621-mf0gp9tb3omc7dfjr71kft8qr30ucjr2.apps.googleusercontent.com"
        id_info = id_token.verify_oauth2_token(token, google_requests.Request(), CLIENT_ID)
        email = id_info.get('email')
        if not email:
            raise HTTPException(status_code=400, detail="Google token does not contain email")
        
        user = db.query(User).filter(User.email == email).first()
        device_name = data.get("device_name")
        os_version = data.get("os_version")

        if not user:
            name = id_info.get('name', email.split('@')[0])
            user = User(name=name, email=email, device_name=device_name, os_version=os_version)
            db.add(user)
        else:
            if device_name: user.device_name = device_name
            if os_version: user.os_version = os_version
        
        db.commit()
        db.refresh(user)
        return user
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Invalid Google token: {str(e)}")

@app.post("/api/alerts/{alert_id}/acknowledge")
def acknowledge_alert(alert_id: int, user_data: dict, db: Session = Depends(get_db)):
    user_id = user_data.get("user_id")
    if not user_id:
        raise HTTPException(status_code=400, detail="user_id is required")
    db_alert = db.query(Alert).filter(Alert.id == alert_id).first()
    if not db_alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    db_alert.acknowledged_by_id = user_id
    db_alert.acknowledged_at = datetime.utcnow()
    db.commit()
    return {"message": "Alert acknowledged"}

@app.post("/api/alerts/{alert_id}/silence")
def silence_alert(alert_id: int, db: Session = Depends(get_db)):
    db_alert = db.query(Alert).filter(Alert.id == alert_id).first()
    if not db_alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    db_alert.is_silenced = 1
    db.commit()
    return {"message": "Alert silenced"}

@app.post("/api/alerts/{alert_id}/unsilence")
def unsilence_alert(alert_id: int, db: Session = Depends(get_db)):
    db_alert = db.query(Alert).filter(Alert.id == alert_id).first()
    if not db_alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    db_alert.is_silenced = 0
    db.commit()
    return {"message": "Alert unsilenced"}

@app.get("/api/alerts/acknowledged", response_model=List[AlertOut])
def get_acknowledged_history(db: Session = Depends(get_db)):
    from sqlalchemy.orm import joinedload
    return db.query(Alert).filter(Alert.acknowledged_by_id != None).options(
        joinedload(Alert.comments), 
        joinedload(Alert.acknowledged_by_user)
    ).order_by(Alert.acknowledged_at.desc()).all()

@app.post("/api/alerts/{alert_id}/comments", response_model=CommentOut)
def create_comment(alert_id: int, comment_data: CommentCreate, db: Session = Depends(get_db)):
    db_alert = db.query(Alert).filter(Alert.id == alert_id).first()
    if not db_alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    db_comment = Comment(alert_id=alert_id, content=comment_data.content)
    db.add(db_comment)
    db.commit()
    db.refresh(db_comment)
    return db_comment

@app.get("/api/alerts/{alert_id}/comments", response_model=List[CommentOut])
def get_comments(alert_id: int, db: Session = Depends(get_db)):
    db_alert = db.query(Alert).filter(Alert.id == alert_id).first()
    if not db_alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    return db.query(Comment).filter(Comment.alert_id == alert_id).all()

@app.put("/api/comments/{comment_id}", response_model=CommentOut)
def update_comment(comment_id: int, comment_data: CommentCreate, db: Session = Depends(get_db)):
    db_comment = db.query(Comment).filter(Comment.id == comment_id).first()
    if not db_comment:
        raise HTTPException(status_code=404, detail="Comment not found")
    db_comment.content = comment_data.content
    db.commit()
    db.refresh(db_comment)
    return db_comment

@app.delete("/api/comments/{comment_id}")
def delete_comment(comment_id: int, db: Session = Depends(get_db)):
    db_comment = db.query(Comment).filter(Comment.id == comment_id).first()
    if not db_comment:
        raise HTTPException(status_code=404, detail="Comment not found")
    db.delete(db_comment)
    db.commit()
    return {"message": "Comment deleted"}

@app.delete("/api/comments")
def clear_all_comments(db: Session = Depends(get_db)):
    db.query(Comment).delete()
    db.commit()
    return {"message": "All comments have been cleared"}

@app.get("/api/alerts/summary")
def get_alert_summary(
    start_date: Optional[datetime] = None, 
    end_date: Optional[datetime] = None, 
    alertname: Optional[str] = None,
    instance: Optional[str] = None,
    job: Optional[str] = None,
    group: Optional[str] = None,
    group1: Optional[str] = None,
    company: Optional[str] = None,
    disk_info: Optional[str] = None,
    asset: Optional[str] = None,
    severity: Optional[str] = None,
    include_silenced: bool = False,
    db: Session = Depends(get_db)
):
    query = db.query(
        Alert.instance, Alert.job, Alert.company, Alert.group_name, Alert.group1, Alert.disk_info, Alert.asset, Alert.alertname, Alert.severity,
        func.sum(case((Alert.status == 'firing', 1), else_=0)).label('firing_count'),
        func.sum(case((Alert.status == 'resolved', 1), else_=0)).label('resolved_count')
    )
    
    query = apply_alert_filters(query, start_date, end_date, alertname, instance, job, group, disk_info, asset, None, severity, include_silenced, company, group1)
        
    summary = query.group_by(Alert.instance, Alert.job, Alert.company, Alert.group_name, Alert.group1, Alert.disk_info, Alert.asset, Alert.alertname, Alert.severity).all()
    
    return [
        {
            "instance": s.instance, "job": s.job, "company": s.company, "group": s.group_name, "group1": s.group1, "disk_info": s.disk_info, "asset": s.asset,
            "alertname": s.alertname, "severity": s.severity, "firing": int(s.firing_count), "resolved": int(s.resolved_count)
        } for s in summary
    ]

@app.get("/api/alerts/summary/export")
def export_alert_summary(
    start_date: Optional[datetime] = None, 
    end_date: Optional[datetime] = None, 
    alertname: Optional[str] = None,
    instance: Optional[str] = None,
    job: Optional[str] = None,
    group: Optional[str] = None,
    group1: Optional[str] = None,
    company: Optional[str] = None,
    disk_info: Optional[str] = None,
    asset: Optional[str] = None,
    severity: Optional[str] = None,
    include_silenced: bool = False,
    db: Session = Depends(get_db)
):
    import csv, io
    from fastapi.responses import StreamingResponse
    query = db.query(
        Alert.instance, Alert.job, Alert.company, Alert.group_name, Alert.group1, Alert.disk_info, Alert.asset, Alert.alertname, Alert.severity,
        func.sum(case((Alert.status == 'firing', 1), else_=0)).label('firing_count'),
        func.sum(case((Alert.status == 'resolved', 1), else_=0)).label('resolved_count')
    )
    query = apply_alert_filters(query, start_date, end_date, alertname, instance, job, group, disk_info, asset, None, severity, include_silenced, company, group1)
    summary = query.group_by(Alert.instance, Alert.job, Alert.company, Alert.group_name, Alert.group1, Alert.disk_info, Alert.asset, Alert.alertname, Alert.severity).all()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Instance", "Job", "Company", "Group", "Group1", "Disk Info", "Asset", "Alert Name", "Severity", "Firing Count", "Resolved Count"])
    for s in summary:
        writer.writerow([s.instance, s.job, s.company, s.group_name, s.group1, s.disk_info, s.asset, s.alertname, s.severity, int(s.firing_count), int(s.resolved_count)])
    output.seek(0)
    return StreamingResponse(iter([output.getvalue()]), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=alerts_summary.csv"})

@app.get("/api/alerts/export")
def export_alerts(
    start_date: Optional[datetime] = None, 
    end_date: Optional[datetime] = None, 
    alertname: Optional[str] = None,
    instance: Optional[str] = None,
    job: Optional[str] = None,
    group: Optional[str] = None,
    group1: Optional[str] = None,
    company: Optional[str] = None,
    disk_info: Optional[str] = None,
    asset: Optional[str] = None,
    status: Optional[str] = None,
    severity: Optional[str] = None,
    include_silenced: bool = False,
    db: Session = Depends(get_db)
):
    import csv, io
    from fastapi.responses import StreamingResponse
    query = db.query(Alert)
    query = apply_alert_filters(query, start_date, end_date, alertname, instance, job, group, disk_info, asset, status, severity, include_silenced, company, group1)
    alerts = query.order_by(Alert.received_at.desc()).all()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["ID", "Received At", "Alert Name", "Instance", "Job", "Company", "Group", "Group1", "Disk Info", "Asset", "Status", "Severity", "Starts At", "Ends At", "Comments"])
    for alert in alerts:
        comments_str = " | ".join([c.content for c in alert.comments]) if alert.comments else ""
        writer.writerow([
            alert.id, alert.received_at.isoformat(), alert.alertname, alert.instance, alert.job, alert.company, alert.group_name, alert.group1, alert.disk_info, alert.asset, alert.status,
            alert.severity, alert.starts_at.isoformat() if alert.starts_at else "",
            alert.ends_at.isoformat() if alert.ends_at else "", comments_str
        ])
    output.seek(0)
    return StreamingResponse(iter([output.getvalue()]), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=alerts_history.csv"})

@app.delete("/api/alerts")
def clear_alerts(db: Session = Depends(get_db)):
    db.query(Comment).delete()
    db.query(Alert).delete()
    db.query(SilenceRule).delete()
    db.query(DeviceToken).delete()
    db.query(UserGroup).delete()
    db.query(User).delete()
    db.query(Setting).delete()
    db.commit()
    return {"message": "All database tables have been cleared"}

# Silence Rules Endpoints
@app.post("/api/silence-rules", response_model=SilenceRuleOut)
def create_silence_rule(rule_data: SilenceRuleCreate, db: Session = Depends(get_db)):
    db_rule = SilenceRule(
        instance=rule_data.instance,
        alertname=rule_data.alertname,
        company=rule_data.company,
        group1=rule_data.group1,
        start_time=rule_data.start_time,
        end_time=rule_data.end_time
    )
    db.add(db_rule)
    
    # Silence ALL EXISTING matching alerts
    query = db.query(Alert)
    if rule_data.instance:
        query = query.filter(Alert.instance.ilike(f"%{rule_data.instance}%"))
    if rule_data.alertname:
        query = query.filter(Alert.alertname.ilike(f"%{rule_data.alertname}%"))
    if rule_data.company:
        query = query.filter(Alert.company.ilike(f"%{rule_data.company}%"))
    if rule_data.group1:
        query = query.filter(Alert.group1.ilike(f"%{rule_data.group1}%"))
    
    query.update({Alert.is_silenced: 1}, synchronize_session=False)
    db.commit()
    db.refresh(db_rule)
    return db_rule

@app.get("/api/silence-rules", response_model=List[SilenceRuleOut])
def get_silence_rules(db: Session = Depends(get_db)):
    return db.query(SilenceRule).order_by(SilenceRule.created_at.desc()).all()

@app.delete("/api/silence-rules/{rule_id}")
def delete_silence_rule(rule_id: int, db: Session = Depends(get_db)):
    db_rule = db.query(SilenceRule).filter(SilenceRule.id == rule_id).first()
    if not db_rule:
        raise HTTPException(status_code=404, detail="Rule not found")
    db.delete(db_rule)
    db.commit()
    return {"message": "Silence rule deleted"}

# Device Token Endpoints
@app.post("/api/v1/mobile/token")
def register_device_token(data: DeviceTokenCreate, db: Session = Depends(get_db)):
    # Update user metadata if user_id is provided
    if data.user_id:
        user = db.query(User).filter(User.id == data.user_id).first()
        if user:
            if data.device_name: user.device_name = data.device_name
            if data.os_version: user.os_version = data.os_version
            db.commit()

    # Check if token already exists
    existing = db.query(DeviceToken).filter(DeviceToken.token == data.token).first()
    if existing:
        existing.user_id = data.user_id
        db.commit()
        return {"message": "Token updated"}
    
    new_token = DeviceToken(token=data.token, user_id=data.user_id)
    db.add(new_token)
    db.commit()
    return {"message": "Token registered"}

# User Management Endpoints
@app.get("/api/users", response_model=List[UserOut])
def get_users(db: Session = Depends(get_db)):
    from sqlalchemy.orm import joinedload
    return db.query(User).options(joinedload(User.groups)).all()

# --- MOBILE COMPATIBILITY LAYER ---
class MobileLoginRequest(BaseModel):
    email: str
    password: str

@app.post("/api/v1/auth/login")
def mobile_login(data: MobileLoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == data.email).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return {
        "token": "dummy-token-for-now",
        "user_email": user.email,
        "user_id": user.id,
        "role": "admin",
        "group_name": "All",
        "user": {"id": user.id, "email": user.email, "name": user.name, "role": "admin"}
    }

@app.get("/api/v1/mobile/alerts")
def get_mobile_alerts(filter: str = "active", include_silenced: bool = False, db: Session = Depends(get_db)):
    from sqlalchemy.orm import joinedload
    query = db.query(Alert).options(joinedload(Alert.acknowledged_by_user))
    if not include_silenced:
        query = query.filter(or_(Alert.is_silenced == 0, Alert.is_silenced == None))
    if filter == "active":
        query = query.filter(Alert.status == "firing")
    
    alerts = query.order_by(Alert.received_at.desc()).limit(100).all()
    mobile_alerts = []
    for a in alerts:
        mobile_alerts.append({
            "id": a.id,
            "server_name": a.instance or "Unknown",
            "server_ip": a.instance or "",
            "created_at": a.received_at.isoformat() if a.received_at else None,
            "alert_type": a.alertname or "Alert",
            "severity": a.severity or "critical",
            "message": a.alertname or "No details available",
            "mobile_status": "acknowledged" if a.acknowledged_by_id else "pending",
            "is_resolved": a.status == "resolved",
            "acknowledged_by_name": a.acknowledged_by_user.name if a.acknowledged_by_user else None,
            "metric_value": None,
            "threshold_value": None
        })
    return mobile_alerts

@app.post("/api/v1/mobile/alerts/{alert_id}/ack")
def mobile_acknowledge(alert_id: int, data: dict, db: Session = Depends(get_db)):
    db_alert = db.query(Alert).filter(Alert.id == alert_id).first()
    if not db_alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    
    # Get user from payload, or fallback to first user for safety
    user_id = data.get("user_id")
    if user_id:
        user = db.query(User).filter(User.id == user_id).first()
    else:
        user = db.query(User).first()

    if not user:
        raise HTTPException(status_code=400, detail="User not found")
    
    db_alert.acknowledged_by_id = user.id
    db_alert.acknowledged_at = datetime.utcnow()
    db.commit()
    return {"message": f"Alert acknowledged by {user.name}"}

@app.post("/api/v1/mobile/logout")
def mobile_logout():
    return {"message": "Logged out"}
# --- END MOBILE COMPATIBILITY LAYER ---

@app.post("/api/users", response_model=UserOut)
def create_user(user_data: UserCreate, db: Session = Depends(get_db)):
    db_user = db.query(User).filter(User.email == user_data.email).first()
    if db_user:
        raise HTTPException(status_code=400, detail="Email already registered")
    db_user = User(name=user_data.name, email=user_data.email)
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user

@app.delete("/api/users/{user_id}")
def delete_user(user_id: int, db: Session = Depends(get_db)):
    db_user = db.query(User).filter(User.id == user_id).first()
    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")
    db.delete(db_user)
    db.commit()
    return {"message": "User deleted"}

@app.put("/api/users/{user_id}/groups")
def update_user_groups(user_id: int, group_data: GroupUpdate, db: Session = Depends(get_db)):
    db_user = db.query(User).filter(User.id == user_id).first()
    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")
    db.query(UserGroup).filter(UserGroup.user_id == user_id).delete()
    for group_name in group_data.groups:
        db_group = UserGroup(user_id=user_id, group_name=group_name)
        db.add(db_group)
    db.commit()
    return {"message": "User groups updated"}

@app.get("/api/settings")
def get_settings(db: Session = Depends(get_db)):
    settings = db.query(Setting).all()
    return {s.key: s.value for s in settings}

@app.post("/api/settings")
def update_setting(setting_data: SettingUpdate, db: Session = Depends(get_db)):
    db_setting = db.query(Setting).filter(Setting.key == setting_data.key).first()
    if db_setting:
        db_setting.value = setting_data.value
    else:
        db_setting = Setting(key=setting_data.key, value=setting_data.value)
        db.add(db_setting)
    db.commit()
    return {"message": "Setting updated", "key": setting_data.key}

@app.get("/api/groups")
def get_all_groups(db: Session = Depends(get_db)):
    groups = db.query(Alert.group_name).filter(Alert.group_name != None).distinct().all()
    return [g[0] for g in groups]

# Prometheus Server Endpoints
@app.get("/api/prometheus-servers", response_model=List[PrometheusServerOut])
def get_prometheus_servers(db: Session = Depends(get_db)):
    return db.query(PrometheusServer).all()

@app.get("/api/prometheus-targets", response_model=List[PrometheusTargetOut])
def get_prometheus_targets(db: Session = Depends(get_db)):
    return db.query(PrometheusTarget).order_by(PrometheusTarget.last_seen.desc()).all()

@app.post("/api/prometheus-servers", response_model=PrometheusServerOut)
def create_prometheus_server(server: PrometheusServerCreate, db: Session = Depends(get_db)):
    db_server = PrometheusServer(**server.dict())
    db.add(db_server)
    db.commit()
    db.refresh(db_server)
    return db_server

@app.delete("/api/prometheus-servers/{server_id}")
def delete_prometheus_server(server_id: int, db: Session = Depends(get_db)):
    db.query(PrometheusServer).filter(PrometheusServer.id == server_id).delete()
    db.commit()
    return {"message": "Server deleted"}

# Alert Group Config Endpoints
@app.get("/api/alert-groups", response_model=List[AlertGroupConfigOut])
def get_alert_groups(db: Session = Depends(get_db)):
    return db.query(AlertGroupConfig).all()

@app.post("/api/alert-groups", response_model=AlertGroupConfigOut)
def create_alert_group(group: AlertGroupConfigCreate, db: Session = Depends(get_db)):
    db_group = AlertGroupConfig(**group.dict())
    db.add(db_group)
    db.commit()
    db.refresh(db_group)
    return db_group

@app.delete("/api/alert-groups/{group_id}")
def delete_alert_group(group_id: int, db: Session = Depends(get_db)):
    db.query(AlertGroupConfig).filter(AlertGroupConfig.id == group_id).delete()
    db.commit()
    return {"message": "Group deleted"}

@app.put("/api/alert-groups/{group_id}", response_model=AlertGroupConfigOut)
def update_alert_group(group_id: int, group_data: AlertGroupConfigCreate, db: Session = Depends(get_db)):
    db_group = db.query(AlertGroupConfig).filter(AlertGroupConfig.id == group_id).first()
    if not db_group:
        raise HTTPException(status_code=404, detail="Group not found")
    
    for key, value in group_data.dict().items():
        setattr(db_group, key, value)
    
    db.commit()
    db.refresh(db_group)
    return db_group

# Alert Rule Endpoints
@app.post("/api/prometheus-servers/{server_id}/sync-groups")
async def sync_prometheus_groups(server_id: int, db: Session = Depends(get_db)):
    server = db.query(PrometheusServer).filter(PrometheusServer.id == server_id).first()
    if not server:
        raise HTTPException(status_code=404, detail="Server not found")
    
    async with httpx.AsyncClient() as client:
        try:
            # Use targets API to find unique labels
            response = await client.get(f"{server.url}/api/v1/targets", timeout=10.0)
            response.raise_for_status()
            targets_data = response.json().get("data", {}).get("activeTargets", [])
            
            discovered_groups = {} # Normalized Name -> details
            new_targets_count = 0
            updated_targets_count = 0
            
            # Clear current targets for this server to keep it fresh
            db.query(PrometheusTarget).filter(PrometheusTarget.server_id == server_id).delete()

            for target in targets_data:
                labels = target.get("labels", {})
                instance_val = labels.get("instance", "unknown")
                job_val = labels.get("job") or labels.get("Job")
                company_val = labels.get("company") or labels.get("Company")
                asset_val = labels.get("asset") or labels.get("Asset")
                
                # Primary group/team
                group_val = labels.get("group") or labels.get("Group") or labels.get("team") or labels.get("Team") or labels.get("service") or labels.get("Service")
                group1_val = labels.get("group1") or labels.get("Group1")

                # ENRICHMENT: If fields are missing in labels, try to find from alert history
                if not company_val or not asset_val:
                    last_alert = db.query(Alert).filter(Alert.instance == instance_val).order_by(Alert.received_at.desc()).first()
                    if last_alert:
                        if not company_val: company_val = last_alert.company
                        if not asset_val: asset_val = last_alert.asset

                # Save target detail
                db_target = PrometheusTarget(
                    instance=instance_val,
                    job=job_val,
                    group_name=group_val,
                    group1=group1_val,
                    company=company_val,
                    asset=asset_val,
                    server_id=server_id,
                    last_seen=datetime.utcnow()
                )
                db.add(db_target)
                new_targets_count += 1
                
                # Process multiple labels as potential group names for AlertGroupConfig
                potential_group_labels = ["group", "group1", "team", "service"]
                
                # Common details for this target
                emails_str = labels.get("emails") or labels.get("email") or ""
                target_emails = set(e.strip() for e in emails_str.split(",") if e.strip())
                slack = labels.get("slack_webhook") or labels.get("slack") or labels.get("webhook") or ""
                voice = 1 if labels.get("voice_enabled") == "true" or labels.get("voice") == "true" else 0

                for label_name in potential_group_labels:
                    g_val = labels.get(label_name)
                    if g_val and g_val.lower() != "unknown":
                        g_val = g_val.strip()
                        g_key = g_val.lower()
                        
                        if g_key not in discovered_groups:
                            discovered_groups[g_key] = {
                                "name": g_val,
                                "emails": target_emails.copy(),
                                "slack_webhook": slack,
                                "voice_enabled": voice
                            }
                        else:
                            discovered_groups[g_key]["emails"].update(target_emails)
                            if not discovered_groups[g_key]["slack_webhook"] and slack:
                                discovered_groups[g_key]["slack_webhook"] = slack
                            if not discovered_groups[g_key]["voice_enabled"] and voice:
                                discovered_groups[g_key]["voice_enabled"] = voice
            
            new_groups_count = 0
            updated_groups_count = 0
            for g_key, details in discovered_groups.items():
                g_name = details["name"]
                emails_to_save = ",".join(sorted(list(details["emails"])))
                # Case-insensitive check
                existing = db.query(AlertGroupConfig).filter(func.lower(AlertGroupConfig.name) == g_key).first()
                if not existing:
                    db_group = AlertGroupConfig(
                        name=g_name, 
                        emails=emails_to_save,
                        slack_webhook=details["slack_webhook"],
                        voice_enabled=details["voice_enabled"]
                    )
                    db.add(db_group)
                    new_groups_count += 1
                else:
                    # Update existing if details are found in targets but missing in DB
                    updated = False
                    
                    # Merge emails
                    if emails_to_save:
                        existing_emails = set(e.strip() for e in (existing.emails or "").split(",") if e.strip())
                        new_set = existing_emails.union(details["emails"])
                        if len(new_set) > len(existing_emails):
                            existing.emails = ",".join(sorted(list(new_set)))
                            updated = True
                            
                    if not existing.slack_webhook and details["slack_webhook"]:
                        existing.slack_webhook = details["slack_webhook"]
                        updated = True
                    if existing.voice_enabled == 0 and details["voice_enabled"] == 1:
                        existing.voice_enabled = 1
                        updated = True
                    
                    if updated:
                        updated_groups_count += 1
            
            db.commit()
            return {
                "message": f"Successfully synced. Added {new_groups_count} groups and {new_targets_count} targets.", 
                "groups": list(discovered_groups.keys()),
                "targets_count": new_targets_count
            }
        except Exception as e:
            import traceback
            traceback.print_exc()
            raise HTTPException(status_code=500, detail=f"Error syncing groups and targets: {str(e)}")

@app.get("/api/alert-rules", response_model=List[AlertRuleOut])
def get_alert_rules(db: Session = Depends(get_db)):
    from sqlalchemy.orm import joinedload
    return db.query(AlertRule).options(joinedload(AlertRule.group), joinedload(AlertRule.notification_groups)).all()

@app.post("/api/prometheus-servers/{server_id}/sync-rules")
async def sync_prometheus_rules(server_id: int, db: Session = Depends(get_db)):
    server = db.query(PrometheusServer).filter(PrometheusServer.id == server_id).first()
    if not server:
        raise HTTPException(status_code=404, detail="Server not found")
    
    # Ensure at least one group exists
    default_group = db.query(AlertGroupConfig).first()
    if not default_group:
        print("Creating default alert group...")
        default_group = AlertGroupConfig(name="Default", emails="")
        db.add(default_group)
        db.commit()
        db.refresh(default_group)
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(f"{server.url}/api/v1/rules", timeout=10.0)
            response.raise_for_status()
            data = response.json().get("data", {})
            groups = data.get("groups", [])
            
            new_rules_count = 0
            for group in groups:
                for rule in group.get("rules", []):
                    if rule.get("type") != "alerting": continue
                    
                    name = rule.get("name")
                    query = rule.get("query")
                    duration = rule.get("duration", "60s")
                    
                    # Check if rule already exists
                    existing = db.query(AlertRule).filter(AlertRule.name == name, AlertRule.promql == query).first()
                    if not existing:
                        db_rule = AlertRule(
                            name=name,
                            promql=query,
                            duration=f"{duration}s" if isinstance(duration, int) else str(duration),
                            severity="warning", # Default
                            group_id=default_group.id,
                            is_active=1
                        )
                        db_rule.notification_groups.append(default_group)
                        db.add(db_rule)
                        new_rules_count += 1
            
            db.commit()
            return {"message": f"Successfully synced rules. Added {new_rules_count} new rules.", "total_added": new_rules_count}
        except Exception as e:
            import traceback
            traceback.print_exc()
            raise HTTPException(status_code=500, detail=f"Error syncing rules: {str(e)}")

@app.post("/api/alert-rules", response_model=AlertRuleOut)
def create_alert_rule(rule: AlertRuleCreate, db: Session = Depends(get_db)):
    rule_data = rule.dict(exclude={"group_ids"})
    # Handle backward compatibility: If group_ids is empty but group_id is set
    group_ids = rule.group_ids
    if not group_ids and rule.group_id:
        group_ids = [rule.group_id]
        
    # If no group_id but we have group_ids, set first one as group_id for backward comp
    if not rule.group_id and group_ids:
        rule_data["group_id"] = group_ids[0]

    db_rule = AlertRule(**rule_data)
    
    if group_ids:
        groups = db.query(AlertGroupConfig).filter(AlertGroupConfig.id.in_(group_ids)).all()
        db_rule.notification_groups = groups

    db.add(db_rule)
    db.commit()
    db.refresh(db_rule)
    return db_rule

@app.put("/api/alert-rules/{rule_id}", response_model=AlertRuleOut)
def update_alert_rule(rule_id: int, rule_data: AlertRuleCreate, db: Session = Depends(get_db)):
    db_rule = db.query(AlertRule).filter(AlertRule.id == rule_id).first()
    if not db_rule:
        raise HTTPException(status_code=404, detail="Rule not found")
    
    update_data = rule_data.dict(exclude={"group_ids"})
    group_ids = rule_data.group_ids
    
    # Backward comp
    if not group_ids and rule_data.group_id:
        group_ids = [rule_data.group_id]
    if not rule_data.group_id and group_ids:
        update_data["group_id"] = group_ids[0]

    for key, value in update_data.items():
        setattr(db_rule, key, value)
        
    if group_ids is not None:
        groups = db.query(AlertGroupConfig).filter(AlertGroupConfig.id.in_(group_ids)).all()
        db_rule.notification_groups = groups
    
    db.commit()
    db.refresh(db_rule)
    return db_rule

@app.delete("/api/alert-rules/{rule_id}")
def delete_alert_rule(rule_id: int, db: Session = Depends(get_db)):
    from models import AlertRuleGroupAssociation
    # First, handle dependent AlertState records
    # Option A: Delete them
    db.query(AlertState).filter(AlertState.rule_id == rule_id).delete()
    
    # Delete association records
    db.query(AlertRuleGroupAssociation).filter(AlertRuleGroupAssociation.rule_id == rule_id).delete()
    
    # Now delete the rule
    db.query(AlertRule).filter(AlertRule.id == rule_id).delete()
    db.commit()
    return {"message": "Rule deleted"}

# Alert State Endpoints
@app.get("/api/alert-state", response_model=List[AlertStateOut])
def get_alert_state(db: Session = Depends(get_db)):
    states = db.query(AlertState).filter(AlertState.status == "firing").all()
    result = []
    for state in states:
        # Find the corresponding Alert to get comments and ack info
        alert = db.query(Alert).filter(
            Alert.fingerprint.like(f"{state.fingerprint}%"), 
            Alert.status == "firing"
        ).order_by(Alert.received_at.desc()).first()
        
        state_dict = {
            "id": state.id,
            "rule_id": state.rule_id,
            "alert_name": state.alert_name,
            "instance": state.instance,
            "cluster": state.cluster,
            "group_name": state.group_name,
            "team": state.team,
            "status": state.status,
            "severity": state.severity,
            "starts_at": state.starts_at,
            "ends_at": state.ends_at,
            "last_notified_at": state.last_notified_at,
            "fingerprint": state.fingerprint,
            "acknowledged_by_user": alert.acknowledged_by_user if alert else None,
            "comments": alert.comments if alert else [],
            "alert_id": alert.id if alert else None
        }
        result.append(state_dict)
    return result

async def periodic_cleanup():
    """Background task to remove duplicate alerts every 30 seconds"""
    while True:
        try:
            from database import SessionLocal
            db = SessionLocal()
            try:
                # Find duplicates based on received_at, alertname, instance
                duplicates = db.query(
                    Alert.received_at, 
                    Alert.alertname, 
                    Alert.instance, 
                    func.min(Alert.id).label('min_id')
                ).group_by(
                    Alert.received_at, 
                    Alert.alertname, 
                    Alert.instance
                ).having(func.count(Alert.id) > 1).all()

                if duplicates:
                    for d in duplicates:
                        # Delete all except the one with min_id
                        db.query(Alert).filter(
                            Alert.received_at == d.received_at,
                            Alert.alertname == d.alertname,
                            Alert.instance == d.instance,
                            Alert.id != d.min_id
                        ).delete(synchronize_session=False)
                    db.commit()
            finally:
                db.close()
        except Exception as e:
            print(f"Error in background cleanup: {e}")
        
        await asyncio.sleep(30)

from alert_engine import run_alert_engine

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(periodic_cleanup())
    asyncio.create_task(run_alert_engine())

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
