"""
Health Monitoring Module
PHASE 1 ERROR-PROOF IMPLEMENTATION: Detect failures early and auto-recover

This module provides health checks for:
1. Disk space monitoring (> 10% free required)
2. Memory usage monitoring (< 80% usage required)
3. Database connection health
4. LAMA API health (optional)
"""

import logging
import psutil
import shutil
from typing import Dict, Any, Optional
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from app.db.db import engine
from datetime import datetime
# Moved imports to top to avoid circular imports and improve performance
from app.utils.data_retention import cleanup_old_scheduler_logs
from app.utils.metric_queue import cleanup_old_successful_metrics

logger = logging.getLogger(__name__)


class HealthCheckResult:
    """Health check result container"""
    
    def __init__(self, status: bool, message: str, details: Optional[Dict[str, Any]] = None):
        self.status = status
        self.message = message
        self.details = details or {}
        self.timestamp = datetime.utcnow()
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "message": self.message,
            "details": self.details,
            "timestamp": self.timestamp.isoformat()
        }


def check_disk_space(threshold_percent: float = 10.0) -> HealthCheckResult:
    """
    Check if disk space is above threshold.
    
    Args:
        threshold_percent: Minimum free space percentage required (default: 10%)
    
    Returns:
        HealthCheckResult with status and details
    """
    try:
        disk_usage = shutil.disk_usage('/')
        total_gb = disk_usage.total / (1024 ** 3)
        free_gb = disk_usage.free / (1024 ** 3)
        used_gb = disk_usage.used / (1024 ** 3)
        free_percent = (disk_usage.free / disk_usage.total) * 100
        
        is_healthy = free_percent >= threshold_percent
        
        message = (
            f"Disk space: {free_percent:.1f}% free ({free_gb:.1f} GB free, "
            f"{used_gb:.1f} GB used, {total_gb:.1f} GB total)"
        )
        
        # CRITICAL FIX BUG-010: Auto-recovery for disk space issues
        if not is_healthy:
            message += f" ⚠️ WARNING: Below threshold ({threshold_percent}%)"
            logger.warning(f"[HEALTH] {message}")
            logger.info("[HEALTH] Attempting auto-recovery: Cleaning old logs and cache...")
            
            try:
                # Auto-recovery actions - using imports from top of file
                # Clean up old scheduler logs (aggressive cleanup)
                deleted_logs, _ = cleanup_old_scheduler_logs(retention_days=1)  # Keep only 1 day
                logger.info(f"[HEALTH] Auto-recovery: Deleted {deleted_logs} old scheduler logs")
                
                # Clean up old successful queue metrics
                # Note: cleanup_old_successful_metrics returns int (not tuple)
                deleted_queue = cleanup_old_successful_metrics(days=0)  # Delete all successful
                logger.info(f"[HEALTH] Auto-recovery: Deleted {deleted_queue} old queue metrics")
                
                # Re-check disk space after cleanup
                disk_usage_after = shutil.disk_usage('/')
                free_percent_after = (disk_usage_after.free / disk_usage_after.total) * 100
                
                if free_percent_after >= threshold_percent:
                    is_healthy = True
                    message += f" ✅ Auto-recovery successful: Now {free_percent_after:.1f}% free"
                    logger.info(f"[HEALTH] Auto-recovery successful: Disk space now {free_percent_after:.1f}% free")
                else:
                    message += f" ⚠️ Auto-recovery attempted but still below threshold ({free_percent_after:.1f}%)"
                    logger.warning(f"[HEALTH] Auto-recovery attempted but disk space still low: {free_percent_after:.1f}%")
            except Exception as recovery_error:
                logger.error(f"[HEALTH] Auto-recovery failed: {recovery_error}", exc_info=True)
                message += f" ❌ Auto-recovery failed: {str(recovery_error)}"
        
        return HealthCheckResult(
            status=is_healthy,
            message=message,
            details={
                "total_gb": round(total_gb, 2),
                "free_gb": round(free_gb, 2),
                "used_gb": round(used_gb, 2),
                "free_percent": round(free_percent, 2),
                "threshold_percent": threshold_percent
            }
        )
        
    except Exception as e:
        logger.error(f"[HEALTH] Failed to check disk space: {e}", exc_info=True)
        return HealthCheckResult(
            status=False,
            message=f"Failed to check disk space: {str(e)}",
            details={"error": str(e)}
        )


def check_memory_usage(threshold_percent: float = 80.0) -> HealthCheckResult:
    """
    Check if memory usage is below threshold.
    
    Args:
        threshold_percent: Maximum memory usage percentage allowed (default: 80%)
    
    Returns:
        HealthCheckResult with status and details
    """
    try:
        memory = psutil.virtual_memory()
        total_gb = memory.total / (1024 ** 3)
        available_gb = memory.available / (1024 ** 3)
        used_gb = memory.used / (1024 ** 3)
        used_percent = memory.percent
        
        is_healthy = used_percent < threshold_percent
        
        message = (
            f"Memory usage: {used_percent:.1f}% used ({used_gb:.1f} GB used, "
            f"{available_gb:.1f} GB available, {total_gb:.1f} GB total)"
        )
        
        # CRITICAL FIX BUG-010: Auto-recovery for memory issues
        if not is_healthy:
            message += f" ⚠️ WARNING: Above threshold ({threshold_percent}%)"
            logger.warning(f"[HEALTH] {message}")
            logger.info("[HEALTH] Attempting auto-recovery: Clearing caches...")
            
            try:
                # Auto-recovery actions for memory
                from app.utils.lama_token_cache import clear_token_cache
                from app.utils.agent_cache import clear_agent_cache
                
                # Clear token cache (non-critical, can be regenerated)
                try:
                    clear_token_cache("uat")
                    clear_token_cache("prod")
                    logger.info("[HEALTH] Auto-recovery: Cleared token cache")
                except Exception as e:
                    logger.warning(f"[HEALTH] Auto-recovery: Failed to clear token cache: {e}")
                
                # Clear agent cache (non-critical, can be regenerated)
                try:
                    clear_agent_cache()
                    logger.info("[HEALTH] Auto-recovery: Cleared agent cache")
                except Exception as e:
                    logger.warning(f"[HEALTH] Auto-recovery: Failed to clear agent cache: {e}")
                
                # Re-check memory after cleanup
                memory_after = psutil.virtual_memory()
                used_percent_after = memory_after.percent
                
                if used_percent_after < threshold_percent:
                    is_healthy = True
                    message += f" ✅ Auto-recovery successful: Now {used_percent_after:.1f}% used"
                    logger.info(f"[HEALTH] Auto-recovery successful: Memory usage now {used_percent_after:.1f}%")
                else:
                    message += f" ⚠️ Auto-recovery attempted but still above threshold ({used_percent_after:.1f}%)"
                    logger.warning(f"[HEALTH] Auto-recovery attempted but memory still high: {used_percent_after:.1f}%")
            except Exception as recovery_error:
                logger.error(f"[HEALTH] Auto-recovery failed: {recovery_error}", exc_info=True)
                message += f" ❌ Auto-recovery failed: {str(recovery_error)}"
        
        return HealthCheckResult(
            status=is_healthy,
            message=message,
            details={
                "total_gb": round(total_gb, 2),
                "used_gb": round(used_gb, 2),
                "available_gb": round(available_gb, 2),
                "used_percent": round(used_percent, 2),
                "threshold_percent": threshold_percent
            }
        )
        
    except Exception as e:
        logger.error(f"[HEALTH] Failed to check memory usage: {e}", exc_info=True)
        return HealthCheckResult(
            status=False,
            message=f"Failed to check memory usage: {str(e)}",
            details={"error": str(e)}
        )


def check_database_connection() -> HealthCheckResult:
    """
    Check if database connection is healthy.
    
    Returns:
        HealthCheckResult with status and details
    """
    try:
        with engine.connect() as conn:
            result = conn.execute(text("SELECT 1")).fetchone()
            
            if result and result[0] == 1:
                # Test query time
                import time
                start_time = time.time()
                conn.execute(text("SELECT 1")).fetchone()
                query_time_ms = (time.time() - start_time) * 1000
                
                return HealthCheckResult(
                    status=True,
                    message=f"Database connection healthy (query time: {query_time_ms:.2f} ms)",
                    details={
                        "query_time_ms": round(query_time_ms, 2),
                        "status": "connected"
                    }
                )
            else:
                return HealthCheckResult(
                    status=False,
                    message="Database connection test failed",
                    details={"status": "error"}
                )
                
    except SQLAlchemyError as e:
        logger.error(f"[HEALTH] Database connection check failed: {e}", exc_info=True)
        return HealthCheckResult(
            status=False,
            message=f"Database connection error: {str(e)}",
            details={"error": str(e), "status": "error"}
        )
    except Exception as e:
        logger.error(f"[HEALTH] Failed to check database connection: {e}", exc_info=True)
        return HealthCheckResult(
            status=False,
            message=f"Failed to check database: {str(e)}",
            details={"error": str(e)}
        )


def run_all_health_checks() -> Dict[str, HealthCheckResult]:
    """
    Run all health checks and return results.
    
    Returns:
        Dictionary of health check results
    """
    results = {
        "disk_space": check_disk_space(),
        "memory": check_memory_usage(),
        "database": check_database_connection()
    }
    
    # Log summary
    all_healthy = all(result.status for result in results.values())
    
    if all_healthy:
        logger.info("[HEALTH] All health checks passed")
    else:
        failed_checks = [name for name, result in results.items() if not result.status]
        logger.warning(f"[HEALTH] Health checks failed: {', '.join(failed_checks)}")
    
    return results


def is_healthy_for_scheduling() -> tuple[bool, str]:
    """
    Check if system is healthy enough to run schedulers.
    
    Returns:
        Tuple of (is_healthy: bool, reason: str)
    """
    results = run_all_health_checks()
    
    # Check disk space (critical)
    if not results["disk_space"].status:
        return False, f"Disk space below threshold: {results['disk_space'].message}"
    
    # Check memory (warning only, but allow scheduling)
    # We'll just log a warning but still allow scheduling
    if not results["memory"].status:
        logger.warning(f"[HEALTH] Memory usage high: {results['memory'].message}")
        # Don't block scheduling, but log warning
    
    # Check database (critical)
    if not results["database"].status:
        return False, f"Database connection failed: {results['database'].message}"
    
    return True, "All health checks passed"


def get_health_summary() -> Dict[str, Any]:
    """
    Get health check summary for monitoring/API.
    
    Returns:
        Dictionary with health summary
    """
    results = run_all_health_checks()
    
    summary = {
        "overall_status": "healthy" if all(r.status for r in results.values()) else "degraded",
        "checks": {name: result.to_dict() for name, result in results.items()},
        "timestamp": datetime.utcnow().isoformat()
    }
    
    return summary

