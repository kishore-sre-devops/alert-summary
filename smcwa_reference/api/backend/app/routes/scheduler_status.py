# api/backend/app/routes/scheduler_status.py
"""
Scheduler Status endpoints for dashboard monitoring
Provides visibility into APScheduler job status and execution
"""

from fastapi import APIRouter, HTTPException, Depends
from datetime import datetime
from typing import List, Dict, Optional
import logging
from app.utils.environment import get_active_environment

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/status/environment")
def get_environment_scheduler_status(environment: str = Depends(get_active_environment)):
    """
    Get status of background scheduler for a specific environment.
    """
    try:
        from app.db.db import engine
        from sqlalchemy import text
        from datetime import datetime, timedelta
        import pytz
        from app.utils.lama_exchange import is_exchange_enabled, get_base_url
        
        ist = pytz.timezone('Asia/Kolkata')
        
        # 1. Check if LAMA Exchange is enabled for this environment (Source of truth for activity)
        is_active = is_exchange_enabled(environment)
        lama_url = get_base_url(environment)
        
        # 2. Get last run time from scheduler_logs
        # Use a specific job like 'Hardware-Scheduler' or 'LAMA-Exchange-Sync-Scheduler'
        last_run_query = text("""
            SELECT created_at 
            FROM scheduler_logs 
            WHERE environment = :env 
              AND action = 'scheduler_start'
            ORDER BY created_at DESC 
            LIMIT 1
        """)
        
        last_run_time = None
        next_run_time = None
        
        with engine.connect() as conn:
            row = conn.execute(last_run_query, {"env": environment}).fetchone()
            if row:
                last_run_utc = row[0].replace(tzinfo=pytz.UTC)
                last_run_time = last_run_utc.isoformat()
                
                # Calculate next run (assuming 5 minute cycle)
                # Next run should be at the next 5-minute boundary
                now_utc = datetime.utcnow().replace(tzinfo=pytz.UTC)
                minutes_past = now_utc.minute % 5
                seconds_past = now_utc.second
                seconds_to_next = ((5 - minutes_past) * 60) - seconds_past
                if seconds_to_next <= 0: seconds_to_next = 300
                
                next_run_utc = now_utc + timedelta(seconds=seconds_to_next)
                next_run_time = next_run_utc.isoformat()

        return {
            "environment": environment.upper(),
            "is_active": is_active,
            "last_run": last_run_time,
            "next_run": next_run_time if is_active else None,
            "lama_url": lama_url
        }
    except Exception as e:
        logger.error(f"Error fetching environment scheduler status: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status")
def get_scheduler_status():
    """
    Get status of background scheduler jobs based on recent activity logs.
    This works even when running in Process Isolation mode.
    """
    try:
        from app.db.db import engine
        from sqlalchemy import text
        from datetime import datetime, timedelta
        import pytz
        
        ist = pytz.timezone('Asia/Kolkata')
        
        # 1. Check if the scheduler is alive via database heartbeat log
        is_running = False
        
        # Look for 'Scheduler Heartbeat' success in the last 3 minutes
        # FIX: Use UTC comparison to match how logs are stored
        hb_query = text("""
            SELECT created_at 
            FROM scheduler_logs 
            WHERE scheduler_name = 'Scheduler Heartbeat' 
              AND status = 'success'
              AND created_at >= (NOW() AT TIME ZONE 'UTC') - INTERVAL '3 minutes'
            LIMIT 1
        """)
        
        with engine.connect() as conn:
            hb_result = conn.execute(hb_query).fetchone()
            if hb_result:
                is_running = True
        
        # 2. Define the "Master List" of jobs we expect to see
        # This ensures Data Retention and SSL Expiry show up even if they haven't run today
        master_jobs = {
            "LAMA-Exchange-Sync-Scheduler": {"trigger": "Every 5m", "interval": 300},
            "Hardware-Scheduler": {"trigger": "Every 5m (via Sync)", "interval": 300},
            "Network-Scheduler": {"trigger": "Every 5m (via Sync)", "interval": 300},
            "DB-Scheduler": {"trigger": "Every 5m (via Sync)", "interval": 300},
            "Application-Scheduler": {"trigger": "Every 5m (via Sync)", "interval": 300},
            "Prometheus Metrics Collection": {"trigger": "Every 10s", "interval": 10},
            "Database Metrics Collection": {"trigger": "Every 6s", "interval": 6},
            "Server Down Monitor": {"trigger": "Every 2m", "interval": 120},
            "Data Retention Cleanup": {"trigger": "Daily 2 AM IST", "cron": "0 2 * * *"},
            "SSL Certificate Expiry Check": {"trigger": "Daily 9 AM IST", "cron": "0 9 * * *"},
            "Scheduler Heartbeat": {"trigger": "Every 1m", "interval": 60}
        }

        # 3. Get latest job statuses from scheduler_logs
        # FIX: Use UTC comparison to match how logs are stored
        query = text("""
            SELECT DISTINCT ON (scheduler_name) 
                scheduler_name, 
                status, 
                message, 
                created_at,
                action
            FROM scheduler_logs
            WHERE created_at >= (NOW() AT TIME ZONE 'UTC') - INTERVAL '48 hours'
            ORDER BY scheduler_name, created_at DESC
        """)
        
        logged_jobs = {}
        with engine.connect() as conn:
            results = conn.execute(query).fetchall()
            for row in results:
                job_name = row[0]
                status_val = row[1]
                msg = row[2]
                last_run_utc = row[3].replace(tzinfo=pytz.UTC)
                last_run_ist = last_run_utc.astimezone(ist)
                
                logged_jobs[job_name] = {
                    "status": status_val,
                    "message": msg,
                    "last_run": last_run_ist
                }

        # 4. Merge Master List with Logged Activity
        final_jobs = []
        for name, config in master_jobs.items():
            log = logged_jobs.get(name)
            
            job_data = {
                "id": name.lower().replace(" ", "_"),
                "name": name,
                "trigger": config["trigger"],
                "status": "scheduled" if is_running else "stopped",
                "last_run_time": log["last_run"].isoformat() if log else None,
                "last_status": log["status"] if log else "pending",
                "last_message": log["message"] if log else "Waiting for next execution"
            }
            
            # Calculate Next Run Time
            if log and "interval" in config:
                next_run = log["last_run"] + timedelta(seconds=config["interval"])
                job_data["next_run_time"] = next_run.isoformat()
            elif "cron" in config:
                # Simple cron logic for 2 AM / 9 AM
                now_ist = datetime.now(ist)
                hour = 2 if "2 AM" in config["trigger"] else 9
                next_run = now_ist.replace(hour=hour, minute=0, second=0, microsecond=0)
                if next_run < now_ist:
                    next_run += timedelta(days=1)
                job_data["next_run_time"] = next_run.isoformat()
            else:
                job_data["next_run_time"] = None
                
            final_jobs.append(job_data)

        return {
            "scheduler_running": is_running,
            "jobs": final_jobs,
            "total_jobs": len(final_jobs),
            "source": "hybrid_master_logs",
            "server_time_ist": datetime.now(ist).isoformat()
        }
    except Exception as e:
        logger.error(f"Error fetching job status: {e}", exc_info=True)
        return {"scheduler_running": False, "jobs": [], "error": str(e)}

import os
import time



@router.get("/status/last-execution")
def get_last_execution_status(environment: Optional[str] = None):
    """
    Get last execution status for LAMA Exchange schedulers
    Queries exchange_transactions table to find last successful execution
    """
    try:
        from app.db.db import engine, exchange_transactions_table
        from sqlalchemy import select, desc, and_
        from datetime import datetime, timedelta
        
        # Query for last successful execution of LAMA Exchange scheduler
        # Look for SUCCESS transactions in last 24 hours
        query = select(exchange_transactions_table).where(
            and_(
                exchange_transactions_table.c.status == 'success',
                exchange_transactions_table.c.metric_type.in_(['hardware', 'network', 'database', 'application']),
                exchange_transactions_table.c.sent_at >= datetime.now() - timedelta(hours=24)
            )
        )
        
        if environment:
            query = query.where(exchange_transactions_table.c.environment == environment)
        
        query = query.order_by(desc(exchange_transactions_table.c.sent_at)).limit(1)
        
        with engine.connect() as conn:
            result = conn.execute(query).fetchone()
            
            if result:
                sent_at = result[14] if len(result) > 14 else None  # sent_at is at index 14
                metric_type = result[7] if len(result) > 7 else None  # metric_type is at index 7
                environment = result[1] if len(result) > 1 else None  # environment is at index 1
                
                return {
                    "last_execution_time": sent_at.isoformat() + 'Z' if sent_at else None,
                    "last_metric_type": metric_type,
                    "environment": environment,
                    "status": "success"
                }
        
        return {
            "last_execution_time": None,
            "status": "no_execution_found",
            "message": "No successful execution found in last 24 hours"
        }
        
    except Exception as e:
        logger.error(f"Error getting last execution status: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get last execution status: {str(e)}")

