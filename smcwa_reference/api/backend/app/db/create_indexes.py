# api/backend/app/db/create_indexes.py
"""
Database index creation script for performance optimization
Creates indexes on frequently queried columns for fast data retrieval
"""

import os
from sqlalchemy import create_engine, text
import urllib.parse
import logging

logger = logging.getLogger(__name__)

# Import engine from db.py to use same connection
from app.db.db import engine


def create_performance_indexes(engine):
    """
    Create indexes on frequently queried columns for performance optimization
    
    Args:
        engine: SQLAlchemy engine instance from db.py
    """
    indexes = [
        # Server Metrics - CRITICAL for Dashboard Performance
        {
            "name": "idx_server_metrics_lookup",
            "table": "server_metrics",
            "columns": "(server_id, metric_name, ts DESC)",
            "description": "Composite index for fast retrieval of latest metrics per server"
        },
        # Exchange transactions table - CRITICAL for Exchange Activity Dashboard
        {
            "name": "idx_exchange_transactions_sent_at",
            "table": "exchange_transactions",
            "columns": "(sent_at)",
            "description": "Index on sent_at for fast time range queries"
        },
        {
            "name": "idx_exchange_transactions_env_sent_at",
            "table": "exchange_transactions",
            "columns": "(environment, sent_at DESC)",
            "description": "Composite index for environment + time range queries (most common pattern)"
        },
        {
            "name": "idx_exchange_transactions_env_metric",
            "table": "exchange_transactions",
            "columns": "(environment, metric_type)",
            "description": "Composite index for environment + metric_type filtering"
        },
        {
            "name": "idx_exchange_transactions_env_status",
            "table": "exchange_transactions",
            "columns": "(environment, status)",
            "description": "Composite index for environment + status filtering"
        },
        {
            "name": "idx_exchange_transactions_server_id",
            "table": "exchange_transactions",
            "columns": "(server_id)",
            "description": "Index on server_id for server-specific queries"
        },
        # JSON GIN index for fast exchange_id extraction from metrics_sent
        {
            "name": "idx_exchange_transactions_metrics_sent_gin",
            "table": "exchange_transactions",
            # Cast to jsonb for GIN operator classes; JSON lacks default GIN opclass
            "columns": "USING GIN ((metrics_sent::jsonb))",
            "description": "GIN index on metrics_sent (cast to jsonb) for fast exchange_id extraction"
        },
        
        # Scheduler logs table - for Scheduler Logs Dashboard
        {
            "name": "idx_scheduler_logs_env_timestamp",
            "table": "scheduler_logs",
            "columns": "(environment, created_at DESC)",
            "description": "Composite index for environment + time range queries"
        },
        {
            "name": "idx_scheduler_logs_scheduler_env",
            "table": "scheduler_logs",
            "columns": "(scheduler_name, environment, created_at DESC)",
            "description": "Composite index for scheduler + environment + time queries"
        },
        {
            "name": "idx_scheduler_logs_exchange_env",
            "table": "scheduler_logs",
            "columns": "(exchange_id, environment, created_at DESC)",
            "description": "Composite index for exchange + environment + time queries"
        },
        
        # Exchange connectivity errors table
        {
            "name": "idx_exchange_connectivity_errors_timestamp",
            "table": "exchange_connectivity_errors",
            "columns": "(sent_at)",
            "description": "Index on sent_at for fast time range queries",
            "optional": True  # Table may not exist yet
        },
        {
            "name": "idx_exchange_connectivity_errors_env_sent_at",
            "table": "exchange_connectivity_errors",
            "columns": "(environment, sent_at DESC)",
            "description": "Composite index for environment + time range queries",
            "optional": True
        },
        
        # Metric queue table - PHASE 1 ERROR-PROOF IMPLEMENTATION
        {
            "name": "idx_metric_queue_status_next_retry",
            "table": "metric_queue",
            "columns": "(status, next_retry_at) WHERE status = 'failed'",
            "description": "Partial index for fast retrieval of failed metrics ready for retry"
        },
        {
            "name": "idx_metric_queue_env_status",
            "table": "metric_queue",
            "columns": "(environment, status, created_at)",
            "description": "Composite index for environment + status queries"
        },
        {
            "name": "idx_metric_queue_scheduler_env",
            "table": "metric_queue",
            "columns": "(scheduler_name, environment, status)",
            "description": "Composite index for scheduler + environment queries"
        },
        {
            "name": "idx_metric_queue_created_at",
            "table": "metric_queue",
            "columns": "(created_at)",
            "description": "Index on created_at for cleanup queries"
        },
        # LAMA tokens table - TOKEN PERSISTENCE IMPLEMENTATION
        {
            "name": "idx_lama_tokens_env_exchange",
            "table": "lama_tokens",
            "columns": "(environment, exchange_id)",
            "description": "Composite index for fast token lookup by environment and exchange"
        },
        {
            "name": "idx_lama_tokens_expires_at",
            "table": "lama_tokens",
            "columns": "(expires_at)",
            "description": "Index on expires_at for expiry checks and cleanup"
        },
        {
            "name": "idx_lama_tokens_status",
            "table": "lama_tokens",
            "columns": "(status)",
            "description": "Index on status for filtering active/expired tokens"
        },
        # Sequence ID reservations table - LONG-TERM FIX
        {
            "name": "idx_seq_reservations_env_exchange_metric",
            "table": "sequence_id_reservations",
            "columns": "(environment, member_id, exchange_id, metric_type)",
            "description": "Composite index for fast lookup of reservations by context"
        },
        {
            "name": "idx_seq_reservations_status_expires",
            "table": "sequence_id_reservations",
            "columns": "(reservation_status, expires_at)",
            "description": "Index for cleanup of expired reservations"
        },
        {
            "name": "idx_seq_reservations_sequence_id",
            "table": "sequence_id_reservations",
            "columns": "(sequence_id)",
            "description": "Index on sequence_id for fast reservation checks"
        },
        # Component health table - Self-healing control plane
        {
            "name": "idx_component_health_component_env",
            "table": "component_health",
            "columns": "(component_name, environment)",
            "description": "Composite index for querying component health per environment"
        },
        {
            "name": "idx_component_health_updated_at",
            "table": "component_health",
            "columns": "(updated_at DESC)",
            "description": "Index on updated_at for retrieving latest health snapshots"
        },
    ]
    
    created_count = 0
    skipped_count = 0
    error_count = 0
    
    # Process each index independently - use fresh connection and simple approach
    # All columns already have parentheses in index definitions to avoid any parsing issues
    for index_def in indexes:
        index_name = index_def["name"]
        table_name = index_def["table"]
        columns = index_def["columns"]  # Already includes parentheses
        is_optional = index_def.get("optional", False)
        
        try:
            # Use a completely fresh transaction for each index
            with engine.begin() as conn:
                # For optional indexes, check if table exists first
                if is_optional:
                    try:
                        table_exists = conn.execute(
                            text("SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_schema = 'public' AND table_name = :table_name)"),
                            {"table_name": table_name}
                        ).scalar()
                        
                        if not table_exists:
                            logger.info(f"Skipping index {index_name} - table {table_name} does not exist")
                            skipped_count += 1
                            continue
                    except Exception:
                        # If check fails, skip this index
                        skipped_count += 1
                        continue
                
                # Create index - columns already have parentheses, use directly
                sql = f"CREATE INDEX IF NOT EXISTS {index_name} ON {table_name} {columns}"
                logger.info(f"Creating index {index_name} on {table_name}...")
                logger.info(f"[DEBUG] SQL: {sql}")  # Debug logging
                conn.execute(text(sql))
                # Transaction auto-commits on successful exit
                
                logger.info(f"✅ Created index {index_name}")
                created_count += 1
                
        except Exception as e:
            error_count += 1
            error_msg = str(e).lower()
            # If index already exists, that's not really an error
            if "already exists" in error_msg or "duplicate" in error_msg:
                logger.info(f"Index {index_name} already exists - skipping")
                skipped_count += 1
                error_count -= 1  # Don't count as error
            elif is_optional:
                logger.warning(f"⚠️  Could not create optional index {index_name}: {e}")
            else:
                logger.error(f"❌ Error creating index {index_name}: {e}")
    
    logger.info(f"Index creation complete: {created_count} created, {skipped_count} skipped, {error_count} errors")
    return {
        "created": created_count,
        "skipped": skipped_count,
        "errors": error_count
    }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("Creating database performance indexes...")
    result = create_performance_indexes(engine)
    print(f"✅ Index creation complete: {result}")
