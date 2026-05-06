# api/backend/app/utils/data_retention.py
"""
Data retention and cleanup utilities

RETENTION POLICY (Per User Request):
- Logs: 10 days retention (scheduler_logs, audit_logs, login_lock_status)
- Alerts: 2 years (730 days) retention
- Exchange Activity Logs (Transactions): 2 years (730 days) retention
- Server and Application metrics: 2 years (730 days) retention

Tables with 10-day retention:
- scheduler_logs: Scheduler activity logs
- audit_logs: User action audit logs
- login_lock_status: Login lock/unlock activity
- metric_queue: Queued metrics (success: 1 day, expired: 7 days)
- lama_tokens: Token cache (expired: 1 day)

Tables with 2-year (730 days) retention:
- alerts: System alerts
- exchange_transactions: Exchange API activity logs
- server_metrics: Server performance metrics (Hardware, Network, etc.)
- application_metrics_storage: Application metrics (Latency, Throughput, etc.)
"""

import logging
from datetime import datetime, timedelta
from sqlalchemy import delete, and_, text
from app.db.db import engine, server_metrics_table, alerts_table, audit_logs_table, scheduler_logs_table, metric_queue_table, login_lock_status_table, exchange_transactions_table, application_metrics_storage_table
from app.models.mobile import mobile_alerts_table
from typing import Dict, Tuple

logger = logging.getLogger(__name__)

# Retention periods (in days)
METRICS_RETENTION_DAYS = 30  # Reduced from 730 to 30 days (ClickHouse handles long-term)
APPLICATION_METRICS_STORAGE_RETENTION_DAYS = 30 # Reduced from 730 to 30 days (ClickHouse handles long-term)
LOG_RETENTION_DAYS = 10  # scheduler_logs, audit_logs, login_lock_status
SCHEDULER_LOGS_RETENTION_DAYS = 10  # Changed from 2 to 10 days
AUDIT_LOGS_RETENTION_DAYS = 10  # Changed from 2 years to 10 days
ALERTS_RETENTION_DAYS = 7  # Changed from 730 days (2 years) to 7 days for mobile alerts as requested
QUEUE_SUCCESS_RETENTION_DAYS = 1  # 1 day for successful queue items
QUEUE_EXPIRED_RETENTION_DAYS = 7  # 7 days for expired queue items
TOKEN_CACHE_RETENTION_DAYS = 1  # 1 day for expired tokens
EXCHANGE_TRANSACTIONS_RETENTION_DAYS = 730  # Exchange activity logs - 730 days retention (2 years)


def cleanup_old_metrics(retention_days: int = METRICS_RETENTION_DAYS) -> Tuple[int, bool]:
    """
    Clean up old metric data from server_metrics table
    
    Args:
        retention_days: Number of days to retain (default: 730)
        
    Returns:
        Tuple of (deleted_count, success)
    """
    try:
        cutoff_date = datetime.utcnow() - timedelta(days=retention_days)
        
        # CRITICAL FIX BUG-007: Use engine.begin() for atomic transactions
        with engine.begin() as conn:
            # Count records to be deleted (for logging)
            from sqlalchemy import select, func
            count_query = select(func.count()).select_from(server_metrics_table).where(
                server_metrics_table.c.ts < cutoff_date
            )
            count_result = conn.execute(count_query).scalar()
            
            if count_result == 0:
                logger.info(f"No old server metrics to clean up (retention: {retention_days} days)")
                return (0, True)
            
            # Delete old metrics
            delete_query = delete(server_metrics_table).where(
                server_metrics_table.c.ts < cutoff_date
            )
            result = conn.execute(delete_query)
            # No manual commit needed - engine.begin() handles it
            
            deleted_count = result.rowcount
            logger.info(
                f"Cleaned up {deleted_count} server metric records older than {retention_days} days "
                f"(cutoff: {cutoff_date.isoformat()})"
            )
            
            return (deleted_count, True)
            
    except Exception as e:
        logger.error(f"Error cleaning up old server metrics: {e}", exc_info=True)
        return (0, False)


def cleanup_old_application_metrics_storage(retention_days: int = APPLICATION_METRICS_STORAGE_RETENTION_DAYS) -> Tuple[int, bool]:
    """
    Clean up old metric data from application_metrics_storage table
    
    Args:
        retention_days: Number of days to retain (default: 730)
        
    Returns:
        Tuple of (deleted_count, success)
    """
    try:
        cutoff_date = datetime.utcnow() - timedelta(days=retention_days)
        
        with engine.begin() as conn:
            # Count records to be deleted (for logging)
            from sqlalchemy import select, func
            count_query = select(func.count()).select_from(application_metrics_storage_table).where(
                application_metrics_storage_table.c.ts < cutoff_date
            )
            count_result = conn.execute(count_query).scalar()
            
            if count_result == 0:
                logger.info(f"No old application metrics to clean up (retention: {retention_days} days)")
                return (0, True)
            
            # Delete old metrics
            delete_query = delete(application_metrics_storage_table).where(
                application_metrics_storage_table.c.ts < cutoff_date
            )
            result = conn.execute(delete_query)
            
            deleted_count = result.rowcount
            logger.info(
                f"Cleaned up {deleted_count} application metric records older than {retention_days} days "
                f"(cutoff: {cutoff_date.isoformat()})"
            )
            
            return (deleted_count, True)
            
    except Exception as e:
        logger.error(f"Error cleaning up old application metrics: {e}", exc_info=True)
        return (0, False)


def cleanup_old_alerts(retention_days: int = ALERTS_RETENTION_DAYS) -> Tuple[int, bool]:
    """
    Clean up old alert data from alerts table
    
    Args:
        retention_days: Number of days to retain (default: 10 days)
        
    Returns:
        Tuple of (deleted_count, success)
    """
    try:
        cutoff_date = datetime.utcnow() - timedelta(days=retention_days)
        
        # CRITICAL FIX BUG-007: Use engine.begin() for atomic transactions
        with engine.begin() as conn:
            # Count records to be deleted (for logging)
            from sqlalchemy import select, func
            count_query = select(func.count()).select_from(alerts_table).where(
                alerts_table.c.created_at < cutoff_date
            )
            count_result = conn.execute(count_query).scalar()
            
            if count_result == 0:
                logger.info(f"No old alerts to clean up (retention: {retention_days} days)")
                return (0, True)
            
            # Delete old alerts (only resolved ones to be safe, or all if older than retention)
            # We'll delete all old alerts regardless of resolution status
            delete_query = delete(alerts_table).where(
                alerts_table.c.created_at < cutoff_date
            )
            result = conn.execute(delete_query)
            # No manual commit needed - engine.begin() handles it
            
            deleted_count = result.rowcount
            logger.info(
                f"Cleaned up {deleted_count} alert records older than {retention_days} days "
                f"(cutoff: {cutoff_date.isoformat()})"
            )
            
            return (deleted_count, True)
            
    except Exception as e:
        logger.error(f"Error cleaning up old alerts: {e}", exc_info=True)
        return (0, False)


def cleanup_old_mobile_alerts(retention_days: int = ALERTS_RETENTION_DAYS) -> Tuple[int, bool]:
    """
    Clean up old mobile alert tracking data from mobile_alerts table
    
    Args:
        retention_days: Number of days to retain (default: 7 days)
        
    Returns:
        Tuple of (deleted_count, success)
    """
    try:
        cutoff_date = datetime.utcnow() - timedelta(days=retention_days)
        
        with engine.begin() as conn:
            from sqlalchemy import select, func
            count_query = select(func.count()).select_from(mobile_alerts_table).where(
                mobile_alerts_table.c.created_at < cutoff_date
            )
            count_result = conn.execute(count_query).scalar()
            
            if count_result == 0:
                logger.info(f"No old mobile alerts to clean up (retention: {retention_days} days)")
                return (0, True)
            
            delete_query = delete(mobile_alerts_table).where(
                mobile_alerts_table.c.created_at < cutoff_date
            )
            result = conn.execute(delete_query)
            
            deleted_count = result.rowcount
            logger.info(
                f"Cleaned up {deleted_count} mobile alert records older than {retention_days} days "
                f"(cutoff: {cutoff_date.isoformat()})"
            )
            
            return (deleted_count, True)
            
    except Exception as e:
        logger.error(f"Error cleaning up old mobile alerts: {e}", exc_info=True)
        return (0, False)


def cleanup_old_audit_logs(retention_days: int = AUDIT_LOGS_RETENTION_DAYS) -> Tuple[int, bool]:
    """
    Clean up old audit log data
    
    Args:
        retention_days: Number of days to retain (default: 10 days)
        
    Returns:
        Tuple of (deleted_count, success)
    """
    try:
        cutoff_date = datetime.utcnow() - timedelta(days=retention_days)
        
        # CRITICAL FIX BUG-007: Use engine.begin() for atomic transactions
        with engine.begin() as conn:
            # Count records to be deleted (for logging)
            from sqlalchemy import select, func
            count_query = select(func.count()).select_from(audit_logs_table).where(
                audit_logs_table.c.created_at < cutoff_date
            )
            count_result = conn.execute(count_query).scalar()
            
            if count_result == 0:
                logger.info(f"No old audit logs to clean up (retention: {retention_days} days)")
                return (0, True)
            
            # Delete old audit logs
            delete_query = delete(audit_logs_table).where(
                audit_logs_table.c.created_at < cutoff_date
            )
            result = conn.execute(delete_query)
            # No manual commit needed - engine.begin() handles it
            
            deleted_count = result.rowcount
            logger.info(
                f"Cleaned up {deleted_count} audit log records older than {retention_days} days "
                f"(cutoff: {cutoff_date.isoformat()})"
            )
            
            return (deleted_count, True)
            
    except Exception as e:
        logger.error(f"Error cleaning up old audit logs: {e}", exc_info=True)
        return (0, False)


def cleanup_old_scheduler_logs(retention_days: int = SCHEDULER_LOGS_RETENTION_DAYS) -> Tuple[int, bool]:
    """
    Clean up old scheduler logs (retention: 10 days)
    
    Args:
        retention_days: Number of days to retain (default: 10)
        
    Returns:
        Tuple of (deleted_count, success)
    """
    try:
        cutoff_date = datetime.utcnow() - timedelta(days=retention_days)
        
        # CRITICAL FIX BUG-007: Use engine.begin() for atomic transactions
        with engine.begin() as conn:
            # Count records to be deleted (for logging)
            from sqlalchemy import select, func
            count_query = select(func.count()).select_from(scheduler_logs_table).where(
                scheduler_logs_table.c.created_at < cutoff_date
            )
            count_result = conn.execute(count_query).scalar()
            
            if count_result == 0:
                logger.info(f"No old scheduler logs to clean up (retention: {retention_days} days)")
                return (0, True)
            
            # Delete old scheduler logs
            delete_query = delete(scheduler_logs_table).where(
                scheduler_logs_table.c.created_at < cutoff_date
            )
            result = conn.execute(delete_query)
            # No manual commit needed - engine.begin() handles it
            
            deleted_count = result.rowcount
            logger.info(
                f"Cleaned up {deleted_count} scheduler log records older than {retention_days} days "
                f"(cutoff: {cutoff_date.isoformat()})"
            )
            
            return (deleted_count, True)
            
    except Exception as e:
        logger.error(f"Error cleaning up old scheduler logs: {e}", exc_info=True)
        return (0, False)


def cleanup_old_queue_metrics() -> Tuple[int, bool]:
    """
    Clean up old metric queue records
    - Successful metrics: 1 day retention
    - Expired metrics: 7 days retention
    
    Returns:
        Tuple of (deleted_count, success)
    """
    try:
        from app.utils.metric_queue import cleanup_old_successful_metrics, cleanup_expired_metrics
        
        # Clean up successful metrics (1 day)
        successful_deleted = cleanup_old_successful_metrics(days=QUEUE_SUCCESS_RETENTION_DAYS)
        
        # Clean up expired metrics (7 days)
        expired_deleted = cleanup_expired_metrics(days=QUEUE_EXPIRED_RETENTION_DAYS)
        
        total_deleted = successful_deleted + expired_deleted
        
        if total_deleted > 0:
            logger.info(
                f"Cleaned up {total_deleted} queue records "
                f"(successful: {successful_deleted}, expired: {expired_deleted})"
            )
        else:
            logger.info("No old queue metrics to clean up")
        
        return (total_deleted, True)
        
    except Exception as e:
        logger.error(f"Error cleaning up old queue metrics: {e}", exc_info=True)
        return (0, False)


def cleanup_old_login_lock_status(retention_days: int = LOG_RETENTION_DAYS) -> Tuple[int, bool]:
    """
    Clean up old login_lock_status records (retention: 10 days)
    
    Only cleans up records that are no longer active (cleared locks, expired errors)
    Active locks (soft_block=TRUE or manual_lock=TRUE or error_907_locked=TRUE) are NOT deleted
    
    Args:
        retention_days: Number of days to retain (default: 10)
        
    Returns:
        Tuple of (deleted_count, success)
    """
    try:
        cutoff_date = datetime.utcnow() - timedelta(days=retention_days)
        
        with engine.begin() as conn:
            # Count records to be deleted (only inactive records older than cutoff)
            from sqlalchemy import select, func
            count_query = select(func.count()).select_from(login_lock_status_table).where(
                and_(
                    login_lock_status_table.c.updated_at < cutoff_date,
                    # Only delete inactive records (all locks cleared)
                    login_lock_status_table.c.soft_block == False,
                    login_lock_status_table.c.manual_lock == False,
                    login_lock_status_table.c.error_907_locked == False
                )
            )
            count_result = conn.execute(count_query).scalar()
            
            if count_result == 0:
                logger.info(f"No old login_lock_status records to clean up (retention: {retention_days} days)")
                return (0, True)
            
            # Delete old inactive login_lock_status records
            delete_query = delete(login_lock_status_table).where(
                and_(
                    login_lock_status_table.c.updated_at < cutoff_date,
                    login_lock_status_table.c.soft_block == False,
                    login_lock_status_table.c.manual_lock == False,
                    login_lock_status_table.c.error_907_locked == False
                )
            )
            result = conn.execute(delete_query)
            
            deleted_count = result.rowcount
            logger.info(
                f"Cleaned up {deleted_count} login_lock_status records older than {retention_days} days "
                f"(cutoff: {cutoff_date.isoformat()})"
            )
            
            return (deleted_count, True)
            
    except Exception as e:
        logger.error(f"Error cleaning up old login_lock_status records: {e}", exc_info=True)
        return (0, False)


def cleanup_old_tokens(retention_days: int = TOKEN_CACHE_RETENTION_DAYS) -> Tuple[int, bool]:
    """
    Clean up expired tokens from lama_tokens table
    
    Args:
        retention_days: Number of days after expiry to retain (default: 1)
        
    Returns:
        Tuple of (deleted_count, success)
    """
    try:
        from app.utils.token_storage import delete_expired_tokens_from_db
        
        # Delete tokens expired more than retention_days ago
        deleted_count = delete_expired_tokens_from_db(older_than_hours=retention_days * 24)
        
        if deleted_count > 0:
            logger.info(f"Cleaned up {deleted_count} expired token records")
        
        return (deleted_count, True)
        
    except Exception as e:
        logger.error(f"Error cleaning up expired tokens: {e}", exc_info=True)
        return (0, False)


def cleanup_old_exchange_transactions(retention_days: int = EXCHANGE_TRANSACTIONS_RETENTION_DAYS) -> Tuple[int, bool]:
    """
    Clean up old exchange transaction logs (retention: 30 days)
    
    This table stores all LAMA API activity (metrics sent to exchanges).
    Records older than 30 days are automatically deleted.
    
    Args:
        retention_days: Number of days to retain (default: 30)
        
    Returns:
        Tuple of (deleted_count, success)
    """
    try:
        cutoff_date = datetime.utcnow() - timedelta(days=retention_days)
        
        with engine.begin() as conn:
            # Count records to be deleted (for logging)
            from sqlalchemy import select, func
            count_query = select(func.count()).select_from(exchange_transactions_table).where(
                exchange_transactions_table.c.sent_at < cutoff_date
            )
            count_result = conn.execute(count_query).scalar()
            
            if count_result == 0:
                logger.info(f"No old exchange transactions to clean up (retention: {retention_days} days)")
                return (0, True)
            
            # Delete old exchange transactions
            delete_query = delete(exchange_transactions_table).where(
                exchange_transactions_table.c.sent_at < cutoff_date
            )
            result = conn.execute(delete_query)
            
            deleted_count = result.rowcount
            logger.info(
                f"Cleaned up {deleted_count} exchange transaction records older than {retention_days} days "
                f"(cutoff: {cutoff_date.isoformat()})"
            )
            
            return (deleted_count, True)
            
    except Exception as e:
        logger.error(f"Error cleaning up old exchange transactions: {e}", exc_info=True)
        return (0, False)


def run_data_retention_cleanup() -> Dict[str, any]:
    """
    Run complete data retention cleanup for all tables
    """
    from app.utils.scheduler_logger import log_scheduler_start, log_scheduler_end
    import time
    start_time = time.time()
    scheduler_name = "Data Retention Cleanup"
    
    try:
        # Log start
        log_scheduler_start(scheduler_name, "all")
        
        logger.info("=" * 60)
        logger.info("Starting data retention cleanup...")
        logger.info("=" * 60)
        
        results = {
            "server_metrics": {"deleted": 0, "success": False, "retention_days": METRICS_RETENTION_DAYS},
            "application_metrics": {"deleted": 0, "success": False, "retention_days": APPLICATION_METRICS_STORAGE_RETENTION_DAYS},
            "alerts": {"deleted": 0, "success": False, "retention_days": ALERTS_RETENTION_DAYS},
            "audit_logs": {"deleted": 0, "success": False, "retention_days": AUDIT_LOGS_RETENTION_DAYS},
            "scheduler_logs": {"deleted": 0, "success": False, "retention_days": SCHEDULER_LOGS_RETENTION_DAYS},
            "login_lock_status": {"deleted": 0, "success": False, "retention_days": LOG_RETENTION_DAYS},
            "queue_metrics": {"deleted": 0, "success": False},
            "tokens": {"deleted": 0, "success": False, "retention_days": TOKEN_CACHE_RETENTION_DAYS},
            "exchange_transactions": {"deleted": 0, "success": False, "retention_days": EXCHANGE_TRANSACTIONS_RETENTION_DAYS},
            "timestamp": datetime.utcnow().isoformat()
        }
        
        # Clean up server metrics (2 years)
        logger.info(f"[CLEANUP] Server metrics: {METRICS_RETENTION_DAYS} days retention")
        deleted_count, success = cleanup_old_metrics(METRICS_RETENTION_DAYS)
        results["server_metrics"] = {"deleted": deleted_count, "success": success, "retention_days": METRICS_RETENTION_DAYS}
        
        # Clean up application metrics (2 years)
        logger.info(f"[CLEANUP] Application metrics: {APPLICATION_METRICS_STORAGE_RETENTION_DAYS} days retention")
        deleted_count, success = cleanup_old_application_metrics_storage(APPLICATION_METRICS_STORAGE_RETENTION_DAYS)
        results["application_metrics"] = {"deleted": deleted_count, "success": success, "retention_days": APPLICATION_METRICS_STORAGE_RETENTION_DAYS}

        # Clean up alerts (7 days for mobile alerts)
        logger.info(f"[CLEANUP] System Alerts: {ALERTS_RETENTION_DAYS} days retention")
        deleted_count, success = cleanup_old_alerts(ALERTS_RETENTION_DAYS)
        results["alerts"] = {"deleted": deleted_count, "success": success, "retention_days": ALERTS_RETENTION_DAYS}
        
        # Clean up mobile alerts (7 days)
        logger.info(f"[CLEANUP] Mobile Alert Logs: {ALERTS_RETENTION_DAYS} days retention")
        m_deleted_count, m_success = cleanup_old_mobile_alerts(ALERTS_RETENTION_DAYS)
        results["mobile_alerts"] = {"deleted": m_deleted_count, "success": m_success, "retention_days": ALERTS_RETENTION_DAYS}

        # Clean up audit logs (10 days)
        logger.info(f"[CLEANUP] Audit logs: {AUDIT_LOGS_RETENTION_DAYS} days retention")
        deleted_count, success = cleanup_old_audit_logs(AUDIT_LOGS_RETENTION_DAYS)
        results["audit_logs"] = {"deleted": deleted_count, "success": success, "retention_days": AUDIT_LOGS_RETENTION_DAYS}
        
        # Clean up scheduler logs (10 days)
        logger.info(f"[CLEANUP] Scheduler logs: {SCHEDULER_LOGS_RETENTION_DAYS} days retention")
        deleted_count, success = cleanup_old_scheduler_logs(SCHEDULER_LOGS_RETENTION_DAYS)
        results["scheduler_logs"] = {"deleted": deleted_count, "success": success, "retention_days": SCHEDULER_LOGS_RETENTION_DAYS}
        
        # Clean up login_lock_status (10 days, only inactive records)
        logger.info(f"[CLEANUP] Login lock status: {LOG_RETENTION_DAYS} days retention (inactive only)")
        deleted_count, success = cleanup_old_login_lock_status(LOG_RETENTION_DAYS)
        results["login_lock_status"] = {"deleted": deleted_count, "success": success, "retention_days": LOG_RETENTION_DAYS}
        
        # Clean up queue metrics (1 day for successful, 7 days for expired)
        logger.info(f"[CLEANUP] Queue metrics: {QUEUE_SUCCESS_RETENTION_DAYS} day (success) / {QUEUE_EXPIRED_RETENTION_DAYS} days (expired)")
        deleted_count, success = cleanup_old_queue_metrics()
        results["queue_metrics"] = {"deleted": deleted_count, "success": success}
        
        # Clean up expired tokens (1 day after expiry)
        logger.info(f"[CLEANUP] Expired tokens: {TOKEN_CACHE_RETENTION_DAYS} day after expiry")
        deleted_count, success = cleanup_old_tokens(TOKEN_CACHE_RETENTION_DAYS)
        results["tokens"] = {"deleted": deleted_count, "success": success, "retention_days": TOKEN_CACHE_RETENTION_DAYS}
        
        # Clean up exchange transactions (2 years)
        logger.info(f"[CLEANUP] Exchange transactions: {EXCHANGE_TRANSACTIONS_RETENTION_DAYS} days retention")
        deleted_count, success = cleanup_old_exchange_transactions(EXCHANGE_TRANSACTIONS_RETENTION_DAYS)
        results["exchange_transactions"] = {"deleted": deleted_count, "success": success, "retention_days": EXCHANGE_TRANSACTIONS_RETENTION_DAYS}
        
        # LONG-TERM FIX: Cleanup expired sequence ID reservations
        try:
            from app.utils.sequence_id_reservation import cleanup_expired_reservations
            expired_reservations = cleanup_expired_reservations()
            results["expired_reservations"] = {"deleted": expired_reservations, "success": True}
            logger.info(f"[CLEANUP] Cleaned up {expired_reservations} expired sequence ID reservations")
        except Exception as e:
            logger.warning(f"Failed to cleanup expired sequence ID reservations: {e}")
            results["expired_reservations"] = {"deleted": 0, "success": False}
        
        total_deleted = (
            results["server_metrics"]["deleted"] +
            results["application_metrics"]["deleted"] +
            results["alerts"]["deleted"] +
            results["audit_logs"]["deleted"] +
            results["scheduler_logs"]["deleted"] +
            results["login_lock_status"]["deleted"] +
            results["queue_metrics"]["deleted"] +
            results["tokens"]["deleted"] +
            results["exchange_transactions"]["deleted"] +
            results.get("expired_reservations", {}).get("deleted", 0)
        )
        
        logger.info("=" * 60)
        logger.info(f"Data retention cleanup completed. Total records deleted: {total_deleted}")
        logger.info("=" * 60)
        
        # Log success
        duration_ms = int((time.time() - start_time) * 1000)
        log_scheduler_end(scheduler_name, "all", duration_ms)
        
        return results
    except Exception as e:
        logger.error(f"Error in run_data_retention_cleanup: {e}")
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
        return {}

