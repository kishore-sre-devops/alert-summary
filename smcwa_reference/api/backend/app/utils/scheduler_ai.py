"""
AI-Powered Scheduler Intelligence Layer
Self-healing, predictive, and adaptive sequence management

CRITICAL: All queries are scoped by (environment, exchange_id, metric_type).
Each exchange has its own independent sequence counter.
DB timestamps are IST (Asia/Kolkata) — use datetime.now(), NOT utcnow().
"""
import logging
from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple
from sqlalchemy import text
from app.db.db import engine

logger = logging.getLogger(__name__)


class SchedulerAI:
    """
    Intelligent scheduler that predicts and prevents 704 errors.
    All operations are scoped per (environment, exchange_id, metric_type).
    """

    def predict_next_sequence(self, environment: str, exchange_id: int,
                             metric_type: str, proposed_seq: int) -> Tuple[bool, Optional[int], str]:
        """
        Predict if proposed sequence will succeed for a specific exchange.
        Returns: (is_safe, corrected_seq, reason)
        """
        exchange_name = {1: "NSE", 2: "BSE", 4: "MCX", 5: "NCDEX"}.get(exchange_id, f"Exch-{exchange_id}")
        try:
            # 1. Check if we're in a 704 loop for THIS exchange
            recent_704_count = self._count_recent_704s(environment, exchange_id, metric_type, minutes=1)
            if recent_704_count >= 3:
                return True, proposed_seq, f"AI paused: 704 loop on {exchange_name} ({recent_704_count} errors)"

            # 2. Check very recent 704 hint for THIS exchange (last 30s)
            recent_704 = self._get_recent_704_hint(environment, exchange_id, metric_type, minutes=0.5)
            if recent_704:
                if recent_704 != proposed_seq:
                    return False, recent_704, f"{exchange_name} 704 hint says {recent_704}, not {proposed_seq}"
                return True, proposed_seq, "Matches recent 704 hint"

            # 3. Validate against last success for THIS exchange
            last_success = self._get_last_success_seq(environment, exchange_id, metric_type)
            if last_success is not None:
                expected = last_success + 1
                if proposed_seq < expected:
                    return False, expected, f"{exchange_name} last 601 was {last_success}, need {expected}"
                elif proposed_seq > expected + 10:
                    return False, expected, f"{exchange_name} gap too large, resetting to {expected}"

            return True, proposed_seq, "Validation passed"

        except Exception as e:
            logger.error(f"[AI] {exchange_name} prediction error: {e}")
            return True, proposed_seq, "Prediction failed, allowing"

    def _count_recent_704s(self, environment: str, exchange_id: int,
                          metric_type: str, minutes: float = 1) -> int:
        """Count 704 errors for THIS exchange in last N minutes."""
        try:
            with engine.connect() as conn:
                result = conn.execute(text("""
                    SELECT COUNT(*) FROM exchange_transactions
                    WHERE environment = :env AND exchange_id = :eid AND metric_type = :mtype
                      AND status_code = 704 AND sent_at > :cutoff
                """), {
                    "env": environment, "eid": exchange_id, "mtype": metric_type,
                    "cutoff": datetime.now() - timedelta(minutes=minutes)
                }).scalar()
                return result or 0
        except Exception as e:
            logger.error(f"[AI] Error counting 704s: {e}")
            return 0

    def _get_recent_704_hint(self, environment: str, exchange_id: int,
                            metric_type: str, minutes: float = 5) -> Optional[int]:
        """Get most recent 704 hint for THIS exchange."""
        try:
            with engine.connect() as conn:
                result = conn.execute(text("""
                    SELECT CAST(exchange_response->>'expectedSequenceId' AS INTEGER)
                    FROM exchange_transactions
                    WHERE environment = :env AND exchange_id = :eid AND metric_type = :mtype
                      AND status_code = 704 AND sent_at > :cutoff
                    ORDER BY sent_at DESC LIMIT 1
                """), {
                    "env": environment, "eid": exchange_id, "mtype": metric_type,
                    "cutoff": datetime.now() - timedelta(minutes=minutes)
                }).scalar()
                return result
        except Exception as e:
            logger.error(f"[AI] Error getting 704 hint: {e}")
            return None

    def _get_last_success_seq(self, environment: str, exchange_id: int,
                             metric_type: str) -> Optional[int]:
        """Get last successful (601) sequence for THIS exchange + metric_type."""
        try:
            with engine.connect() as conn:
                result = conn.execute(text("""
                    SELECT CAST(sequence_id AS INTEGER)
                    FROM exchange_transactions
                    WHERE environment = :env AND exchange_id = :eid AND metric_type = :mtype
                      AND status_code = 601 AND sequence_id ~ '^[0-9]+$'
                    ORDER BY sent_at DESC LIMIT 1
                """), {
                    "env": environment, "eid": exchange_id, "mtype": metric_type
                }).scalar()
                return result
        except Exception as e:
            logger.error(f"[AI] Error getting last success: {e}")
            return None

    def auto_heal(self, environment: str, exchange_id: int, metric_type: str) -> bool:
        """Sync cache with DB truth for a specific exchange."""
        exchange_name = {1: "NSE", 2: "BSE", 4: "MCX", 5: "NCDEX"}.get(exchange_id, f"Exch-{exchange_id}")
        try:
            # Try 704 hint first, then last success + 1
            expected = self._get_recent_704_hint(environment, exchange_id, metric_type, minutes=10)
            if not expected:
                last_success = self._get_last_success_seq(environment, exchange_id, metric_type)
                if last_success is not None:
                    expected = last_success + 1

            if expected:
                from app.utils.lama_exchange_api import update_sequence_cache_after_704
                update_sequence_cache_after_704(environment, exchange_id, metric_type, expected)
                logger.info(f"[AI] ✅ {exchange_name} {metric_type} auto-healed → seq {expected}")
                return True

            logger.warning(f"[AI] {exchange_name} {metric_type}: no ground truth for auto-heal")
            return False
        except Exception as e:
            logger.error(f"[AI] {exchange_name} auto-heal failed: {e}")
            return False

    def health_check(self, environment: str, exchange_id: int, metric_type: str) -> Dict:
        """Health check for a specific exchange + metric_type."""
        exchange_name = {1: "NSE", 2: "BSE", 4: "MCX", 5: "NCDEX"}.get(exchange_id, f"Exch-{exchange_id}")
        try:
            with engine.connect() as conn:
                result = conn.execute(text("""
                    SELECT
                        COUNT(*) FILTER (WHERE status_code = 601) as success_count,
                        COUNT(*) FILTER (WHERE status_code = 704) as error_704_count,
                        COUNT(*) as total_count
                    FROM exchange_transactions
                    WHERE environment = :env AND exchange_id = :eid AND metric_type = :mtype
                      AND sent_at > :cutoff
                """), {
                    "env": environment, "eid": exchange_id, "mtype": metric_type,
                    "cutoff": datetime.now() - timedelta(minutes=30)
                }).fetchone()

                if result and result[2] > 0:
                    rate = (result[0] / result[2]) * 100
                    return {
                        "exchange": exchange_name, "metric_type": metric_type,
                        "success_count": result[0], "error_704_count": result[1],
                        "total_count": result[2], "success_rate": round(rate, 2),
                        "health": "healthy" if rate >= 95 else "degraded" if rate >= 80 else "critical"
                    }
                return {"exchange": exchange_name, "health": "no_data"}
        except Exception as e:
            logger.error(f"[AI] Health check error: {e}")
            return {"exchange": exchange_name, "health": "error", "error": str(e)}


# Global AI instance
scheduler_ai = SchedulerAI()
