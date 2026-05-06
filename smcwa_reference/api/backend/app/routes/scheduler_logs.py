# api/backend/app/routes/scheduler_logs.py
"""
Scheduler Logs endpoints
Returns structured scheduler logs for dashboard visibility
Shows token information, sequence IDs, scheduler operations, and errors
"""

from fastapi import APIRouter, HTTPException, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import select, and_, or_, desc
from app.db.db import get_db, engine, scheduler_logs_table
from app.utils.environment import get_active_environment
from datetime import datetime, timedelta
from typing import Optional, List
import logging

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/scheduler-logs")
def get_scheduler_logs(
    start_date: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    start_time: Optional[str] = Query(None, description="Start time (HH:MM:SS)"),
    end_time: Optional[str] = Query(None, description="End time (HH:MM:SS)"),
    minutes: Optional[int] = Query(None, description="Last N minutes (relative time range, overrides start_date/end_date if provided)"),
    environment: str = Depends(get_active_environment),
    scheduler_name: Optional[str] = Query(None, description="Filter by scheduler name"),
    exchange_id: Optional[int] = Query(None, description="Filter by exchange ID (1=NSE, 2=BSE, 4=MCX, 5=NCDEX)"),
    metric_type: Optional[str] = Query(None, description="Filter by metric type"),
    log_type: Optional[str] = Query(None, description="Filter by log type (token, sequence_id, scheduler, error, success)"),
    action: Optional[str] = Query(None, description="Filter by action"),
    status: Optional[str] = Query(None, description="Filter by status (success, failed, warning, info)"),
    limit: int = Query(1000, description="Maximum number of records to return"),
    db: Session = Depends(get_db)
):
    """
    Get scheduler logs with filtering options
    Returns structured logs showing tokens, sequence IDs, scheduler operations, and errors
    """
    try:
        query = select(scheduler_logs_table)
        
        # Relative time range filtering (e.g., "Last 15 mins")
        # This supports frontend "Last N minutes" dropdown selection
        if minutes is not None:
            now_utc = datetime.utcnow()
            start_dt = now_utc - timedelta(minutes=minutes)
            query = query.where(scheduler_logs_table.c.created_at >= start_dt)
            query = query.where(scheduler_logs_table.c.created_at <= now_utc)
        # Date and time range filtering (absolute dates)
        elif start_date:
            try:
                if start_time:
                    start_dt = datetime.strptime(f"{start_date} {start_time}", "%Y-%m-%d %H:%M:%S")
                else:
                    start_dt = datetime.strptime(start_date, "%Y-%m-%d")
                query = query.where(scheduler_logs_table.c.created_at >= start_dt)
            except ValueError as e:
                raise HTTPException(status_code=400, detail=f"Invalid start_date/start_time format: {str(e)}. Use YYYY-MM-DD for date and HH:MM:SS for time")
        
        if end_date:
            try:
                if end_time:
                    end_dt = datetime.strptime(f"{end_date} {end_time}", "%Y-%m-%d %H:%M:%S")
                else:
                    end_dt = datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1)
                query = query.where(scheduler_logs_table.c.created_at < end_dt)
            except ValueError as e:
                raise HTTPException(status_code=400, detail=f"Invalid end_date/end_time format: {str(e)}. Use YYYY-MM-DD for date and HH:MM:SS for time")
        
        # Environment filter
        if environment:
            if environment not in ['prod', 'uat']:
                raise HTTPException(status_code=400, detail="Environment must be 'prod' or 'uat'")
            from sqlalchemy import or_
            query = query.where(or_(
                scheduler_logs_table.c.environment == environment,
                scheduler_logs_table.c.environment == 'all'
            ))
        
        # Scheduler name filter (supports partial matching)
        # Frontend may send "Application" or "Hardware" but database has "Application-Scheduler" or "Hardware-Scheduler"
        # Use ILIKE for case-insensitive partial matching
        # This allows "Application" to match "Application-Scheduler", "Hardware" to match "Hardware-Scheduler", etc.
        mapped_name = None
        if scheduler_name:
            # Map common frontend short names to full scheduler names
            # This ensures "Application" matches "Application-Scheduler" (not "App-Scheduler")
            scheduler_name_mapping = {
                "Hardware": "Hardware-Scheduler",
                "Network": "Network-Scheduler",
                "Application": "Application-Scheduler",
                "App": "Application-Scheduler",  # Map "App" to "Application-Scheduler" (not old "App-Scheduler")
                "App-Scheduler": "Application-Scheduler",  # TEMPORARY: Handle old cached frontend value until browsers refresh
                "DB": "DB-Scheduler",
                "Database": "DB-Scheduler"
            }
            
            # Get mapped name (full scheduler name) or use original if no mapping exists
            mapped_name = scheduler_name_mapping.get(scheduler_name, scheduler_name)
            # Use exact match (case-insensitive) to ensure only correct scheduler logs are returned
            # The mapping already converts short names (e.g., "Hardware", "Application") to full names (e.g., "Hardware-Scheduler", "Application-Scheduler")
            # This prevents old "App-Scheduler" logs from appearing when filtering for "Application-Scheduler"
            # ILIKE is used for case-insensitive matching (PostgreSQL)
            query = query.where(scheduler_logs_table.c.scheduler_name.ilike(mapped_name))
        
        # Exchange ID filter
        if exchange_id is not None:
            query = query.where(scheduler_logs_table.c.exchange_id == exchange_id)
        
        # Metric type filter
        if metric_type:
            query = query.where(scheduler_logs_table.c.metric_type == metric_type)
        
        # Log type filter
        if log_type:
            query = query.where(scheduler_logs_table.c.log_type == log_type)
        
        # Action filter
        if action:
            query = query.where(scheduler_logs_table.c.action == action)
        
        # Status filter
        if status:
            query = query.where(scheduler_logs_table.c.status == status)
        
        # Order by most recent first
        query = query.order_by(desc(scheduler_logs_table.c.created_at)).limit(limit)
        
        with engine.connect() as conn:
            results = conn.execute(query).fetchall()
            
            # Debug logging
            logger.info(f"[SCHEDULER_LOGS] Query executed: scheduler_name={scheduler_name}, mapped={mapped_name if scheduler_name else None}, environment={environment}, time_range={start_dt if 'start_dt' in locals() else 'N/A'} to {end_dt if 'end_dt' in locals() else 'N/A'}, results={len(results)}")
            
            # Additional debug: Print first result if any
            if len(results) > 0:
                logger.info(f"[SCHEDULER_LOGS] First result: scheduler_name={results[0][2]}, environment={results[0][3]}, created_at={results[0][13]}")
            else:
                logger.warning(f"[SCHEDULER_LOGS] No results found! Checking database...")
                # Quick check without filters
                check_query = select(scheduler_logs_table).where(
                    scheduler_logs_table.c.environment == environment
                ).limit(1)
                check_results = conn.execute(check_query).fetchall()
                if check_results:
                    logger.warning(f"[SCHEDULER_LOGS] Database has logs for environment={environment}, but query returned 0. Possible filter issue.")
                else:
                    logger.warning(f"[SCHEDULER_LOGS] No logs found for environment={environment} at all.")
            
            # Convert rows to dictionaries
            logs = []
            for row in results:
                log_entry = {
                    "id": row[0],
                    "timestamp": (row[1].isoformat() + 'Z') if row[1] else None,
                    "scheduler_name": row[2],
                    "environment": row[3],
                    "exchange_id": row[4],
                    "exchange_name": row[5],
                    "metric_type": row[6],
                    "log_type": row[7],
                    "action": row[8],
                    "message": row[9],
                    "details": row[10] if row[10] else {},
                    "status": row[11],
                    "duration_ms": row[12],
                    "created_at": (row[13].isoformat() + 'Z') if row[13] else None
                }
                logs.append(log_entry)
            
            return {
                "logs": logs,
                "total": len(logs),
                "limit": limit
            }
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching scheduler logs: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error fetching scheduler logs: {str(e)}")


@router.get("/scheduler-logs/stats")
def get_scheduler_logs_stats(
    start_date: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    environment: str = Depends(get_active_environment),
    db: Session = Depends(get_db)
):
    """
    Get statistics about scheduler logs (for dashboard summaries)
    """
    try:
        query = select(scheduler_logs_table)
        
        # Date range filtering
        if start_date:
            start_dt = datetime.strptime(start_date, "%Y-%m-%d")
            query = query.where(scheduler_logs_table.c.created_at >= start_dt)
        
        if end_date:
            end_dt = datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1)
            query = query.where(scheduler_logs_table.c.created_at < end_dt)
        
        # Environment filter
        if environment:
            from sqlalchemy import or_
            query = query.where(or_(
                scheduler_logs_table.c.environment == environment,
                scheduler_logs_table.c.environment == 'all'
            ))
        
        with engine.connect() as conn:
            results = conn.execute(query).fetchall()
            
            # Calculate statistics
            stats = {
                "total_logs": len(results),
                "by_scheduler": {},
                "by_log_type": {},
                "by_status": {},
                "by_exchange": {},
                "success_count": 0,
                "failed_count": 0,
                "error_count": 0
            }
            
            for row in results:
                scheduler_name = row[2]  # scheduler_name
                log_type = row[7]  # log_type
                status = row[11]  # status
                exchange_name = row[5]  # exchange_name
                
                # Count by scheduler
                stats["by_scheduler"][scheduler_name] = stats["by_scheduler"].get(scheduler_name, 0) + 1
                
                # Count by log type
                stats["by_log_type"][log_type] = stats["by_log_type"].get(log_type, 0) + 1
                
                # Count by status
                if status:
                    stats["by_status"][status] = stats["by_status"].get(status, 0) + 1
                    if status == "success":
                        stats["success_count"] += 1
                    elif status == "failed":
                        stats["failed_count"] += 1
                    elif status == "error":
                        stats["error_count"] += 1
                
                # Count by exchange
                if exchange_name:
                    stats["by_exchange"][exchange_name] = stats["by_exchange"].get(exchange_name, 0) + 1
            
            return stats
            
    except Exception as e:
        logger.error(f"Error fetching scheduler logs stats: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error fetching scheduler logs stats: {str(e)}")

