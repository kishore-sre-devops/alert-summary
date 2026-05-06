"""
Alert sending utility - sends alerts via Email, Slack, and Mobile App (FCM)
REMOVED: C-Zentrix and Twilio logic
"""

import logging
import smtplib
import json
import re
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from sqlalchemy import select
from app.db.db import alert_config_table, alerts_table, server_status_table, get_connection
from typing import Optional, List
import httpx
import pytz
from app.services.push import send_push_notification

print("DEBUG: alert_sender.py module imported")
logger = logging.getLogger(__name__)

def get_severity_label(severity: str) -> str:
    """Map internal severity to user-facing labels with emojis"""
    severity_map = {
        'error': '🔴 CRITICAL',
        'critical': '🔴 CRITICAL',
        'warning': '⚠️ WARNING',
        'info': 'ℹ️ INFO',
        'high': '🔴 CRITICAL',
        'medium': '⚠️ WARNING',
        'low': 'ℹ️ INFO'
    }
    return severity_map.get(severity.lower(), severity.upper())

def format_timestamp_professional(dt: datetime) -> str:
    """Format datetime in professional IST format for email"""
    ist = pytz.timezone('Asia/Kolkata')
    dt_utc = dt.replace(tzinfo=pytz.UTC)
    dt_ist = dt_utc.astimezone(ist)
    return dt_ist.strftime("%d %b %Y, %I:%M:%S %p IST")

def format_timestamp_compact(dt: datetime) -> str:
    """Format datetime in compact IST format for Slack"""
    ist = pytz.timezone('Asia/Kolkata')
    dt_utc = dt.replace(tzinfo=pytz.UTC)
    dt_ist = dt_utc.astimezone(ist)
    return dt_ist.strftime("%d %b %Y, %I:%M %p IST")

from app.utils.aes_encryption import decrypt_password

def get_alert_config(channel: str):
    """Get alert configuration for a specific channel"""
    try:
        with get_connection() as conn:
            query = select(alert_config_table).where(
                alert_config_table.c.alert_channel == channel,
                alert_config_table.c.enabled == True
            )
            result = conn.execute(query).fetchone()
            return result
    except Exception as e:
        logger.error(f"Error fetching alert config for {channel}: {e}", exc_info=True)
        return None

def send_email_alert(alert_id: int, server_name: str, server_ip: str, metric_type: str, metric_key: str, value: float, severity: str, message: str, environment: str = "prod") -> bool:
    """Send alert via email"""
    res = get_alert_config('email')
    if not res:
        return False
    
    config = res._mapping
    try:
        smtp_host = config.get('smtp_host')
        smtp_port = config.get('smtp_port')
        smtp_username = config.get('smtp_username')
        smtp_password = decrypt_password(config.get('smtp_password'))
        smtp_from = config.get('smtp_from_email')
        
        # Safe JSON parsing for emails
        to_emails_raw = config.get('smtp_to_emails')
        smtp_to_emails = to_emails_raw if isinstance(to_emails_raw, list) else json.loads(to_emails_raw) if to_emails_raw else []
        
        to_user_ids_raw = config.get('smtp_to_user_ids')
        smtp_to_user_ids = to_user_ids_raw if isinstance(to_user_ids_raw, list) else json.loads(to_user_ids_raw) if to_user_ids_raw else []
        
        if smtp_to_user_ids:
            try:
                from app.routes.alert_config import get_user_emails
                user_emails = get_user_emails(smtp_to_user_ids)
                if user_emails:
                    smtp_to_emails = list(set(smtp_to_emails + user_emails))
            except Exception as e:
                logger.error(f"Failed to resolve user emails: {e}")
            
        smtp_use_tls = config.get('smtp_use_tls') if config.get('smtp_use_tls') is not None else True
        
        if not smtp_to_emails:
            return False
        
        env_prefix = f"[{environment.upper()}] " if environment else "[PROD] "
        severity_label = get_severity_label(severity)
        timestamp = format_timestamp_professional(datetime.utcnow())
        
        msg = MIMEMultipart()
        msg['From'] = smtp_from
        msg['To'] = ', '.join(smtp_to_emails)
        msg['Subject'] = f"LAMA {env_prefix}[{severity_label}] Alert: {metric_type}.{metric_key} on {server_name}"
        
        body = f"Alert ID: {alert_id}\nServer: {server_name} ({server_ip})\nMetric: {metric_type}.{metric_key}\nSeverity: {severity_label}\nMessage: {message}\nTime: {timestamp}"
        msg.attach(MIMEText(body, 'plain'))
        
        server = smtplib.SMTP(smtp_host, smtp_port)
        if smtp_use_tls:
            server.starttls()
        server.login(smtp_username, smtp_password)
        server.send_message(msg)
        server.quit()
        return True
    except Exception as e:
        logger.error(f"Email fail: {e}")
        return False

def send_slack_alert(alert_id: int, server_name: str, server_ip: str, metric_type: str, metric_key: str, value: float, severity: str, message: str, environment: str = "prod") -> bool:
    """Send alert via Slack webhook"""
    res = get_alert_config('slack')
    if not res:
        return False
    
    config = res._mapping
    # Double check enabled flag
    if not config.get('enabled', True):
        return False

    try:
        webhook_url_enc = config.get('slack_webhook_url')
        webhook_url = decrypt_password(webhook_url_enc) if webhook_url_enc else None
        if not webhook_url:
            return False
        
        severity_label = get_severity_label(severity)
        timestamp = format_timestamp_compact(datetime.utcnow())
        env_prefix = f"[{environment.upper()}] " if environment else "[PROD] "
        
        # Professional Slack block formatting
        payload = {
            "text": f"{env_prefix}{severity_label} Alert: {server_name}",
            "blocks": [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*SMC LAMA {env_prefix}{severity_label} Alert*\n*ID:* {alert_id}"
                    }
                },
                {
                    "type": "section",
                    "fields": [
                        {"type": "mrkdwn", "text": f"*Server:*\n{server_name}"},
                        {"type": "mrkdwn", "text": f"*IP:*\n{server_ip}"},
                        {"type": "mrkdwn", "text": f"*Metric:*\n{metric_type}.{metric_key}"},
                        {"type": "mrkdwn", "text": f"*Time:*\n{timestamp}"}
                    ]
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*Message:*\n{message}"
                    }
                }
            ]
        }
        
        with httpx.Client(timeout=10.0) as client:
            response = client.post(webhook_url, json=payload)
            if response.status_code >= 400:
                logger.error(f"Slack API error {response.status_code}: {response.text}")
                return False
        return True
    except Exception as e:
        logger.error(f"Slack fail: {e}")
        return False

def send_alert(alert_id: int) -> dict:
    """Send alert via all active channels"""
    if alert_id is None:
        logger.warning("send_alert called with alert_id=None, skipping")
        return {"error": "alert_id is None"}
        
    logger.info(f"🔔 send_alert processing alert {alert_id}...")
    with get_connection() as conn:
        query = select(alerts_table).where(alerts_table.c.id == alert_id)
        result = conn.execute(query).fetchone()
        if not result:
            return {"error": "Not found"}
        
        # Use _mapping for reliable named access in SQLAlchemy Core
        alert = result._mapping
        
        server_id = alert.get('server_id')
        alert_type = alert.get('alert_type') or "System"
        severity = alert.get('severity') or "critical"
        message = alert.get('message') or "No message content"
        
        server_name = "System"
        server_ip = "System"
        server_env = "prod"

        if server_id:
            s_query = select(server_status_table).where(server_status_table.c.id == server_id)
            s_result = conn.execute(s_query).fetchone()
            if s_result:
                s_row = s_result._mapping
                server_name = s_row.get('name') or "Unknown"
                server_ip = s_row.get('ip') or "Unknown"
                server_env = s_row.get('environment') or "prod"

        # Parse for metric details
        metric_type = "system"
        metric_key = alert_type
        if alert_type and "." in alert_type:
            metric_type, metric_key = alert_type.split('.', 1)

        # 1. Trigger Mobile App Alert (Primary)
        # This handles the internal "Voice/Ringing" experience
        try:
            from app.services.escalation import start_escalation
            import asyncio
            import threading
            
            # Start escalation in a background thread to avoid blocking
            def run_async_escalation(aid):
                try:
                    asyncio.run(start_escalation(aid))
                except Exception as e:
                    logger.error(f"Error in escalation background worker: {e}")

            threading.Thread(target=run_async_escalation, args=(alert_id,), daemon=True).start()
            logger.info(f"📱 Mobile escalation triggered for alert {alert_id} ({alert_type})")
            
            # BROADCAST UI REFRESH: Signal that a new alert is available
            try:
                from app.utils.ws_broadcast import broadcast_ui_update
                broadcast_ui_update("new_alert", {"alert_id": alert_id, "type": alert_type})
            except Exception as b_e:
                logger.error(f"Failed to broadcast alert create: {b_e}")
                
        except Exception as e:
            logger.error(f"Failed to start escalation background worker: {e}")
        
        # 2. Email and Slack (Secondary)
        res_email = False
        res_slack = False
        try:
            res_email = send_email_alert(alert_id, server_name, server_ip, metric_type, metric_key, 0.0, severity, message, server_env)
        except Exception as e: logger.error(f"Email error: {e}")
        
        try:
            res_slack = send_slack_alert(alert_id, server_name, server_ip, metric_type, metric_key, 0.0, severity, message, server_env)
        except Exception as e: logger.error(f"Slack error: {e}")

        return {
            "email": res_email,
            "slack": res_slack,
            "mobile_app": True
        }

def send_scheduler_metric_missing_alert(scheduler_name: str, metric_type: str, environment: str, reason: str, required_metrics: str) -> dict:
    """Send alert for missing metrics"""
    try:
        message = f"[{environment.upper()}] {scheduler_name}: Missing {metric_type} metrics. Reason: {reason}"
        with get_connection() as conn:
            stmt = alerts_table.insert().values(alert_type=f"missing.{metric_type}", severity="warning", message=message, is_resolved=False)
            result = conn.execute(stmt)
            conn.commit()
            alert_id = result.inserted_primary_key[0]
        
        return {
            "email": send_email_alert(alert_id, scheduler_name, "System", "scheduler", "missing", 0.0, "warning", message, environment),
            "slack": send_slack_alert(alert_id, scheduler_name, "System", "scheduler", "missing", 0.0, "warning", message, environment)
        }
    except Exception as e:
        logger.error(f"Missing metric alert fail: {e}")
        return {"error": str(e)}
