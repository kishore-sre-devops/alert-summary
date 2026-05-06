"""
Alert Configuration endpoints - Email, Slack, Mobile App
REMOVED: External Telephony (C-Zentrix/Twilio)
"""

from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel
from sqlalchemy import select, update, insert, delete, and_
from sqlalchemy.orm import Session
from app.db.db import get_db, alert_config_table, engine, get_connection
from app.utils.permissions import require_admin
from typing import Optional, List
from datetime import datetime
import logging
import json
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import httpx
from app.utils.aes_encryption import encrypt_password, decrypt_password

logger = logging.getLogger(__name__)

router = APIRouter()

class EmailConfig(BaseModel):
    smtp_host: str
    smtp_port: int
    smtp_username: str
    smtp_password: Optional[str] = None
    smtp_from_email: str
    smtp_to_emails: List[str]
    smtp_to_user_ids: Optional[List[int]] = None
    smtp_use_tls: bool = True

class SlackConfig(BaseModel):
    slack_webhook_url: Optional[str] = None
    slack_channel: Optional[str] = None
    slack_to_user_ids: Optional[List[int]] = None

class AlertConfigCreate(BaseModel):
    alert_channel: str # 'email', 'slack', 'mobile'
    enabled: bool = False
    email_config: Optional[EmailConfig] = None
    slack_config: Optional[SlackConfig] = None

class AlertConfigResponse(BaseModel):
    id: Optional[int] = None
    alert_channel: str
    enabled: bool
    email_config: Optional[dict] = None
    slack_config: Optional[dict] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

from app.utils.permissions import require_admin

@router.get("/", response_model=List[AlertConfigResponse])
def list_alert_configs(request: Request = None):
    """List all alert configurations - Admin only"""
    require_admin(request)
    try:
        with get_connection() as conn:
            query = select(alert_config_table).order_by(alert_config_table.c.alert_channel)
            results = conn.execute(query).fetchall()
            configs = []
            for r in results:
                row = r._mapping
                email_config = None
                slack_config = None
                
                if row['alert_channel'] == 'email':
                    email_config = {
                        "smtp_host": row['smtp_host'],
                        "smtp_port": row['smtp_port'],
                        "smtp_username": row['smtp_username'],
                        "smtp_from_email": row['smtp_from_email'],
                        "smtp_to_emails": row['smtp_to_emails'] if isinstance(row['smtp_to_emails'], list) else json.loads(row['smtp_to_emails']) if row['smtp_to_emails'] else [],
                        "smtp_to_user_ids": row['smtp_to_user_ids'] if isinstance(row['smtp_to_user_ids'], list) else json.loads(row['smtp_to_user_ids']) if row['smtp_to_user_ids'] else [],
                        "smtp_use_tls": row['smtp_use_tls'] if row['smtp_use_tls'] is not None else True
                    }
                elif row['alert_channel'] == 'slack':
                    slack_config = {
                        "slack_channel": row['slack_channel'],
                        "slack_to_user_ids": row['slack_to_user_ids'] if isinstance(row['slack_to_user_ids'], list) else json.loads(row['slack_to_user_ids']) if row['slack_to_user_ids'] else []
                    }
                
                configs.append(AlertConfigResponse(
                    id=row['id'],
                    alert_channel=row['alert_channel'],
                    enabled=row['enabled'],
                    email_config=email_config,
                    slack_config=slack_config,
                    created_at=row['created_at'].isoformat() if row['created_at'] else None,
                    updated_at=row['updated_at'].isoformat() if row['updated_at'] else None
                ))
            return configs
    except Exception as e:
        logger.error(f"Config list fail: {e}")
        return []

@router.get("/{channel}", response_model=AlertConfigResponse)
def get_alert_config_by_channel(channel: str, request: Request = None):
    """Get specific channel config - Admin only"""
    require_admin(request)
    try:
        with get_connection() as conn:
            query = select(alert_config_table).where(alert_config_table.c.alert_channel == channel)
            r = conn.execute(query).fetchone()
            if not r:
                # Return empty config instead of 404 to satisfy frontend
                return AlertConfigResponse(alert_channel=channel, enabled=False)
            
            row = r._mapping
            email_config = None
            slack_config = None
            
            if channel == 'email':
                email_config = {
                    "smtp_host": row['smtp_host'],
                    "smtp_port": row['smtp_port'],
                    "smtp_username": row['smtp_username'],
                    "smtp_from_email": row['smtp_from_email'],
                    "smtp_to_emails": row['smtp_to_emails'] if isinstance(row['smtp_to_emails'], list) else json.loads(row['smtp_to_emails']) if row['smtp_to_emails'] else [],
                    "smtp_to_user_ids": row['smtp_to_user_ids'] if isinstance(row['smtp_to_user_ids'], list) else json.loads(row['smtp_to_user_ids']) if row['smtp_to_user_ids'] else [],
                    "smtp_use_tls": row['smtp_use_tls'] if row['smtp_use_tls'] is not None else True
                }
            elif channel == 'slack':
                slack_config = {
                    "slack_channel": row['slack_channel'],
                    "slack_to_user_ids": row['slack_to_user_ids'] if isinstance(row['slack_to_user_ids'], list) else json.loads(row['slack_to_user_ids']) if row['slack_to_user_ids'] else []
                }
            
            return AlertConfigResponse(
                id=row['id'],
                alert_channel=row['alert_channel'],
                enabled=row['enabled'],
                email_config=email_config,
                slack_config=slack_config,
                created_at=row['created_at'].isoformat() if row['created_at'] else None,
                updated_at=row['updated_at'].isoformat() if row['updated_at'] else None
            )
    except Exception as e:
        logger.error(f"Config get fail for {channel}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/")
def create_alert_config(config: AlertConfigCreate, request: Request):
    """Update or create config"""
    require_admin(request)
    if config.alert_channel not in ['email', 'slack', 'mobile']:
        raise HTTPException(status_code=400, detail="Invalid channel")
    
    try:
        with get_connection() as conn:
            # Check if exists
            query = select(alert_config_table).where(alert_config_table.c.alert_channel == config.alert_channel)
            existing = conn.execute(query).fetchone()
            
            values = {
                "enabled": config.enabled,
                "updated_at": datetime.utcnow()
            }
            
            if config.alert_channel == 'email' and config.email_config:
                ec = config.email_config
                values.update({
                    "smtp_host": ec.smtp_host,
                    "smtp_port": ec.smtp_port,
                    "smtp_username": ec.smtp_username,
                    "smtp_from_email": ec.smtp_from_email,
                    "smtp_to_emails": json.dumps(ec.smtp_to_emails),
                    "smtp_to_user_ids": json.dumps(ec.smtp_to_user_ids) if ec.smtp_to_user_ids else json.dumps([]),
                    "smtp_use_tls": ec.smtp_use_tls
                })
                if ec.smtp_password:
                    values["smtp_password"] = encrypt_password(ec.smtp_password)
            
            elif config.alert_channel == 'slack' and config.slack_config:
                sc = config.slack_config
                values.update({
                    "slack_channel": sc.slack_channel,
                    "slack_to_user_ids": json.dumps(sc.slack_to_user_ids) if sc.slack_to_user_ids else json.dumps([])
                })
                if sc.slack_webhook_url:
                    values["slack_webhook_url"] = encrypt_password(sc.slack_webhook_url)
            
            if existing:
                stmt = update(alert_config_table).where(alert_config_table.c.alert_channel == config.alert_channel).values(**values)
                conn.execute(stmt)
            else:
                values["alert_channel"] = config.alert_channel
                values["created_at"] = datetime.utcnow()
                stmt = insert(alert_config_table).values(**values)
                conn.execute(stmt)
            
            conn.commit()
            return {"status": "success"}
    except Exception as e:
        logger.error(f"Save config fail: {e}")
        raise HTTPException(status_code=500, detail=str(e))

import logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

@router.post("/{channel}/test")
async def test_alert_config(channel: str, config: AlertConfigCreate, request: Request):
    """Test the alert configuration"""
    require_admin(request)
    
    if channel == 'email':
        if not config.email_config:
            raise HTTPException(status_code=400, detail="Email config missing")
        
        ec = config.email_config
        password = ec.smtp_password
        
        # If password is empty, try to get from DB
        if not password or password == "":
            logger.info("Test Email: Password empty in request, fetching from DB...")
            with get_connection() as conn:
                r = conn.execute(select(alert_config_table.c.smtp_password).where(alert_config_table.c.alert_channel == 'email')).fetchone()
                if r and r[0]:
                    password = decrypt_password(r[0])
                    logger.info("Test Email: Password retrieved and decrypted from DB")
                else:
                    logger.warning("Test Email: No password found in DB")
        else:
            logger.info("Test Email: Using password provided in request")
        
        if not password:
            raise HTTPException(status_code=400, detail="SMTP password is required for testing")
            
        try:
            # Prepare test email recipients from UI configuration
            recipients = []
            
            # 1. Add custom emails from UI
            if ec.smtp_to_emails:
                for email in ec.smtp_to_emails:
                    if email and email.strip() and email not in recipients:
                        recipients.append(email.strip())
            
            # 2. Add selected user emails from UI
            if ec.smtp_to_user_ids:
                user_emails = get_user_emails(ec.smtp_to_user_ids)
                for email in user_emails:
                    if email and email.strip() and email not in recipients:
                        recipients.append(email.strip())
            
            # 3. Fallback: If NO valid recipients were added, ONLY then use the 'From' address
            if not recipients:
                recipients = [ec.smtp_from_email]
            
            # Final sanity check: remove duplicates just in case
            recipients = list(dict.fromkeys(recipients))
            
            print(f"DEBUG: FINAL recipients for sending: {recipients}", flush=True)
            logger.info(f"Test Email: Sending to {', '.join(recipients)}")
            
            # Prepare test email
            msg = MIMEMultipart()
            msg['From'] = ec.smtp_from_email
            msg['To'] = ", ".join(recipients)
            msg['Subject'] = "SMC LAMA - Test Alert Configuration"
            body = f"This is a test email from SMC LAMA to verify your SMTP settings.\n\nTime: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            msg.attach(MIMEText(body, 'plain'))
            
            # Use blocking SMTP for test endpoint
            server = smtplib.SMTP(ec.smtp_host, ec.smtp_port, timeout=10)
            if ec.smtp_use_tls:
                server.starttls()
            server.login(ec.smtp_username, password)
            server.send_message(msg)
            server.quit()
            
            return {"success": True, "message": f"Test email sent successfully to {', '.join(recipients)}"}
        except Exception as e:
            logger.error(f"Email test failed: {e}")
            return {"success": False, "message": f"Email test failed: {str(e)}"}
            
    elif channel == 'slack':
        if not config.slack_config:
            raise HTTPException(status_code=400, detail="Slack config missing")
        
        webhook_url = config.slack_config.slack_webhook_url
        
        # If empty, try to get from DB
        if not webhook_url:
            with get_connection() as conn:
                r = conn.execute(select(alert_config_table.c.slack_webhook_url).where(alert_config_table.c.alert_channel == 'slack')).fetchone()
                if r and r[0]:
                    webhook_url = decrypt_password(r[0])
        
        if not webhook_url:
            raise HTTPException(status_code=400, detail="Slack Webhook URL is required for testing")
            
        try:
            payload = {"text": f"🚀 *SMC LAMA - Test Alert Configuration*\nThis is a test message to verify your Slack Webhook settings.\nTime: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"}
            async with httpx.AsyncClient() as client:
                response = await client.post(webhook_url, json=payload, timeout=10.0)
                if response.status_code == 200:
                    return {"success": True, "message": "Test Slack message sent successfully"}
                else:
                    return {"success": False, "message": f"Slack API returned error: {response.text}"}
        except Exception as e:
            logger.error(f"Slack test failed: {e}")
            return {"success": False, "message": f"Slack test failed: {str(e)}"}
            
    else:
        raise HTTPException(status_code=400, detail=f"Testing for {channel} not supported")

@router.delete("/{channel}")
def delete_alert_config(channel: str, request: Request):
    """Delete config"""
    require_admin(request)
    try:
        with get_connection() as conn:
            stmt = delete(alert_config_table).where(alert_config_table.c.alert_channel == channel)
            conn.execute(stmt)
            conn.commit()
            return {"message": f"Configuration for {channel} deleted"}
    except Exception as e:
        logger.error(f"Delete config fail: {e}")
        raise HTTPException(status_code=500, detail=str(e))

def get_user_emails(user_ids: List[int]) -> List[str]:
    """Helper function to get emails for a list of user IDs"""
    if not user_ids:
        return []
    try:
        from sqlalchemy import and_
        with engine.connect() as conn:
            from app.db.db import users_table
            query = select(users_table.c.email).where(
                and_(
                    users_table.c.id.in_(user_ids),
                    users_table.c.is_active == True
                )
            )
            results = conn.execute(query).fetchall()
            return [r[0] for r in results if r[0]]
    except Exception as e:
        logger.error(f"Error getting user emails: {e}")
        return []
