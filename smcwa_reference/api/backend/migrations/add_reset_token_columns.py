"""
Database migration: Add reset_token columns to users table
Required for forgot password functionality
"""

import sys
import os
from pathlib import Path

# Add parent directory to path to import app modules
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.database import engine
from sqlalchemy import text
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def run_migration():
    """
    Add reset_token and reset_token_expiry columns to users table
    """
    try:
        with engine.connect() as conn:
            # Check if columns already exist
            result = conn.execute(text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name='users' 
                AND column_name IN ('reset_token', 'reset_token_expiry')
            """))
            existing_columns = [row[0] for row in result.fetchall()]
            
            if 'reset_token' in existing_columns and 'reset_token_expiry' in existing_columns:
                logger.info("✓ Columns reset_token and reset_token_expiry already exist in users table")
                return True
            
            # Add reset_token column if not exists
            if 'reset_token' not in existing_columns:
                logger.info("Adding reset_token column to users table...")
                conn.execute(text("""
                    ALTER TABLE users 
                    ADD COLUMN reset_token VARCHAR(100)
                """))
                logger.info("✓ Added reset_token column")
            
            # Add reset_token_expiry column if not exists
            if 'reset_token_expiry' not in existing_columns:
                logger.info("Adding reset_token_expiry column to users table...")
                conn.execute(text("""
                    ALTER TABLE users 
                    ADD COLUMN reset_token_expiry TIMESTAMP
                """))
                logger.info("✓ Added reset_token_expiry column")
            
            conn.commit()
            logger.info("✓ Migration completed successfully!")
            return True
            
    except Exception as e:
        logger.error(f"✗ Migration failed: {e}")
        return False

def rollback_migration():
    """
    Remove reset_token columns from users table
    """
    try:
        with engine.connect() as conn:
            # Check if columns exist
            result = conn.execute(text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name='users' 
                AND column_name IN ('reset_token', 'reset_token_expiry')
            """))
            existing_columns = [row[0] for row in result.fetchall()]
            
            if not existing_columns:
                logger.info("✓ Columns do not exist, nothing to rollback")
                return True
            
            # Drop columns if they exist
            if 'reset_token' in existing_columns:
                logger.info("Removing reset_token column from users table...")
                conn.execute(text("""
                    ALTER TABLE users 
                    DROP COLUMN reset_token
                """))
                logger.info("✓ Removed reset_token column")
            
            if 'reset_token_expiry' in existing_columns:
                logger.info("Removing reset_token_expiry column from users table...")
                conn.execute(text("""
                    ALTER TABLE users 
                    DROP COLUMN reset_token_expiry
                """))
                logger.info("✓ Removed reset_token_expiry column")
            
            conn.commit()
            logger.info("✓ Rollback completed successfully!")
            return True
            
    except Exception as e:
        logger.error(f"✗ Rollback failed: {e}")
        return False

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Database migration for forgot password feature')
    parser.add_argument('action', choices=['migrate', 'rollback'], 
                       help='Action to perform: migrate (add columns) or rollback (remove columns)')
    
    args = parser.parse_args()
    
    if args.action == 'migrate':
        success = run_migration()
    else:
        success = rollback_migration()
    
    sys.exit(0 if success else 1)
