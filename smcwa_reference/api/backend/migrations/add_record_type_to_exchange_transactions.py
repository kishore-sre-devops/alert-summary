"""
Database migration: Add record_type to exchange_transactions table
Required to prevent 704 hint pollution of sequence_id counters.
"""

import sys
import os
from pathlib import Path

# Add parent directory to path to import app modules
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db.db import engine
from sqlalchemy import text
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def run_migration():
    logger.info("Starting migration: add_record_type_to_exchange_transactions")
    
    try:
        with engine.begin() as conn:
            # Check if column already exists
            result = conn.execute(text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name='exchange_transactions' AND column_name='record_type'
            """)).fetchall()
            
            if not result:
                logger.info("Adding record_type column to exchange_transactions table...")
                conn.execute(text("""
                    ALTER TABLE exchange_transactions 
                    ADD COLUMN record_type VARCHAR(50) DEFAULT 'sent'
                """))
                logger.info("Successfully added record_type column.")
            else:
                logger.info("record_type column already exists.")
                
    except Exception as e:
        logger.error(f"Migration failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    run_migration()
