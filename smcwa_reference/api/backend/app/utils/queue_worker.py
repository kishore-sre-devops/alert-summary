"""
Queue Worker Module
PHASE 1 ERROR-PROOF IMPLEMENTATION: Background worker for processing failed metrics

This module provides a background worker that:
1. Continuously processes failed metrics from the queue
2. Retries with exponential backoff
3. Handles token refresh and sequence ID correction automatically
4. Processes up to 10 metrics per cycle
"""

import logging
import time
import threading
from datetime import datetime
from typing import Optional, Dict, Any
from app.utils.metric_queue import (
    get_failed_metrics,
    mark_metric_sent,
    mark_metric_failed,
    calculate_next_retry_time
)
from app.utils.lama_exchange_api import (
    get_next_sequence_id,
    send_metrics_to_lama_exchange
)
from app.utils.lama_token_cache import get_lama_exchange_token, clear_token_cache

logger = logging.getLogger(__name__)

# Worker state
_worker_thread: Optional[threading.Thread] = None
_worker_running = False
_worker_lock = threading.Lock()


def process_failed_metric(metric: Dict[str, Any]) -> bool:
    """
    Process a single failed metric from the queue.
    
    Args:
        metric: Queue record dictionary
    
    Returns:
        True if successfully sent, False otherwise
    """
    queue_id = metric["id"]
    environment = metric["environment"]
    exchange_id = metric["exchange_id"]
    exchange_name = metric["exchange_name"]
    scheduler_name = metric["scheduler_name"]
    metric_type = metric["metric_type"]
    sequence_id = metric["sequence_id"]
    payload = metric["payload"]
    retry_count = metric["retry_count"]
    error_code = metric.get("error_code")
    expected_sequence_id = metric.get("expected_sequence_id")
    
    try:
        logger.info(
            f"[QUEUE_WORKER] Processing failed metric: {environment}/{exchange_name}/"
            f"{scheduler_name}/{metric_type} queue_id={queue_id} retry={retry_count + 1}"
        )
        
        # Step 1: Get fresh token
        # get_lama_exchange_token returns token string directly, not a dict
        token = get_lama_exchange_token(
            environment=environment,
            exchange_id=exchange_id,
            scheduler_name=f"{scheduler_name}-Worker"
        )
        
        if not token:
            error_msg = "Failed to get token from cache or login"
            logger.error(f"[QUEUE_WORKER] {error_msg} for queue_id={queue_id}")
            mark_metric_failed(
                queue_id=queue_id,
                error_message=error_msg,
                error_code="TOKEN_ERROR",
                current_retry_count=retry_count
            )
            return False
        
        # Step 2: Extract member_id from payload first (needed for sequence ID calculation)
        member_id = payload.get("member_id")
        if not member_id:
            logger.error(f"[QUEUE_WORKER] Missing member_id in payload for queue_id={queue_id}")
            mark_metric_failed(
                queue_id=queue_id,
                error_message="Missing member_id in payload",
                error_code="PAYLOAD_ERROR",
                current_retry_count=retry_count
            )
            return False
        
        # Step 3: Determine sequence ID to use
        # Priority: expected_sequence_id (from Error 704) > recalculated > original sequence_id
        if expected_sequence_id is not None:
            logger.info(
                f"[QUEUE_WORKER] Using expected_sequence_id={expected_sequence_id} "
                f"(from previous Error 704) for queue_id={queue_id}"
            )
            use_sequence_id = expected_sequence_id
        else:
            # LONG-TERM FIX: Always recalculate sequence ID (never use stored)
            # Recalculate sequence ID (might have changed)
            try:
                # get_next_sequence_id returns int directly, not a dict
                use_sequence_id = get_next_sequence_id(
                    environment=environment,
                    member_id=member_id,
                    exchange_id=exchange_id,
                    metric_type=metric_type,
                    scheduler_name=f"{scheduler_name}-Worker",
                )
                
                # LONG-TERM FIX: Handle None return value (calculation error)
                if use_sequence_id is None:
                    logger.error(
                        f"[QUEUE_WORKER] ❌ CRITICAL: Sequence ID recalculation returned None for queue_id={queue_id}"
                    )
                    mark_metric_failed(
                        queue_id=queue_id,
                        error_message="Sequence ID calculation failed (database error)",
                        error_code="SEQUENCE_ID_ERROR",
                        current_retry_count=retry_count
                    )
                    return False
                
                logger.info(
                    f"[QUEUE_WORKER] Recalculated sequence_id={use_sequence_id} "
                    f"for queue_id={queue_id}"
                )
            except Exception as e:
                logger.error(
                    f"[QUEUE_WORKER] ❌ CRITICAL: Error recalculating sequence ID: {e} for queue_id={queue_id}"
                )
                mark_metric_failed(
                    queue_id=queue_id,
                    error_message=f"Sequence ID calculation exception: {str(e)}",
                    error_code="SEQUENCE_ID_EXCEPTION",
                    current_retry_count=retry_count
                )
                return False
        
        # Step 4: Extract remaining parameters from payload
        # CRITICAL FIX BUG-006: Add type validation before processing
        instance_id = payload.get("instance_id", "combined")
        metrics_list = payload.get("metrics", [])
        server_name = payload.get("server_name", "combined")
        server_ip = payload.get("server_ip", "combined")
        application_id = payload.get("application_id")
        sent_at_str = payload.get("sent_at")
        nse_timestamp = payload.get("nse_timestamp")
        stored_metrics = payload.get("stored_metrics")
        
        # CRITICAL FIX BUG-006: Validate metrics_list type and content
        if not isinstance(metrics_list, list):
            logger.error(f"[QUEUE_WORKER] Invalid metrics type for queue_id={queue_id}: {type(metrics_list)}, expected list")
            mark_metric_failed(
                queue_id=queue_id,
                error_message=f"Invalid metrics type: {type(metrics_list)}, expected list",
                error_code="PAYLOAD_TYPE_ERROR",
                current_retry_count=retry_count
            )
            return False
        
        if not metrics_list:
            logger.error(f"[QUEUE_WORKER] Empty metrics list in payload for queue_id={queue_id}")
            mark_metric_failed(
                queue_id=queue_id,
                error_message="Empty metrics list",
                error_code="PAYLOAD_EMPTY_ERROR",
                current_retry_count=retry_count
            )
            return False
        
        # Convert sent_at string back to datetime if needed
        sent_at = None
        if sent_at_str:
            try:
                if isinstance(sent_at_str, str):
                    sent_at = datetime.fromisoformat(sent_at_str.replace('Z', '+00:00'))
                elif isinstance(sent_at_str, datetime):
                    sent_at = sent_at_str
            except Exception as e:
                logger.warning(f"[QUEUE_WORKER] Failed to parse sent_at: {e}, using None")
        
        # Step 4: Send metrics
        send_result = send_metrics_to_lama_exchange(
            environment=environment,
            member_id=member_id,
            instance_id=instance_id,
            metrics=metrics_list,
            auth_token=token,  # Fixed: was 'token=token', should be 'auth_token=token'
            metric_type=metric_type,
            server_id=payload.get("server_id"),
            server_name=server_name,
            server_ip=server_ip,
            exchange_id=exchange_id,
            application_id=application_id,
            sequence_id=use_sequence_id,
            sent_at=sent_at,
            nse_timestamp=nse_timestamp,
            scheduler_name=f"{scheduler_name}-Worker",
            stored_metrics=stored_metrics
        )
        
        if send_result and send_result.get("success"):
            # Success!
            response_code = send_result.get("response_code", 601)
            logger.info(
                f"[QUEUE_WORKER] Successfully sent metric: {environment}/{exchange_name}/"
                f"{scheduler_name}/{metric_type} queue_id={queue_id} response_code={response_code}"
            )
            
            mark_metric_sent(queue_id=queue_id)
            return True
            
        else:
            # Failed - determine error code and handle accordingly
            error_message = send_result.get("message", "Unknown error") if send_result else "Send failed"
            response_code = send_result.get("response_code") if send_result else None
            
            # Handle Error 704 (Invalid Sequence ID)
            if response_code == 704:
                # Extract expected sequence ID from response
                expected_seq = send_result.get("expected_sequence_id")
                if expected_seq:
                    logger.warning(
                        f"[QUEUE_WORKER] Error 704: Expected sequence ID={expected_seq} "
                        f"for queue_id={queue_id}, will retry with correct ID"
                    )
                    mark_metric_failed(
                        queue_id=queue_id,
                        error_message=error_message,
                        error_code="704",
                        expected_sequence_id=expected_seq,
                        current_retry_count=retry_count
                    )
                else:
                    mark_metric_failed(
                        queue_id=queue_id,
                        error_message=error_message,
                        error_code="704",
                        current_retry_count=retry_count
                    )
            
            # Handle Error 801/802/401 (Invalid Token)
            elif response_code in [801, 802, 401]:
                logger.warning(
                    f"[QUEUE_WORKER] Token error {response_code}: Clearing token cache "
                    f"for {environment}/{exchange_id} queue_id={queue_id}"
                )
                clear_token_cache(environment, exchange_id)
                mark_metric_failed(
                    queue_id=queue_id,
                    error_message=error_message,
                    error_code=str(response_code),
                    current_retry_count=retry_count
                )
            
            # Other errors
            else:
                mark_metric_failed(
                    queue_id=queue_id,
                    error_message=error_message,
                    error_code=str(response_code) if response_code else "UNKNOWN",
                    current_retry_count=retry_count
                )
            
            return False
            
    except Exception as e:
        logger.error(
            f"[QUEUE_WORKER] Exception processing metric queue_id={queue_id}: {e}",
            exc_info=True
        )
        mark_metric_failed(
            queue_id=queue_id,
            error_message=f"Exception: {str(e)}",
            error_code="EXCEPTION",
            current_retry_count=retry_count
        )
        return False


def _worker_loop():
    """Main worker loop - processes failed metrics continuously"""
    global _worker_running
    
    logger.info("[QUEUE_WORKER] Background worker started")
    
    while _worker_running:
        try:
            # Get failed metrics ready for retry
            failed_metrics = get_failed_metrics(limit=10)
            
            if not failed_metrics:
                # No failed metrics, sleep for 30 seconds
                time.sleep(30)
                continue
            
            logger.info(f"[QUEUE_WORKER] Found {len(failed_metrics)} failed metrics to process")
            
            # Process each failed metric
            success_count = 0
            for metric in failed_metrics:
                if not _worker_running:
                    break
                
                if process_failed_metric(metric):
                    success_count += 1
                
                # Small delay between metrics to avoid overwhelming the API
                time.sleep(2)
            
            logger.info(
                f"[QUEUE_WORKER] Processed {len(failed_metrics)} metrics, "
                f"{success_count} successful"
            )
            
            # Sleep for 10 seconds before next cycle
            time.sleep(10)
            
        except Exception as e:
            logger.error(f"[QUEUE_WORKER] Error in worker loop: {e}", exc_info=True)
            # Sleep for 60 seconds on error before retrying
            time.sleep(60)
    
    logger.info("[QUEUE_WORKER] Background worker stopped")


def start_worker():
    """Start the background worker thread"""
    global _worker_thread, _worker_running
    
    with _worker_lock:
        if _worker_running:
            logger.warning("[QUEUE_WORKER] Worker already running")
            return
        
        _worker_running = True
        _worker_thread = threading.Thread(target=_worker_loop, daemon=True, name="QueueWorker")
        _worker_thread.start()
        logger.info("[QUEUE_WORKER] Background worker thread started")


def stop_worker():
    """Stop the background worker thread"""
    global _worker_running, _worker_thread
    
    with _worker_lock:
        if not _worker_running:
            logger.warning("[QUEUE_WORKER] Worker not running")
            return
        
        logger.info("[QUEUE_WORKER] Stopping background worker...")
        _worker_running = False
        
        if _worker_thread and _worker_thread.is_alive():
            # Wait up to 30 seconds for worker to finish current cycle
            _worker_thread.join(timeout=30)
            
            if _worker_thread.is_alive():
                logger.warning("[QUEUE_WORKER] Worker thread did not stop gracefully within 30 seconds")
            else:
                logger.info("[QUEUE_WORKER] Background worker stopped gracefully")
        
        _worker_thread = None


def is_worker_running() -> bool:
    """Check if worker is running"""
    return _worker_running

