# api/backend/app/routes/retention.py
"""
Data retention management endpoints
Allows manual triggering of data retention cleanup
"""

from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from app.db.db import get_db
from app.utils.data_retention import (
    run_data_retention_cleanup,
    cleanup_old_metrics,
    cleanup_old_alerts,
    cleanup_old_audit_logs,
    METRICS_RETENTION_DAYS,
    ALERTS_RETENTION_DAYS,
    AUDIT_LOGS_RETENTION_DAYS,
    LOG_RETENTION_DAYS,
)
import logging

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/cleanup")
def trigger_cleanup(db: Session = Depends(get_db)):
    """
    Manually trigger data retention cleanup
    This will:
    - Delete metrics older than 2 years (730 days)
    - Delete alerts older than 2 years (730 days)
    - Delete audit logs older than 10 days
    """
    try:
        results = run_data_retention_cleanup()
        return {
            "status": "success",
            "message": "Data retention cleanup completed",
            "results": results
        }
    except Exception as e:
        logger.error(f"Error during manual cleanup: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Cleanup failed: {str(e)}")


@router.get("/status")
def get_retention_status(db: Session = Depends(get_db)):
    """
    Get data retention policy status and configuration
    """
    return {
        "metrics_retention_days": METRICS_RETENTION_DAYS,
        "log_retention_days": LOG_RETENTION_DAYS,
        "alerts_retention_days": ALERTS_RETENTION_DAYS,
        "audit_logs_retention_days": AUDIT_LOGS_RETENTION_DAYS,
        "policies": {
            "metrics": {
                "table": "server_metrics",
                "retention_days": METRICS_RETENTION_DAYS,
                "description": "Metric data retention period"
            },
            "alerts": {
                "table": "alerts",
                "retention_days": ALERTS_RETENTION_DAYS,
                "description": "Alerts retention period"
            },
            "audit_logs": {
                "table": "audit_logs",
                "retention_days": AUDIT_LOGS_RETENTION_DAYS,
                "description": "Audit logs retention period"
            }
        },
        "scheduled": {
            "enabled": True,
            "schedule": "Daily at 2:00 AM IST",
            "description": "Automatic cleanup runs daily"
        }
    }

