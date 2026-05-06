"""
Alert checking utility - checks metrics against thresholds and generates alerts
"""

import logging
from datetime import datetime
from sqlalchemy import select, update
from app.db.db import alert_thresholds_table, alerts_table, engine, get_connection
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

def get_severity_label(severity: str) -> str:
    """
    Map internal severity to user-facing labels with emojis
    - error -> 🔴 CRITICAL
    - warning -> ⚠️ WARNING
    """
    return '🔴 CRITICAL' if severity.lower() == 'error' else '⚠️ WARNING'

def format_alert_message(metric_type: str, metric_key: str, value: float, severity: str, warning_threshold: float, error_threshold: float, interface: str = None) -> str:
    """
    Format professional alert message based on severity
    Shows only the relevant threshold that was crossed
    """
    severity_label = get_severity_label(severity)
    
    # Determine which threshold to show
    if severity == 'error':
        threshold_value = error_threshold
        threshold_label = "critical threshold"
    else:
        threshold_value = warning_threshold
        threshold_label = "warning threshold"
    
    # Determine unit based on metric_key
    unit = "%"  # Default unit
    is_low_bad = False
    
    if metric_key == 'uptime':
        unit = " minutes"
        is_low_bad = True
    elif metric_key == 'db_status':
        unit = ""  # 0 or 1
        is_low_bad = True
    elif 'latency' in metric_key.lower():
        unit = " ms"
    elif 'count' in metric_key.lower() or 'qsize' in metric_key.lower():
        unit = ""  # No unit for counts
    elif 'throughput' in metric_key.lower():
        unit = " req/s"
    
    # Build professional message
    interface_label = "partition" if metric_key == "disk" else "interface"
    
    # SPECIAL CASE: Database Replication Status
    if metric_type == "database" and (metric_key == "status" or metric_key == "db_status") and value == 0:
        return "Database replication is DOWN"

    if is_low_bad:
        if interface:
            message = f"{metric_type}.{metric_key} on {interface_label} {interface} is {value:.2f}{unit} (below {threshold_label} of {threshold_value:.2f}{unit})"
        else:
            message = f"{metric_type}.{metric_key} is {value:.2f}{unit} (below {threshold_label} of {threshold_value:.2f}{unit})"
    else:
        if interface:
            message = f"{metric_type}.{metric_key} on {interface_label} {interface} is {value:.2f}{unit} (exceeded {threshold_label} of {threshold_value:.2f}{unit})"
        else:
            message = f"{metric_type}.{metric_key} is {value:.2f}{unit} (exceeded {threshold_label} of {threshold_value:.2f}{unit})"
    
    return message

def check_threshold(metric_type: str, metric_key: str, value: float) -> Optional[Tuple[str, float, float]]:
    """
    Check if a metric value crosses any threshold
    """
    try:
        with get_connection() as conn:
            query = select(alert_thresholds_table).where(
                alert_thresholds_table.c.metric_type == metric_type,
                alert_thresholds_table.c.metric_key == metric_key,
                alert_thresholds_table.c.enabled == True
            )
            threshold = conn.execute(query).fetchone()
            
            if not threshold:
                return None
            
            warning_threshold = threshold[3]
            error_threshold = threshold[4]
            
            # LOW IS BAD: Uptime (Hardware), Status (Database), Status (Network/Application)
            # Thresholds trigger when value <= threshold
            low_is_bad_metrics = ['uptime', 'status', 'db_status']
            
            if metric_key in low_is_bad_metrics:
                if value <= error_threshold:
                    return ('error', warning_threshold, error_threshold)
                elif value <= warning_threshold:
                    return ('warning', warning_threshold, error_threshold)
            else:
                if value >= error_threshold:
                    return ('error', warning_threshold, error_threshold)
                elif value >= warning_threshold:
                    return ('warning', warning_threshold, error_threshold)
            
            return None
    except Exception as e:
        logger.error(f"Error checking threshold for {metric_type}.{metric_key}: {e}", exc_info=True)
        return None

def create_alert(server_id: Optional[int], metric_type: str, metric_key: str, value: float, severity: str, warning_threshold: float, error_threshold: float):
    """
    Create an alert in the database and trigger notification channels
    """
    try:
        alert_id = None
        with engine.begin() as conn:
            query = select(alerts_table).where(
                alerts_table.c.server_id == server_id,
                alerts_table.c.alert_type == f"{metric_type}.{metric_key}",
                alerts_table.c.is_resolved == False
            )
            existing = conn.execute(query).fetchone()
            
            if existing:
                if severity == 'error' and existing[3] == 'warning':
                    interface = None
                    base_key = metric_key
                    if "." in metric_key:
                        parts = metric_key.split(".", 1)
                        base_key = parts[0]
                        interface = parts[1]
                    
                    msg_key = base_key
                    if base_key == "network_bandwidth": msg_key = "bandwidth"
                    
                    message = format_alert_message(metric_type, msg_key, value, severity, warning_threshold, error_threshold, interface)
                    
                    update_query = update(alerts_table).where(
                        alerts_table.c.id == existing[0]
                    ).values(
                        severity=severity,
                        message=message,
                        metric_value=value,
                        threshold_value=error_threshold if severity == 'error' else warning_threshold
                    )
                    conn.execute(update_query)
                    alert_id = existing[0]
                else:
                    return existing[0]
            else:
                interface = None
                base_key = metric_key
                if "." in metric_key:
                    parts = metric_key.split(".", 1)
                    base_key = parts[0]
                    interface = parts[1]
                    
                msg_key = base_key
                if base_key == "network_bandwidth": msg_key = "bandwidth"
                    
                message = format_alert_message(metric_type, msg_key, value, severity, warning_threshold, error_threshold, interface)
                
                insert_query = alerts_table.insert().values(
                    server_id=server_id,
                    alert_type=f"{metric_type}.{metric_key}",
                    severity=severity,
                    message=message,
                    metric_value=value,
                    threshold_value=error_threshold if severity == 'error' else warning_threshold,
                    is_resolved=False
                )
                result = conn.execute(insert_query)
                alert_id = result.inserted_primary_key[0]
        
        # TRIGGER NOTIFICATION (Mobile Escalation, Email, Slack)
        if alert_id:
            try:
                from app.utils.alert_sender import send_alert
                send_alert(alert_id)
            except Exception as notify_err:
                logger.error(f"Failed to trigger notifications for alert {alert_id}: {notify_err}")
                
        return alert_id
    except Exception as e:
        logger.error(f"Error creating alert: {e}", exc_info=True)
        return None

def resolve_alert_if_normal(server_id: Optional[int], metric_type: str, metric_key: str, value: float):
    """
    Check if a metric is back to normal and resolve any active alerts
    """
    try:
        threshold_result = check_threshold(metric_type, metric_key, value)
        if threshold_result is None:
            alert_type = f"{metric_type}.{metric_key}"
            with engine.begin() as conn:
                # 1. Find the alert ID before resolving
                query = select(alerts_table.c.id).where(
                    alerts_table.c.server_id == server_id,
                    alerts_table.c.alert_type == alert_type,
                    alerts_table.c.is_resolved == False
                )
                result = conn.execute(query).fetchone()
                
                if result:
                    alert_id = result[0]
                    
                    # 2. Mark alert as resolved
                    update_query = update(alerts_table).where(
                        alerts_table.c.id == alert_id
                    ).values(
                        is_resolved=True,
                        resolved_at=datetime.utcnow()
                    )
                    conn.execute(update_query)
                    
                    # 3. Stop any active escalations for this alert
                    from app.models.mobile import active_escalations_table
                    stop_esc_query = update(active_escalations_table).where(
                        active_escalations_table.c.alert_id == alert_id,
                        active_escalations_table.c.status == 'active'
                    ).values(
                        status='resolved',
                        updated_at=datetime.utcnow()
                    )
                    conn.execute(stop_esc_query)
                    logger.info(f"✅ Resolved alert {alert_id} and stopped its escalation ({alert_type})")
    except Exception as e:
        logger.error(f"Error in resolve_alert_if_normal: {e}")

def check_and_create_alert(server_id: Optional[int], metric_type: str, metric_key: str, value: float) -> Optional[int]:
    """
    Check metric against threshold and create alert if threshold is crossed.
    """
    threshold_result = check_threshold(metric_type, metric_key, value)
    if threshold_result:
        severity, warning_threshold, error_threshold = threshold_result
        return create_alert(server_id, metric_type, metric_key, value, severity, warning_threshold, error_threshold)
    else:
        resolve_alert_if_normal(server_id, metric_type, metric_key, value)
    return None

def check_and_create_alert_with_interface(server_id: int, metric_type: str, metric_key: str, value: float, interface_name: str) -> Optional[int]:
    """
    Check per-interface metric against threshold and create alert
    """
    threshold_result = check_threshold(metric_type, metric_key, value)
    if threshold_result:
        severity, warning_threshold, error_threshold = threshold_result
        metric_key_with_interface = f"{metric_key}.{interface_name}"
        return create_alert(server_id, metric_type, metric_key_with_interface, value, severity, warning_threshold, error_threshold)
    return None
