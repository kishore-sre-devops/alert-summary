"""
Server Down Monitor - Detects when servers go down and creates alerts
"""

import logging
from datetime import datetime, timedelta
from sqlalchemy import select, update, text
from app.db.db import server_status_table, alerts_table, engine, get_connection
from typing import List, Optional
from app.utils.alert_sender import send_alert
from app.utils.hot_store import update_hot_store_server_status

logger = logging.getLogger(__name__)

# Configuration: Server is considered DOWN if no heartbeat received in last N minutes
SERVER_DOWN_THRESHOLD_MINUTES = 5  # Reduced to 5m for faster detection

def check_server_down_status(server_id: int, server_name: str, server_ip: str, 
                            last_seen: datetime) -> bool:
    """
    Check if a server is down based on last_seen
    Returns: True if server is down, False if server is up
    """
    try:
        now = datetime.now()
        
        # Use last_seen (now updated by Prometheus collector)
        last_activity = last_seen
        
        if not last_activity:
            # Server has never sent a heartbeat - consider it down
            return True
        
        # Check if last activity is older than threshold
        time_since_last_activity = now - last_activity
        threshold = timedelta(minutes=SERVER_DOWN_THRESHOLD_MINUTES)
        
        is_down = time_since_last_activity > threshold
        if is_down:
            logger.info(f"🔍 Server {server_name} ({server_ip}) considered DOWN: last_activity={last_activity}, now={now}, diff={time_since_last_activity.total_seconds()/60:.2f}m, threshold={SERVER_DOWN_THRESHOLD_MINUTES}m")
        
        return is_down
    except Exception as e:
        logger.error(f"Error checking server down status for server {server_id}: {e}", exc_info=True)
        return False  # Default to not down if check fails

def create_server_down_alert(server_id: int, server_name: str, server_ip: str, 
                             last_seen: datetime, environment: str = "prod") -> Optional[int]:
    """
    Create an alert for a server that is down
    Returns: alert_id if alert was created, None otherwise
    """
    try:
        with get_connection() as conn:
            # Check if alert already exists (not resolved) for this server
            query = select(alerts_table).where(
                alerts_table.c.server_id == server_id,
                alerts_table.c.alert_type == "server.down",
                alerts_table.c.is_resolved == False
            )
            existing = conn.execute(query).fetchone()
            
            if existing:
                # Alert already exists - don't create duplicate
                logger.debug(f"Server down alert already exists for server {server_id} ({server_name})")
                return existing[0]  # Return existing alert ID
            
            # Calculate time since last seen
            now = datetime.now()
            if last_seen:
                time_since = now - last_seen
                minutes_ago = int(time_since.total_seconds() / 60)
                last_seen_str = f"{minutes_ago} minutes ago"
            else:
                last_seen_str = "Never"
            
            # Create new alert
            message = f"Server {server_name} ({server_ip}) is DOWN - Last seen: {last_seen_str}"
            
            insert_query = alerts_table.insert().values(
                server_id=server_id,
                alert_type="server.down",
                severity="error",  # Server down is always error severity
                message=message,
                is_resolved=False
            )
            result = conn.execute(insert_query)
            conn.commit()
            alert_id = result.inserted_primary_key[0]
            
            logger.warning(f"🚨 Created server down alert for server {server_id} ({server_name}): {message}")
            
            # Send alert via configured channels (email, slack, SMS)
            try:
                send_result = send_alert(alert_id)
                if send_result and not send_result.get("error"):
                    logger.info(f"✅ Server down alert sent via channels: {send_result}")
                else:
                    logger.warning(f"⚠️  Server down alert created but sending failed: {send_result}")
            except Exception as send_error:
                logger.error(f"Error sending server down alert: {send_error}", exc_info=True)
                # Don't fail alert creation if sending fails
            
            return alert_id
    except Exception as e:
        logger.error(f"Error creating server down alert for server {server_id}: {e}", exc_info=True)
        return None

def resolve_server_down_alert(server_id: int, server_name: str) -> bool:
    """
    Resolve (mark as resolved) any existing server down alerts for a server
    Returns: True if alert was resolved, False otherwise
    """
    try:
        with get_connection() as conn:
            # Find unresolved server down alerts for this server
            query = select(alerts_table).where(
                alerts_table.c.server_id == server_id,
                alerts_table.c.alert_type == "server.down",
                alerts_table.c.is_resolved == False
            )
            unresolved_alerts = conn.execute(query).fetchall()
            
            if not unresolved_alerts:
                return False  # No alerts to resolve
            
            # Resolve all unresolved alerts
            now = datetime.now()
            for alert in unresolved_alerts:
                alert_id = alert[0]
                update_query = update(alerts_table).where(
                    alerts_table.c.id == alert_id
                ).values(
                    is_resolved=True,
                    resolved_at=now
                )
                conn.execute(update_query)
            
            conn.commit()
            
            logger.info(f"✅ Resolved {len(unresolved_alerts)} server down alert(s) for server {server_id} ({server_name})")
            
            # BROADCAST UI REFRESH: Signal that alerts were resolved
            try:
                from app.utils.ws_broadcast import broadcast_ui_update
                broadcast_ui_update("alerts_resolved", {"server_id": server_id, "count": len(unresolved_alerts)})
            except Exception as b_e:
                logger.error(f"Failed to broadcast alerts resolve: {b_e}")
                
            return True
    except Exception as e:
        logger.error(f"Error resolving server down alert for server {server_id}: {e}", exc_info=True)
        return False

def monitor_servers_for_down_status(environment: Optional[str] = None):
    """
    Monitor all servers and create/resolve alerts based on their status
    This function should be called periodically (e.g., every 2-5 minutes)
    """
    try:
        logger.info(f"[SERVER_DOWN_MONITOR] Starting server down status check (environment={environment})")
        
        with get_connection() as conn:
            # Query to get all servers with their last_seen
            query = text("""
                SELECT 
                    id,
                    name,
                    ip,
                    environment,
                    status,
                    last_seen
                FROM server_status
                WHERE (:environment IS NULL OR environment = :environment)
                ORDER BY environment, id
            """)
            
            params = {"environment": environment}
            result = conn.execute(query, params)
            servers = result.fetchall()
            
            logger.info(f"[SERVER_DOWN_MONITOR] Checking {len(servers)} server(s)")
            
            alerts_created = 0
            alerts_resolved = 0
            
            for row in servers:
                server_id = row[0]
                server_name = row[1]
                server_ip = row[2]
                server_env = row[3] or "prod"
                server_status = row[4] or "offline"
                last_seen = row[5]
                
                # Check if server is down based on Postgres last_seen
                is_down = check_server_down_status(server_id, server_name, server_ip, last_seen)
                
                # CRITICAL FIX: If considered down, DOUBLE CHECK ClickHouse for recent metrics
                # This prevents "Fake" alerts when Postgres last_seen is delayed
                if is_down:
                    try:
                        # Check ClickHouse for ANY metrics in last 5 minutes
                        from app.db.db import clickhouse_client
                        ch_check = clickhouse_client.command(f"""
                            SELECT count() FROM lama.server_metrics 
                            WHERE server_id = {server_id} 
                            AND ts >= now() - INTERVAL 5 MINUTE
                        """)
                        if int(ch_check) > 0:
                            logger.info(f"🛡️  Fake down prevented for {server_name}: ClickHouse has {ch_check} recent points.")
                            is_down = False
                            
                            # Self-Heal Postgres: Update last_seen so monitor stops tripping
                            with get_connection() as conn_heal:
                                conn_update = update(server_status_table).where(
                                    server_status_table.c.id == server_id
                                ).values(last_seen=datetime.now(), status="online")
                                conn_heal.execute(conn_update)
                                conn_heal.commit()
                    except Exception as ch_err:
                        logger.error(f"ClickHouse liveness check failed: {ch_err}")

                if is_down:
                    # Server is down - update status in DB
                    if server_status != "offline":
                        with get_connection() as conn_update:
                            conn_update.execute(
                                update(server_status_table)
                                .where(server_status_table.c.id == server_id)
                                .values(status="offline", updated_at=datetime.now())
                            )
                            conn_update.commit()
                        # Update Hot-Store
                        update_hot_store_server_status(server_id, {"status": "offline"})
                        logger.info(f"Updated server {server_id} ({server_name}) status to offline")

                    # Create alert if not already exists
                    alert_id = create_server_down_alert(server_id, server_name, server_ip, last_seen, server_env)
                    if alert_id:
                        alerts_created += 1
                else:
                    # Server is up - update status in DB
                    if server_status != "online":
                        with get_connection() as conn_update:
                            conn_update.execute(
                                update(server_status_table)
                                .where(server_status_table.c.id == server_id)
                                .values(status="online", updated_at=datetime.now())
                            )
                            conn_update.commit()
                        # Update Hot-Store
                        update_hot_store_server_status(server_id, {"status": "online"})
                        logger.info(f"Updated server {server_id} ({server_name}) status to online")

                    # resolve any existing alerts
                    if resolve_server_down_alert(server_id, server_name):
                        alerts_resolved += 1
            
            logger.info(f"[SERVER_DOWN_MONITOR] ✅ Check complete: {alerts_created} alert(s) created, {alerts_resolved} alert(s) resolved")
            
            return {
                "servers_checked": len(servers),
                "alerts_created": alerts_created,
                "alerts_resolved": alerts_resolved
            }
    except Exception as e:
        logger.error(f"[SERVER_DOWN_MONITOR] Error monitoring servers: {e}", exc_info=True)
        return {
            "error": str(e),
            "servers_checked": 0,
            "alerts_created": 0,
            "alerts_resolved": 0
        }

def server_down_monitor_scheduler():
    """
    Scheduler function to monitor servers for down status
    This runs periodically and checks all servers
    """
    from app.utils.scheduler_logger import log_scheduler_start, log_scheduler_end
    import time
    start_time = time.time()
    scheduler_name = "Server Down Monitor"
    
    try:
        # Log start
        log_scheduler_start(scheduler_name, "all")
        
        # Check both UAT and PROD environments
        for env in ['uat', 'prod']:
            try:
                result = monitor_servers_for_down_status(environment=env)
                logger.info(f"[SERVER_DOWN_MONITOR] {env.upper()}: {result}")
            except Exception as e:
                logger.error(f"[SERVER_DOWN_MONITOR] Error checking {env.upper()} servers: {e}", exc_info=True)
        
        # Log success
        duration_ms = int((time.time() - start_time) * 1000)
        log_scheduler_end(scheduler_name, "all", duration_ms)
        
    except Exception as e:
        logger.error(f"[SERVER_DOWN_MONITOR] Scheduler error: {e}", exc_info=True)
        # Log failure
        try:
            from app.utils.scheduler_logger import log_scheduler_event
            log_scheduler_event(
                scheduler_name=scheduler_name,
                environment="all",
                log_type="scheduler",
                action="scheduler_error",
                message=str(e),
                status="failed"
            )
        except: pass

