"""
Dedicated Scheduler Process for SMC-LAMA
Isolates background tasks from the UI/API process.
"""
import os
import sys
import time
import logging
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from pytz import timezone
from concurrent.futures import ThreadPoolExecutor

# Add parent directory to path to allow imports from app
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.db import init_db
from app.utils.data_retention import run_data_retention_cleanup
from app.utils.database_metrics_collector import collect_database_metrics
from app.utils.prom_metrics_collector import collect_prom_metrics
from app.utils.server_down_monitor import server_down_monitor_scheduler
from app.schedulers import (
    hardware_scheduler, network_scheduler, db_scheduler, application_scheduler,
    historical_application as historical_app_scheduler
)
from app.services.escalation import process_escalations
from app.utils.scheduler_logger import log_scheduler_event
import asyncio

# Configure Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("lama_scheduler")

def mobile_escalation_wrapper():
    """Wrapper for async process_escalations"""
    try:
        # Use a new event loop for each run to avoid event loop closed errors
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(process_escalations())
        loop.close()
    except Exception as e:
        logger.error(f"Mobile escalation worker failed: {e}")

def touch_heartbeat():
    """Touch a file to indicate the scheduler is alive"""
    heartbeat_file = os.environ.get("SCHEDULER_HEARTBEAT_PATH", "/tmp/scheduler_heartbeat")
    try:
        # Log heartbeat to DB for dashboard status
        log_scheduler_event(
            scheduler_name='Scheduler Heartbeat',
            environment='all',
            log_type='scheduler',
            action='heartbeat',
            message='Scheduler is alive',
            status='success'
        )
        
        # ONLY try to touch if the directory exists and is writable
        if os.path.exists(os.path.dirname(heartbeat_file)):
            with open(heartbeat_file, 'w') as f:
                f.write(str(time.time()))
            try: os.chmod(heartbeat_file, 0o666)
            except: pass
        else:
            # Fallback to local /tmp
            with open("/tmp/heartbeat", 'w') as f:
                f.write(str(time.time()))
    except Exception:
        # Last resort fallback to /tmp/heartbeat
        try:
            with open("/tmp/heartbeat", 'w') as f:
                f.write(str(time.time()))
        except:
            pass

def collect_database_metrics_wrapper():
    """Wrapper to add logging to DB metrics collection"""
    try:
        collect_database_metrics()
        log_scheduler_event(
            scheduler_name='Database Metrics Collection',
            environment='all',
            log_type='scheduler',
            action='collection',
            message='Database metrics collected successfully',
            status='success'
        )
    except Exception as e:
        logger.error(f"Database metrics collection failed: {e}")
        log_scheduler_event(
            scheduler_name='Database Metrics Collection',
            environment='all',
            log_type='error',
            action='collection_failed',
            message=f'Database metrics collection failed: {str(e)}',
            status='failed'
        )

def collect_prom_metrics_wrapper():
    """Wrapper to add logging to Prometheus metrics collection"""
    try:
        collect_prom_metrics()
        log_scheduler_event(
            scheduler_name='Prometheus Metrics Collection',
            environment='all',
            log_type='scheduler',
            action='collection',
            message='Prometheus metrics collected successfully',
            status='success'
        )
    except Exception as e:
        logger.error(f"Prometheus metrics collection failed: {e}")
        log_scheduler_event(
            scheduler_name='Prometheus Metrics Collection',
            environment='all',
            log_type='error',
            action='collection_failed',
            message=f'Prometheus metrics collection failed: {str(e)}',
            status='failed'
        )

def server_down_monitor_wrapper():
    """Wrapper to add logging to Server Down Monitor"""
    try:
        server_down_monitor_scheduler()
        log_scheduler_event(
            scheduler_name='Server Down Monitor',
            environment='all',
            log_type='scheduler',
            action='monitor',
            message='Server down check completed',
            status='success'
        )
    except Exception as e:
        logger.error(f"Server down monitor failed: {e}")
        log_scheduler_event(
            scheduler_name='Server Down Monitor',
            environment='all',
            log_type='error',
            action='monitor_failed',
            message=f'Server down monitor failed: {str(e)}',
            status='failed'
        )

def lama_exchange_sync_scheduler():
    """
    Parallel Wrapper for LAMA Exchange Schedulers.
    Executes all 4 metric schedulers concurrently to drastically improve performance 
    and prevent redundant data collection.
    """
    from app.utils.lama_exchange import get_active_configs
    from concurrent.futures import ThreadPoolExecutor, as_completed
    
    active_configs = get_active_configs()
    
    if not active_configs:
        logger.warning("⚡ [SYNC] No active exchange configs found. Skipping cycle.")
        return

    logger.info(f"⚡ [SYNC] Triggering Parallel LAMA Exchange Schedulers for {len(active_configs)} environments...")
    
    def safe_run(func, name, env):
        try:
            logger.info(f"⚡ [SYNC] Starting {name} for {env}...")
            # Schedulers now handle fetching and pushing to all active exchanges internally
            func(environment=env)
            logger.info(f"✅ [SYNC] {name} for {env} completed.")
        except Exception as e:
            logger.error(f"❌ [SYNC] {name} for {env} FAILED: {e}", exc_info=True)

    for config in active_configs:
        env = config['environment']
        logger.info(f"🚀 [SYNC] Processing Schedulers in PARALLEL for {env}...")
        
        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = []
            futures.append(executor.submit(safe_run, hardware_scheduler, "Hardware", env))
            futures.append(executor.submit(safe_run, network_scheduler, "Network", env))
            futures.append(executor.submit(safe_run, db_scheduler, "Database", env))
            futures.append(executor.submit(safe_run, application_scheduler, "Application", env))
            
            for future in as_completed(futures):
                try:
                    future.result()
                except Exception as e:
                    logger.error(f"Scheduler execution error: {e}")
        
        logger.info(f"🏁 [SYNC] Finished all schedulers for {env}.")

def check_certificate_expiry():
    """Check SSL certificate expiry and log alerts"""
    try:
        from app.routes.certificate_status import check_certificate_expiry as cert_check
        result = cert_check()
        if result.get('needs_alert'):
            alert_level = result.get('alert_level', 'info')
            message = result.get('message', 'Certificate check completed')
            if alert_level == 'critical':
                logger.critical(f"[CERT] 🚨 {message}")
            elif alert_level == 'warning':
                logger.warning(f"[CERT] ⚠️ {message}")
            else:
                logger.info(f"[CERT] ℹ️ {message}")
        else:
            logger.info(f"[CERT] ✅ {result.get('message', 'Certificate valid')}")
    except Exception as e:
        logger.error(f"[CERT] Error checking certificate expiry: {e}")

def main():
    logger.info("Starting SMC-LAMA Dedicated Scheduler Process...")
    
    # Initialize DB (creates tables if missing)
    try:
        init_db()
        logger.info("Database initialized.")
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")

    scheduler = BackgroundScheduler(executors={'default': {'type': 'threadpool', 'max_workers': 50}})
    ist = timezone('Asia/Kolkata')

    # Load scheduler config from DB (UI-managed)
    sched_cfg = {}
    try:
        from sqlalchemy import text as _text
        with engine.connect() as conn:
            rows = conn.execute(_text("SELECT job_id, cron_expression, interval_minutes, enabled FROM scheduler_config")).fetchall()
            for r in rows:
                sched_cfg[r[0]] = {"cron": r[1], "interval": r[2], "enabled": r[3]}
        logger.info(f"Loaded scheduler config from DB: {len(sched_cfg)} jobs")
    except Exception as e:
        logger.warning(f"Could not load scheduler_config from DB, using defaults: {e}")

    def is_enabled(job_id):
        return sched_cfg.get(job_id, {}).get("enabled", True)

    def get_interval(job_id, default):
        return sched_cfg.get(job_id, {}).get("interval") or default

    def get_cron_field(job_id, field, default):
        """Parse a cron field from stored cron_expression. Fields: minute, hour, day_of_week, etc."""
        expr = sched_cfg.get(job_id, {}).get("cron")
        if not expr:
            return default
        parts = expr.split()
        idx = {"minute": 0, "hour": 1, "day": 2, "month": 3, "day_of_week": 4}.get(field)
        if idx is not None and idx < len(parts) and parts[idx] != '*':
            return parts[idx]
        return default

    # 0. Heartbeat (Every 1 minute) - For Docker Healthcheck
    if is_enabled('heartbeat'):
        scheduler.add_job(
            touch_heartbeat,
            trigger='interval',
            minutes=get_interval('heartbeat', 1),
            id='heartbeat',
            name='Scheduler Heartbeat',
            replace_existing=True
        )
        logger.info("Scheduled: Heartbeat")

    # 1. Data Retention Cleanup (2 AM IST)
    if is_enabled('data_retention_cleanup'):
        scheduler.add_job(
            run_data_retention_cleanup,
            trigger=CronTrigger(hour=int(get_cron_field('data_retention_cleanup', 'hour', 2)), minute=int(get_cron_field('data_retention_cleanup', 'minute', 0)), timezone=ist),
            id='data_retention_cleanup',
            name='Data Retention Cleanup',
            replace_existing=True
        )
        logger.info("Scheduled: Data Retention Cleanup")

    # 2. Database Metrics Collection (Every 2 minutes - Optimized)
    if is_enabled('database_metrics_collection'):
        scheduler.add_job(
            collect_database_metrics_wrapper,
            trigger='interval',
            minutes=get_interval('database_metrics_collection', 2),
            id='database_metrics_collection',
            name='Database Metrics Collection',
            replace_existing=True
        )
        logger.info("Scheduled: Database Metrics Collection")

    # 3. Prometheus Metrics Collection (Every 2 minutes - Optimized)
    if is_enabled('prom_metrics_collection'):
        scheduler.add_job(
            collect_prom_metrics_wrapper,
            trigger='interval',
            minutes=get_interval('prom_metrics_collection', 2),
            id='prom_metrics_collection',
            name='Prometheus Metrics Collection',
            replace_existing=True,
            max_instances=1,
            coalesce=True
        )
        logger.info("Scheduled: Prometheus Metrics Collection")

    # 4. Server Down Monitoring (Every 5 minutes)
    if is_enabled('server_down_monitor'):
        scheduler.add_job(
            server_down_monitor_wrapper,
            trigger='interval',
            minutes=get_interval('server_down_monitor', 5),
            id='server_down_monitor',
            name='Server Down Monitor',
            replace_existing=True,
            max_instances=1,
            coalesce=True
        )
        logger.info("Scheduled: Server Down Monitor")

    # 4b. Mobile Escalation Check (Every 1 minute)
    if is_enabled('mobile_escalation'):
        scheduler.add_job(
            mobile_escalation_wrapper,
            trigger='interval',
            minutes=get_interval('mobile_escalation', 1),
            id='mobile_escalation',
            name='Mobile Escalation Worker',
            replace_existing=True,
            max_instances=1,
            coalesce=True
        )
        logger.info("Scheduled: Mobile Escalation Worker")

    # 4c. ECS Application Metrics (DISABLED - Redundant with Hardware)
    # from app.utils.ecs_app_collector import collect_ecs_app_metrics
    # scheduler.add_job(...)
    logger.info("Skipped: ECS Application Metrics Collection (Combined with Hardware)")
    logger.info("Scheduled: ECS Application Metrics Collection (Every 1m)")

    # 5. SSL Certificate Expiry Check (Daily 9 AM IST)
    if is_enabled('certificate_expiry_check'):
        scheduler.add_job(
            check_certificate_expiry,
            trigger=CronTrigger(hour=int(get_cron_field('certificate_expiry_check', 'hour', 9)), minute=int(get_cron_field('certificate_expiry_check', 'minute', 0)), timezone=ist),
            id='certificate_expiry_check',
            name='SSL Certificate Expiry Check',
            replace_existing=True,
            misfire_grace_time=3600,
            coalesce=True
        )
        logger.info("Scheduled: SSL Certificate Expiry Check")

    # 6. LAMA Exchange Schedulers (Synchronized - Every 5 minutes)
    # We now use a single job to ensure all 4 metric types follow the same boundary
    if is_enabled('lama_exchange_sync_scheduler'):
        cron_min = get_cron_field('lama_exchange_sync_scheduler', 'minute', '*/5')
        scheduler.add_job(
            lama_exchange_sync_scheduler,
            trigger=CronTrigger(minute=cron_min, timezone=ist),
            id='lama_exchange_sync_scheduler',
            name='LAMA-Exchange-Sync-Scheduler',
            replace_existing=True,
            max_instances=1,
            coalesce=True,
            misfire_grace_time=300
        )
        logger.info("Scheduled: LAMA Exchange Sync Scheduler")

    # =========================================================================
    # CRITICAL: DO NOT TOUCH - DAILY HISTORICAL AUDIT (7 AM IST)
    # This job calculates 21-day Application Metrics. Mandatory for LAMA V1.3.
    # =========================================================================
    # 6b. Daily Historical Application Audit (7 AM IST)
    if is_enabled('historical_application_audit'):
        scheduler.add_job(
            historical_app_scheduler.historical_application_scheduler,
            trigger=CronTrigger(hour=int(get_cron_field('historical_application_audit', 'hour', 7)), minute=int(get_cron_field('historical_application_audit', 'minute', 0)), timezone=ist),
            id='historical_application_audit',
            name='Daily 21-day Historical Application Audit',
            replace_existing=True,
            misfire_grace_time=3600,
            coalesce=True
        )
        logger.info("Scheduled: Daily 21-day Historical Application Audit")
    # =========================================================================

    # 7. Start Queue Worker (DISABLED FOR TROUBLESHOOTING)
    # try:
    #     from app.utils.queue_worker import start_worker
    #     start_worker()
    #     logger.info("Queue Worker started in scheduler process.")
    # except Exception as e:
    #     logger.error(f"Failed to start queue worker: {e}")

    # scheduler.start()

    # 8. Self-Healing Watchdog (DISABLED FOR TROUBLESHOOTING)
    # try:
    #     from app.utils.scheduler_watchdog import start_watchdog
    #     start_watchdog()
    #     logger.info("✅ Self-healing scheduler watchdog started")
    # except Exception as e:
    #     logger.error(f"Watchdog initialization failed: {e}")
    
    scheduler.start()

    # 9. IMMEDIATE TRIGGER: Execute LAMA Exchange Schedulers once on startup
    # ONLY if we are not too close to the next cycle (within 60s)
    try:
        now = datetime.utcnow()
        if now.minute % 5 != 0 or now.second < 30: # If not in first 30s of cycle minute
            logger.info("⚡ Executing immediate LAMA Exchange Schedulers run (Startup)...")
            scheduler.add_job(lama_exchange_sync_scheduler, id='lama_exchange_immediate', name='LAMA-Exchange-Immediate')
        else:
            logger.info("⌛ Close to cycle boundary, skipping immediate run to prevent double-push.")
    except Exception as e:
        logger.error(f"Failed to trigger immediate scheduler run: {e}")
    
    # Touch heartbeat immediately on start
    touch_heartbeat()
    
    logger.info("Scheduler started successfully. Process is running.")

    try:
        while True:
            time.sleep(60)
            # Optional: Touch heartbeat in main loop too as a double check
            # touch_heartbeat() 
    except (KeyboardInterrupt, SystemExit):
        logger.info("Scheduler shutting down...")
        scheduler.shutdown()

if __name__ == "__main__":
    main()