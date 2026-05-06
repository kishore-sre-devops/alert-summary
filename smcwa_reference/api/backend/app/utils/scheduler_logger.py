# api/backend/app/utils/scheduler_logger.py
"""
Scheduler Logger - Structured logging for scheduler operations
Logs token information, sequence IDs, scheduler actions, and errors for dashboard visibility

CRITICAL: Non-blocking, asynchronous logging to ensure schedulers are never slowed down
- Uses background thread with queue for async logging
- Failures never impact scheduler performance
- Logging is fire-and-forget

Retention: 10 days (automatically cleaned up)
"""

import logging
import threading
import queue
from datetime import datetime
from typing import Optional, Dict, Any
from app.db.db import engine, scheduler_logs_table
from sqlalchemy import insert

logger = logging.getLogger(__name__)

# Exchange name mapping
EXCHANGE_NAMES = {1: "NSE", 2: "BSE", 4: "MCX", 5: "NCDEX"}

# Thread-safe queue for async logging
_log_queue = queue.Queue(maxsize=1000)  # Max 1000 pending logs (prevent memory issues)
_log_worker_thread = None
_log_worker_lock = threading.Lock()
_logging_enabled = True  # Can be disabled if needed


def _start_log_worker():
    """Start background worker thread for async logging (thread-safe, called once)"""
    global _log_worker_thread
    
    with _log_worker_lock:
        if _log_worker_thread is None or not _log_worker_thread.is_alive():
            _log_worker_thread = threading.Thread(target=_log_worker_loop, daemon=True, name="SchedulerLoggerWorker")
            _log_worker_thread.start()
            logger.info("Scheduler logger background worker thread started")


def _log_worker_loop():
    """Background worker loop that processes log queue using BULK INSERTS for efficiency"""
    logger.info("Scheduler logger worker thread started - processing logs in batches")
    
    batch_size = 50
    while True:
        try:
            batch = []
            
            # Wait for the first log entry
            try:
                log_entry = _log_queue.get(timeout=1.0)
                batch.append(log_entry)
            except queue.Empty:
                continue
                
            # Try to pull more entries to fill the batch (non-blocking)
            while len(batch) < batch_size:
                try:
                    next_entry = _log_queue.get_nowait()
                    batch.append(next_entry)
                except queue.Empty:
                    break
            
            # Process the batch
            try:
                with engine.begin() as conn:
                    conn.execute(insert(scheduler_logs_table), batch)
                
                for _ in range(len(batch)):
                    _log_queue.task_done()
                    
            except Exception as e:
                logger.error(f"Failed to write log batch ({len(batch)}) to database: {e}")
                # Optional: If DB failed, we could re-queue them, but for logs fire-and-forget is safer
            
        except Exception as e:
            logger.error(f"Error in scheduler logger worker loop: {e}", exc_info=True)
            import time
            time.sleep(1)


def log_scheduler_event(
    scheduler_name: str,
    environment: str,
    log_type: str,  # 'token', 'sequence_id', 'scheduler', 'error', 'success'
    action: str,  # 'login', 'token_cached', 'token_used', 'sequence_calculated', 'metrics_sent', etc.
    message: str,
    exchange_id: Optional[int] = None,
    metric_type: Optional[str] = None,
    status: Optional[str] = None,  # 'success', 'failed', 'warning', 'info'
    details: Optional[Dict[str, Any]] = None,
    duration_ms: Optional[int] = None
):
    """
    Log a scheduler event to database for dashboard visibility
    
    CRITICAL: This function is NON-BLOCKING and ASYNC
    - Logs are queued in background thread
    - Never blocks scheduler execution
    - Failures never impact scheduler performance
    
    Args:
        scheduler_name: Name of scheduler (e.g., 'Hardware-Scheduler', 'Network-Scheduler')
        environment: 'uat' or 'prod'
        log_type: Type of log ('token', 'sequence_id', 'scheduler', 'error', 'success')
        action: Action being logged (e.g., 'login', 'token_cached', 'sequence_calculated')
        message: Human-readable log message
        exchange_id: Exchange ID (1=NSE, 2=BSE, 4=MCX, 5=NCDEX) - optional
        metric_type: Metric type ('hardware', 'network', 'database', 'application') - optional
        status: Status ('success', 'failed', 'warning', 'info') - optional
        details: Additional structured details (dict) - optional
        duration_ms: Duration in milliseconds - optional
    """
    # Early return if logging disabled
    if not _logging_enabled:
        return
    
    # Start worker thread if not running (thread-safe)
    try:
        _start_log_worker()
    except Exception:
        pass  # Worker startup failure is non-critical
    
    try:
        exchange_name = EXCHANGE_NAMES.get(exchange_id) if exchange_id else None
        
        log_entry = {
            "timestamp": datetime.utcnow(),
            "scheduler_name": scheduler_name,
            "environment": environment,
            "exchange_id": exchange_id,
            "exchange_name": exchange_name,
            "metric_type": metric_type,
            "log_type": log_type,
            "action": action,
            "message": message,
            "details": details if details else {},
            "status": status,
            "duration_ms": duration_ms,
            "created_at": datetime.utcnow()
        }
        
        # Queue log entry (non-blocking, fire-and-forget)
        # If queue is full, drop the log (better than blocking schedulers)
        try:
            _log_queue.put_nowait(log_entry)
        except queue.Full:
            # Queue full - drop log silently (logging should never slow schedulers)
            logger.debug(f"Scheduler log queue full, dropping log entry for {scheduler_name} {action}")
            
    except Exception as e:
        # Any error in logging is completely non-critical - never impact schedulers
        logger.debug(f"Failed to queue scheduler log (non-critical): {e}")


def log_token_login(scheduler_name: str, environment: str, exchange_id: int, success: bool, token_preview: str = None, error_message: str = None, duration_ms: int = None):
    """
    Log token login event
    
    NOTE: LAMA API login is ENVIRONMENT-wide, not exchange-specific.
    The exchange_id here is just for tracking which scheduler triggered the login.
    Token is shared for ALL exchanges (NSE, BSE, MCX, NCDEX) in the environment.
    """
    exchange_name = EXCHANGE_NAMES.get(exchange_id, f"Exchange {exchange_id}")
    
    if success:
        log_scheduler_event(
            scheduler_name=scheduler_name,
            environment=environment,
            log_type="token",
            action="login",
            message=f"✅ Login successful for {environment.upper()} (shared for all exchanges)",
            exchange_id=exchange_id,
            status="success",
            details={
                "token_preview": token_preview[:20] + "..." if token_preview and len(token_preview) > 20 else token_preview,
                "token_length": len(token_preview) if token_preview else None,
                "triggered_by": exchange_name,
                "note": "Token shared for NSE, BSE, MCX, NCDEX"
            },
            duration_ms=duration_ms
        )
    else:
        log_scheduler_event(
            scheduler_name=scheduler_name,
            environment=environment,
            log_type="error",
            action="login_failed",
            message=f"❌ Login failed for {environment.upper()}: {error_message or 'Unknown error'}",
            exchange_id=exchange_id,
            status="failed",
            details={"error_message": error_message, "triggered_by": exchange_name} if error_message else {"triggered_by": exchange_name},
            duration_ms=duration_ms
        )


def log_token_used(scheduler_name: str, environment: str, exchange_id: int, metric_type: str, token_preview: str = None):
    """Log when a token is used to send metrics"""
    exchange_name = EXCHANGE_NAMES.get(exchange_id, f"Exchange {exchange_id}")
    
    log_scheduler_event(
        scheduler_name=scheduler_name,
        environment=environment,
        log_type="token",
        action="token_used",
        message=f"🔑 Using token for {exchange_name} {metric_type}",
        exchange_id=exchange_id,
        metric_type=metric_type,
        status="info",
        details={
            "token_preview": token_preview[:20] + "..." if token_preview and len(token_preview) > 20 else token_preview,
            "token_length": len(token_preview) if token_preview else None
        }
    )


def log_token_cached(scheduler_name: str, environment: str, exchange_id: int, expires_in_hours: float):
    """Log when a token is cached"""
    exchange_name = EXCHANGE_NAMES.get(exchange_id, f"Exchange {exchange_id}")
    
    log_scheduler_event(
        scheduler_name=scheduler_name,
        environment=environment,
        log_type="token",
        action="token_cached",
        message=f"💾 Token cached for {exchange_name} (expires in {expires_in_hours:.1f}h)",
        exchange_id=exchange_id,
        status="info",
        details={"expires_in_hours": expires_in_hours}
    )


def log_sequence_id(scheduler_name: str, environment: str, exchange_id: int, metric_type: str, sequence_id: int, source: str = None):
    """Log sequence ID calculation/usage"""
    exchange_name = EXCHANGE_NAMES.get(exchange_id, f"Exchange {exchange_id}")
    
    log_scheduler_event(
        scheduler_name=scheduler_name,
        environment=environment,
        log_type="sequence_id",
        action="sequence_calculated",
        message=f"🔢 Sequence ID {sequence_id} for {exchange_name} {metric_type}" + (f" (from {source})" if source else ""),
        exchange_id=exchange_id,
        metric_type=metric_type,
        status="info",
        details={
            "sequence_id": sequence_id,
            "source": source  # 'last_success', 'error_704_hint', 'calculated', etc.
        }
    )


def log_metrics_sent(scheduler_name: str, environment: str, exchange_id: int, metric_type: str, success: bool, response_code: int = None, error_message: str = None, sequence_id: int = None, duration_ms: int = None):
    """Log metrics sending event"""
    exchange_name = EXCHANGE_NAMES.get(exchange_id, f"Exchange {exchange_id}")
    
    if success:
        log_scheduler_event(
            scheduler_name=scheduler_name,
            environment=environment,
            log_type="success",
            action="metrics_sent",
            message=f"✅ {metric_type} metrics sent successfully to {exchange_name}",
            exchange_id=exchange_id,
            metric_type=metric_type,
            status="success",
            details={
                "response_code": response_code,
                "sequence_id": sequence_id
            },
            duration_ms=duration_ms
        )
    else:
        log_scheduler_event(
            scheduler_name=scheduler_name,
            environment=environment,
            log_type="error",
            action="metrics_send_failed",
            message=f"❌ Failed to send {metric_type} metrics to {exchange_name}: {error_message or 'Unknown error'}",
            exchange_id=exchange_id,
            metric_type=metric_type,
            status="failed",
            details={
                "response_code": response_code,
                "error_message": error_message,
                "sequence_id": sequence_id
            },
            duration_ms=duration_ms
        )


def log_scheduler_start(scheduler_name: str, environment: str):
    """Log scheduler start"""
    log_scheduler_event(
        scheduler_name=scheduler_name,
        environment=environment,
        log_type="scheduler",
        action="scheduler_start",
        message=f"🚀 {scheduler_name} started for {environment.upper()}",
        status="info"
    )


def log_scheduler_end(scheduler_name: str, environment: str, duration_ms: int = None):
    """Log scheduler completion"""
    log_scheduler_event(
        scheduler_name=scheduler_name,
        environment=environment,
        log_type="scheduler",
        action="scheduler_end",
        message=f"✅ {scheduler_name} completed for {environment.upper()}",
        status="success",
        duration_ms=duration_ms
    )


def log_704_retry(
    scheduler_name: str, 
    environment: str, 
    exchange_id: int, 
    metric_type: str, 
    original_seq_id: int,
    hint_seq_id: int,
    full_error_response: str = None
):
    """Log Error 704 retry attempt with hint from exchange"""
    exchange_name = EXCHANGE_NAMES.get(exchange_id, f"Exchange {exchange_id}")
    
    log_scheduler_event(
        scheduler_name=scheduler_name,
        environment=environment,
        log_type="retry",
        action="704_retry",
        message=f"⚡ 704 RETRY: {exchange_name} {metric_type} - sent={original_seq_id}, hint={hint_seq_id}",
        exchange_id=exchange_id,
        metric_type=metric_type,
        status="warning",
        details={
            "original_sequence_id": original_seq_id,
            "hint_sequence_id": hint_seq_id,
            "retry_reason": "Error 704 - Invalid Sequence ID",
            "full_response": full_error_response
        }
    )


def log_704_retry_result(
    scheduler_name: str, 
    environment: str, 
    exchange_id: int, 
    metric_type: str, 
    hint_seq_id: int,
    success: bool,
    response_code: int = None,
    full_response: str = None,
    duration_ms: int = None
):
    """Log the result of a 704 retry attempt"""
    exchange_name = EXCHANGE_NAMES.get(exchange_id, f"Exchange {exchange_id}")
    
    if success:
        log_scheduler_event(
            scheduler_name=scheduler_name,
            environment=environment,
            log_type="retry",
            action="704_retry_success",
            message=f"✅ RETRY SUCCESS: {exchange_name} {metric_type} with seq={hint_seq_id}",
            exchange_id=exchange_id,
            metric_type=metric_type,
            status="success",
            details={
                "sequence_id": hint_seq_id,
                "response_code": response_code,
                "full_response": full_response
            },
            duration_ms=duration_ms
        )
    else:
        log_scheduler_event(
            scheduler_name=scheduler_name,
            environment=environment,
            log_type="retry",
            action="704_retry_failed",
            message=f"❌ RETRY FAILED: {exchange_name} {metric_type} with seq={hint_seq_id}",
            exchange_id=exchange_id,
            metric_type=metric_type,
            status="failed",
            details={
                "sequence_id": hint_seq_id,
                "response_code": response_code,
                "full_response": full_response
            },
            duration_ms=duration_ms
        )

