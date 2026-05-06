# api/backend/app/utils/token_storage.py
"""
Token storage functions for database persistence
Stores and retrieves LAMA Exchange API tokens from database
"""

import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, List
from sqlalchemy import select, update, delete, text
from app.db.db import engine, lama_tokens_table

logger = logging.getLogger(__name__)


def store_token_in_db(
    environment: str,
    exchange_id: int,
    token: str,
    expires_at: datetime,
    login_count: Optional[int] = None,
    credential_hash: Optional[str] = None,
    max_retries: int = 3
) -> bool:
    """
    Store or update token in database using UPSERT (atomic operation)
    
    LONG-TERM FIX: Uses PostgreSQL UPSERT to prevent race conditions
    
    Args:
        environment: 'uat' or 'prod'
        exchange_id: Exchange ID (1=NSE, 2=BSE, 4=MCX, 5=NCDEX)
        token: Token string from LAMA API
        expires_at: Token expiry datetime (as datetime object)
        login_count: Number of times logged in (default: 1)
        credential_hash: Hash of credentials used to generate token (for proactive invalidation)
        max_retries: Maximum retry attempts (default: 3)
        
    Returns:
        True if successful, False otherwise
    """
    import time
    
    # Ensure expires_at is a datetime object
    if isinstance(expires_at, (int, float)):
        # Convert Unix timestamp to datetime
        expires_at = datetime.utcfromtimestamp(expires_at)
    
    resolved_login_count = login_count or 1
    
    for attempt in range(max_retries):
        try:
            with engine.begin() as conn:
                # Use PostgreSQL UPSERT (INSERT ON CONFLICT DO UPDATE)
                # This is atomic and prevents race conditions
                upsert_sql = text("""
                    INSERT INTO lama_tokens (environment, exchange_id, token, expires_at, login_count, status, credential_hash, created_at, updated_at)
                    VALUES (:environment, :exchange_id, :token, :expires_at, :login_count, 'active', :credential_hash, NOW(), NOW())
                    ON CONFLICT (environment, exchange_id) 
                    DO UPDATE SET 
                        token = EXCLUDED.token,
                        expires_at = EXCLUDED.expires_at,
                        login_count = COALESCE(lama_tokens.login_count, 0) + 1,
                        status = 'active',
                        credential_hash = EXCLUDED.credential_hash,
                        updated_at = NOW(),
                        last_used_at = NULL
                """)
                
                conn.execute(upsert_sql, {
                    'environment': environment,
                    'exchange_id': exchange_id,
                    'token': token,
                    'expires_at': expires_at,
                    'login_count': resolved_login_count,
                    'credential_hash': credential_hash
                })
                
                logger.debug(f"[TOKEN_STORAGE] ✅ Token stored/updated for {environment.upper()} Exchange {exchange_id} (atomic UPSERT)")
                return True
                
        except Exception as e:
            if attempt < max_retries - 1:
                # Exponential backoff: 1s, 2s, 4s
                wait_seconds = 2 ** attempt
                logger.warning(
                    f"[TOKEN_STORAGE] Failed to store token (attempt {attempt + 1}/{max_retries}) for "
                    f"{environment.upper()} Exchange {exchange_id}: {e}. Retrying in {wait_seconds}s..."
                )
                time.sleep(wait_seconds)
            else:
                # Last attempt failed
                logger.error(
                    f"[TOKEN_STORAGE] ❌ Failed to store token after {max_retries} attempts for "
                    f"{environment.upper()} Exchange {exchange_id}: {e}",
                    exc_info=True
                )
                return False
    
    return False


def get_token_from_db(environment: str, exchange_id: int) -> Optional[Dict]:
    """
    Get token from database
    
    Args:
        environment: 'uat' or 'prod'
        exchange_id: Exchange ID (1=NSE, 2=BSE, 4=MCX, 5=NCDEX)
        
    Returns:
        Dict with token data or None if not found
    """
    try:
        with engine.connect() as conn:
            query = select(lama_tokens_table).where(
                lama_tokens_table.c.environment == environment,
                lama_tokens_table.c.exchange_id == exchange_id
            )
            result = conn.execute(query).fetchone()
            
            if result:
                # Column order: id, environment, exchange_id, token, expires_at, created_at, updated_at, last_used_at, login_count, status, credential_hash
                return {
                    'id': result[0],
                    'environment': result[1],
                    'exchange_id': result[2],
                    'token': result[3],
                    'expires_at': result[4],
                    'created_at': result[5],
                    'updated_at': result[6],
                    'last_used_at': result[7],
                    'login_count': result[8],
                    'status': result[9],
                    'credential_hash': result[10] if len(result) > 10 else None  # credential_hash column (may not exist in older DBs)
                }
            return None
    except Exception as e:
        logger.error(f"[TOKEN_STORAGE] Failed to get token for {environment.upper()} Exchange {exchange_id}: {e}", exc_info=True)
        return None


def delete_token_from_db(environment: str, exchange_id: int) -> bool:
    """
    Delete token from database
    
    Args:
        environment: 'uat' or 'prod'
        exchange_id: Exchange ID (1=NSE, 2=BSE, 4=MCX, 5=NCDEX)
        
    Returns:
        True if successful, False otherwise
    """
    try:
        with engine.begin() as conn:
            delete_query = delete(lama_tokens_table).where(
                lama_tokens_table.c.environment == environment,
                lama_tokens_table.c.exchange_id == exchange_id
            )
            result = conn.execute(delete_query)
            if result.rowcount > 0:
                logger.debug(f"[TOKEN_STORAGE] Deleted token for {environment.upper()} Exchange {exchange_id} from database")
                return True
            else:
                logger.debug(f"[TOKEN_STORAGE] No token found to delete for {environment.upper()} Exchange {exchange_id}")
                return False
    except Exception as e:
        logger.error(f"[TOKEN_STORAGE] Failed to delete token for {environment.upper()} Exchange {exchange_id}: {e}", exc_info=True)
        return False


def load_all_tokens_from_db() -> List[Dict]:
    """
    Load all tokens from database
    
    Returns:
        List of token dictionaries
    """
    try:
        with engine.connect() as conn:
            query = select(lama_tokens_table)
            results = conn.execute(query).fetchall()
            
            tokens = []
            for result in results:
                # Column order: id, environment, exchange_id, token, expires_at, created_at, updated_at, last_used_at, login_count, status, credential_hash
                tokens.append({
                    'id': result[0],
                    'environment': result[1],
                    'exchange_id': result[2],
                    'token': result[3],
                    'expires_at': result[4],
                    'created_at': result[5],
                    'updated_at': result[6],
                    'last_used_at': result[7],
                    'login_count': result[8],
                    'status': result[9],
                    'credential_hash': result[10] if len(result) > 10 else None  # credential_hash column (may not exist in older DBs)
                })
            return tokens
    except Exception as e:
        logger.error(f"[TOKEN_STORAGE] Failed to load all tokens: {e}", exc_info=True)
        return []


def update_token_status(environment: str, exchange_id: int, status: str) -> bool:
    """
    Update token status in database
    
    Args:
        environment: 'uat' or 'prod'
        exchange_id: Exchange ID (1=NSE, 2=BSE, 4=MCX, 5=NCDEX)
        status: 'active', 'expired', or 'invalid'
        
    Returns:
        True if successful, False otherwise
    """
    try:
        with engine.begin() as conn:
            update_query = update(lama_tokens_table).where(
                lama_tokens_table.c.environment == environment,
                lama_tokens_table.c.exchange_id == exchange_id
            ).values(
                status=status,
                updated_at=datetime.utcnow()
            )
            conn.execute(update_query)
            logger.debug(f"[TOKEN_STORAGE] Updated token status to '{status}' for {environment.upper()} Exchange {exchange_id}")
            return True
    except Exception as e:
        logger.error(f"[TOKEN_STORAGE] Failed to update token status for {environment.upper()} Exchange {exchange_id}: {e}", exc_info=True)
        return False


def update_token_last_used(environment: str, exchange_id: int) -> bool:
    """
    Update last_used_at timestamp for token
    
    Args:
        environment: 'uat' or 'prod'
        exchange_id: Exchange ID (1=NSE, 2=BSE, 4=MCX, 5=NCDEX)
        
    Returns:
        True if successful, False otherwise
    """
    try:
        with engine.begin() as conn:
            update_query = update(lama_tokens_table).where(
                lama_tokens_table.c.environment == environment,
                lama_tokens_table.c.exchange_id == exchange_id
            ).values(
                last_used_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )
            conn.execute(update_query)
            return True
    except Exception as e:
        logger.debug(f"[TOKEN_STORAGE] Failed to update last_used_at for {environment.upper()} Exchange {exchange_id}: {e}")
        return False


def delete_expired_tokens_from_db(older_than_hours: int = 1) -> int:
    """
    Delete expired tokens older than specified hours
    
    Args:
        older_than_hours: Delete tokens expired more than this many hours ago (default: 1)
        
    Returns:
        Number of tokens deleted
    """
    try:
        cutoff_time = datetime.utcnow() - timedelta(hours=older_than_hours)
        with engine.begin() as conn:
            delete_query = delete(lama_tokens_table).where(
                lama_tokens_table.c.expires_at < cutoff_time
            )
            result = conn.execute(delete_query)
            deleted_count = result.rowcount
            if deleted_count > 0:
                logger.info(f"[TOKEN_STORAGE] Deleted {deleted_count} expired token(s) older than {older_than_hours} hour(s)")
            return deleted_count
    except Exception as e:
        logger.error(f"[TOKEN_STORAGE] Failed to delete expired tokens: {e}", exc_info=True)
        return 0

