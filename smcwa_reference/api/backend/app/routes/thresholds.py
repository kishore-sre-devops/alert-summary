"""
Alert Threshold Management endpoints
"""

from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel
from sqlalchemy import select, update, insert, delete
from sqlalchemy.orm import Session
from app.db.db import get_db, alert_thresholds_table, engine, get_connection
from app.utils.permissions import require_admin, require_role
from typing import Optional, List, Dict
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

router = APIRouter()

class ThresholdCreate(BaseModel):
    metric_type: str  # 'hardware', 'network', 'database', 'application'
    metric_key: str
    warning_threshold: float
    error_threshold: float
    enabled: bool = True

class ThresholdUpdate(BaseModel):
    warning_threshold: Optional[float] = None
    error_threshold: Optional[float] = None
    enabled: Optional[bool] = None

class ThresholdResponse(BaseModel):
    id: int
    metric_type: str
    metric_key: str
    warning_threshold: float
    error_threshold: float
    enabled: bool
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

def get_hardware_thresholds_internal(db: Session):
    """Helper for internal use to get hardware thresholds without a request object."""
    try:
        query = select(alert_thresholds_table).where(
            alert_thresholds_table.c.metric_type == 'hardware'
        )
        results = db.execute(query).fetchall()
        map = {}
        for r in results:
            if r[5]:  # enabled
                map[r[2]] = { # metric_key
                    'warning': r[3], # warning_threshold
                    'error': r[4]    # error_threshold
                }
        return map
    except Exception as e:
        logger.error(f"Error in get_hardware_thresholds_internal: {e}")
        return {}

@router.get("/", response_model=List[ThresholdResponse])
def list_thresholds(request: Request = None):
    """List all alert thresholds - Admin only"""
    require_admin(request)
    try:
        with get_connection() as conn:
            query = select(alert_thresholds_table).order_by(
                alert_thresholds_table.c.metric_type,
                alert_thresholds_table.c.metric_key
            )
            results = conn.execute(query).fetchall()
            thresholds = []
            for r in results:
                # Row access: id, metric_type, metric_key, warning_threshold, error_threshold, enabled, created_at, updated_at, unique_metric
                # Index: 0=id, 1=metric_type, 2=metric_key, 3=warning_threshold, 4=error_threshold, 5=enabled, 6=created_at, 7=updated_at
                created_at_str = r[6].isoformat() if r[6] else None
                updated_at_str = r[7].isoformat() if r[7] else None
                thresholds.append(ThresholdResponse(
                    id=r[0],
                    metric_type=r[1],
                    metric_key=r[2],
                    warning_threshold=r[3],
                    error_threshold=r[4],
                    enabled=r[5],
                    created_at=created_at_str,
                    updated_at=updated_at_str
                ))
            return thresholds
    except Exception as e:
        logger.error(f"Error fetching thresholds: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error fetching thresholds: {str(e)}")

@router.get("/{metric_type}", response_model=List[ThresholdResponse])
def get_thresholds_by_type(metric_type: str, request: Request = None):
    """Get thresholds for a specific metric type - Admin only"""
    require_admin(request)
    try:
        with get_connection() as conn:
            query = select(alert_thresholds_table).where(
                alert_thresholds_table.c.metric_type == metric_type
            ).order_by(alert_thresholds_table.c.metric_key)
            results = conn.execute(query).fetchall()
            thresholds = []
            for r in results:
                created_at_str = r[6].isoformat() if r[6] else None
                updated_at_str = r[7].isoformat() if r[7] else None
                thresholds.append(ThresholdResponse(
                    id=r[0],
                    metric_type=r[1],
                    metric_key=r[2],
                    warning_threshold=r[3],
                    error_threshold=r[4],
                    enabled=r[5],
                    created_at=created_at_str,
                    updated_at=updated_at_str
                ))
            return thresholds
    except Exception as e:
        logger.error(f"Error fetching thresholds: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error fetching thresholds: {str(e)}")

@router.post("/", response_model=ThresholdResponse)
def create_threshold(threshold: ThresholdCreate, request: Request):
    """Create a new alert threshold - Admin only"""
    require_admin(request)
    
    if threshold.metric_type not in ['hardware', 'network', 'database', 'application']:
        raise HTTPException(status_code=400, detail="metric_type must be one of: hardware, network, database, application")
    
    # Validation based on metric type (High-is-bad vs Low-is-bad)
    # Low-is-bad metrics: uptime, status, db_status (Alert when value <= threshold)
    low_is_bad = threshold.metric_key in ['uptime', 'status', 'db_status']
    is_binary = threshold.metric_key in ['status', 'db_status']
    
    if low_is_bad and not is_binary:
        if threshold.warning_threshold <= threshold.error_threshold:
            raise HTTPException(status_code=400, detail="For this metric, warning_threshold must be greater than error_threshold (e.g. Warning=10, Critical=5)")
    elif not is_binary:
        if threshold.warning_threshold >= threshold.error_threshold:
            raise HTTPException(status_code=400, detail="warning_threshold must be less than error_threshold")
    
    try:
        with get_connection() as conn:
            # Check if threshold already exists
            query = select(alert_thresholds_table).where(
                alert_thresholds_table.c.metric_type == threshold.metric_type,
                alert_thresholds_table.c.metric_key == threshold.metric_key
            )
            existing = conn.execute(query).fetchone()
            if existing:
                raise HTTPException(
                    status_code=400,
                    detail=f"Threshold already exists for {threshold.metric_type}.{threshold.metric_key}"
                )
            
            # Insert new threshold
            unique_metric = f"{threshold.metric_type}.{threshold.metric_key}"
            insert_query = alert_thresholds_table.insert().values(
                metric_type=threshold.metric_type,
                metric_key=threshold.metric_key,
                warning_threshold=threshold.warning_threshold,
                error_threshold=threshold.error_threshold,
                enabled=threshold.enabled,
                unique_metric=unique_metric
            )
            conn.execute(insert_query)
            conn.commit()
            
            # Fetch created threshold
            query = select(alert_thresholds_table).where(
                alert_thresholds_table.c.metric_type == threshold.metric_type,
                alert_thresholds_table.c.metric_key == threshold.metric_key
            )
            created = conn.execute(query).fetchone()
            
            created_at_str = created[6].isoformat() if created[6] else None
            updated_at_str = created[7].isoformat() if created[7] else None
            return ThresholdResponse(
                id=created[0],
                metric_type=created[1],
                metric_key=created[2],
                warning_threshold=created[3],
                error_threshold=created[4],
                enabled=created[5],
                created_at=created_at_str,
                updated_at=updated_at_str
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating threshold: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error creating threshold: {str(e)}")

@router.put("/{threshold_id}", response_model=ThresholdResponse)
def update_threshold(threshold_id: int, threshold: ThresholdUpdate, request: Request):
    """Update an alert threshold - Admin only"""
    require_admin(request)
    
    try:
        with get_connection() as conn:
            # Check if threshold exists
            query = select(alert_thresholds_table).where(alert_thresholds_table.c.id == threshold_id)
            existing = conn.execute(query).fetchone()
            if not existing:
                raise HTTPException(status_code=404, detail="Threshold not found")
            
            metric_key = existing[2]
            low_is_bad = metric_key in ['uptime', 'status', 'db_status']
            is_binary = metric_key in ['status', 'db_status']
            
            # Validate thresholds if both are being updated
            if threshold.warning_threshold is not None and threshold.error_threshold is not None:
                if low_is_bad and not is_binary:
                    if threshold.warning_threshold <= threshold.error_threshold:
                        raise HTTPException(status_code=400, detail="For this metric, warning_threshold must be greater than error_threshold (e.g. Warning=10, Critical=5)")
                elif not is_binary:
                    if threshold.warning_threshold >= threshold.error_threshold:
                        raise HTTPException(status_code=400, detail="warning_threshold must be less than error_threshold")
            elif threshold.warning_threshold is not None and not is_binary:
                if low_is_bad:
                    if threshold.warning_threshold <= existing[4]:  # existing error_threshold
                        raise HTTPException(status_code=400, detail="For this metric, warning_threshold must be greater than error_threshold (e.g. Warning=10, Critical=5)")
                else:
                    if threshold.warning_threshold >= existing[4]:  # existing error_threshold
                        raise HTTPException(status_code=400, detail="warning_threshold must be less than error_threshold")
            elif threshold.error_threshold is not None and not is_binary:
                if low_is_bad:
                    if existing[3] <= threshold.error_threshold:  # existing warning_threshold
                        raise HTTPException(status_code=400, detail="For this metric, warning_threshold must be greater than error_threshold (e.g. Warning=10, Critical=5)")
                else:
                    if existing[3] >= threshold.error_threshold:  # existing warning_threshold
                        raise HTTPException(status_code=400, detail="warning_threshold must be less than error_threshold")
            
            # Update threshold
            update_values = {"updated_at": datetime.utcnow()}
            if threshold.warning_threshold is not None:
                update_values["warning_threshold"] = threshold.warning_threshold
            if threshold.error_threshold is not None:
                update_values["error_threshold"] = threshold.error_threshold
            if threshold.enabled is not None:
                update_values["enabled"] = threshold.enabled
            
            update_query = update(alert_thresholds_table).where(
                alert_thresholds_table.c.id == threshold_id
            ).values(**update_values)
            conn.execute(update_query)
            conn.commit()
            
            # Fetch updated threshold
            query = select(alert_thresholds_table).where(alert_thresholds_table.c.id == threshold_id)
            updated = conn.execute(query).fetchone()
            
            created_at_str = updated[6].isoformat() if updated[6] else None
            updated_at_str = updated[7].isoformat() if updated[7] else None
            return ThresholdResponse(
                id=updated[0],
                metric_type=updated[1],
                metric_key=updated[2],
                warning_threshold=updated[3],
                error_threshold=updated[4],
                enabled=updated[5],
                created_at=created_at_str,
                updated_at=updated_at_str
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating threshold: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error updating threshold: {str(e)}")

@router.delete("/{threshold_id}")
def delete_threshold(threshold_id: int, request: Request):
    """Delete an alert threshold - Admin only"""
    require_admin(request)
    
    try:
        with get_connection() as conn:
            query = select(alert_thresholds_table).where(alert_thresholds_table.c.id == threshold_id)
            result = conn.execute(query).fetchone()
            if not result:
                raise HTTPException(status_code=404, detail="Threshold not found")
            
            delete_query = delete(alert_thresholds_table).where(alert_thresholds_table.c.id == threshold_id)
            conn.execute(delete_query)
            conn.commit()
            
            return {"message": "Threshold deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting threshold: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error deleting threshold: {str(e)}")

