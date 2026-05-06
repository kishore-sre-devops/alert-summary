"""
Database metrics collector - periodically checks database replication/sync status
and updates server metrics
"""

import logging
from datetime import datetime
from sqlalchemy import select, update
from app.db.db import database_config_table, server_status_table, engine
from app.utils.database_monitor import check_database_metrics
from app.routes.database_config import decrypt_password
from app.utils.metrics_calculator import store_metric_value
from app.utils.alert_checker import check_and_create_alert
from app.utils.alert_sender import send_alert
from app.utils.hot_store import update_hot_store_server_status
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger(__name__)

def process_single_database(config):
    """Worker function to collect metrics for a single database configuration"""
    try:
        # Row access: id, server_id, db_type, host, port, database, username, password,
        # is_replication, master_host, master_port, enabled, created_at, updated_at, unique_server_db
        server_id = config[1]
        db_type = config[2]
        host = config[3]
        port = config[4]
        database = config[5]
        username = config[6]
        encrypted_password = config[7]

        # Skip databases monitored via Prometheus exporters or AWS CloudWatch (metrics collected by schedulers)
        if username in ('prometheus_exporter', 'aws_cloudwatch_managed', 'aws_managed') or encrypted_password == 'N/A':
            return
        
        # Decrypt password (SKIP for AWS managed resources which use IAM or standard N/A)
        password = encrypted_password
        if encrypted_password and encrypted_password != 'N/A' and username != 'aws_cloudwatch_managed':
            try:
                password = decrypt_password(encrypted_password)
            except Exception as decrypt_error:
                logger.warning(f"Error decrypting password for database {host}:{port}/{database}: {str(decrypt_error)}")
                # For AWS, we continue anyway as metrics are usually CloudWatch-based if standard connection fails
                if username == 'aws_cloudwatch_managed':
                    password = 'N/A'
                else:
                    store_metric_value(server_id, "db_status", 0.0)
                    return
        
        # Check database metrics
        is_replication = config[8] # is_replication is at index 8
        metrics = check_database_metrics(
            host=host,
            port=port,
            database=database,
            username=username,
            password=password,
            db_type=db_type,
            is_replication=is_replication
        )
        
        if 'error' in metrics:
            logger.warning(f"Error checking database {host}:{port}/{database}: {metrics.get('error')}")
            # Store error status
            store_metric_value(server_id, "db_status", 0.0)
            return
        
        # AGENTLESS HEARTBEAT: Update last_seen and status (Optimized for Postgres Write Pressure)
        try:
            now = datetime.now()
            # 1. ALWAYS Update Redis (Hot Store) for real-time UI
            update_hot_store_server_status(server_id, {"status": "online", "last_seen": now.isoformat()})
            
            # 2. Sync to PostgreSQL only every 30 seconds
            from app.routes.metrics import get_redis_client
            redis = get_redis_client()
            should_sync = True
            
            if redis:
                last_sync_key = f"server:last_db_sync_dbcol:{server_id}"
                last_sync = redis.get(last_sync_key)
                if last_sync:
                    try:
                        val = last_sync.decode() if isinstance(last_sync, bytes) else last_sync
                        last_sync_dt = datetime.fromisoformat(val)
                        if (now - last_sync_dt).total_seconds() < 30:
                            should_sync = False
                    except: pass
                
                if should_sync:
                    redis.set(last_sync_key, now.isoformat())
            
            if should_sync:
                with engine.begin() as conn:
                    conn.execute(
                        update(server_status_table).where(
                            server_status_table.c.id == server_id
                        ).values(
                            last_seen=now,
                            status="online"
                        )
                    )
        except Exception as heartbeat_err:
            logger.debug(f"Could not update heartbeat for agentless DB server {server_id}: {heartbeat_err}")
        
        # Store metrics and check thresholds for alerting
        alert_ids = []
        
        if metrics.get('status') is not None:
            store_metric_value(server_id, "db_status", metrics['status'])
            alert_id = check_and_create_alert(server_id, "database", "db_status", metrics['status'])
            if alert_id: alert_ids.append(alert_id)
            
        if metrics.get('qsize') is not None:
            store_metric_value(server_id, "db_qsize", metrics['qsize'])
            alert_id = check_and_create_alert(server_id, "database", "qSize", metrics['qsize'])
            if alert_id: alert_ids.append(alert_id)
            
        if metrics.get('bandwidth') is not None:
            store_metric_value(server_id, "db_bandwidth", metrics['bandwidth'])
            alert_id = check_and_create_alert(server_id, "database", "bandwidth", metrics['bandwidth'])
            if alert_id: alert_ids.append(alert_id)
            
        if metrics.get('latency') is not None:
            store_metric_value(server_id, "db_latency", metrics['latency'])
            alert_id = check_and_create_alert(server_id, "database", "latency", metrics['latency'])
            if alert_id: alert_ids.append(alert_id)
        
        # Send any triggered alerts
        for alert_id in alert_ids:
            try:
                send_alert(alert_id)
            except Exception as alert_err:
                logger.error(f"Error sending database alert {alert_id}: {alert_err}")
        
        logger.debug(f"Database metrics collected for server {server_id}: status={metrics.get('status')}, qsize={metrics.get('qsize')}")
        
    except Exception as e:
        logger.error(f"Error collecting metrics for database config {config[0]}: {e}")

def collect_database_metrics():
    """
    Collect database metrics for all enabled database configurations
    and update server metrics - now in PARALLEL for scale
    """
    from app.utils.scheduler_logger import log_scheduler_start, log_scheduler_end
    import time
    start_time = time.time()
    scheduler_name = "Database Metrics Collection"
    
    try:
        # Log start
        log_scheduler_start(scheduler_name, "all")
        
        with engine.connect() as conn:
            # Get all enabled database configurations
            query = select(database_config_table).where(
                database_config_table.c.enabled == True
            )
            configs = conn.execute(query).fetchall()
            
            if not configs:
                logger.debug("No enabled database configurations found")
                duration_ms = int((time.time() - start_time) * 1000)
                log_scheduler_end(scheduler_name, "all", duration_ms)
                return
            
            logger.info(f"Collecting database metrics for {len(configs)} database(s) in parallel")
            
            # PARALLEL EXECUTION: Use ThreadPoolExecutor to handle many databases
            with ThreadPoolExecutor(max_workers=20) as executor:
                executor.map(process_single_database, configs)
            
            logger.info("Database metrics collection completed")
            # Log success
            duration_ms = int((time.time() - start_time) * 1000)
            log_scheduler_end(scheduler_name, "all", duration_ms)
            
    except Exception as e:
        logger.error(f"Error in collect_database_metrics: {e}", exc_info=True)

def get_database_metrics_for_server(server_id: int) -> dict:
    """
    Get latest database metrics for a specific server
    Returns: {
        'db_status': float,
        'db_qsize': float,
        'db_bandwidth': float,
        'db_latency': float
    }
    """
    try:
        with engine.connect() as conn:
            # Get database config for this server
            query = select(database_config_table).where(
                database_config_table.c.server_id == server_id,
                database_config_table.c.enabled == True
            )
            config = conn.execute(query).fetchone()
            
            if not config:
                # No database config for this server
                return None
            
            # Decrypt password
            encrypted_password = config[7]  # password is at index 7
            password = decrypt_password(encrypted_password)
            
            # Check database metrics
            metrics = check_database_metrics(
                host=config[3],  # host
                port=config[4],  # port
                database=config[5],  # database
                username=config[6],  # username
                password=password,
                db_type=config[2], # db_type
                is_replication=config[8] # is_replication
            )
            
            if 'error' in metrics:
                logger.warning(f"Error checking database for server {server_id}: {metrics.get('error')}")
                return None
            
            return {
                'db_status': metrics.get('status', 0.0),
                'db_qsize': metrics.get('qsize', 0.0),
                'db_bandwidth': metrics.get('bandwidth', 0.0),
                'db_latency': metrics.get('latency', 0.0)
            }
            
    except Exception as e:
        logger.error(f"Error getting database metrics for server {server_id}: {e}", exc_info=True)
        return None

