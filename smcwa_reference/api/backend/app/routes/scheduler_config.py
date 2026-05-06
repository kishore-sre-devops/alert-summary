"""
Scheduler Configuration Routes
UI-driven management of scheduler jobs: enable/disable, change timing.
"""
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from typing import Optional
from sqlalchemy import select, update
from datetime import datetime
import logging
from app.db.db import engine, scheduler_config_table
from app.utils.permissions import require_role

logger = logging.getLogger(__name__)
router = APIRouter()


class SchedulerConfigUpdate(BaseModel):
    cron_expression: Optional[str] = None
    interval_minutes: Optional[int] = None
    enabled: Optional[bool] = None


@router.get("/")
def list_scheduler_configs(request: Request):
    """List all scheduler job configurations."""
    require_role(request, ['admin'])
    with engine.connect() as conn:
        rows = conn.execute(select(scheduler_config_table).order_by(scheduler_config_table.c.id)).fetchall()
        return [dict(r._mapping) for r in rows]


@router.put("/{job_id}")
def update_scheduler_config(job_id: str, data: SchedulerConfigUpdate, request: Request):
    """Update a scheduler job's timing or enabled status. Requires container restart to take effect."""
    require_role(request, ['admin'])
    values = {k: v for k, v in data.dict(exclude_unset=True).items() if v is not None}
    if not values:
        raise HTTPException(status_code=400, detail="No fields to update")
    values['updated_at'] = datetime.utcnow()
    with engine.begin() as conn:
        result = conn.execute(
            update(scheduler_config_table)
            .where(scheduler_config_table.c.job_id == job_id)
            .values(**values)
            .returning(scheduler_config_table)
        ).fetchone()
        if not result:
            raise HTTPException(status_code=404, detail="Scheduler job not found")
        return dict(result._mapping)


@router.put("/{job_id}/toggle")
def toggle_scheduler(job_id: str, request: Request):
    """Toggle a scheduler job on/off."""
    require_role(request, ['admin'])
    with engine.begin() as conn:
        current = conn.execute(
            select(scheduler_config_table.c.enabled).where(scheduler_config_table.c.job_id == job_id)
        ).scalar()
        if current is None:
            raise HTTPException(status_code=404, detail="Scheduler job not found")
        new_val = not bool(current)
        conn.execute(
            update(scheduler_config_table)
            .where(scheduler_config_table.c.job_id == job_id)
            .values(enabled=new_val, updated_at=datetime.utcnow())
        )
        return {"job_id": job_id, "enabled": new_val}
