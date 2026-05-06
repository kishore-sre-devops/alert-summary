import logging
from datetime import datetime, timedelta
from sqlalchemy import select, update, insert, delete, and_, or_, text
from app.db.db import engine, alerts_table, users_table, server_status_table
from app.models.mobile import active_escalations_table, escalation_policies_table, mobile_devices_table, mobile_alerts_table, incident_audit_trail_table
from app.services.push import send_push_notification
from app.services.tts import generate_tts
import json

logger = logging.getLogger(__name__)

async def start_escalation(alert_id: int, policy_id: int = None):
    """
    Starts an escalation process for a new alert.
    """
    logger.info(f"⚡ Entering start_escalation for alert_id={alert_id}")
    try:
        with engine.connect() as conn:
            # Check if alert exists and is not resolved
            logger.info(f"Checking alert {alert_id} in DB...")
            alert = conn.execute(
                select(alerts_table).where(alerts_table.c.id == alert_id)
            ).fetchone()
            
            if not alert:
                logger.warning(f"❌ Alert {alert_id} not found!")
                return
            if alert.is_resolved:
                logger.info(f"Alert {alert_id} is already resolved.")
                return

            logger.info(f"Checking for existing escalation for alert {alert_id}...")
            # Check if an escalation already exists for this alert
            existing_esc = conn.execute(
                select(active_escalations_table).where(
                    active_escalations_table.c.alert_id == alert_id,
                    active_escalations_table.c.status == 'active'
                )
            ).fetchone()
            
            should_start_new = True
            if existing_esc:
                # If escalation exists, only skip if it's the same severity or lower
                # If new alert is critical/error and existing was warning, we MUST re-trigger
                if alert.severity.lower() in ['critical', 'error'] and existing_esc.status == 'active':
                    # We want to re-trigger if the current step doesn't reflect the new severity
                    logger.info(f"Existing escalation found for alert {alert_id}, checking if severity upgrade is needed...")
                    # If we are already at step 0 and it was just started, maybe skip, 
                    # but usually it's better to allow re-triggering for severity changes
                    should_start_new = True 
                else:
                    logger.info(f"Escalation already active for alert {alert_id}, skipping start")
                    return

            logger.info(f"Finding policy for alert {alert_id}...")
            # If no policy specified, try to find a default one (e.g. first enabled one)
            if not policy_id:
                policy = conn.execute(
                    select(escalation_policies_table).where(escalation_policies_table.c.enabled == True).limit(1)
                ).fetchone()
                if policy:
                    policy_id = policy.id
            
            if not policy_id:
                logger.warning(f"No escalation policy found for alert {alert_id}")
                return

            logger.info(f"Policy ID identified: {policy_id}")
            # Check if escalation already exists to avoid UniqueViolation
            check_stmt = select(active_escalations_table.c.id).where(active_escalations_table.c.alert_id == alert_id)
            existing = conn.execute(check_stmt).fetchone()

            if existing:
                logger.info(f"Escalation already exists for alert {alert_id}, updating...")
                stmt = update(active_escalations_table).where(
                    active_escalations_table.c.alert_id == alert_id
                ).values(
                    status='active',
                    current_step=0,
                    next_escalation_at=datetime.utcnow(),
                    updated_at=datetime.utcnow()
                )
            else:
                logger.info(f"Inserting new active_escalations record for alert {alert_id}...")
                # Create active escalation record
                stmt = insert(active_escalations_table).values(
                    alert_id=alert_id,
                    policy_id=policy_id,
                    current_step=0,
                    next_escalation_at=datetime.utcnow(), # Start immediately
                    status='active',
                    created_at=datetime.utcnow(),
                    updated_at=datetime.utcnow()
                )
            conn.execute(stmt)
            conn.commit()
            logger.info(f"Started/Updated escalation for alert {alert_id} with policy {policy_id}")
            
            # Log to Incident Audit Trail
            try:
                logger.info(f"Attempting to log 'Triggered' action for alert {alert_id}...")
                conn.execute(insert(incident_audit_trail_table).values(
                    alert_id=alert_id,
                    action="Triggered",
                    details=json.dumps({"severity": alert.severity, "metric": alert.alert_type}),
                    created_at=datetime.utcnow()
                ))
                conn.commit()
                logger.info(f"✅ Audit log 'Triggered' recorded for alert {alert_id}")
            except Exception as e: 
                logger.error(f"❌ Failed to log audit trail for alert {alert_id}: {e}")

            # Trigger immediate processing
            logger.info(f"Calling process_escalations() for alert {alert_id}...")
            await process_escalations()


    except Exception as e:
        logger.error(f"Failed to start escalation: {e}")

async def acknowledge_alert_with_ert(alert_id: int, user_id: int, ert_minutes: int, justification: str = None):
    """
    Acknowledges an alert, pausing escalation until ERT expires.
    """
    try:
        ert_at = datetime.utcnow() + timedelta(minutes=ert_minutes)
        with engine.connect() as conn:
            # 1. Update active escalation with ERT
            stmt_esc = update(active_escalations_table).where(
                active_escalations_table.c.alert_id == alert_id
            ).values(
                status='acknowledged',
                ert_at=ert_at,
                ert_justification=justification,
                updated_at=datetime.utcnow()
            )
            conn.execute(stmt_esc)
            
            # 2. Update OR Insert mobile_alerts entry
            # Check if record exists
            check_mobile = conn.execute(select(mobile_alerts_table).where(
                and_(mobile_alerts_table.c.alert_id == alert_id, mobile_alerts_table.c.user_id == user_id)
            )).fetchone()

            if check_mobile:
                stmt_track = update(mobile_alerts_table).where(
                    and_(mobile_alerts_table.c.alert_id == alert_id, mobile_alerts_table.c.user_id == user_id)
                ).values(
                    status='acknowledged',
                    acknowledged_by=user_id,
                    acknowledged_at=datetime.utcnow(),
                    ert_at=ert_at,
                    ert_justification=justification
                )
            else:
                # If no record (e.g. manual ack before push or for other users), create one
                stmt_track = insert(mobile_alerts_table).values(
                    alert_id=alert_id,
                    user_id=user_id,
                    title="Manual Acknowledge",
                    body="User acknowledged alert in-app",
                    status='acknowledged',
                    acknowledged_by=user_id,
                    acknowledged_at=datetime.utcnow(),
                    ert_at=ert_at,
                    ert_justification=justification,
                    created_at=datetime.utcnow()
                )
            conn.execute(stmt_track)
            
            conn.commit()
            logger.info(f"Alert {alert_id} acknowledged by user {user_id} with ERT {ert_minutes}m")
            
            # BROADCAST: Tell all devices to stop ringing
            try:
                from app.utils.ws_broadcast import broadcast_ui_update
                broadcast_ui_update("alert_acknowledged", {"alert_id": alert_id, "user_id": user_id})
            except: pass
            
            return True
    except Exception as e:
        logger.error(f"Ack with ERT failed: {e}")
        return False

async def acknowledge_alert(alert_id: int, user_id: int):
    # Fallback to 10 min default if no ERT specified
    return await acknowledge_alert_with_ert(alert_id, user_id, 10, "Manual Acknowledge (Default 10m)")

async def process_escalations():
    """
    Checks for active escalations due for the next step or expired ERT.
    """
    try:
        with engine.connect() as conn:
            # Find active escalations:
            # - status 'active' and next_escalation_at <= now
            # - status 'acknowledged' and ert_at < now AND is_resolved is False
            query = select(
                active_escalations_table.c.id,
                active_escalations_table.c.alert_id,
                active_escalations_table.c.current_step,
                active_escalations_table.c.policy_id,
                active_escalations_table.c.status.label("esc_status"),
                active_escalations_table.c.ert_justification,
                escalation_policies_table.c.steps,
                alerts_table.c.message,
                alerts_table.c.severity,
                alerts_table.c.alert_type,
                alerts_table.c.is_resolved,
                alerts_table.c.metric_value,
                alerts_table.c.threshold_value,
                server_status_table.c.name.label("server_name"),
                server_status_table.c.ip.label("server_ip")
            ).join(
                escalation_policies_table, 
                active_escalations_table.c.policy_id == escalation_policies_table.c.id
            ).join(
                alerts_table,
                active_escalations_table.c.alert_id == alerts_table.c.id
            ).outerjoin(
                server_status_table,
                alerts_table.c.server_id == server_status_table.c.id
            ).where(
                and_(
                    alerts_table.c.is_resolved == False,
                    or_(
                        and_(
                            active_escalations_table.c.status == 'active',
                            active_escalations_table.c.next_escalation_at <= datetime.utcnow()
                        ),
                        and_(
                            active_escalations_table.c.status == 'acknowledged',
                            active_escalations_table.c.ert_at <= datetime.utcnow()
                        )
                    )
                )
            )
            
            results = conn.execute(query).fetchall()
            if results:
                logger.info(f"🔍 Found {len(results)} active escalations due for processing")
            
            for row in results:
                esc = row._mapping
                esc_id = esc['id']
                alert_id = esc['alert_id']
                current_step_idx = esc['current_step']
                steps = esc['steps']
                status = esc['esc_status']
                message = esc['message'] or "Alert triggered"
                severity = esc['severity']
                
                if not steps or not isinstance(steps, list):
                    logger.warning(f"No steps found for escalation {esc_id}, marking completed")
                    conn.execute(update(active_escalations_table).where(active_escalations_table.c.id == esc_id).values(status='completed'))
                    conn.commit()
                    continue

                # Escalation Logic:
                # If was 'acknowledged' but ERT expired -> move to next level
                new_step_idx = current_step_idx
                if status == 'acknowledged':
                    new_step_idx += 1
                    logger.info(f"⏰ ERT Expired for alert {alert_id}. Escalating to level {new_step_idx}")
                    
                    # Log ERT Expiry to Audit Trail
                    try:
                        conn.execute(insert(incident_audit_trail_table).values(
                            alert_id=alert_id,
                            action="ERT Expired",
                            details=json.dumps({"failed_step": current_step_idx, "justification": esc['ert_justification']}),
                            created_at=datetime.utcnow()
                        ))
                        conn.commit()
                    except: pass
                
                # Boundary check: If we reached the end, repeat the last step every 5 mins
                if new_step_idx >= len(steps):
                    new_step_idx = len(steps) - 1
                    next_run = datetime.utcnow() + timedelta(minutes=5)
                    logger.info(f"🔄 Reaching final level for alert {alert_id}. Re-triggering in 5m.")
                else:
                    # Normal delay from policy for next step
                    delay = steps[new_step_idx].get('delay', 5)
                    next_run = datetime.utcnow() + timedelta(minutes=delay)

                step = steps[new_step_idx]
                user_ids = step.get('notify', [])
                
                # Prepare data with full details
                server_ip = esc['server_ip'] or "Unknown IP"
                metric_raw = esc['alert_type'] or "System"
                
                # Extract hardware/interface details from metric key if available
                hardware_details = "N/A"
                component_prefix = ""
                if metric_raw == "server.down":
                    hardware_details = "Network Heartbeat"
                elif "." in metric_raw:
                    parts = metric_raw.split(".")
                    if len(parts) >= 3:
                        hardware_details = parts[2] # e.g. network.bandwidth.eth0 -> eth0
                        if "disk" in metric_raw: component_prefix = "of Drive: "
                        elif "bandwidth" in metric_raw: component_prefix = "of Interface: "
                    elif parts[0] == 'hardware' and len(parts) >= 2:
                        # For hardware.cpu or hardware.memory, parts[1] is the detail
                        hardware_details = parts[1].upper()
                    else:
                        hardware_details = "System"
                
                # --- PROFESSIONAL METRIC TRANSLATOR ---
                METRIC_VOICE_MAP = {
                    'application.failureAuthentication': ('Application Client Authentication Failure Count', 'Count'),
                    'application.failureTradeApi': ('Application Trading API Failure Count', 'Count'),
                    'application.historicalLatency': ('Application Historical Response Time', 'Milliseconds'),
                    'application.historicalThroughput': ('Application Historical Throughput', 'Requests per Second'),
                    'application.latency': ('Application Response Time', 'Milliseconds'),
                    'application.log': ('Application Log Monitoring', ''),
                    'application.throughput': ('Application Throughput', 'Requests per Second'),
                    'database.bandwidth': ('Database Replication Bandwidth Utilization', 'Percent'),
                    'database.latency': ('Database Replication Latency', 'Milliseconds'),
                    'database.qSize': ('Database Replication Queue Size', 'Units'),
                    'database.status': ('Database Replication Status', ''),
                    'hardware.cpu': ('Hardware CPU Utilization', 'Percent'),
                    'hardware.disk': ('Disk Space Usage', 'Percent'),
                    'hardware.memory': ('Hardware Memory Utilization', 'Percent'),
                    'hardware.uptime': ('Hardware Uptime', 'Minutes'),
                    'network.bandwidth': ('Network Bandwidth', 'Percent'),
                    'network.packetCount': ('Network Packet Error Count', 'Errors'),
                    'network.latency': ('Network Latency', 'Milliseconds')
                }
                
                # Use base metric for lookup if it has parts (e.g. hardware.disk.C: -> hardware.disk)
                base_metric = metric_raw
                if "." in metric_raw:
                    parts_for_lookup = metric_raw.split(".")
                    if len(parts_for_lookup) >= 2:
                        base_metric = f"{parts_for_lookup[0]}.{parts_for_lookup[1]}"

                mapped_name, unit = METRIC_VOICE_MAP.get(base_metric, (None, ""))
                
                if not mapped_name:
                    # Robust fallback: Replace dots/underscores, split camelCase, and capitalize
                    import re
                    clean_name = metric_raw.replace('.', ' ').replace('_', ' ')
                    # Split camelCase (e.g. failureTradeApi -> failure Trade Api)
                    clean_name = re.sub(r'([a-z])([A-Z])', r'\1 \2', clean_name)
                    metric_name = clean_name.title()
                else:
                    metric_name = mapped_name
                
                # --- UNIT FORMATTING LOGIC ---
                # Map full unit names to symbols for the UI
                UNIT_SYMBOL_MAP = {
                    'Percent': '%',
                    'Milliseconds': 'ms',
                    'Requests per Second': ' Req/s',
                    'Minutes': 'm',
                    'Count': '',
                    'Errors': ' errors',
                    'Units': ''
                }
                unit_symbol = UNIT_SYMBOL_MAP.get(unit, "")
                
                # Format the numeric values for display
                raw_val = esc['metric_value'] or 0.0
                raw_thresh = esc['threshold_value'] or 0.0
                
                # Professional formatting: 1 decimal place if float, else plain
                display_val = f"{float(raw_val):.1f}" if float(raw_val) % 1 != 0 else str(int(raw_val))
                display_thresh = f"{float(raw_thresh):.1f}" if float(raw_thresh) % 1 != 0 else str(int(raw_thresh))
                
                val_with_unit = f"{display_val}{unit_symbol}"
                thresh_with_unit = f"{display_thresh}{unit_symbol}"
                
                # Voice friendly values (use full word 'Percent' instead of '%')
                voice_val = f"{display_val} {unit}" if unit else display_val
                if str(raw_val).lower() == "0.0" and "status" in metric_raw.lower():
                    voice_val = "DOWN"
                    val_with_unit = "DOWN"

                # Send Notification
                logger.info(f"🚀 Executing step {new_step_idx} for alert {alert_id} -> Users {user_ids}")
                
                # Create the professional body text for UI display
                formatted_body = f"{metric_name} is {val_with_unit} (Threshold: {thresh_with_unit}) on {esc['server_name']} ({server_ip})."
                
                # --- TTS SANITIZATION LOGIC ---
                # 1. Convert Server Name to Voice Friendly (No dashes, Title Case to prevent spelling out)
                v_server_name = str(esc['server_name']).replace('-', ' ').replace('_', ' ').title()
                # 2. Convert IP to Voice Friendly (192.168 -> 192 dot 168)
                v_server_ip = str(server_ip).replace('.', ' dot ')
                # 3. Convert Metric and Hardware to Voice Friendly
                v_metric = str(metric_name).title()
                v_hardware = str(hardware_details).replace('-', ' ').replace('_', ' ').replace(':', ' ').title() if hardware_details not in ["N/A", "System"] else ""
                v_severity = str(severity).lower()
                v_value = str(voice_val).lower().replace('%', ' percent')

                # CREATE THE REQUESTED VOICE ALERT STRING
                # User requested format: "Attention Required: ServerName ServerIP. MetricName of Drive: D: is 50% and is in [severity] state, kindly check and resolve."
                v_component = f" of {component_prefix} {v_hardware}" if v_hardware else ""
                voice_alert_str = f"Attention Required: {v_server_name} {v_server_ip}. {v_metric}{v_component} is {v_value} and is in {v_severity} state, kindly check and resolve."
                
                await send_push_notification(
                    user_ids=user_ids,
                    title=f"🚨 {severity.upper()} ALERT: {metric_name}",
                    body=formatted_body,
                    data={
                        "type": "call",
                        "alert_id": str(alert_id),
                        "site_name": str(esc['server_name']),
                        "server_ip": str(server_ip),
                        "alert_type": str(metric_name),
                        "hardware_details": str(hardware_details),
                        "message": formatted_body, # UI Display Message
                        "voice_alert": voice_alert_str, # Professional Voice String
                        "severity": str(severity),
                        "metric_value": val_with_unit,
                        "threshold_value": thresh_with_unit,
                        "voice_message_value": voice_val, # Keep for legacy compatibility
                        "alert_time": (datetime.utcnow() + timedelta(hours=5, minutes=30)).strftime("%I:%M %p")
                    },
                    severity=severity
                )

                # Log Escalation/Notification to Audit Trail
                try:
                    conn.execute(insert(incident_audit_trail_table).values(
                        alert_id=alert_id,
                        action="Escalated",
                        details=json.dumps({
                            "level": new_step_idx + 1,
                            "notified_users_count": len(user_ids),
                            "triggered_by": "ERT_Expiry" if status == 'acknowledged' else "Time_Delay"
                        }),
                        created_at=datetime.utcnow()
                    ))
                    conn.commit()
                except: pass

                # Update escalation state
                conn.execute(update(active_escalations_table).where(active_escalations_table.c.id == esc_id).values(
                    status='active',
                    current_step=new_step_idx,
                    next_escalation_at=next_run,
                    last_processed_at=datetime.utcnow(),
                    ert_at=None,
                    updated_at=datetime.utcnow()
                ))
                conn.commit()

    except Exception as e:
        logger.error(f"process_escalations error: {e}", exc_info=True)

async def can_user_acknowledge(alert_id: int, user_id: int):
    # Standard logic: if user is in any escalation step or is admin
    return True # Simple version for now
