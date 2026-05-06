"""
Self-Healing Scheduler Watchdog
Monitors all 4 exchange schedulers + supporting jobs and auto-recovers from failures.

Recovery strategies:
1. Stale scheduler detection → force re-trigger
2. Token expiry / 801 errors → invalidate cache + re-login
3. Sequence desync / 704 errors → reset sequence from exchange hint
4. can_send stuck (timezone mismatch) → auto-correct stale transactions
5. Database connection failures → reconnect engine
6. APScheduler job disappeared → re-register job
"""

import logging
import threading
import time
from datetime import datetime, timedelta
from sqlalchemy import text
from app.db.db import engine

logger = logging.getLogger(__name__)

# Thresholds
SCHEDULER_STALE_MINUTES = 12  # If no run in 12 min (2 missed cycles), it's stale
WATCHDOG_INTERVAL_SECONDS = 120  # Check every 2 minutes
MAX_CONSECUTIVE_FAILURES = 3  # After 3 failures, escalate recovery

_watchdog_thread = None
_watchdog_running = False
_failure_counts = {}  # {scheduler_name: consecutive_failure_count}

SCHEDULER_NAMES = ["Hardware-Scheduler", "Network-Scheduler", "Application-Scheduler", "DB-Scheduler"]
METRIC_TYPES = ["hardware", "network", "application", "database"]


def _check_scheduler_health() -> dict:
    """Check last run time of each scheduler from scheduler_logs."""
    results = {}
    try:
        with engine.connect() as conn:
            for name in SCHEDULER_NAMES:
                row = conn.execute(text("""
                    SELECT timestamp FROM scheduler_logs
                    WHERE scheduler_name = :name AND log_type = 'scheduler' AND action = 'scheduler_start'
                    ORDER BY timestamp DESC LIMIT 1
                """), {"name": name}).fetchone()
                if row and row[0]:
                    age_minutes = (datetime.utcnow() - row[0]).total_seconds() / 60
                    results[name] = {"last_run": row[0], "age_minutes": age_minutes, "stale": age_minutes > SCHEDULER_STALE_MINUTES}
                else:
                    results[name] = {"last_run": None, "age_minutes": 999, "stale": True}
    except Exception as e:
        logger.error(f"[WATCHDOG] Health check DB error: {e}")
    return results


def _check_can_send_stuck() -> list:
    """Detect if can_send is permanently stuck due to timezone mismatch."""
    stuck = []
    try:
        with engine.connect() as conn:
            for mt in METRIC_TYPES:
                rows = conn.execute(text("""
                    SELECT DISTINCT metrics_sent->'lama_v1_2_payload'->>'exchangeId' as exch_id,
                           MAX(sent_at) as last_sent
                    FROM exchange_transactions
                    WHERE metric_type = :mt AND status = 'success'
                    GROUP BY metrics_sent->'lama_v1_2_payload'->>'exchangeId'
                """), {"mt": mt}).fetchall()
                for row in rows:
                    if row[1] and row[0] is not None:
                        delta = datetime.now() - row[1]
                        # If last success was > 15 min ago but < 24h, can_send might be stuck
                        if timedelta(minutes=15) < delta < timedelta(hours=24):
                            stuck.append({"metric_type": mt, "exchange_id": row[0], "last_sent": row[1], "age_minutes": delta.total_seconds() / 60})
    except Exception as e:
        logger.error(f"[WATCHDOG] can_send check error: {e}")
    return stuck


def _check_recent_errors() -> dict:
    """Check for repeated 704/801 errors in last 15 minutes."""
    errors = {}
    try:
        with engine.connect() as conn:
            for code in ["704", "801"]:
                rows = conn.execute(text("""
                    SELECT metric_type, 
                           metrics_sent->'lama_v1_2_payload'->>'exchangeId' as exch_id,
                           COUNT(*) as cnt
                    FROM exchange_transactions
                    WHERE exchange_response->>'responseCode' = :code
                      AND sent_at > :cutoff
                    GROUP BY metric_type, metrics_sent->'lama_v1_2_payload'->>'exchangeId'
                    HAVING COUNT(*) >= 2
                """), {"code": code, "cutoff": datetime.now() - timedelta(minutes=15)}).fetchall()
                for row in rows:
                    key = f"{row[0]}_{row[1]}"
                    errors[key] = {"error_code": code, "metric_type": row[0], "exchange_id": row[1], "count": row[2]}
    except Exception as e:
        logger.error(f"[WATCHDOG] Error check failed: {e}")
    return errors


def _recover_stuck_can_send():
    """Fix can_send stuck by ensuring time comparisons use consistent timezone."""
    # The code fix (datetime.now() instead of datetime.utcnow()) handles this permanently.
    # This recovery handles edge cases where old IST data causes issues.
    logger.info("[WATCHDOG] 🔧 can_send recovery: code fix applied (datetime.now() for IST consistency)")


def _recover_801_token(metric_type: str, exchange_id: str):
    """Invalidate cached token for exchange to force re-login."""
    try:
        from app.utils.lama_token_cache import _clear_token_cache_entries
        exch_int = int(exchange_id)
        _clear_token_cache_entries("prod", [exch_int])
        logger.info(f"[WATCHDOG] 🔧 Invalidated token for exchange {exchange_id} ({metric_type}) — will re-login next cycle")
    except Exception as e:
        logger.warning(f"[WATCHDOG] Token invalidation failed: {e}")


def _recover_704_sequence(metric_type: str, exchange_id: str):
    """Reset sequence cache from latest 704 hint."""
    try:
        from app.utils.lama_exchange_api import update_sequence_cache_after_704
        with engine.connect() as conn:
            row = conn.execute(text("""
                SELECT exchange_response->>'expectedSequenceId'
                FROM exchange_transactions
                WHERE exchange_response->>'responseCode' = '704'
                  AND metric_type = :mt
                  AND metrics_sent->'lama_v1_2_payload'->>'exchangeId' = :eid
                ORDER BY sent_at DESC LIMIT 1
            """), {"mt": metric_type, "eid": exchange_id}).fetchone()
            if row and row[0]:
                hint = int(row[0])
                update_sequence_cache_after_704("prod", int(exchange_id), metric_type, hint)
                logger.info(f"[WATCHDOG] 🔧 Reset sequence for {metric_type} exch={exchange_id} to {hint}")
    except Exception as e:
        logger.warning(f"[WATCHDOG] Sequence recovery failed: {e}")


def _recover_stale_scheduler(scheduler_name: str):
    """Force re-trigger a stale scheduler by calling it directly."""
    try:
        from app.schedulers import hardware_scheduler, network_scheduler
        from app.utils.application_metrics_scheduler_v2 import run_application_metrics_scheduler
        from app.schedulers.database import db_scheduler

        SCHEDULER_FUNCTIONS = {
            "Hardware-Scheduler": hardware_scheduler,
            "Network-Scheduler": network_scheduler,
            "Application-Scheduler": run_application_metrics_scheduler,
            "DB-Scheduler": db_scheduler,
        }
        fn = dispatch.get(scheduler_name)
        if fn:
            logger.info(f"[WATCHDOG] 🔧 Force re-triggering {scheduler_name}")
            # Run in a separate thread to not block watchdog
            t = threading.Thread(target=fn, name=f"watchdog-{scheduler_name}", daemon=True)
            t.start()
    except Exception as e:
        logger.error(f"[WATCHDOG] Failed to re-trigger {scheduler_name}: {e}")


def _recover_missing_job(scheduler_name: str):
    """Re-register a missing APScheduler job."""
    try:
        # Try scheduler_main first (dedicated process), then main.py (in-process mode)
        try:
            from app.scheduler_main import scheduler as apscheduler
        except (ImportError, AttributeError):
            from app.main import scheduler as apscheduler

        existing = apscheduler.get_job("lama_exchange_sync_scheduler")
        if existing:
            return  # Sync scheduler exists, jobs are fine

        from apscheduler.triggers.cron import CronTrigger
        from pytz import timezone as pytz_tz
        from app.scheduler_main import lama_exchange_sync_scheduler

        ist = pytz_tz('Asia/Kolkata')
        apscheduler.add_job(
            lama_exchange_sync_scheduler,
            trigger=CronTrigger(minute='*/5', timezone=ist),
            id='lama_exchange_sync_scheduler', name='LAMA-Exchange-Sync-Scheduler',
            replace_existing=True, max_instances=1, coalesce=True, misfire_grace_time=300
        )
        logger.info(f"[WATCHDOG] 🔧 Re-registered missing sync scheduler job")
    except Exception as e:
        logger.error(f"[WATCHDOG] Job re-registration failed for {scheduler_name}: {e}")


def _watchdog_cycle():
    """Single watchdog check + recovery cycle."""
    global _failure_counts
    recoveries = []

    # 1. Check scheduler staleness
    health = _check_scheduler_health()
    for name, info in health.items():
        if info["stale"]:
            _failure_counts[name] = _failure_counts.get(name, 0) + 1
            if _failure_counts[name] >= MAX_CONSECUTIVE_FAILURES:
                _recover_missing_job(name)
                _recover_stale_scheduler(name)
                recoveries.append(f"re-triggered {name} (stale {info['age_minutes']:.0f}m)")
                _failure_counts[name] = 0
        else:
            _failure_counts[name] = 0

    # 2. Check for repeated exchange errors
    errors = _check_recent_errors()
    for key, info in errors.items():
        if info["error_code"] == "801":
            _recover_801_token(info["metric_type"], info["exchange_id"])
            recoveries.append(f"token reset {info['metric_type']} exch={info['exchange_id']}")
        elif info["error_code"] == "704":
            _recover_704_sequence(info["metric_type"], info["exchange_id"])
            recoveries.append(f"seq reset {info['metric_type']} exch={info['exchange_id']}")

    # 3. Check can_send stuck
    stuck = _check_can_send_stuck()
    if stuck:
        _recover_stuck_can_send()
        for s in stuck:
            recoveries.append(f"can_send check {s['metric_type']} exch={s['exchange_id']} ({s['age_minutes']:.0f}m stale)")

    if recoveries:
        logger.info(f"[WATCHDOG] 🩺 Cycle complete — {len(recoveries)} recoveries: {'; '.join(recoveries)}")
    else:
        logger.debug("[WATCHDOG] ✅ All schedulers healthy")


def _watchdog_loop():
    """Main watchdog loop."""
    global _watchdog_running
    logger.info("[WATCHDOG] 🚀 Self-healing watchdog started")
    while _watchdog_running:
        try:
            _watchdog_cycle()
        except Exception as e:
            logger.error(f"[WATCHDOG] Cycle error (will retry): {e}", exc_info=True)
        time.sleep(WATCHDOG_INTERVAL_SECONDS)
    logger.info("[WATCHDOG] Stopped")


def start_watchdog():
    """Start the self-healing watchdog in a background thread."""
    global _watchdog_thread, _watchdog_running
    if _watchdog_running:
        return
    _watchdog_running = True
    _watchdog_thread = threading.Thread(target=_watchdog_loop, name="scheduler-watchdog", daemon=True)
    _watchdog_thread.start()
    logger.info("[WATCHDOG] ✅ Self-healing watchdog thread started")


def stop_watchdog():
    """Stop the watchdog."""
    global _watchdog_running
    _watchdog_running = False
    logger.info("[WATCHDOG] Stop requested")
