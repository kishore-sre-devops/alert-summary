"""
Persistent Queue Management Module
PHASE 1 ERROR-PROOF IMPLEMENTATION: Store-first approach for zero data loss

This module provides functions to:
1. Store metrics in queue BEFORE sending (guarantees zero data loss)
2. Update queue status after send attempts
3. Retrieve failed metrics for retry
4. Clean up old successful metrics
"""

import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from sqlalchemy import select, update, delete, and_, func
from sqlalchemy.exc import SQLAlchemyError
from app.db.db import engine, metric_queue_table
from app.utils.scheduler_logger import log_scheduler_event

logger = logging.getLogger(__name__)


def queue_metric(
    environment: str,
    exchange_id: int,
    exchange_name: str,
    scheduler_name: str,
    metric_type: str,
    sequence_id: int,
    payload: Dict[str, Any],
    status: str = "pending"
) -> Optional[int]:
    """
    Store metric in queue BEFORE sending to guarantee zero data loss.
    
    Args:
        environment: 'uat' or 'prod'
        exchange_id: Exchange ID (1=NSE, 2=BSE, 4=MCX, 5=NCDEX)
        exchange_name: Exchange name ('NSE', 'BSE', 'MCX', 'NCDEX')
        scheduler_name: Scheduler name ('Hardware-Scheduler', etc.)
        metric_type: Metric type ('hardware', 'network', 'database', 'application')
        sequence_id: Sequence ID for this metric
        payload: Complete metric payload to send (JSON)
        status: Initial status ('pending', 'sent', 'failed', 'expired')
    
    Returns:
        Queue record ID if successful, None if failed
    """
    try:
        with engine.begin() as conn:
            result = conn.execute(
                metric_queue_table.insert().values(
                    environment=environment,
                    exchange_id=exchange_id,
                    exchange_name=exchange_name,
                    scheduler_name=scheduler_name,
                    metric_type=metric_type,
                    sequence_id=sequence_id,
                    payload=payload,
                    status=status,
                    retry_count=0,
                    max_retries=7,
                    created_at=datetime.utcnow(),
                    updated_at=datetime.utcnow()
                )
            )
            queue_id = result.inserted_primary_key[0]
            
            logger.info(
                f"[QUEUE] Stored metric in queue: {environment}/{exchange_name}/{scheduler_name}/"
                f"{metric_type} seq={sequence_id} queue_id={queue_id}"
            )
            
            return queue_id
            
    except SQLAlchemyError as e:
        logger.error(f"[QUEUE] Failed to store metric in queue: {e}", exc_info=True)
        return None


def update_queue_status(
    queue_id: int,
    status: str,
    error_message: Optional[str] = None,
    error_code: Optional[str] = None,
    expected_sequence_id: Optional[int] = None,
    sent_at: Optional[datetime] = None,
    next_retry_at: Optional[datetime] = None,
    retry_count: Optional[int] = None
) -> bool:
    """
    Update queue record status after send attempt.
    
    Args:
        queue_id: Queue record ID
        status: New status ('sent', 'failed', 'expired')
        error_message: Error message if failed
        error_code: LAMA API error code (704, 801, etc.)
        expected_sequence_id: Expected sequence ID from Error 704
        sent_at: Timestamp when successfully sent
        next_retry_at: When to retry next (exponential backoff)
        retry_count: Current retry count
    
    Returns:
        True if successful, False otherwise
    """
    try:
        update_values = {
            "status": status,
            "updated_at": datetime.utcnow()
        }
        
        if error_message is not None:
            update_values["error_message"] = error_message
        if error_code is not None:
            update_values["error_code"] = error_code
        if expected_sequence_id is not None:
            update_values["expected_sequence_id"] = expected_sequence_id
        if sent_at is not None:
            update_values["sent_at"] = sent_at
        if next_retry_at is not None:
            update_values["next_retry_at"] = next_retry_at
        if retry_count is not None:
            update_values["retry_count"] = retry_count
        
        with engine.begin() as conn:
            result = conn.execute(
                update(metric_queue_table)
                .where(metric_queue_table.c.id == queue_id)
                .values(**update_values)
            )
            
            if result.rowcount > 0:
                logger.info(
                    f"[QUEUE] Updated queue record {queue_id}: status={status}, "
                    f"retry_count={retry_count}, next_retry_at={next_retry_at}"
                )
                return True
            else:
                logger.warning(f"[QUEUE] Queue record {queue_id} not found for update")
                return False
                
    except SQLAlchemyError as e:
        logger.error(f"[QUEUE] Failed to update queue record {queue_id}: {e}", exc_info=True)
        return False


def get_failed_metrics(limit: int = 10) -> List[Dict[str, Any]]:
    """
    Get failed metrics ready for retry (next_retry_at <= now).
    
    Args:
        limit: Maximum number of records to return
    
    Returns:
        List of queue records ready for retry
    """
    try:
        now = datetime.utcnow()
        
        with engine.connect() as conn:
            query = select(metric_queue_table).where(
                and_(
                    metric_queue_table.c.status == "failed",
                    metric_queue_table.c.next_retry_at <= now,
                    metric_queue_table.c.retry_count < metric_queue_table.c.max_retries
                )
            ).order_by(
                metric_queue_table.c.created_at.asc()
            ).limit(limit)
            
            result = conn.execute(query)
            rows = result.fetchall()
            
            metrics = []
            for row in rows:
                metrics.append({
                    "id": row.id,
                    "environment": row.environment,
                    "exchange_id": row.exchange_id,
                    "exchange_name": row.exchange_name,
                    "scheduler_name": row.scheduler_name,
                    "metric_type": row.metric_type,
                    "sequence_id": row.sequence_id,
                    "payload": row.payload,
                    "status": row.status,
                    "retry_count": row.retry_count,
                    "max_retries": row.max_retries,
                    "next_retry_at": row.next_retry_at,
                    "error_message": row.error_message,
                    "error_code": row.error_code,
                    "expected_sequence_id": row.expected_sequence_id,
                    "sent_at": row.sent_at,
                    "created_at": row.created_at
                })
            
            return metrics
            
    except SQLAlchemyError as e:
        logger.error(f"[QUEUE] Failed to get failed metrics: {e}", exc_info=True)
        return []


def calculate_next_retry_time(retry_count: int) -> datetime:
    """
    Calculate next retry time using exponential backoff.
    
    Backoff schedule:
    - Retry 0: Immediate
    - Retry 1: 1 minute
    - Retry 2: 5 minutes
    - Retry 3: 15 minutes
    - Retry 4: 1 hour
    - Retry 5: 4 hours
    - Retry 6: 24 hours
    - Retry 7: 7 days (final)
    
    Args:
        retry_count: Current retry count (0-based)
    
    Returns:
        Next retry datetime
    """
    backoff_minutes = [0, 1, 5, 15, 60, 240, 1440, 10080]  # 0, 1m, 5m, 15m, 1h, 4h, 24h, 7d
    
    if retry_count < len(backoff_minutes):
        minutes = backoff_minutes[retry_count]
    else:
        minutes = backoff_minutes[-1]  # Use max backoff
    
    return datetime.utcnow() + timedelta(minutes=minutes)


def mark_metric_failed(
    queue_id: int,
    error_message: str,
    error_code: Optional[str] = None,
    expected_sequence_id: Optional[int] = None,
    current_retry_count: int = 0
) -> bool:
    """
    Mark metric as failed and schedule next retry.
    
    Args:
        queue_id: Queue record ID
        error_message: Error message
        error_code: LAMA API error code
        expected_sequence_id: Expected sequence ID from Error 704
        current_retry_count: Current retry count (will be incremented)
    
    Returns:
        True if successful, False otherwise
    """
    next_retry_count = current_retry_count + 1
    next_retry_at = calculate_next_retry_time(next_retry_count)
    
    # Check if max retries reached
    with engine.connect() as conn:
        result = conn.execute(
            select(metric_queue_table.c.max_retries)
            .where(metric_queue_table.c.id == queue_id)
        ).fetchone()
        
        if result:
            max_retries = result.max_retries
            if next_retry_count >= max_retries:
                # Max retries reached, mark as expired
                return update_queue_status(
                    queue_id=queue_id,
                    status="expired",
                    error_message=f"{error_message} (Max retries {max_retries} reached)",
                    error_code=error_code,
                    retry_count=next_retry_count
                )
    
    return update_queue_status(
        queue_id=queue_id,
        status="failed",
        error_message=error_message,
        error_code=error_code,
        expected_sequence_id=expected_sequence_id,
        next_retry_at=next_retry_at,
        retry_count=next_retry_count
    )


def mark_metric_sent(queue_id: int) -> bool:
    """
    Mark metric as successfully sent.
    
    Args:
        queue_id: Queue record ID
    
    Returns:
        True if successful, False otherwise
    """
    return update_queue_status(
        queue_id=queue_id,
        status="sent",
        sent_at=datetime.utcnow()
    )


def cleanup_old_successful_metrics(days: int = 1) -> int:
    """
    Clean up successful metrics older than specified days.
    
    Args:
        days: Delete metrics older than this many days (default: 1 day)
    
    Returns:
        Number of records deleted
    """
    try:
        cutoff_date = datetime.utcnow() - timedelta(days=days)
        
        with engine.begin() as conn:
            result = conn.execute(
                delete(metric_queue_table).where(
                    and_(
                        metric_queue_table.c.status == "sent",
                        metric_queue_table.c.sent_at < cutoff_date
                    )
                )
            )
            
            deleted_count = result.rowcount
            
            if deleted_count > 0:
                logger.info(f"[QUEUE] Cleaned up {deleted_count} old successful metrics")
            
            return deleted_count
            
    except SQLAlchemyError as e:
        logger.error(f"[QUEUE] Failed to cleanup old metrics: {e}", exc_info=True)
        return 0


def cleanup_expired_metrics(days: int = 7) -> int:
    """
    Clean up expired metrics older than specified days.
    
    Args:
        days: Delete expired metrics older than this many days (default: 7 days)
    
    Returns:
        Number of records deleted
    """
    try:
        cutoff_date = datetime.utcnow() - timedelta(days=days)
        
        with engine.begin() as conn:
            result = conn.execute(
                delete(metric_queue_table).where(
                    and_(
                        metric_queue_table.c.status == "expired",
                        metric_queue_table.c.updated_at < cutoff_date
                    )
                )
            )
            
            deleted_count = result.rowcount
            
            if deleted_count > 0:
                logger.info(f"[QUEUE] Cleaned up {deleted_count} expired metrics")
            
            return deleted_count
            
    except SQLAlchemyError as e:
        logger.error(f"[QUEUE] Failed to cleanup expired metrics: {e}", exc_info=True)
        return 0


def get_queue_stats() -> Dict[str, Any]:
    """
    Get queue statistics for monitoring.
    
    Returns:
        Dictionary with queue statistics
    """
    try:
        with engine.connect() as conn:
            # Count by status
            status_counts = conn.execute(
                select(
                    metric_queue_table.c.status,
                    func.count(metric_queue_table.c.id).label("count")
                ).group_by(metric_queue_table.c.status)
            ).fetchall()
            
            stats = {
                "pending": 0,
                "sent": 0,
                "failed": 0,
                "expired": 0,
                "total": 0
            }
            
            for row in status_counts:
                status = row.status
                count = row.count
                stats[status] = count
                stats["total"] += count
            
            return stats
            
    except SQLAlchemyError as e:
        logger.error(f"[QUEUE] Failed to get queue stats: {e}", exc_info=True)
        return {
            "pending": 0,
            "sent": 0,
            "failed": 0,
            "expired": 0,
            "total": 0
        }

