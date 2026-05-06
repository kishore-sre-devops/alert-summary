import logging
import os
import json
from datetime import datetime
import firebase_admin
from firebase_admin import credentials, messaging
from app.db.db import engine, users_table, audit_logs_table
from app.models.mobile import mobile_devices_table
from sqlalchemy import select, and_, insert, delete

logger = logging.getLogger(__name__)

# Initialize Firebase Admin
# Expects google-services.json content in FIREBASE_CREDENTIALS env var or path
FIREBASE_CREDENTIALS_PATH = os.getenv("FIREBASE_CREDENTIALS_PATH", "firebase-credentials.json")

_firebase_app = None

def init_firebase():
    global _firebase_app
    if _firebase_app:
        return

    try:
        if os.path.exists(FIREBASE_CREDENTIALS_PATH):
            cred = credentials.Certificate(FIREBASE_CREDENTIALS_PATH)
            _firebase_app = firebase_admin.initialize_app(cred)
            logger.info("Firebase Admin initialized successfully")
        else:
            logger.warning(f"Firebase credentials not found at {FIREBASE_CREDENTIALS_PATH}. Push notifications will fail.")
    except Exception as e:
        logger.error(f"Failed to initialize Firebase: {e}")

async def send_push_notification(user_ids: list[int], title: str, body: str, data: dict = None, severity: str = "info"):
    """
    Sends push notification to specified users' registered devices.
    """
    if not _firebase_app:
        init_firebase()
        if not _firebase_app:
            return 0

    if not user_ids:
        return 0

    if data is None:
        data = {}
    
    # Normalize 'error' to 'critical' for mobile consistency
    if severity.lower() == "error":
        severity = "critical"

    # Add severity to data for client-side handling (e.g. playing alarm sound)
    data["severity"] = severity
    # Ensure all data values are strings for FCM
    data = {k: str(v) for k, v in data.items()}

    try:
        with engine.connect() as conn:
            # 1. Get all users and their devices
            query = select(
                users_table.c.id,
                users_table.c.email,
                mobile_devices_table.c.push_token,
                mobile_devices_table.c.is_logged_in
            ).outerjoin(
                mobile_devices_table,
                users_table.c.id == mobile_devices_table.c.user_id
            ).where(
                users_table.c.id.in_(user_ids)
            )
            
            user_device_data = conn.execute(query).fetchall()
            
            user_tokens_map = {} # user_id -> list of tokens
            user_email_map = {}
            
            logger.info(f"🔍 Found {len(user_device_data)} rows in DB for user_ids {user_ids}")

            for row in user_device_data:
                u_id, u_email, u_token, u_logged_in = row
                user_email_map[u_id] = u_email
                
                logger.debug(f"Row: id={u_id}, email={u_email}, token={u_token[:10]}..., logged_in={u_logged_in}")

                # STRICT AUTOMATION: Only collect tokens where is_logged_in is True
                if u_token and bool(u_logged_in):
                    if u_id not in user_tokens_map: user_tokens_map[u_id] = []
                    user_tokens_map[u_id].append(u_token)
                else:
                    logger.info(f"⚠️ User {u_email} (ID {u_id}) skipped. Token present: {bool(u_token)}, Logged in: {u_logged_in}")

            tokens = []
            active_users = []
            skipped_users = []
            
            for u_id in user_ids:
                if u_id in user_tokens_map and user_tokens_map[u_id]:
                    tokens.extend(user_tokens_map[u_id])
                    active_users.append(u_id)
                else:
                    skipped_users.append({"id": u_id, "email": user_email_map.get(u_id, "Unknown"), "reason": "logged_out"})

        # Log skipping only if no active device was found for that user
        if skipped_users:
            for skipped in skipped_users:
                logger.info(f"⏭️ Skipping alert for user {skipped['email']} (Reason: {skipped['reason']})")
                
                # Record the skip in mobile_alerts for history visibility
                try:
                    from app.models.mobile import mobile_alerts_table
                    conn.execute(insert(mobile_alerts_table).values(
                        alert_id=int(data.get("alert_id")) if data.get("alert_id") and data.get("alert_id").isdigit() else None,
                        user_id=skipped['id'],
                        title=title,
                        body=body,
                        severity=severity,
                        status="skipped_logged_out" if skipped['reason'] == "logged_out" else "no_device",
                        created_at=datetime.utcnow()
                    ))
                    conn.commit()
                except Exception as log_err:
                    logger.warning(f"Failed to record skip for {skipped['email']}: {log_err}")

        if not tokens:
            logger.info(f"No active logged-in devices found for users {user_ids}")
            return 0

        # Prepare Data Payload
        data_payload = {
            **data,
            "severity": severity,
            "title": title, # Critical for Android Service
            "message": body, # Critical for Android Service
            "id": data.get("alert_id", str(int(datetime.utcnow().timestamp()))), # Added 'id' for IncomingAlertScreen.js
            "alertId": data.get("alert_id", str(int(datetime.utcnow().timestamp()))),
            "screen": "IncomingAlert",
            "created_at": str(datetime.utcnow()),
            "site_name": data.get("site_name", "Unknown"),
            "alert_type": data.get("alert_type", "Alert")
        }
        
        logger.info(f"📤 Push Data Payload: {json.dumps(data_payload)}")

        # Construct Message based on Severity
        if severity.lower() in ['critical', 'error', 'warning']:
            # CRITICAL/ERROR/WARNING: Data-only message for native voice alert handling
            android_config = messaging.AndroidConfig(
                priority='high',
                ttl=0, # Immediate delivery
                data=data_payload # Redundant but safe
            )
            
            message = messaging.MulticastMessage(
                tokens=tokens,
                # NO notification block for critical/warning alerts
                data=data_payload,
                android=android_config,
                apns=messaging.APNSConfig(
                    payload=messaging.APNSPayload(
                        aps=messaging.Aps(
                            content_available=True, # Wakes up iOS app in background
                            sound='alarm.mp3' if severity.lower() != 'warning' else 'warning.mp3',
                            category="critical" if severity.lower() != 'warning' else "warning"
                        )
                    )
                )
            )
        else:
            # STANDARD: Notification message for normal alerts
            message = messaging.MulticastMessage(
                tokens=tokens,
                notification=messaging.Notification(
                    title=title,
                    body=body,
                ),
                data=data_payload,
                android=messaging.AndroidConfig(
                    priority='normal',
                    notification=messaging.AndroidNotification(
                        channel_id='smc_alerts',
                        icon='ic_notification',
                        color='#2196F3'
                    )
                ),
                 apns=messaging.APNSConfig(
                    payload=messaging.APNSPayload(
                        aps=messaging.Aps(
                            sound='default'
                        )
                    )
                )
            )

        response = messaging.send_each_for_multicast(message)
        logger.info(f"Sent {response.success_count} messages. Failed: {response.failure_count}")
        
        # Record successful sends in mobile_alerts
        if response.success_count > 0:
            with engine.connect() as conn:
                for u_id in active_users:
                    try:
                        conn.execute(insert(mobile_alerts_table).values(
                            alert_id=int(data.get("alert_id")) if data.get("alert_id") and data.get("alert_id").isdigit() else None,
                            user_id=u_id,
                            title=title,
                            body=body,
                            severity=severity,
                            status="sent",
                            created_at=datetime.utcnow()
                        ))
                        conn.commit()
                    except:
                        pass
        
        # Cleanup invalid tokens
        if response.failure_count > 0:
            invalid_tokens = []
            for idx, resp in enumerate(response.responses):
                if not resp.success:
                    # Check for invalid token error codes
                    if resp.exception.code == 'NOT_FOUND' or resp.exception.code == 'INVALID_ARGUMENT':
                        invalid_tokens.append(tokens[idx])
            
            if invalid_tokens:
                 with engine.connect() as conn:
                    # Remove invalid tokens
                    # Note: We can't easily delete by token in Core without a WHERE clause
                    # Assuming mobile_devices_table.c.push_token is unique
                    from sqlalchemy import delete
                    stmt = delete(mobile_devices_table).where(mobile_devices_table.c.push_token.in_(invalid_tokens))
                    conn.execute(stmt)
                    conn.commit()
                    logger.info(f"Removed {len(invalid_tokens)} invalid tokens")

        return response.success_count

    except Exception as e:
        logger.error(f"Error sending push notification: {e}")
        return 0
