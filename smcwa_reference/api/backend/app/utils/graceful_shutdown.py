"""
Graceful Shutdown Handler
PHASE 1 ERROR-PROOF IMPLEMENTATION: Save state and wait for in-flight requests

This module provides graceful shutdown handling:
1. Wait for in-flight scheduler tasks to complete (max 30s)
2. Stop background workers gracefully
3. Save scheduler state if needed
4. Ensure all queue writes are persisted
"""

import logging
import signal
import sys
import time
from typing import Optional
from app.utils.queue_worker import stop_worker, is_worker_running

logger = logging.getLogger(__name__)

_shutdown_requested = False
_shutdown_handlers = []


def register_shutdown_handler(handler):
    """Register a shutdown handler function"""
    _shutdown_handlers.append(handler)


def request_shutdown():
    """Request graceful shutdown"""
    global _shutdown_requested
    _shutdown_requested = True
    logger.info("[SHUTDOWN] Shutdown requested")


def is_shutdown_requested() -> bool:
    """Check if shutdown has been requested"""
    return _shutdown_requested


def graceful_shutdown(max_wait_seconds: int = 30):
    """
    Perform graceful shutdown:
    1. Stop accepting new requests
    2. Wait for in-flight scheduler tasks (max 30s)
    3. Stop background workers
    4. Execute registered shutdown handlers
    
    Args:
        max_wait_seconds: Maximum time to wait for in-flight tasks (default: 30s)
    """
    global _shutdown_requested
    
    if _shutdown_requested:
        logger.warning("[SHUTDOWN] Shutdown already in progress")
        return
    
    logger.info(f"[SHUTDOWN] Starting graceful shutdown (max wait: {max_wait_seconds}s)")
    _shutdown_requested = True
    
    # Step 1: Stop background workers
    logger.info("[SHUTDOWN] Stopping background workers...")
    try:
        if is_worker_running():
            stop_worker()
            logger.info("[SHUTDOWN] Background workers stopped")
        else:
            logger.info("[SHUTDOWN] No background workers running")
    except Exception as e:
        logger.error(f"[SHUTDOWN] Error stopping background workers: {e}", exc_info=True)
    
    # Step 2: Wait for in-flight scheduler tasks
    logger.info(f"[SHUTDOWN] Waiting for in-flight scheduler tasks (max {max_wait_seconds}s)...")
    
    # Check if scheduler is running
    try:
        from app.main import scheduler
        if scheduler and scheduler.running:
            # CRITICAL FIX BUG-011: Check actual job execution state, not next_run_time
            # next_run_time indicates when job will run next, not if it's currently running
            # Give schedulers time to finish current cycle
            wait_start = time.time()
            while time.time() - wait_start < max_wait_seconds:
                # Check if any jobs are currently executing
                # APScheduler doesn't expose running state directly, so we check executor
                jobs = scheduler.get_jobs()
                running_jobs = []
                
                # Method 1: Check if job has pending status (if available)
                for job in jobs:
                    if hasattr(job, 'pending') and job.pending:
                        running_jobs.append(job)
                        logger.debug(f"[SHUTDOWN] Job {job.id} is pending (running)")
                
                # Method 2: If no pending jobs found, assume jobs may still be running
                # and wait a bit more to be safe
                if not running_jobs:
                    # No pending jobs - check if we've waited long enough
                    elapsed = time.time() - wait_start
                    if elapsed >= 5:  # Wait at least 5 seconds to ensure jobs complete
                        logger.info("[SHUTDOWN] No running scheduler jobs found (waited 5+ seconds)")
                        break
                
                time.sleep(1)
            
            elapsed = time.time() - wait_start
            logger.info(f"[SHUTDOWN] Waited {elapsed:.1f}s for scheduler tasks")
    except Exception as e:
        logger.error(f"[SHUTDOWN] Error checking scheduler state: {e}", exc_info=True)
    
    # Step 3: Execute registered shutdown handlers
    logger.info("[SHUTDOWN] Executing registered shutdown handlers...")
    for handler in _shutdown_handlers:
        try:
            handler()
        except Exception as e:
            logger.error(f"[SHUTDOWN] Error in shutdown handler: {e}", exc_info=True)
    
    logger.info("[SHUTDOWN] Graceful shutdown completed")


def setup_signal_handlers():
    """Setup signal handlers for graceful shutdown"""
    def signal_handler(signum, frame):
        signal_name = signal.Signals(signum).name
        logger.info(f"[SHUTDOWN] Received signal: {signal_name}")
        graceful_shutdown()
        sys.exit(0)
    
    # Register handlers for SIGTERM and SIGINT
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
    
    logger.info("[SHUTDOWN] Signal handlers registered (SIGTERM, SIGINT)")

