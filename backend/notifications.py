import httpx
import aiosmtplib
from email.message import EmailMessage
import os
from dotenv import load_dotenv

load_dotenv()

# Notification settings from environment or defaults
SMTP_HOST = os.getenv("SMTP_HOST", "localhost")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SMTP_FROM = os.getenv("SMTP_FROM", "alerts@smcindiaonline.com")

VOICE_ALERT_API = "https://smcalert.smcindiaonline.com/api/alerts"

async def send_email(to_emails: str, subject: str, body: str):
    if not to_emails:
        return
    
    message = EmailMessage()
    message["From"] = SMTP_FROM
    message["To"] = to_emails
    message["Subject"] = subject
    message.set_content(body)
    
    try:
        await aiosmtplib.send(
            message,
            hostname=SMTP_HOST,
            port=SMTP_PORT,
            username=SMTP_USER,
            password=SMTP_PASSWORD,
            use_tls=SMTP_PORT == 465
        )
        print(f"Email sent to {to_emails}")
    except Exception as e:
        print(f"Error sending email: {e}")

async def send_slack(webhook_url: str, text: str):
    if not webhook_url:
        return
    
    payload = {"text": text}
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(webhook_url, json=payload)
            response.raise_for_status()
            print(f"Slack notification sent")
        except Exception as e:
            print(f"Error sending Slack notification: {e}")

async def send_voice_alert(payload: dict):
    # Payload format as per roadmap
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(VOICE_ALERT_API, json=payload)
            response.raise_for_status()
            print(f"Voice alert sent")
        except Exception as e:
            print(f"Error sending voice alert: {e}")

async def notify(group_config, alert_data):
    # alert_data should have alert_name, instance, cluster, group, team, severity, status
    
    subject = f"[{alert_data['status'].upper()}] {alert_data['alert_name']} - {alert_data['instance']}"
    body = f"""
    Alert: {alert_data['alert_name']}
    Instance: {alert_data['instance']}
    Cluster: {alert_data['cluster']}
    Group: {alert_data['group']}
    Team: {alert_data['team']}
    Severity: {alert_data['severity']}
    Status: {alert_data['status']}
    Time: {alert_data.get('startsAt', '')}
    """

    # 1. Email
    if group_config.emails:
        await send_email(group_config.emails, subject, body)
    
    # 2. Slack
    if group_config.slack_webhook:
        await send_slack(group_config.slack_webhook, f"*{subject}*\n{body}")
    
    # 3. Voice
    if group_config.voice_enabled and alert_data['status'] == 'firing':
        voice_payload = {
            "alert_name": alert_data['alert_name'],
            "instance": alert_data['instance'],
            "group": alert_data['group'],
            "team": alert_data['team'],
            "cluster": alert_data['cluster'],
            "severity": alert_data['severity'],
            "status": alert_data['status'],
            "startsAt": alert_data.get('startsAt', '')
        }
        await send_voice_alert(voice_payload)
