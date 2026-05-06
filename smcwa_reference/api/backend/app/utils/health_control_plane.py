"""
Self-Healing Control Plane
--------------------------
Runs continuous health probes for every critical component and persists
the results to the `component_health` table so alerts and remediation
logic can react automatically.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional

from sqlalchemy import and_, desc, func, select
from sqlalchemy.exc import SQLAlchemyError

from app.db.db import (
    component_health_table,
    engine,
    lama_config_table,
    lama_tokens_table,
    scheduler_logs_table,
)
from app.utils.health_monitor import (
    check_database_connection,
    check_disk_space,
    check_memory_usage,
)
from app.utils.metric_queue import get_queue_stats

logger = logging.getLogger(__name__)


class HealthStatus(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    FAILED = "failed"


@dataclass
class HealthRecord:
    component_name: str
    environment: Optional[str]
    status: HealthStatus
    summary: str
    details: Dict[str, Any]
    severity: str
    last_error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload["status"] = self.status.value
        return payload


HEALTH_MONITOR_INTERVAL = int(os.getenv("HEALTH_MONITOR_INTERVAL_SECONDS", "60"))
SCHEDULER_WARN_THRESHOLD_MINUTES = int(os.getenv("HEALTH_MONITOR_SCHEDULER_WARN_MINUTES", "7"))
SCHEDULER_FAIL_THRESHOLD_MINUTES = int(os.getenv("HEALTH_MONITOR_SCHEDULER_FAIL_MINUTES", "15"))
QUEUE_FAILED_WARN_THRESHOLD = int(os.getenv("HEALTH_MONITOR_QUEUE_FAILED_WARN", "10"))

_monitor_thread: Optional[threading.Thread] = None
_monitor_lock = threading.Lock()
_stop_event = threading.Event()
_last_run_timestamp: Optional[datetime] = None

_SCHEDULER_COMPONENTS = [
    ("Hardware-Scheduler", "hardware"),
    ("Network-Scheduler", "network"),
    ("App-Scheduler", "application"),
    ("DB-Scheduler", "database"),
]


def _status_to_severity(status: HealthStatus) -> str:
    if status == HealthStatus.HEALTHY:
        return "info"
    if status == HealthStatus.DEGRADED:
        return "warning"
    return "critical"


def _get_configured_environments() -> List[str]:
    try:
        with engine.connect() as conn:
            rows = conn.execute(
                select(lama_config_table.c.environment).distinct()
            ).fetchall()
            envs = sorted({row[0] for row in rows if row[0]})
            return envs or ["uat", "prod"]
    except SQLAlchemyError as exc:
        logger.debug(f"[HEALTH] Failed to read environments: {exc}")
        return ["uat", "prod"]


def _persist_health_record(record: HealthRecord) -> None:
    """Upsert component health into the database using INSERT ON CONFLICT DO UPDATE."""
    try:
        from sqlalchemy.dialects.postgresql import insert as pg_insert
        
        with engine.begin() as conn:
            # Use PostgreSQL INSERT ON CONFLICT DO UPDATE (upsert)
            # This is atomic and avoids race conditions between DELETE + INSERT
            stmt = pg_insert(component_health_table).values(
                component_name=record.component_name,
                environment=record.environment,
                status=record.status.value,
                severity=record.severity,
                summary=record.summary[:255] if record.summary else None,
                details=record.details,
                last_error=record.last_error,
                updated_at=datetime.utcnow(),
            )
            
            # On conflict with unique constraint (component_name, environment), update
            stmt = stmt.on_conflict_do_update(
                constraint='unique_component_health',
                set_={
                    'status': stmt.excluded.status,
                    'severity': stmt.excluded.severity,
                    'summary': stmt.excluded.summary,
                    'details': stmt.excluded.details,
                    'last_error': stmt.excluded.last_error,
                    'updated_at': stmt.excluded.updated_at,
                }
            )
            
            conn.execute(stmt)
    except SQLAlchemyError as exc:
        logger.error(f"[HEALTH] Failed to persist component health ({record.component_name}): {exc}")


def _probe_system_resources() -> List[HealthRecord]:
    records: List[HealthRecord] = []

    disk_result = check_disk_space()
    disk_status = HealthStatus.HEALTHY if disk_result.status else HealthStatus.FAILED
    records.append(
        HealthRecord(
            component_name="system_disk",
            environment=None,
            status=disk_status,
            summary=disk_result.message,
            details=disk_result.details,
            severity=_status_to_severity(disk_status),
        )
    )

    memory_result = check_memory_usage()
    memory_status = HealthStatus.HEALTHY if memory_result.status else HealthStatus.DEGRADED
    records.append(
        HealthRecord(
            component_name="system_memory",
            environment=None,
            status=memory_status,
            summary=memory_result.message,
            details=memory_result.details,
            severity=_status_to_severity(memory_status),
        )
    )

    return records


def _probe_database() -> List[HealthRecord]:
    db_result = check_database_connection()
    db_status = HealthStatus.HEALTHY if db_result.status else HealthStatus.FAILED
    return [
        HealthRecord(
            component_name="database",
            environment=None,
            status=db_status,
            summary=db_result.message,
            details=db_result.details,
            severity=_status_to_severity(db_status),
            last_error=None if db_result.status else db_result.details.get("error"),
        )
    ]


def _probe_queue_worker() -> List[HealthRecord]:
    from app.utils import queue_worker  # Local import to avoid circular dependency

    stats = get_queue_stats()
    failed_count = stats.get("failed", 0)
    pending = stats.get("pending", 0)
    running = queue_worker.is_worker_running()

    if not running:
        status = HealthStatus.FAILED
        summary = "Queue worker is not running"
    elif failed_count > QUEUE_FAILED_WARN_THRESHOLD:
        status = HealthStatus.DEGRADED
        summary = f"Queue worker running but {failed_count} failed metrics awaiting retry"
    else:
        status = HealthStatus.HEALTHY
        summary = "Queue worker running"

    summary += f" | pending={pending}, failed={failed_count}"

    return [
        HealthRecord(
            component_name="queue_worker",
            environment=None,
            status=status,
            summary=summary,
            details=stats,
            severity=_status_to_severity(status),
        )
    ]


def _probe_token_cache() -> List[HealthRecord]:
    records: List[HealthRecord] = []
    environments = _get_configured_environments()
    now = datetime.utcnow()

    with engine.connect() as conn:
        for environment in environments:
            stmt = select(func.count(lama_tokens_table.c.id)).where(
                and_(
                    lama_tokens_table.c.environment == environment,
                    lama_tokens_table.c.expires_at > now,
                )
            )
            count = conn.execute(stmt).scalar() or 0
            if count > 0:
                status = HealthStatus.HEALTHY
                summary = f"{count} active token(s) cached in DB"
            else:
                status = HealthStatus.DEGRADED
                summary = "No active token persisted – next scheduler run will trigger login"

            records.append(
                HealthRecord(
                    component_name="token_cache",
                    environment=environment,
                    status=status,
                    summary=summary,
                    details={"active_tokens": count},
                    severity=_status_to_severity(status),
                )
            )

    return records


def _probe_scheduler_activity() -> List[HealthRecord]:
    records: List[HealthRecord] = []
    environments = _get_configured_environments()
    warn_threshold = datetime.utcnow() - timedelta(minutes=SCHEDULER_WARN_THRESHOLD_MINUTES)
    fail_threshold = datetime.utcnow() - timedelta(minutes=SCHEDULER_FAIL_THRESHOLD_MINUTES)

    with engine.connect() as conn:
        for scheduler_name, metric_type in _SCHEDULER_COMPONENTS:
            for environment in environments:
                stmt = (
                    select(scheduler_logs_table.c.created_at)
                    .where(
                        and_(
                            scheduler_logs_table.c.scheduler_name == scheduler_name,
                            scheduler_logs_table.c.environment == environment,
                            scheduler_logs_table.c.action == "scheduler_end",
                        )
                    )
                    .order_by(desc(scheduler_logs_table.c.created_at))
                    .limit(1)
                )
                row = conn.execute(stmt).fetchone()
                last_run = row[0] if row else None

                if last_run is None:
                    status = HealthStatus.DEGRADED
                    summary = "No successful run recorded yet"
                elif last_run >= warn_threshold:
                    status = HealthStatus.HEALTHY
                    summary = f"Last run at {last_run.isoformat()} UTC"
                elif last_run >= fail_threshold:
                    status = HealthStatus.DEGRADED
                    summary = f"Last run {int((datetime.utcnow() - last_run).total_seconds() / 60)} minutes ago"
                else:
                    status = HealthStatus.FAILED
                    summary = f"No run in past {SCHEDULER_FAIL_THRESHOLD_MINUTES} minutes"

                records.append(
                    HealthRecord(
                        component_name=f"scheduler.{metric_type}",
                        environment=environment,
                        status=status,
                        summary=summary,
                        details={
                            "scheduler_name": scheduler_name,
                            "metric_type": metric_type,
                            "last_run": last_run.isoformat() if last_run else None,
                        },
                        severity=_status_to_severity(status),
                    )
                )

    return records


def _probe_metric_queue_depth() -> List[HealthRecord]:
    stats = get_queue_stats()
    total = stats.get("total", 0)
    failed = stats.get("failed", 0)

    if failed > QUEUE_FAILED_WARN_THRESHOLD:
        status = HealthStatus.DEGRADED
        summary = f"{failed} failed items waiting on retry"
    else:
        status = HealthStatus.HEALTHY
        summary = f"Queue depth OK (total={total}, failed={failed})"

    return [
        HealthRecord(
            component_name="metric_queue",
            environment=None,
            status=status,
            summary=summary,
            details=stats,
            severity=_status_to_severity(status),
        )
    ]


def _run_health_checks() -> List[HealthRecord]:
    records: List[HealthRecord] = []
    for probe in (
        _probe_system_resources,
        _probe_database,
        _probe_queue_worker,
        _probe_metric_queue_depth,
        _probe_token_cache,
        _probe_scheduler_activity,
    ):
        try:
            records.extend(probe())
        except Exception as exc:  # pylint: disable=broad-except
            logger.error(f"[HEALTH] Probe {probe.__name__} failed: {exc}", exc_info=True)
            records.append(
                HealthRecord(
                    component_name=probe.__name__,
                    environment=None,
                    status=HealthStatus.FAILED,
                    summary=f"Probe failed: {exc}",
                    details={},
                    severity="critical",
                    last_error=str(exc),
                )
            )
    return records


def run_health_checks_once(trigger: str = "manual") -> List[HealthRecord]:
    """Run every probe once and persist the results."""
    logger.info(f"[HEALTH] Running health control plane checks (trigger={trigger})")
    records = _run_health_checks()
    for record in records:
        _persist_health_record(record)

    global _last_run_timestamp  # pylint: disable=global-statement
    _last_run_timestamp = datetime.utcnow()
    logger.info("[HEALTH] Health probes completed")
    return records


def _health_monitor_loop() -> None:
    logger.info("[HEALTH] Control plane monitor started")
    while not _stop_event.is_set():
        try:
            run_health_checks_once(trigger="automatic")
        except Exception as exc:  # pylint: disable=broad-except
            logger.error(f"[HEALTH] Control plane loop error: {exc}", exc_info=True)
        finally:
            _stop_event.wait(HEALTH_MONITOR_INTERVAL)
    logger.info("[HEALTH] Control plane monitor stopped")


def start_health_monitor() -> None:
    """Start the background health monitor if it is not already running."""
    global _monitor_thread  # pylint: disable=global-statement
    with _monitor_lock:
        if _monitor_thread and _monitor_thread.is_alive():
            logger.info("[HEALTH] Control plane monitor already running")
            return

        _stop_event.clear()
        # Run a bootstrap pass synchronously so the table is populated immediately
        run_health_checks_once(trigger="bootstrap")

        _monitor_thread = threading.Thread(
            target=_health_monitor_loop,
            daemon=True,
            name="HealthControlPlane",
        )
        _monitor_thread.start()
        logger.info("[HEALTH] Control plane monitor thread started")


def stop_health_monitor() -> None:
    """Stop the background health monitor."""
    global _monitor_thread  # pylint: disable=global-statement
    with _monitor_lock:
        if not _monitor_thread:
            return
        _stop_event.set()
        _monitor_thread.join(timeout=10)
        _monitor_thread = None
        logger.info("[HEALTH] Control plane monitor thread stopped")


def get_health_snapshot(
    component_name: Optional[str] = None,
    environment: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Return the most recent health records for all components."""
    filters = []
    if component_name:
        filters.append(component_health_table.c.component_name == component_name)
    if environment:
        filters.append(component_health_table.c.environment == environment)

    stmt = select(component_health_table).order_by(desc(component_health_table.c.updated_at))
    if filters:
        stmt = stmt.where(and_(*filters))

    try:
        with engine.connect() as conn:
            rows = conn.execute(stmt).fetchall()
            return [
                {
                    "component_name": row.component_name,
                    "environment": row.environment,
                    "status": row.status,
                    "severity": row.severity,
                    "summary": row.summary,
                    "details": row.details or {},
                    "last_error": row.last_error,
                    "updated_at": row.updated_at.isoformat() if row.updated_at else None,
                }
                for row in rows
            ]
    except SQLAlchemyError as exc:
        logger.error(f"[HEALTH] Failed to load component health snapshot: {exc}", exc_info=True)
        return []


def get_last_run_timestamp() -> Optional[datetime]:
    return _last_run_timestamp

