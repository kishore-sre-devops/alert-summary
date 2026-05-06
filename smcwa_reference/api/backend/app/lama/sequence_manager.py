"""
SequenceManager: SMC LAMA V2.0 Implementation
Atomic, DB-backed sequence management per exchange and metric type
CRITICAL FIX: Each exchange has INDEPENDENT sequence counters
"""
import logging
from sqlalchemy import text
from app.db.db import engine

logger = logging.getLogger(__name__)

class SequenceManager:
    def __init__(self):
        self._ensure_table_exists()

    def _ensure_table_exists(self):
        """Create lama_sequence table if it doesn't exist"""
        try:
            with engine.connect() as conn:
                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS lama_sequence (
                        id SERIAL PRIMARY KEY,
                        exchange_id INT NOT NULL,
                        environment VARCHAR(10) NOT NULL,
                        metric_type VARCHAR(50) DEFAULT 'hardware',
                        current_seq BIGINT NOT NULL DEFAULT 0,
                        last_updated TIMESTAMPTZ DEFAULT NOW(),
                        UNIQUE (exchange_id, environment, metric_type)
                    )
                """))
                conn.commit()
        except Exception as e:
            logger.error(f"Failed to ensure lama_sequence table: {e}")

    def get_next_sequence(self, exchange_id: int, environment: str = "prod", metric_type: str = "global") -> int:
        """
        CORRECT LAMA SPEC: Each exchange has INDEPENDENT sequence counters.
        Includes SELF-HEALING: Anchor to last successful 601 if current counter is behind.
        """
        m_type = metric_type if metric_type else "global"
        
        try:
            with engine.begin() as conn:
                # SELF-HEALING: Check for the last successful 601 for THIS SPECIFIC EXCHANGE
                success_query = text("""
                    SELECT sequence_id FROM exchange_transactions 
                    WHERE environment = :env AND exchange_id = :exch_id AND metric_type = :m_type AND status = 'success'
                    ORDER BY sent_at DESC LIMIT 1
                """)
                last_success = conn.execute(success_query, {"env": environment, "exch_id": exchange_id, "m_type": m_type}).fetchone()
                
                # Ensure the row for THIS EXCHANGE exists
                conn.execute(text("""
                    INSERT INTO lama_sequence (exchange_id, environment, metric_type, current_seq)
                    VALUES (:exch_id, :env, :m_type, 0)
                    ON CONFLICT (exchange_id, environment, metric_type) DO NOTHING
                """), {"exch_id": exchange_id, "env": environment, "m_type": m_type})

                # If we found a successful 601 that is higher than our current tracker, 
                # we heal the tracker to match the last known truth
                if last_success and last_success[0]:
                    last_good_id = int(last_success[0])
                    conn.execute(text("""
                        UPDATE lama_sequence 
                        SET current_seq = GREATEST(current_seq, :last_id)
                        WHERE exchange_id = :exch_id AND environment = :env AND metric_type = :m_type
                    """), {"last_id": last_good_id, "exch_id": exchange_id, "env": environment, "m_type": m_type})

                # Atomically increment THIS EXCHANGE's counter
                query = text("""
                    UPDATE lama_sequence 
                    SET current_seq = current_seq + 1, last_updated = NOW()
                    WHERE exchange_id = :exch_id AND environment = :env AND metric_type = :m_type
                    RETURNING current_seq
                """)
                res = conn.execute(query, {"exch_id": exchange_id, "env": environment, "m_type": m_type}).fetchone()
                return res[0] if res else 1
        except Exception as e:
            exchange_name = {1: "NSE", 2: "BSE", 4: "MCX", 5: "NCDEX"}.get(exchange_id, f"Exchange {exchange_id}")
            logger.error(f"Failed to get next sequence for {exchange_name} {m_type}: {e}")
            return 0

    def get_next_application_id(self, service_name: str, environment: str = "uat") -> int:
        """
        Dynamically generates and persists a unique Application ID for each service.
        UAT Range: 100+
        PROD Range: 200+
        """
        try:
            with engine.begin() as conn:
                # 1. Check if this service already has an ID assigned in lama_sequence
                check_query = text("""
                    SELECT current_seq FROM lama_sequence 
                    WHERE exchange_id = -1 AND environment = :env AND metric_type = :svc
                """)
                existing = conn.execute(check_query, {"env": environment, "svc": service_name}).fetchone()
                if existing:
                    return int(existing[0])

                # 2. If not, find the current max ID for this environment (using exchange_id -1 as a special marker for App IDs)
                # UAT starts at 100, PROD starts at 200
                start_id = 200 if environment.lower() == "prod" else 100
                max_query = text("""
                    SELECT MAX(current_seq) FROM lama_sequence 
                    WHERE exchange_id = -1 AND environment = :env
                """)
                current_max = conn.execute(max_query, {"env": environment}).fetchone()[0]
                next_id = max(start_id, (current_max or start_id)) + 1

                # 3. Store and return the new ID
                conn.execute(text("""
                    INSERT INTO lama_sequence (exchange_id, environment, metric_type, current_seq)
                    VALUES (-1, :env, :svc, :next_id)
                """), {"env": environment, "svc": service_name, "next_id": next_id})
                
                logger.info(f"✅ Assigned new Application ID {next_id} to service {service_name} in {environment}")
                return next_id
        except Exception as e:
            logger.error(f"Failed to manage dynamic Application ID for {service_name}: {e}")
            return -1

    def resync_sequence(self, exchange_id: int, environment: str, correct_seq: int, metric_type: str = "global"):
        """
        Force update THIS EXCHANGE's sequence ID.
        """
        m_type = metric_type if metric_type else "global"
        try:
            with engine.begin() as conn:
                conn.execute(text("""
                    UPDATE lama_sequence 
                    SET current_seq = :seq, last_updated = NOW()
                    WHERE exchange_id = :exch_id AND environment = :env AND metric_type = :m_type
                """), {"seq": correct_seq, "exch_id": exchange_id, "env": environment, "m_type": m_type})
                exchange_name = {1: "NSE", 2: "BSE", 4: "MCX", 5: "NCDEX"}.get(exchange_id, f"Exchange {exchange_id}")
                logger.info(f"✅ {exchange_name} {m_type.upper()} sequence resynced to {correct_seq}")
        except Exception as e:
            exchange_name = {1: "NSE", 2: "BSE", 4: "MCX", 5: "NCDEX"}.get(exchange_id, f"Exchange {exchange_id}")
            logger.error(f"Failed to resync {exchange_name} {m_type} sequence: {e}")
