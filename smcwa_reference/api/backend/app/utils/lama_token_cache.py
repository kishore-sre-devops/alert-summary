# api/backend/app/utils/lama_token_cache.py
"""
Token cache for LAMA Exchange API authentication
Caches authentication tokens to avoid repeated logins

CRITICAL: Per LAMA API Specification V1.2:
- Token validity: 24 hours (single token, not refresh token)
- Only login when token is EXPIRED or MISSING
- NO proactive refresh - only login when actually needed
- NO multiple concurrent logins for same exchange
"""

import time
import logging
import threading
import hashlib
from typing import Optional, Dict, Tuple, List
from datetime import datetime
from app.utils.lama_exchange_api import call_lama_exchange_login
from app.utils.lama_exchange import get_exchange_credentials, get_enabled_exchanges
from app.utils.token_storage import (
    store_token_in_db,
    get_token_from_db,
    delete_token_from_db,
    update_token_last_used,
    load_all_tokens_from_db
)

logger = logging.getLogger(__name__)

# Import scheduler logger functions (optional - only if scheduler_name is provided)
try:
    from app.utils.scheduler_logger import log_token_login, log_token_used, log_token_cached
except ImportError:
    # Scheduler logger not available - logging will be skipped
    log_token_login = None
    log_token_used = None
    log_token_cached = None

# In-memory token cache: {(environment, exchange_id): {"token": str, "expires_at": float}}
# CRITICAL: Per LAMA API spec the login token is issued per MEMBER (environment), not per exchange.
# We still expose per-exchange keys for backward compatibility, but the same token is shared
# across all enabled exchanges inside an environment.
_token_cache: Dict[tuple, Dict] = {}

# Lock to prevent concurrent logins for the same exchange
# CRITICAL: Prevents multiple login attempts that cause API lockout
_login_locks: Dict[tuple, threading.Lock] = {}
_lock_manager = threading.Lock()  # Lock for managing login_locks dict

# Failed login attempt tracking
# CRITICAL: Stop after 3 failed attempts to prevent reaching 5 (which causes Error 907)
# Per LAMA API spec: Account locks after 5 invalid password attempts
# We stop at 3 and set soft block (waiting for admin confirmation)
_failed_login_attempts: Dict[tuple, int] = {}  # {cache_key: consecutive_failed_count}
_failed_attempts_manager = threading.Lock()  # Lock for managing failed_login_attempts dict
MAX_FAILED_ATTEMPTS = 3  # Changed from 2 to 3 - allows 3 attempts before soft block
SOFT_BLOCK_THRESHOLD = 3  # Soft block after 3 failed attempts

# Error 907 (Password attempt Limit Exceeded) tracking
# CRITICAL: Error 907 means account is ALREADY locked BY LAMA (after 5 invalid attempts)
# NOTE: LAMA can unlock the account anytime upon request - it's NOT always 24 hours!
# Our system should:
#   1. Set a flag when Error 907 is received (to prevent hammering LAMA)
#   2. Allow admin to clear the flag from Dashboard when LAMA unlocks
#   3. Auto-clear on successful login
# Store lockout time per (environment, exchange_id): {cache_key: lockout_until_timestamp}
_error_907_lockouts: Dict[tuple, float] = {}
_error_907_lock_manager = threading.Lock()  # Lock for managing error_907_lockouts dict

# Error 907 cooldown period: 15 MINUTES (not 24 hours!)
# This is a COOLDOWN to prevent hammering LAMA, NOT the actual LAMA lockout period
# LAMA can unlock anytime - admin can clear this flag from Dashboard when LAMA is unlocked
# The 15-minute cooldown prevents:
#   1. Continuous failed login attempts that annoy LAMA
#   2. Wasting API calls when we know account is locked
# Admin can override this anytime via Dashboard "Clear Error 907" button
ERROR_907_BACKOFF_SECONDS = 15 * 60  # 15 minutes cooldown (NOT 24 hours!)

# Token expiry time (24 hours in seconds) - per LAMA API spec
TOKEN_EXPIRY_SECONDS = 24 * 60 * 60

# LONG-TERM FIX: Token expiry buffer (1 hour early) to prevent expiry during long operations
# Consider token expired 1 hour before actual expiry to prevent mid-operation failures
TOKEN_EXPIRY_BUFFER_SECONDS = 1 * 60 * 60  # 1 hour buffer

# CRITICAL: Per LAMA API spec, tokens are valid for 24 hours
# LONG-TERM FIX: We consider token expired 1 hour early to prevent expiry during operations
# NO proactive refresh - this causes multiple logins and lockouts


def _calculate_credential_hash(credentials: dict) -> str:
    """
    Calculate a hash of credentials for proactive invalidation detection.
    
    When credentials change (login_id, password, secret_key), the hash will differ
    from the stored hash, allowing us to detect the change BEFORE making an API call
    with an invalid token.
    
    Args:
        credentials: dict containing member_id, login_id, password, secret_key
        
    Returns:
        SHA256 hash (first 16 chars) of the credential combination
    """
    if not credentials:
        return ""
    
    # Combine key credential fields that affect token validity
    # If any of these change, the token generated with old credentials becomes invalid
    credential_string = "|".join([
        str(credentials.get('member_id', '')),
        str(credentials.get('login_id', '')),
        str(credentials.get('password', '')),
        str(credentials.get('secret_key', ''))
    ])
    
    # Use SHA256 and take first 16 chars for reasonable uniqueness with minimal storage
    hash_full = hashlib.sha256(credential_string.encode('utf-8')).hexdigest()
    return hash_full[:16]


def _get_current_credential_hash(environment: str) -> str:
    """
    Get credential hash for current credentials in database.
    
    Args:
        environment: 'prod' or 'uat'
        
    Returns:
        Hash of current credentials, or empty string if credentials not found
    """
    try:
        credentials = get_exchange_credentials(environment)
        if credentials:
            return _calculate_credential_hash(credentials)
    except Exception as e:
        logger.warning(f"[CREDENTIAL_HASH] Failed to get credentials for hash calculation: {e}")
    return ""


def _get_failed_attempts_count(environment: str, exchange_id: int = None) -> int:
    """
    Get current failed login attempts count for the ENVIRONMENT (not per exchange)
    
    CRITICAL FIX: LAMA counts ALL login attempts environment-wide toward the 5-attempt limit.
    Our counter must also be environment-wide to properly track and trigger soft lock at 3.
    
    Args:
        environment: 'prod' or 'uat'
        exchange_id: IGNORED - kept for backward compatibility
        
    Returns:
        Number of consecutive failed login attempts for the environment (0 if none)
    """
    # Use environment only as key (not exchange_id) - LAMA counts all attempts together
    env_key = environment
    
    with _failed_attempts_manager:
        return _failed_login_attempts.get(env_key, 0)


def _increment_failed_attempts(environment: str, exchange_id: int = None) -> int:
    """
    Increment failed login attempts count for the ENVIRONMENT (not per exchange)
    
    CRITICAL FIX: LAMA counts ALL login attempts environment-wide toward the 5-attempt limit.
    Our counter must also be environment-wide to properly track and trigger soft lock at 3.
    
    Args:
        environment: 'prod' or 'uat'
        exchange_id: IGNORED - kept for backward compatibility, logged for context
        
    Returns:
        New failed attempts count for the environment
    """
    # Use environment only as key (not exchange_id) - LAMA counts all attempts together
    env_key = environment
    exchange_name = {1: "NSE", 2: "BSE", 4: "MCX", 5: "NCDEX"}.get(exchange_id, f"Exchange {exchange_id}") if exchange_id else "N/A"
    
    with _failed_attempts_manager:
        current_count = _failed_login_attempts.get(env_key, 0)
        new_count = current_count + 1
        _failed_login_attempts[env_key] = new_count
        logger.warning(f"[FAILED_ATTEMPTS] {environment.upper()} failed attempt #{new_count} (triggered by {exchange_name})")
        return new_count


def _clear_failed_attempts(environment: str, exchange_id: int = None) -> None:
    """
    Clear failed login attempts count for the ENVIRONMENT (on successful login)
    
    CRITICAL FIX: Since counter is environment-wide, clearing it clears for all exchanges.
    
    Args:
        environment: 'prod' or 'uat'
        exchange_id: IGNORED - kept for backward compatibility, logged for context
    """
    # Use environment only as key (not exchange_id) - matches the increment function
    env_key = environment
    exchange_name = {1: "NSE", 2: "BSE", 4: "MCX", 5: "NCDEX"}.get(exchange_id, f"Exchange {exchange_id}") if exchange_id else "N/A"
    
    with _failed_attempts_manager:
        if env_key in _failed_login_attempts:
            old_count = _failed_login_attempts.pop(env_key)
            logger.info(f"[FAILED_ATTEMPTS] ✅ Cleared failed attempts counter for {environment.upper()} (was {old_count}, triggered by {exchange_name} success)")


def _get_cache_key(environment: str, exchange_id: int) -> tuple:
    """
    Get cache key for token storage
    
    Args:
        environment: 'prod' or 'uat'
        exchange_id: Exchange ID (1=NSE, 2=BSE, 4=MCX, 5=NCDEX)
        
    Returns:
        Tuple (environment, exchange_id) for use as cache key
    """
    return (environment, exchange_id)


def _get_exchange_ids_for_environment(environment: str, fallback_exchange_id: Optional[int] = None) -> List[int]:
    """
    Return the list of exchange IDs that should share the same token for an environment.
    
    CRITICAL FIX: ALWAYS return ALL 4 exchange IDs because:
    1. LAMA API returns the SAME token for ALL exchanges in an environment
    2. If we only cache for "enabled" exchanges, other exchanges will trigger duplicate logins
    3. Token sharing must be environment-wide, not exchange-specific
    
    This prevents multiple logins when different schedulers request tokens for different exchanges.
    """
    # ALWAYS cache for ALL exchanges - LAMA returns same token for all in an environment
    ALL_EXCHANGE_IDS = [1, 2, 4, 5]  # NSE, BSE, MCX, NCDEX
    return ALL_EXCHANGE_IDS


def _set_token_cache_entries(environment: str, exchange_ids: List[int], token: str, expires_at: float, credential_hash: str = None):
    """
    Populate in-memory cache entries for all provided exchanges.
    
    Args:
        environment: 'prod' or 'uat'
        exchange_ids: List of exchange IDs to cache for
        token: The authentication token
        expires_at: Token expiry timestamp
        credential_hash: Hash of credentials used to generate this token (for proactive invalidation)
    """
    # If no hash provided, calculate from current credentials
    if credential_hash is None:
        credential_hash = _get_current_credential_hash(environment)
    
    for exch in set(exchange_ids):
        cache_key = _get_cache_key(environment, exch)
        _token_cache[cache_key] = {
            "token": token,
            "expires_at": expires_at,
            "credential_hash": credential_hash  # Store hash for proactive invalidation
        }


def _clear_token_cache_entries(environment: str, exchange_ids: Optional[List[int]] = None):
    """Remove cached tokens for the provided exchanges (or entire environment)."""
    if exchange_ids:
        for exch in set(exchange_ids):
            cache_key = _get_cache_key(environment, exch)
            _token_cache.pop(cache_key, None)
    else:
        keys_to_remove = [key for key in _token_cache.keys() if key[0] == environment]
        for key in keys_to_remove:
            _token_cache.pop(key, None)


def _store_token_in_db_for_exchanges(
    environment: str,
    exchange_ids: List[int],
    token: str,
    expires_at_datetime: datetime,
    login_count: Optional[int] = None,
    credential_hash: Optional[str] = None
) -> int:
    """
    Persist the same token for every exchange in the provided list.
    
    Args:
        environment: 'prod' or 'uat'
        exchange_ids: List of exchange IDs to store token for
        token: The authentication token
        expires_at_datetime: Token expiry datetime
        login_count: Number of logins (optional)
        credential_hash: Hash of credentials used to generate token (for proactive invalidation)
    """
    # If no hash provided, calculate from current credentials
    if credential_hash is None:
        credential_hash = _get_current_credential_hash(environment)
    
    stored = 0
    for exch in set(exchange_ids):
        try:
            store_token_in_db(
                environment=environment,
                exchange_id=exch,
                token=token,
                expires_at=expires_at_datetime,
                login_count=login_count,
                credential_hash=credential_hash
            )
            stored += 1
        except Exception as e:
            logger.warning(f"[TOKEN] Failed to store token in database for {environment.upper()} exchange_id={exch}: {e}")
    return stored


def _delete_tokens_from_db_for_exchanges(environment: str, exchange_ids: Optional[List[int]] = None):
    """Delete token rows for all exchanges in the environment (or provided subset)."""
    targets = set(exchange_ids) if exchange_ids else None
    try:
        if targets is None:
            all_tokens = load_all_tokens_from_db()
            targets = {token_data['exchange_id'] for token_data in all_tokens if token_data['environment'] == environment}
            if not targets:
                # Nothing persisted for this environment yet
                return
    except Exception as e:
        logger.debug(f"[TOKEN] Failed to enumerate tokens for deletion: {e}")
        if targets is None:
            # Fall back to deleting common exchange IDs
            targets = {1, 2, 4, 5}
    for exch in targets:
        try:
            delete_token_from_db(environment, exch)
        except Exception as e:
            logger.debug(f"[TOKEN] Failed to delete token for {environment.upper()} exchange_id={exch} (non-critical): {e}")


def _is_error_907_locked_out(environment: str, exchange_id: int) -> Tuple[bool, Optional[float]]:
    """
    Check if account is locked out due to Error 907 (Password attempt Limit Exceeded)
    
    PERSISTED: Now checks both in-memory cache AND database for persistence across restarts.
    THREAD-SAFE: Fixed TOCTOU race condition with atomic checks under lock.
    
    Per LAMA API Specification V1.2:
    - Error 907: Password attempt Limit Exceeded
    - Account locks after 5 invalid password attempts
    - We implement 15-minute cooldown period when Error 907 is detected
    
    Args:
        environment: 'prod' or 'uat'
        exchange_id: Exchange ID (1=NSE, 2=BSE, 4=MCX, 5=NCDEX)
        
    Returns:
        Tuple (is_locked_out: bool, lockout_until_timestamp: Optional[float])
        - is_locked_out: True if still locked out, False if lockout expired
        - lockout_until_timestamp: Unix timestamp when lockout expires (None if not locked)
    """
    cache_key = _get_cache_key(environment, exchange_id)
    current_time = time.time()
    
    # First check in-memory cache (fast path) - THREAD SAFE atomic check under lock
    with _error_907_lock_manager:
        lockout_until = _error_907_lockouts.get(cache_key)
        
        if lockout_until is not None:
            # TOCTOU FIX: Perform expiration check while still holding the lock
            if current_time >= lockout_until:
                # Lockout expired - remove from dict atomically
                _error_907_lockouts.pop(cache_key, None)
                # Fall through to check database
            else:
                # Still locked out (in-memory) - return immediately under lock
                return True, lockout_until
    
    # If in-memory lockout expired or doesn't exist, check database for persistence
    # This is safe because we already released the lock after checking in-memory state
    try:
        from app.db.db import engine, login_lock_status_table
        from sqlalchemy import select
        
        with engine.connect() as conn:
            query = select(
                login_lock_status_table.c.error_907_locked,
                login_lock_status_table.c.error_907_locked_at
            ).where(
                login_lock_status_table.c.environment == environment,
                login_lock_status_table.c.exchange_id == exchange_id
            )
            result = conn.execute(query).fetchone()
            
            if result and result[0]:  # error_907_locked is True
                error_907_locked_at = result[1]
                if error_907_locked_at:
                    # Calculate lockout_until from locked_at timestamp
                    if isinstance(error_907_locked_at, datetime):
                        locked_at_timestamp = error_907_locked_at.timestamp()
                    else:
                        locked_at_timestamp = time.mktime(error_907_locked_at.timetuple()) if hasattr(error_907_locked_at, 'timetuple') else 0
                    
                    lockout_until = locked_at_timestamp + ERROR_907_BACKOFF_SECONDS
                    
                    # TOCTOU FIX: Re-check current time to ensure lockout is still valid
                    current_time_recheck = time.time()
                    if current_time_recheck >= lockout_until:
                        # Lockout expired - clear from database
                        _clear_error_907_in_db(environment, exchange_id)
                        return False, None
                    
                    # Still locked out - update in-memory cache atomically
                    with _error_907_lock_manager:
                        _error_907_lockouts[cache_key] = lockout_until
                    
                    logger.warning(f"[ERROR 907] ⚠️  Loaded Error 907 lockout from database for {environment.upper()}")
                    return True, lockout_until
    except Exception as e:
        logger.debug(f"[ERROR 907] Could not check database for Error 907 lockout: {e}")
    
    return False, None


def _set_error_907_in_db(environment: str, exchange_id: int) -> None:
    """Persist Error 907 lockout state to database for survival across restarts."""
    try:
        from app.db.db import engine, login_lock_status_table
        from sqlalchemy import text
        
        ALL_EXCHANGE_IDS = [1, 2, 4, 5]  # NSE, BSE, MCX, NCDEX
        
        with engine.begin() as conn:
            for exch_id in ALL_EXCHANGE_IDS:
                # UPSERT: Insert or update Error 907 state
                conn.execute(text("""
                    INSERT INTO login_lock_status (environment, exchange_id, error_907_locked, error_907_locked_at, updated_at)
                    VALUES (:env, :exch_id, TRUE, NOW(), NOW())
                    ON CONFLICT (environment, exchange_id) 
                    DO UPDATE SET error_907_locked = TRUE, error_907_locked_at = NOW(), error_907_cleared_at = NULL, updated_at = NOW()
                """), {"env": environment, "exch_id": exch_id})
        
        logger.info(f"[ERROR 907] ✅ Persisted Error 907 lockout to database for {environment.upper()} (all exchanges)")
    except Exception as e:
        logger.warning(f"[ERROR 907] Failed to persist Error 907 to database: {e}")


def _clear_error_907_in_db(environment: str, exchange_id: int) -> None:
    """Clear Error 907 lockout state from database."""
    try:
        from app.db.db import engine, login_lock_status_table
        from sqlalchemy import text
        
        ALL_EXCHANGE_IDS = [1, 2, 4, 5]  # NSE, BSE, MCX, NCDEX
        
        with engine.begin() as conn:
            for exch_id in ALL_EXCHANGE_IDS:
                conn.execute(text("""
                    UPDATE login_lock_status 
                    SET error_907_locked = FALSE, error_907_cleared_at = NOW(), updated_at = NOW()
                    WHERE environment = :env AND exchange_id = :exch_id
                """), {"env": environment, "exch_id": exch_id})
        
        logger.info(f"[ERROR 907] ✅ Cleared Error 907 lockout from database for {environment.upper()} (all exchanges)")
    except Exception as e:
        logger.debug(f"[ERROR 907] Failed to clear Error 907 from database: {e}")


def _set_error_907_lockout(environment: str, exchange_id: int) -> None:
    """
    Set Error 907 lockout for ALL exchanges in the environment
    
    PERSISTED: Now stores in both memory AND database for survival across restarts.
    
    CRITICAL FIX: LAMA login is ENVIRONMENT-wide, not exchange-specific.
    When Error 907 happens, the entire environment is locked, not just one exchange.
    We must set lockout for ALL exchanges to prevent further attempts.
    
    Called when Error 907 (Password attempt Limit Exceeded) is detected in login response.
    This prevents repeated login attempts that would keep the account locked.
    
    Args:
        environment: 'prod' or 'uat'
        exchange_id: Exchange ID that triggered the error (for logging)
    """
    ALL_EXCHANGE_IDS = [1, 2, 4, 5]  # NSE, BSE, MCX, NCDEX
    lockout_until = time.time() + ERROR_907_BACKOFF_SECONDS
    
    # Store in memory
    with _error_907_lock_manager:
        # Set lockout for ALL exchanges in this environment
        for exch_id in ALL_EXCHANGE_IDS:
            cache_key = _get_cache_key(environment, exch_id)
            _error_907_lockouts[cache_key] = lockout_until
    
    # PERSIST to database for survival across container restarts
    _set_error_907_in_db(environment, exchange_id)
    
    lockout_until_datetime = datetime.fromtimestamp(lockout_until).strftime('%Y-%m-%d %H:%M:%S UTC')
    cooldown_minutes = int(ERROR_907_BACKOFF_SECONDS / 60)
    exchange_name = {1: "NSE", 2: "BSE", 4: "MCX", 5: "NCDEX"}.get(exchange_id, f"Exchange {exchange_id}")
    logger.error(f"[ERROR 907] ⚠️  LAMA account locked for {environment.upper()} - ALL EXCHANGES (triggered by {exchange_name})")
    logger.error(f"[ERROR 907] ⚠️  Cooldown set for: NSE, BSE, MCX, NCDEX (environment-wide)")
    logger.error(f"[ERROR 907] ⚠️  Cooldown period: {cooldown_minutes} minutes (until {lockout_until_datetime})")
    logger.error(f"[ERROR 907] ⚠️  State persisted to database - survives container restart!")
    logger.error(f"[ERROR 907] ⚠️  NOTE: This is a COOLDOWN to prevent hammering LAMA, not the actual LAMA lockout!")
    logger.error(f"[ERROR 907] ⚠️  LAMA can unlock anytime upon request - contact LAMA support if needed")
    logger.error(f"[ERROR 907] ⚠️  Admin can clear this cooldown from Dashboard 'Clear Error 907' button")
    logger.error(f"[ERROR 907] ⚠️  Or wait {cooldown_minutes} minutes for automatic cooldown expiry")


def _clear_error_907_lockout(environment: str, exchange_id: int) -> None:
    """
    Clear Error 907 lockout for ALL exchanges in the environment (e.g., after successful login or admin action)
    
    PERSISTED: Clears from both memory AND database.
    
    CRITICAL FIX: Since LAMA login is environment-wide, when login succeeds,
    we clear lockout for ALL exchanges in that environment.
    
    Args:
        environment: 'prod' or 'uat'
        exchange_id: Exchange ID that triggered the clear (for logging)
    """
    ALL_EXCHANGE_IDS = [1, 2, 4, 5]  # NSE, BSE, MCX, NCDEX
    cleared = False
    
    # Clear from memory
    with _error_907_lock_manager:
        for exch_id in ALL_EXCHANGE_IDS:
            cache_key = _get_cache_key(environment, exch_id)
            if cache_key in _error_907_lockouts:
                _error_907_lockouts.pop(cache_key, None)
                cleared = True
    
    # ALWAYS clear from database (even if not in memory - may have been loaded from DB)
    _clear_error_907_in_db(environment, exchange_id)
    
    exchange_name = {1: "NSE", 2: "BSE", 4: "MCX", 5: "NCDEX"}.get(exchange_id, f"Exchange {exchange_id}")
    logger.info(f"[ERROR 907] ✅ Lockout cleared for {environment.upper()} - ALL EXCHANGES (triggered by {exchange_name})")


def is_soft_blocked(environment: str, exchange_id: int) -> bool:
    """
    Check if login is soft blocked (waiting for admin confirmation)
    
    Args:
        environment: 'prod' or 'uat'
        exchange_id: Exchange ID (1=NSE, 2=BSE, 4=MCX, 5=NCDEX)
        
    Returns:
        True if soft block is active (after 3 failed attempts)
    """
    try:
        from app.db.db import engine, login_lock_status_table
        from sqlalchemy import select
        
        with engine.connect() as conn:
            query = select(login_lock_status_table.c.soft_block).where(
                login_lock_status_table.c.environment == environment,
                login_lock_status_table.c.exchange_id == exchange_id
            )
            result = conn.execute(query).fetchone()
            
            if result:
                return result[0] is True
            
            # Also check if failed attempts >= 3 (soft block threshold)
            failed_count = _get_failed_attempts_count(environment, exchange_id)
            return failed_count >= SOFT_BLOCK_THRESHOLD
    except Exception as e:
        logger.warning(f"[SOFT_BLOCK] Error checking soft block status: {e}")
        # On error, check failed attempts count as fallback
        failed_count = _get_failed_attempts_count(environment, exchange_id)
        return failed_count >= SOFT_BLOCK_THRESHOLD


def set_soft_block(environment: str, exchange_id: int) -> None:
    """
    Set soft block for ALL exchanges in the environment after 3 failed attempts (automatic)
    
    CRITICAL FIX: Since LAMA login is environment-wide, soft block must also be
    set for ALL exchanges when triggered by any one exchange.
    
    Args:
        environment: 'prod' or 'uat'
        exchange_id: Exchange ID that triggered the soft block (for logging)
    """
    ALL_EXCHANGE_IDS = [1, 2, 4, 5]  # NSE, BSE, MCX, NCDEX
    exchange_name = {1: "NSE", 2: "BSE", 4: "MCX", 5: "NCDEX"}.get(exchange_id, f"Exchange {exchange_id}")
    
    try:
        from app.db.db import engine, login_lock_status_table
        from sqlalchemy import select, update, insert
        
        with engine.begin() as conn:
            # Set soft block for ALL exchanges in this environment
            for exch_id in ALL_EXCHANGE_IDS:
                # Check if record exists
                query = select(login_lock_status_table).where(
                    login_lock_status_table.c.environment == environment,
                    login_lock_status_table.c.exchange_id == exch_id
                )
                existing = conn.execute(query).fetchone()
                
                if existing:
                    # Update existing record
                    update_query = update(login_lock_status_table).where(
                        login_lock_status_table.c.environment == environment,
                        login_lock_status_table.c.exchange_id == exch_id
                    ).values(
                        soft_block=True,
                        soft_block_at=datetime.utcnow(),
                        updated_at=datetime.utcnow()
                    )
                    conn.execute(update_query)
                else:
                    # Insert new record
                    insert_query = insert(login_lock_status_table).values(
                        environment=environment,
                        exchange_id=exch_id,
                        soft_block=True,
                        soft_block_at=datetime.utcnow(),
                        created_at=datetime.utcnow(),
                        updated_at=datetime.utcnow()
                    )
                    conn.execute(insert_query)
            
            logger.error(f"[SOFT_BLOCK] ⚠️  Soft block activated for {environment.upper()} - ALL EXCHANGES (triggered by {exchange_name})")
            logger.error(f"[SOFT_BLOCK] ⚠️  Soft block set for: NSE, BSE, MCX, NCDEX (environment-wide)")
            logger.error(f"[SOFT_BLOCK] ⚠️  Login blocked - waiting for admin confirmation")
    except Exception as e:
        logger.error(f"[SOFT_BLOCK] Error setting soft block: {e}", exc_info=True)


def clear_soft_block(environment: str, exchange_id: int) -> None:
    """
    Clear soft block for ALL exchanges in the environment (admin unlocked, allow more attempts)
    
    CRITICAL FIX: Since soft block is set environment-wide, clearing must also be environment-wide.
    Also clears the failed attempts counter to reset the count.
    
    Args:
        environment: 'prod' or 'uat'
        exchange_id: Exchange ID that triggered the clear (for logging)
    """
    ALL_EXCHANGE_IDS = [1, 2, 4, 5]  # NSE, BSE, MCX, NCDEX
    exchange_name = {1: "NSE", 2: "BSE", 4: "MCX", 5: "NCDEX"}.get(exchange_id, f"Exchange {exchange_id}")
    
    try:
        from app.db.db import engine, login_lock_status_table
        from sqlalchemy import update
        
        with engine.begin() as conn:
            # Clear soft block for ALL exchanges in this environment
            for exch_id in ALL_EXCHANGE_IDS:
                update_query = update(login_lock_status_table).where(
                    login_lock_status_table.c.environment == environment,
                    login_lock_status_table.c.exchange_id == exch_id
                ).values(
                    soft_block=False,
                    soft_block_cleared_at=datetime.utcnow(),
                    updated_at=datetime.utcnow()
                )
                conn.execute(update_query)
            
            logger.info(f"[SOFT_BLOCK] ✅ Soft block cleared for {environment.upper()} - ALL EXCHANGES (triggered by {exchange_name})")
        
        # Also clear the failed attempts counter so we start fresh
        _clear_failed_attempts(environment, exchange_id)
        logger.info(f"[SOFT_BLOCK] ✅ Failed attempts counter reset for {environment.upper()}")
        
    except Exception as e:
        logger.warning(f"[SOFT_BLOCK] Error clearing soft block: {e}")


def is_manually_locked(environment: str, exchange_id: int) -> bool:
    """
    Check if login is manually locked (permanent lock set by admin)
    
    Args:
        environment: 'prod' or 'uat'
        exchange_id: Exchange ID (1=NSE, 2=BSE, 4=MCX, 5=NCDEX)
        
    Returns:
        True if manual lock is active
    """
    try:
        from app.db.db import engine, login_lock_status_table
        from sqlalchemy import select
        
        with engine.connect() as conn:
            query = select(login_lock_status_table.c.manual_lock).where(
                login_lock_status_table.c.environment == environment,
                login_lock_status_table.c.exchange_id == exchange_id
            )
            result = conn.execute(query).fetchone()
            
            if result:
                return result[0] is True
            
            return False
    except Exception as e:
        logger.warning(f"[MANUAL_LOCK] Error checking manual lock status: {e}")
        return False


def set_manual_lock(environment: str, exchange_id: int, user_id: int, reason: str = None) -> None:
    """
    Set permanent lock (admin action)
    
    Args:
        environment: 'prod' or 'uat'
        exchange_id: Exchange ID (1=NSE, 2=BSE, 4=MCX, 5=NCDEX)
        user_id: User ID who locked
        reason: Optional reason for lock
    """
    try:
        from app.db.db import engine, login_lock_status_table
        from sqlalchemy import select, update, insert
        
        with engine.begin() as conn:
            # Check if record exists
            query = select(login_lock_status_table).where(
                login_lock_status_table.c.environment == environment,
                login_lock_status_table.c.exchange_id == exchange_id
            )
            existing = conn.execute(query).fetchone()
            
            if existing:
                # Update existing record
                update_query = update(login_lock_status_table).where(
                    login_lock_status_table.c.environment == environment,
                    login_lock_status_table.c.exchange_id == exchange_id
                ).values(
                    manual_lock=True,
                    soft_block=False,  # Clear soft block when converting to permanent lock
                    locked_by=user_id,
                    locked_at=datetime.utcnow(),
                    reason=reason,
                    updated_at=datetime.utcnow()
                )
                conn.execute(update_query)
            else:
                # Insert new record
                insert_query = insert(login_lock_status_table).values(
                    environment=environment,
                    exchange_id=exchange_id,
                    manual_lock=True,
                    soft_block=False,
                    locked_by=user_id,
                    locked_at=datetime.utcnow(),
                    reason=reason,
                    created_at=datetime.utcnow(),
                    updated_at=datetime.utcnow()
                )
                conn.execute(insert_query)
            
            logger.error(f"[MANUAL_LOCK] 🔒 Login permanently locked for {environment.upper()} exchange_id={exchange_id} by user_id={user_id}")
            if reason:
                logger.error(f"[MANUAL_LOCK] Reason: {reason}")
    except Exception as e:
        logger.error(f"[MANUAL_LOCK] Error setting manual lock: {e}", exc_info=True)


def clear_manual_lock(environment: str, exchange_id: int) -> None:
    """
    Clear permanent lock (admin action)
    
    Args:
        environment: 'prod' or 'uat'
        exchange_id: Exchange ID (1=NSE, 2=BSE, 4=MCX, 5=NCDEX)
    """
    try:
        from app.db.db import engine, login_lock_status_table
        from sqlalchemy import update
        
        with engine.begin() as conn:
            update_query = update(login_lock_status_table).where(
                login_lock_status_table.c.environment == environment,
                login_lock_status_table.c.exchange_id == exchange_id
            ).values(
                manual_lock=False,
                unlocked_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )
            conn.execute(update_query)
            
            logger.info(f"[MANUAL_LOCK] ✅ Manual lock cleared for {environment.upper()} exchange_id={exchange_id} (admin unlocked)")
    except Exception as e:
        logger.warning(f"[MANUAL_LOCK] Error clearing manual lock: {e}")


def get_lama_exchange_token(environment: str, exchange_id: int = None, force_refresh: bool = False, scheduler_name: str = None) -> Optional[str]:
    """
    Get authentication token for LAMA Exchange API
    
    CRITICAL: Per LAMA API Specification V1.2:
    - Token validity: 24 hours (single token, not refresh token)
    - Only login when token is EXPIRED or MISSING
    - NO proactive refresh - only login when actually needed
    - NO multiple concurrent logins for same exchange (uses locking)
    
    Args:
        environment: 'prod' or 'uat'
        exchange_id: Exchange ID (1=NSE, 2=BSE, 4=MCX, 5=NCDEX)
                    If None, uses default exchange (NSE=1) for backward compatibility
        force_refresh: DEPRECATED - Only login when token is actually expired
                      This parameter is ignored to prevent multiple logins
        scheduler_name: Optional scheduler name for logging (e.g., 'Hardware-Scheduler', 'Network-Scheduler')
        
    Returns:
        Authentication token string or None if failed
    """
    if environment not in ['prod', 'uat']:
        logger.error(f"Invalid environment: {environment}")
        return None
    
    # CRITICAL FIX: Check if exchange is enabled BEFORE attempting any login
    # This prevents timeout alerts when UAT/PROD is disabled from UI
    # IMPORTANT: Block login when exchange is disabled (respects UI toggle)
    # Only proceed on exception (database error) to prevent silent blocking
    import os
    from app.utils.lama_exchange import is_exchange_enabled
    
    # Check if bypass is enabled via environment variable (for troubleshooting only)
    bypass_check = os.getenv("LAMA_BYPASS_ENABLED_CHECK", "false").lower() == "true"
    
    if not bypass_check:
        try:
            exchange_enabled = is_exchange_enabled(environment)
            if not exchange_enabled:
                logger.warning(f"[TOKEN] ⚠️  LAMA Exchange not enabled for {environment.upper()}, skipping token fetch (no login attempt)")
                logger.warning(f"[TOKEN] ⚠️  Check: Is 'enabled = TRUE' in 'lama_config' table for {environment.upper()}?")
                logger.warning(f"[TOKEN] ⚠️  Enable LAMA Exchange from UI to allow login attempts")
                return None  # ✅ Block login when disabled (respects UI toggle)
            else:
                logger.debug(f"[TOKEN] ✅ Exchange enabled check passed for {environment.upper()}")
        except Exception as e:
            logger.error(f"[TOKEN] ❌ ERROR checking exchange enabled status for {environment.upper()}: {e}", exc_info=True)
            logger.warning(f"[TOKEN] ⚠️  Exchange enabled check failed - proceeding with login attempt (may be database issue)")
            # Don't block login if check fails (database error) - proceed with login attempt
            # This prevents silent failures from blocking legitimate logins
            # But if check returns False (exchange disabled), we block (above)
    else:
        logger.info(f"[TOKEN] ⚠️  Exchange enabled check bypassed (LAMA_BYPASS_ENABLED_CHECK=true)")
    
    # Default to NSE (1) if exchange_id not provided (backward compatibility)
    if exchange_id is None:
        exchange_id = 1  # NSE
        logger.debug(f"exchange_id not provided, defaulting to NSE (1)")
    
    exchange_name = {1: "NSE", 2: "BSE", 4: "MCX", 5: "NCDEX"}.get(exchange_id, f"Exchange {exchange_id}")
    cache_key = _get_cache_key(environment, exchange_id)
    exchange_ids_for_cache = _get_exchange_ids_for_environment(environment, exchange_id)
    
    # CRITICAL: Per LAMA API spec, only login when token is EXPIRED or MISSING
    # PROACTIVE CREDENTIAL CHECK: Also check if credentials have changed
    # TOKEN PERSISTENCE: Check memory cache first, then database
    
    # Get current credential hash for comparison
    current_credential_hash = _get_current_credential_hash(environment)
    
    if cache_key in _token_cache:
        cached = _token_cache[cache_key]
        expires_at = cached.get("expires_at", 0)
        stored_credential_hash = cached.get("credential_hash", "")
        current_time = time.time()
        
        # PROACTIVE CHECK: Did credentials change since token was cached?
        # If hash differs, credentials changed → invalidate token BEFORE using it
        if current_credential_hash and stored_credential_hash and current_credential_hash != stored_credential_hash:
            logger.warning(f"[TOKEN] 🔄 CREDENTIALS CHANGED detected for {environment.upper()} {exchange_name}!")
            logger.warning(f"[TOKEN] 🔄 Stored hash: {stored_credential_hash[:8]}..., Current hash: {current_credential_hash[:8]}...")
            logger.warning(f"[TOKEN] 🔄 Invalidating cached token - will re-login with NEW credentials")
            _clear_token_cache_entries(environment, exchange_ids_for_cache)
            # Delete old token from database
            try:
                _delete_tokens_from_db_for_exchanges(environment, exchange_ids_for_cache)
            except Exception as e:
                logger.debug(f"[TOKEN] Failed to delete old token from DB (non-critical): {e}")
            # Continue to login with new credentials (don't return, fall through)
        
        # Per LAMA API spec: token valid for 24 hours
        # LONG-TERM FIX: Consider token expired 1 hour early to prevent expiry during operations
        elif cache_key in _token_cache:  # Re-check in case we just cleared it above
            effective_expires_at = expires_at - TOKEN_EXPIRY_BUFFER_SECONDS
            if effective_expires_at > current_time:
                token = cached.get("token")
                if token:
                    time_remaining = (expires_at - current_time) / 3600  # hours
                    logger.info(f"[TOKEN] ✅ Using cached token for {environment.upper()} {exchange_name} (expires in {time_remaining:.1f}h, valid until {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(expires_at))})")
                    
                    # Update last_used_at in database (non-blocking)
                    try:
                        update_token_last_used(environment, exchange_id)
                    except Exception as e:
                        logger.debug(f"[TOKEN] Failed to update last_used_at (non-critical): {e}")
                    
                    # Log token usage if scheduler_name is provided
                    # CRITICAL FIX BUG-005: Log all exceptions instead of silently ignoring
                    if scheduler_name and log_token_used:
                        try:
                            log_token_used(
                                scheduler_name=scheduler_name,
                                environment=environment,
                                exchange_id=exchange_id,
                                metric_type=None,  # Token usage is not metric-specific
                                token_preview=token[:20] + "..." if len(token) > 20 else token
                            )
                        except (ImportError, AttributeError) as e:
                            # Logging function not available - expected in some cases
                            logger.debug(f"[TOKEN] Logging not available: {e}")
                        except Exception as e:
                            # Unexpected error - log as warning (BUG-005 fix)
                            logger.warning(f"[TOKEN] Non-critical: Failed to log token usage: {e}", exc_info=True)
                    
                    return token
                else:
                    logger.warning(f"[TOKEN] Cached entry exists but no token found for {environment.upper()} {exchange_name}, clearing cache")
                    _clear_token_cache_entries(environment, exchange_ids_for_cache)
            else:
                # Token is ACTUALLY expired - clear cache and database
                logger.info(f"[TOKEN] ⚠️  Token for {environment.upper()} {exchange_name} is EXPIRED (per LAMA spec: 24h validity), will login...")
                _clear_token_cache_entries(environment, exchange_ids_for_cache)
                # Delete expired token from database
                try:
                    _delete_tokens_from_db_for_exchanges(environment, exchange_ids_for_cache)
                except Exception as e:
                    logger.debug(f"[TOKEN] Failed to delete expired token from DB (non-critical): {e}")
    else:
        # TOKEN PERSISTENCE: Check database if not in memory cache
        logger.info(f"[TOKEN] No cached token found for {environment.upper()} {exchange_name}, checking database...")
        token_data = get_token_from_db(environment, exchange_id)
        
        if token_data:
            expires_at_db = token_data['expires_at']
            if isinstance(expires_at_db, datetime):
                expires_at_timestamp = expires_at_db.timestamp()
            else:
                expires_at_timestamp = time.mktime(expires_at_db.timetuple()) if hasattr(expires_at_db, 'timetuple') else 0
            
            current_time = time.time()
            stored_credential_hash = token_data.get('credential_hash', "")
            
            # PROACTIVE CHECK: Did credentials change since token was stored in DB?
            if current_credential_hash and stored_credential_hash and current_credential_hash != stored_credential_hash:
                logger.warning(f"[TOKEN] 🔄 CREDENTIALS CHANGED detected for {environment.upper()} {exchange_name} (from database)!")
                logger.warning(f"[TOKEN] 🔄 Stored hash: {stored_credential_hash[:8]}..., Current hash: {current_credential_hash[:8]}...")
                logger.warning(f"[TOKEN] 🔄 Invalidating stored token - will re-login with NEW credentials")
                # Delete old token from database
                try:
                    _delete_tokens_from_db_for_exchanges(environment, exchange_ids_for_cache)
                except Exception as e:
                    logger.debug(f"[TOKEN] Failed to delete old token from DB (non-critical): {e}")
                # Continue to login with new credentials (don't return, fall through)
            
            # LONG-TERM FIX: Consider token expired 1 hour early
            elif expires_at_timestamp:  # Re-check in case token was just invalidated
                effective_expires_at = expires_at_timestamp - TOKEN_EXPIRY_BUFFER_SECONDS
                if effective_expires_at > current_time:
                    # Valid token from database - load into memory cache with credential hash
                    token = token_data['token']
                    _set_token_cache_entries(
                        environment=environment,
                        exchange_ids=exchange_ids_for_cache,
                        token=token,
                        expires_at=expires_at_timestamp,
                        credential_hash=stored_credential_hash or current_credential_hash
                    )
                    time_remaining = (effective_expires_at - current_time) / 3600  # hours (with buffer)
                    logger.info(f"[TOKEN] ✅ Loaded token from database for {environment.upper()} {exchange_name} (expires in {time_remaining:.1f}h, with 1h buffer)")
                    
                    # Update last_used_at
                    try:
                        update_token_last_used(environment, exchange_id)
                    except Exception as e:
                        logger.debug(f"[TOKEN] Failed to update last_used_at (non-critical): {e}")
                    
                    # Log token usage if scheduler_name is provided
                    if scheduler_name and log_token_used:
                        try:
                            log_token_used(
                                scheduler_name=scheduler_name,
                                environment=environment,
                                exchange_id=exchange_id,
                                metric_type=None,
                                token_preview=token[:20] + "..." if len(token) > 20 else token
                            )
                        except Exception as e:
                            logger.debug(f"[TOKEN] Logging not available: {e}")
                    
                    return token
                else:
                    # Token in database is expired - delete it
                    logger.info(f"[TOKEN] Token in database for {environment.upper()} {exchange_name} is EXPIRED, deleting...")
                    try:
                        _delete_tokens_from_db_for_exchanges(environment, exchange_ids_for_cache)
                    except Exception as e:
                        logger.debug(f"[TOKEN] Failed to delete expired token from DB (non-critical): {e}")
        
        logger.info(f"[TOKEN] No valid token found for {environment.upper()} {exchange_name}, will login...")
    
    # CRITICAL: Check for Error 907 lockout BEFORE attempting login
    # Per LAMA API spec: Error 907 means account is ALREADY locked (after 5 invalid attempts)
    # Account locks for 24 hours when Error 907 occurs
    is_locked_out, lockout_until = _is_error_907_locked_out(environment, exchange_id)
    if is_locked_out:
        remaining_seconds = lockout_until - time.time()
        remaining_minutes = int(remaining_seconds / 60)
        logger.error(f"[ERROR 907] ⚠️  LAMA account locked - cooldown active for {environment.upper()} {exchange_name}")
        logger.error(f"[ERROR 907] ⚠️  Cooldown: {remaining_minutes} minutes remaining")
        logger.error(f"[ERROR 907] ⚠️  Admin can clear this from Dashboard 'Clear Error 907' button")
        logger.error(f"[ERROR 907] ⚠️  Or contact LAMA support to unlock, then clear from Dashboard")
        return None  # Block login attempt - return None
    
    # CRITICAL: Check for manual lock (permanent lock set by admin)
    if is_manually_locked(environment, exchange_id):
        logger.error(f"[MANUAL_LOCK] ⚠️  Login manually locked for {environment.upper()} {exchange_name}")
        logger.error(f"[MANUAL_LOCK] ⚠️  Please unlock via UI to allow login attempts")
        return None  # Block login attempt - return None
    
    # CRITICAL: Check for soft block (after 3 failed attempts, waiting for admin)
    failed_count_early = _get_failed_attempts_count(environment, exchange_id)
    if failed_count_early >= SOFT_BLOCK_THRESHOLD:  # >= 3
        if is_soft_blocked(environment, exchange_id):
            logger.error(f"[SOFT_BLOCK] ⚠️  Login soft blocked for {environment.upper()} {exchange_name}")
            logger.error(f"[SOFT_BLOCK] ⚠️  Waiting for admin confirmation (3 failed attempts)")
            logger.error(f"[SOFT_BLOCK] ⚠️  Admin can lock permanently or unlock to allow more attempts")
            return None  # Block login attempt - return None
    
    # CRITICAL: Prevent concurrent logins for the same ENVIRONMENT
    # Lock is per ENVIRONMENT (not per exchange) to ensure only ONE login happens
    # When one scheduler logs in, it caches the token for ALL exchanges in that environment
    # This prevents multiple concurrent login attempts that cause API lockout (Error 907)
    lock_key = environment  # Lock by environment only ('uat' or 'prod')
    with _lock_manager:
        if lock_key not in _login_locks:
            _login_locks[lock_key] = threading.Lock()
        login_lock = _login_locks[lock_key]
    
    # Acquire lock to prevent concurrent logins
    # CRITICAL FIX BUG-008: Add thread identification for better debugging
    # NOTE: threading is already imported at module level, don't import again (causes UnboundLocalError)
    current_thread = threading.current_thread()
    thread_name = current_thread.name or f"Thread-{current_thread.ident}"
    thread_id = current_thread.ident
    
    lock_acquired = login_lock.acquire(blocking=False)
    if not lock_acquired:
        # Another thread is already logging in - wait and check cache again
        logger.warning(f"[TOKEN] 🔒 Another login in progress for {environment.upper()} {exchange_name}, waiting... (Thread: {thread_name}, ID: {thread_id})")
        # CRITICAL FIX: Lock timeout must be longer than login timeout (60s) + buffer (30s) = 90s
        # Login timeout is 60 seconds, so we need at least 90 seconds to wait for login to complete
        # This ensures all schedulers can wait for the first one to complete login and share the token
        lock_acquired = login_lock.acquire(blocking=True, timeout=90)  # Wait up to 90 seconds (longer than login timeout)
        if not lock_acquired:
            # Timeout occurred - could not acquire lock within 90 seconds
            # CRITICAL FIX BUG-008: Add detailed thread information
            logger.error(f"[TOKEN] ❌ Timeout waiting for login lock for {environment.upper()} {exchange_name} (waited 90 seconds)")
            logger.error(f"[TOKEN] Current thread: {thread_name} (ID: {thread_id})")
            logger.error(f"[TOKEN] Lock key: {lock_key}")
            logger.error(f"[TOKEN] Another thread may be stuck or login is taking too long (>90s). Returning None to prevent deadlock.")
            return None  # Return early - we don't hold the lock, so no cleanup needed
    
    # CRITICAL FIX BUG-001: Re-check failed attempts and locks AFTER acquiring lock
    # This prevents race condition where multiple threads pass initial check
    # Another thread may have failed or locked while we were waiting for lock
    
    # CRITICAL FIX: Re-check Error 907 lockout AFTER acquiring lock
    # Another thread may have received Error 907 and set lockout while we were waiting
    is_locked_out_recheck, lockout_until_recheck = _is_error_907_locked_out(environment, exchange_id)
    if is_locked_out_recheck:
        remaining_seconds = lockout_until_recheck - time.time()
        remaining_minutes = int(remaining_seconds / 60)
        logger.error(f"[ERROR 907] ⚠️  LAMA account locked - cooldown active (re-checked after lock)")
        logger.error(f"[ERROR 907] ⚠️  Another thread got Error 907 while we were waiting - blocking login")
        logger.error(f"[ERROR 907] ⚠️  Cooldown: {remaining_minutes} minutes remaining")
        login_lock.release()  # Release lock before returning
        return None  # Block login attempt - return None
    
    # Re-check manual lock
    if is_manually_locked(environment, exchange_id):
        logger.error(f"[MANUAL_LOCK] ⚠️  Login manually locked for {environment.upper()} {exchange_name} (re-checked after lock)")
        login_lock.release()  # Release lock before returning
        return None  # Block login attempt - return None
    
    # Re-check soft block
    failed_count = _get_failed_attempts_count(environment, exchange_id)
    if failed_count >= SOFT_BLOCK_THRESHOLD:  # >= 3
        if is_soft_blocked(environment, exchange_id):
            logger.error(f"[SOFT_BLOCK] ⚠️  Login soft blocked for {environment.upper()} {exchange_name} (re-checked after lock)")
            logger.error(f"[SOFT_BLOCK] ⚠️  Another thread may have failed while waiting for lock - blocking login")
            login_lock.release()  # Release lock before returning
            return None  # Block login attempt - return None
    
    # Now we hold the lock - don't release it yet
    
    # Check cache again after waiting (another thread may have logged in)
    if cache_key in _token_cache:
        cached = _token_cache[cache_key]
        expires_at = cached.get("expires_at", 0)
        if expires_at > time.time():
            token = cached.get("token")
            if token:
                logger.info(f"[TOKEN] ✅ Token obtained by another thread for {environment.upper()} {exchange_name} (Thread: {thread_name})")
                login_lock.release()  # Release lock before returning
                return token
    
    # TOKEN PERSISTENCE: Also check database after waiting (another thread may have stored it)
    token_data = get_token_from_db(environment, exchange_id)
    if token_data:
        expires_at_db = token_data['expires_at']
        if isinstance(expires_at_db, datetime):
            expires_at_timestamp = expires_at_db.timestamp()
        else:
            expires_at_timestamp = time.mktime(expires_at_db.timetuple()) if hasattr(expires_at_db, 'timetuple') else 0
        
        # LONG-TERM FIX: Consider token expired 1 hour early
        effective_expires_at = expires_at_timestamp - TOKEN_EXPIRY_BUFFER_SECONDS
        if effective_expires_at > time.time():
            # Valid token from database - load into memory cache
            token = token_data['token']
            _set_token_cache_entries(
                environment=environment,
                exchange_ids=exchange_ids_for_cache,
                token=token,
                expires_at=expires_at_timestamp
            )
            logger.info(f"[TOKEN] ✅ Token loaded from database by another thread for {environment.upper()} {exchange_name} (shared across {len(exchange_ids_for_cache)} exchange(s), 1h buffer)")
            login_lock.release()  # Release lock before returning
            return token
    
    # If we reach here, no token found - we still hold the lock, proceed to login below
    # At this point, we hold the lock (either acquired immediately or after waiting)
    try:
        # Get credentials
        credentials = get_exchange_credentials(environment)
        if not credentials:
            logger.warning(f"No credentials found for {environment.upper()}")
            return None
        
        # CRITICAL: Per LAMA API spec, only ONE login per ENVIRONMENT (not per exchange)
        # The login API doesn't take exchange_id - token is valid for ALL exchanges in the environment
        # Do NOT logout old token - new login will invalidate old token automatically
        logger.info(f"[TOKEN] Logging in to {environment.upper()} LAMA Exchange (triggered by {exchange_name} request, token shared for all exchanges)...")
        login_start_time = time.time()
        login_result = call_lama_exchange_login(
            environment=environment,
            member_id=credentials['member_id'],
            login_id=credentials['login_id'],
            password=credentials['password'],
            secret_key=credentials['secret_key']
        )
        login_duration_ms = int((time.time() - login_start_time) * 1000)
    
        if login_result.get("success"):
            # Extract token from response (adjust based on actual API response format)
            # Per API spec: Login provides a unique token per request, valid for 24 hours
            response_data = login_result.get("response_data", {})
            logger.info(f"[TOKEN] ✅ Login successful for {environment.upper()} (triggered by {exchange_name}), extracting token...")
            
            token = (
                response_data.get("token") or
                response_data.get("accessToken") or
                response_data.get("access_token") or
                response_data.get("authToken") or
                response_data.get("auth_token") or
                response_data.get("sessionToken") or
                response_data.get("session_token")
            )
            
            if token:
                # Cache the token per exchange
                # CRITICAL: Per API spec, token validity is 24 hours (single token, not refresh token)
                expires_at = time.time() + TOKEN_EXPIRY_SECONDS  # 24 hours
                expires_at_datetime = datetime.utcfromtimestamp(expires_at)
                
                # TOKEN PERSISTENCE: Store in both memory cache and database for ALL enabled exchanges
                _set_token_cache_entries(
                    environment=environment,
                    exchange_ids=exchange_ids_for_cache,
                    token=token,
                    expires_at=expires_at
                )
                
                try:
                    stored_count = _store_token_in_db_for_exchanges(
                        environment=environment,
                        exchange_ids=exchange_ids_for_cache,
                        token=token,
                        expires_at_datetime=expires_at_datetime
                    )
                    logger.info(f"[TOKEN] ✅ Token stored in database for {environment.upper()} ({stored_count} exchange record(s) updated))")
                except Exception as e:
                    logger.warning(f"[TOKEN] Failed to store token in database (non-critical, will retry on next access): {e}")
                
                logger.info(f"[TOKEN] ✅ Token cached for {environment.upper()} - ALL {len(exchange_ids_for_cache)} exchanges (NSE, BSE, MCX, NCDEX), expires at {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(expires_at))}")
                
                # CRITICAL: Clear failed attempts counter on successful login
                # Successful login means credentials are correct - reset counter
                _clear_failed_attempts(environment, exchange_id)
                
                # CRITICAL: Clear soft block on successful login
                # Successful login means credentials are correct - clear soft block
                clear_soft_block(environment, exchange_id)
                
                # CRITICAL: Clear Error 907 lockout on successful login
                # If account was previously locked, successful login means lockout is cleared
                _clear_error_907_lockout(environment, exchange_id)
                
                # Log token login success and caching if scheduler_name is provided
                if scheduler_name and log_token_login and log_token_cached:
                    try:
                        log_token_login(
                            scheduler_name=scheduler_name,
                            environment=environment,
                            exchange_id=exchange_id,
                            success=True,
                            token_preview=token[:20] + "..." if len(token) > 20 else token,
                            duration_ms=login_duration_ms
                        )
                        expires_in_hours = TOKEN_EXPIRY_SECONDS / 3600
                        log_token_cached(
                            scheduler_name=scheduler_name,
                            environment=environment,
                            exchange_id=exchange_id,
                            expires_in_hours=expires_in_hours
                        )
                    except (ImportError, AttributeError) as e:
                        # Logging function not available - expected in some cases
                        logger.debug(f"[TOKEN] Logging not available: {e}")
                    except Exception as e:
                        # Unexpected error - log as warning (BUG-005 fix)
                        logger.warning(f"[TOKEN] Non-critical: Failed to log token login/cache: {e}", exc_info=True)
                
                return token
            else:
                logger.error(f"[TOKEN] ❌ Login successful but NO TOKEN found in response for {environment.upper()} {exchange_name}")
                logger.error(f"[TOKEN] Response data keys: {list(response_data.keys()) if isinstance(response_data, dict) else 'Not a dict'}")
                return None
        else:
            login_message = login_result.get('message', 'Unknown error')
            login_status = login_result.get('status_code', 'Unknown')
            response_code = login_result.get('response_code')  # LAMA API responseCode (e.g., 907)
            
            # CRITICAL: Detect Error 907 (Password attempt Limit Exceeded)
            # Per LAMA API Specification V1.2: Error 907 means account is ALREADY locked (after 5 invalid attempts)
            # Account locks for 24 hours when Error 907 occurs
            if response_code == 907 or response_code == "907":
                logger.error(f"[ERROR 907] ⚠️  Password attempt Limit Exceeded for {environment.upper()} {exchange_name}")
                logger.error(f"[ERROR 907] ⚠️  LAMA has locked the account (after 5 invalid attempts)")
                logger.error(f"[ERROR 907] ⚠️  Contact LAMA support to unlock, OR wait for LAMA's lockout to expire")
                logger.error(f"[ERROR 907] ⚠️  Setting 15-minute cooldown to prevent hammering LAMA")
                _set_error_907_lockout(environment, exchange_id)
                # Clear failed attempts counter - account is already locked, no point tracking
                _clear_failed_attempts(environment, exchange_id)
            else:
                # Increment failed attempts counter
                failed_count = _increment_failed_attempts(environment, exchange_id)
                logger.error(f"[TOKEN] ❌ Failed to login to {environment.upper()} LAMA Exchange for {exchange_name}: {login_message} (HTTP {login_status}, responseCode: {response_code})")
                logger.error(f"[TOKEN] Failed attempts count: {failed_count}/{MAX_FAILED_ATTEMPTS}")
                
                # CRITICAL: Set soft block after 3 failed attempts (automatic)
                if failed_count >= SOFT_BLOCK_THRESHOLD:  # >= 3
                    set_soft_block(environment, exchange_id)
                    logger.error(f"[SOFT_BLOCK] ⚠️  Soft block activated after {failed_count} failed attempts")
                    logger.error(f"[SOFT_BLOCK] ⚠️  Login blocked - waiting for admin confirmation")
                    logger.error(f"[SOFT_BLOCK] ⚠️  Admin can lock permanently or unlock to allow more attempts")
                elif failed_count >= MAX_FAILED_ATTEMPTS:
                    # This should not happen if soft block is working correctly, but keep as safety check
                    logger.error(f"[FAILED_ATTEMPTS] ⚠️  Reached maximum failed attempts ({MAX_FAILED_ATTEMPTS})")
                    logger.error(f"[FAILED_ATTEMPTS] ⚠️  Further login attempts will be blocked to prevent account lockout")
                    logger.error(f"[FAILED_ATTEMPTS] ⚠️  Possible causes:")
                    logger.error(f"[FAILED_ATTEMPTS] ⚠️    1. Wrong secret key used for password encryption")
                    logger.error(f"[FAILED_ATTEMPTS] ⚠️    2. Password changed in LAMA Exchange but not updated in our system")
                    logger.error(f"[FAILED_ATTEMPTS] ⚠️    3. Secret key changed but password not re-encrypted")
                    logger.error(f"[FAILED_ATTEMPTS] ⚠️  Please verify credentials manually via Postman")
                else:
                    remaining_attempts = MAX_FAILED_ATTEMPTS - failed_count
                    logger.warning(f"[FAILED_ATTEMPTS] ⚠️  {remaining_attempts} attempt(s) remaining before soft block (at {SOFT_BLOCK_THRESHOLD} attempts)")
                    logger.warning(f"[TOKEN] This could indicate: invalid credentials, network issue, or API rate limiting/lockout")
            
            # Log token login failure if scheduler_name is provided
            if scheduler_name and log_token_login:
                try:
                    log_token_login(
                        scheduler_name=scheduler_name,
                        environment=environment,
                        exchange_id=exchange_id,
                        success=False,
                        error_message=f"{login_message} (HTTP {login_status})",
                        duration_ms=login_duration_ms
                    )
                except (ImportError, AttributeError) as e:
                    # Logging function not available - expected in some cases
                    logger.debug(f"[TOKEN] Logging not available: {e}")
                except Exception as e:
                    # Unexpected error - log as warning (BUG-005 fix)
                    logger.warning(f"[TOKEN] Non-critical: Failed to log token login failure: {e}", exc_info=True)
            
            # CRITICAL: Clear token cache when login fails to prevent using stale/invalid tokens
            # This ensures we don't accidentally send metrics with old expired tokens
            logger.warning(f"[TOKEN] Clearing token cache for {environment.upper()} {exchange_name} to prevent using stale/invalid tokens")
            _clear_token_cache_entries(environment, exchange_ids_for_cache)
            # TOKEN PERSISTENCE: Also delete from database
            try:
                _delete_tokens_from_db_for_exchanges(environment, exchange_ids_for_cache)
            except Exception as e:
                logger.debug(f"[TOKEN] Failed to delete token from DB (non-critical): {e}")
            
            return None
    finally:
        # Always release lock if we hold it
        # Check if we actually acquired the lock before releasing
        if lock_acquired:
            try:
                login_lock.release()
            except RuntimeError as e:
                # Lock might have been released already or wasn't acquired
                logger.warning(f"[TOKEN] Error releasing lock for {environment.upper()} {exchange_name}: {e}")


def update_token_cache(environment: str, exchange_id: int, token: str) -> bool:
    """
    Update token cache for a specific exchange from response
    
    CRITICAL: Tokens can be provided in success responses (601) from each exchange.
    This function stores the token per exchange.
    
    Args:
        environment: 'prod' or 'uat'
        exchange_id: Exchange ID (1=NSE, 2=BSE, 4=MCX, 5=NCDEX)
        token: Token string to cache
        
    Returns:
        True if token was cached, False otherwise
    """
    if environment not in ['prod', 'uat']:
        logger.error(f"Invalid environment: {environment}")
        return False
    
    if not token:
        logger.warning(f"No token provided for {environment.upper()} exchange_id={exchange_id}")
        return False
    
    exchange_name = {1: "NSE", 2: "BSE", 4: "MCX", 5: "NCDEX"}.get(exchange_id, f"Exchange {exchange_id}")
    exchange_ids = _get_exchange_ids_for_environment(environment, exchange_id)
    expires_at = time.time() + TOKEN_EXPIRY_SECONDS
    expires_at_datetime = datetime.utcfromtimestamp(expires_at)
    
    # TOKEN PERSISTENCE: Store in both memory cache and database for all enabled exchanges
    _set_token_cache_entries(
        environment=environment,
        exchange_ids=exchange_ids,
        token=token,
        expires_at=expires_at
    )
    
    try:
        stored_count = _store_token_in_db_for_exchanges(
            environment=environment,
            exchange_ids=exchange_ids,
            token=token,
            expires_at_datetime=expires_at_datetime
        )
        logger.info(f"[TOKEN] ✅ Token stored in database for {environment.upper()} ({stored_count} exchange record(s) updated) from response")
    except Exception as e:
        logger.warning(f"[TOKEN] Failed to store token in database (non-critical): {e}")
    
    logger.info(f"Token cache updated for {environment.upper()} {exchange_name} (shared across {len(exchange_ids)} exchange(s)) from response")
    return True


def clear_token_cache(environment: str = None, exchange_id: int = None):
    """
    Clear token cache for an exchange, environment, or all
    
    TOKEN PERSISTENCE: Also deletes from database
    
    Args:
        environment: 'prod' or 'uat' or None to clear all for an exchange
        exchange_id: Exchange ID (1=NSE, 2=BSE, 4=MCX, 5=NCDEX) or None to clear all for environment
    """
    if environment and exchange_id is not None:
        # Clear tokens for the provided exchange AND any other exchange sharing the same credential set
        exchange_name = {1: "NSE", 2: "BSE", 4: "MCX", 5: "NCDEX"}.get(exchange_id, f"Exchange {exchange_id}")
        exchange_ids = _get_exchange_ids_for_environment(environment, exchange_id)
        _clear_token_cache_entries(environment, exchange_ids)
        _delete_tokens_from_db_for_exchanges(environment, exchange_ids)
        logger.info(f"Cleared token cache for {environment.upper()} {exchange_name} (shared across {len(exchange_ids)} exchange(s))")
    elif environment:
        # Clear all exchanges for an environment
        _clear_token_cache_entries(environment)
        _delete_tokens_from_db_for_exchanges(environment)
        logger.info(f"Cleared token cache for all exchanges in {environment.upper()}")
    else:
        # Clear all
        _token_cache.clear()
        # TOKEN PERSISTENCE: Also delete all tokens from database
        try:
            all_tokens = load_all_tokens_from_db()
            for token_data in all_tokens:
                delete_token_from_db(token_data['environment'], token_data['exchange_id'])
        except Exception as e:
            logger.debug(f"[TOKEN] Failed to delete all tokens from DB (non-critical): {e}")
        logger.info("Cleared all token caches")


def check_token_expiration(environment: str, exchange_id: int) -> tuple[bool, float]:
    """
    Check if token is expired (per LAMA API spec: only login when expired)
    
    CRITICAL: Per LAMA API Specification V1.2:
    - Token validity: 24 hours
    - Only login when token is ACTUALLY expired (not "about to expire")
    - NO proactive refresh - this causes multiple logins and lockouts
    
    Args:
        environment: 'prod' or 'uat'
        exchange_id: Exchange ID (1=NSE, 2=BSE, 4=MCX, 5=NCDEX)
        
    Returns:
        Tuple of (needs_refresh, time_remaining_seconds)
        - needs_refresh: True ONLY if token is EXPIRED or MISSING
        - time_remaining_seconds: Seconds until token expires (0 if expired or not found)
    """
    if environment not in ['prod', 'uat']:
        return False, 0
    
    cache_key = _get_cache_key(environment, exchange_id)
    
    if cache_key not in _token_cache:
        # No token cached - needs login
        return True, 0
    
    cached = _token_cache[cache_key]
    expires_at = cached.get("expires_at", 0)
    current_time = time.time()
    
    if expires_at <= current_time:
        # Token is ACTUALLY expired - needs login
        return True, 0
    
    # Token is still valid - do NOT login
    time_remaining = expires_at - current_time
    return False, time_remaining


def logout_lama_exchange(environment: str, exchange_id: int = None) -> bool:
    """
    Logout from LAMA Exchange API and clear token cache
    
    Args:
        environment: 'prod' or 'uat'
        exchange_id: Exchange ID (1=NSE, 2=BSE, 4=MCX, 5=NCDEX) or None for all exchanges in environment
        
    Returns:
        True if logout successful, False otherwise
    """
    if environment not in ['prod', 'uat']:
        logger.error(f"Invalid environment: {environment}")
        return False
    
    # Get credentials
    credentials = get_exchange_credentials(environment)
    if not credentials:
        logger.warning(f"No credentials found for {environment.upper()}")
        return False
    
    if exchange_id is not None:
        # Logout specific exchange
        exchange_name = {1: "NSE", 2: "BSE", 4: "MCX", 5: "NCDEX"}.get(exchange_id, f"Exchange {exchange_id}")
        cache_key = _get_cache_key(environment, exchange_id)
        token = _token_cache.get(cache_key, {}).get("token")
        
        if not token:
            logger.info(f"No token found in cache for {environment.upper()} {exchange_name} - login likely failed or token expired, skipping logout API call (per LAMA API Spec: no token = no logout needed)")
            # Clear cache if exists, but don't call logout API (no token to logout)
            # Per LAMA API Spec V1.2: Logout only makes sense when there's a valid token
            clear_token_cache(environment, exchange_id)
            return True
        
        # Only call logout API if we have a valid token
        # Per LAMA API Spec V1.2: Logout requires Authorization header with valid token
        from app.utils.lama_exchange_api import call_lama_exchange_logout
        logout_result = call_lama_exchange_logout(
            environment=environment,
            member_id=credentials['member_id'],
            login_id=credentials['login_id'],
            auth_token=token
        )
        
        # Clear token cache regardless of API response (always clear after logout attempt)
        clear_token_cache(environment, exchange_id)
        
        if logout_result.get("success"):
            logger.info(f"✅ Successfully logged out from {environment.upper()} {exchange_name}")
            return True
        else:
            error_code = logout_result.get("status_code") or logout_result.get("response_code")
            error_msg = logout_result.get("message", "Unknown error")
            # Log warning but still return True (token cache cleared, which is the goal)
            logger.warning(f"⚠️ Logout API call failed for {environment.upper()} {exchange_name} (HTTP {error_code}): {error_msg}")
            logger.info(f"Token cache cleared for {environment.upper()} {exchange_name} regardless of logout API response")
            return True
    else:
        # Logout all exchanges in environment
        keys_to_remove = []
        for cache_key in list(_token_cache.keys()):
            if cache_key[0] == environment:
                token = _token_cache[cache_key].get("token")
                if token:
                    try:
                        from app.utils.lama_exchange_api import call_lama_exchange_logout
                        call_lama_exchange_logout(
                            environment=environment,
                            member_id=credentials['member_id'],
                            login_id=credentials['login_id'],
                            auth_token=token
                        )
                    except Exception as e:
                        logger.warning(f"Failed to logout token for {environment.upper()} exchange_id={cache_key[1]}: {e}")
                keys_to_remove.append(cache_key)
        
        # Clear all tokens for this environment
        clear_token_cache(environment)
        
        logger.info(f"Logged out from all exchanges in {environment.upper()}")
        return True


def check_login_lock_status(environment: str = None, exchange_id: int = None) -> Dict:
    """
    Check status of login locks - diagnostic function to detect stuck locks
    
    CRITICAL: This is a diagnostic function only. Locks are in-memory and automatically
    released when threads complete. If a lock appears stuck, it means a thread is
    actively holding it (login in progress).
    
    Args:
        environment: Optional - check specific environment, or None for all
        exchange_id: Optional - check specific exchange, or None for all
        
    Returns:
        Dict with lock status information
    """
    lock_status = {
        "total_locks": 0,
        "locks": [],
        "stuck_locks": []
    }
    
    with _lock_manager:
        lock_status["total_locks"] = len(_login_locks)
        for cache_key, lock in _login_locks.items():
            env, exch_id = cache_key
            exchange_name = {1: "NSE", 2: "BSE", 4: "MCX", 5: "NCDEX"}.get(exch_id, f"Exchange {exch_id}")
            
            # Filter by environment/exchange if specified
            if environment and env != environment:
                continue
            if exchange_id and exch_id != exchange_id:
                continue
            
            # Try to acquire lock non-blocking to check if it's held
            is_locked = not lock.acquire(blocking=False)
            if is_locked:
                # Lock is held - this is normal if login is in progress
                lock_status["locks"].append({
                    "environment": env,
                    "exchange_id": exch_id,
                    "exchange_name": exchange_name,
                    "status": "locked",
                    "note": "Lock is held (login may be in progress - this is normal)"
                })
                # If lock held for > 60 seconds, consider it potentially stuck
                lock_status["stuck_locks"].append({
                    "environment": env,
                    "exchange_id": exch_id,
                    "exchange_name": exchange_name,
                    "status": "potentially_stuck",
                    "note": "Lock held - check if login is actually in progress (>60s may indicate stuck thread)"
                })
            else:
                # Lock was acquired (wasn't locked) - release it immediately
                lock.release()
                lock_status["locks"].append({
                    "environment": env,
                    "exchange_id": exch_id,
                    "exchange_name": exchange_name,
                    "status": "unlocked",
                    "note": "Lock is available (no login in progress)"
                })
    
    return lock_status


def release_stuck_login_locks(environment: str = None, exchange_id: int = None) -> Dict:
    """
    Release potentially stuck login locks - USE WITH EXTREME CAUTION
    
    WARNING: Only use if locks are confirmed stuck and preventing login.
    Python threading.Lock() is automatically released when thread dies, but
    if a thread is stuck (not dead), the lock could remain held.
    
    This function only removes locks that are NOT currently held (unlocked locks).
    It cannot force-release locks that are actively held by threads.
    
    Args:
        environment: Optional - release locks for specific environment, or None for all
        exchange_id: Optional - release locks for specific exchange, or None for all
        
    Returns:
        Dict with release status
    """
    released = []
    
    with _lock_manager:
        locks_to_remove = []
        for cache_key, lock in _login_locks.items():
            env, exch_id = cache_key
            exchange_name = {1: "NSE", 2: "BSE", 4: "MCX", 5: "NCDEX"}.get(exch_id, f"Exchange {exch_id}")
            
            # Filter by environment/exchange if specified
            if environment and env != environment:
                continue
            if exchange_id and exch_id != exchange_id:
                continue
            
            # Try to acquire lock non-blocking
            if lock.acquire(blocking=False):
                # Lock was not held - release it and remove from dict
                lock.release()
                locks_to_remove.append(cache_key)
                released.append({
                    "environment": env,
                    "exchange_id": exch_id,
                    "exchange_name": exchange_name,
                    "status": "released",
                    "note": "Lock was not held, removed from dict"
                })
            else:
                # Lock is held - this is normal, don't force release
                logger.warning(f"[LOCK] Lock for {env.upper()} {exchange_name} is currently held - not forcing release (login may be in progress)")
                released.append({
                    "environment": env,
                    "exchange_id": exch_id,
                    "exchange_name": exchange_name,
                    "status": "held",
                    "note": "Lock is currently held (login may be in progress) - cannot force release"
                })
        
        # Remove unlocked locks from dict
        for cache_key in locks_to_remove:
            _login_locks.pop(cache_key, None)
            logger.info(f"[LOCK] Removed unused lock for {cache_key}")
    
    return {
        "released_count": len([r for r in released if r["status"] == "released"]),
        "held_count": len([r for r in released if r["status"] == "held"]),
        "details": released
    }

