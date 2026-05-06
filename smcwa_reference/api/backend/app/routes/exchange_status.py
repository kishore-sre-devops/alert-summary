# api/backend/app/routes/exchange_status.py
"""
Exchange login status and lock/unlock endpoints
Provides status information and allows admin to lock/unlock login attempts
"""

from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.db.db import get_db, engine, login_lock_status_table
from app.utils.permissions import require_admin
from app.utils.lama_token_cache import (
    _get_failed_attempts_count,
    _is_error_907_locked_out,
    is_soft_blocked,
    is_manually_locked
)
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

router = APIRouter()

class LoginLockRequest(BaseModel):
    environment: str  # 'prod' or 'uat'
    exchange_id: int = None  # Optional, NULL = all exchanges for environment
    action: str  # 'lock_permanently', 'unlock_soft_block', or 'unlock_manual'
    reason: str = None  # Optional reason for lock

@router.get("/login-status")
def get_login_status(
    environment: str = None,
    exchange_id: int = None,
    request: Request = None,
    db: Session = Depends(get_db)
):
    """
    Get failed attempts and lock status for all environments/exchanges
    
    Query Parameters:
    - environment (optional): Filter by 'uat' or 'prod'
    - exchange_id (optional): Filter by exchange ID (1, 2, 4, 5)
    
    Returns status for all environments/exchanges if no filters provided
    """
    try:
        exchange_names = {1: "NSE", 2: "BSE", 4: "MCX", 5: "NCDEX"}
        environments_to_check = ['uat', 'prod']
        
        if environment and environment != 'all':
            if environment not in ['uat', 'prod']:
                raise HTTPException(status_code=400, detail="Environment must be 'uat', 'prod', or 'all'")
            environments_to_check = [environment]
        
        result = {
            "status": "ok",
            "environments": {}
        }
        
        with engine.connect() as conn:
            for env in environments_to_check:
                result["environments"][env] = {}
                
                # Get enabled exchanges for this environment
                exchange_ids_to_check = [1, 2, 4, 5]  # All possible exchanges
                if exchange_id:
                    exchange_ids_to_check = [exchange_id]
                
                for exch_id in exchange_ids_to_check:
                    # Get failed attempts count (in-memory, but _is_error_907_locked_out now also checks DB)
                    failed_attempts = _get_failed_attempts_count(env, exch_id)
                    
                    # Get Error 907 lockout status (now checks both memory AND database)
                    is_error_907_locked, error_907_lockout_until = _is_error_907_locked_out(env, exch_id)
                    
                    # Also check database directly for Error 907 (in case in-memory check failed)
                    if not is_error_907_locked:
                        try:
                            db_query = select(
                                login_lock_status_table.c.error_907_locked,
                                login_lock_status_table.c.error_907_locked_at
                            ).where(
                                login_lock_status_table.c.environment == env,
                                login_lock_status_table.c.exchange_id == exch_id
                            )
                            db_result = conn.execute(db_query).fetchone()
                            if db_result and db_result[0]:  # error_907_locked is True in DB
                                is_error_907_locked = True
                                if db_result[1]:  # error_907_locked_at
                                    from app.utils.lama_token_cache import ERROR_907_BACKOFF_SECONDS
                                    import time
                                    if isinstance(db_result[1], datetime):
                                        locked_at_ts = db_result[1].timestamp()
                                    else:
                                        locked_at_ts = time.mktime(db_result[1].timetuple()) if hasattr(db_result[1], 'timetuple') else 0
                                    error_907_lockout_until = locked_at_ts + ERROR_907_BACKOFF_SECONDS
                        except Exception as e:
                            logger.debug(f"Error checking Error 907 from DB: {e}")
                    
                    # Get soft block status from database
                    query = select(login_lock_status_table).where(
                        login_lock_status_table.c.environment == env,
                        login_lock_status_table.c.exchange_id == exch_id
                    )
                    lock_status = conn.execute(query).fetchone()
                    
                    is_soft_block = False
                    soft_blocked_at = None
                    is_manual_lock = False
                    locked_at = None
                    locked_by = None
                    reason_text = None
                    
                    if lock_status:
                        is_soft_block = lock_status[3] if len(lock_status) > 3 else False  # soft_block column
                        soft_blocked_at = lock_status[4] if len(lock_status) > 4 else None  # soft_block_at
                        is_manual_lock = lock_status[6] if len(lock_status) > 6 else False  # manual_lock
                        locked_at = lock_status[8] if len(lock_status) > 8 else None  # locked_at
                        locked_by = lock_status[7] if len(lock_status) > 7 else None  # locked_by
                        reason_text = lock_status[9] if len(lock_status) > 9 else None  # reason
                    
                    # Also check if soft block should be active (failed attempts >= 3)
                    if failed_attempts >= 3:
                        # Check if soft block is set in database, if not, it should be set
                        if not is_soft_block:
                            # Soft block should be active but not in DB - this is a race condition
                            # Return status as if soft block is active
                            is_soft_block = True
                    
                    # Determine status
                    if is_error_907_locked:
                        status = "error_907_locked"
                    elif is_manual_lock:
                        status = "manually_locked"
                    elif is_soft_block:
                        status = "soft_blocked"
                    else:
                        status = "normal"
                    
                    # Format error_907_lockout_until (it's a timestamp, not datetime)
                    error_907_lockout_until_iso = None
                    if error_907_lockout_until:
                        try:
                            error_907_lockout_until_iso = datetime.fromtimestamp(error_907_lockout_until).isoformat()
                        except:
                            error_907_lockout_until_iso = None
                    
                    result["environments"][env][str(exch_id)] = {
                        "failed_attempts": failed_attempts,
                        "max_attempts": 3,
                        "is_soft_blocked": is_soft_block,
                        "soft_blocked_at": soft_blocked_at.isoformat() if soft_blocked_at else None,
                        "is_manually_locked": is_manual_lock,
                        "locked_at": locked_at.isoformat() if locked_at else None,
                        "locked_by": locked_by,
                        "is_error_907_locked": is_error_907_locked,
                        "error_907_lockout_until": error_907_lockout_until_iso,
                        "reason": reason_text,
                        "status": status,
                        "exchange_name": exchange_names.get(exch_id, f"Exchange {exch_id}")
                    }
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting login status: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error getting login status: {str(e)}")


@router.post("/login-lock")
def lock_unlock_login(
    lock_request: LoginLockRequest,
    request: Request = None,
    db: Session = Depends(get_db)
):
    """
    Lock or unlock login attempts (admin only)
    
    Actions:
    - 'lock_permanently': Convert soft block to permanent lock
    - 'unlock_soft_block': Clear soft block, allow more attempts
    - 'unlock_manual': Clear permanent lock
    - 'clear_error_907': Clear Error 907 cooldown (use when LAMA unlocks the account)
    """
    try:
        # Require admin role (raises exception if not admin)
        user = require_admin(request)
        user_id = user.get('user_id') if user else None
        
        if not user_id:
            raise HTTPException(status_code=401, detail="Authentication required")
        
        environment = lock_request.environment
        if environment not in ['uat', 'prod']:
            raise HTTPException(status_code=400, detail="Environment must be 'uat' or 'prod'")
        
        action = lock_request.action
        if action not in ['lock_permanently', 'unlock_soft_block', 'unlock_manual', 'clear_error_907']:
            raise HTTPException(status_code=400, detail="Action must be 'lock_permanently', 'unlock_soft_block', 'unlock_manual', or 'clear_error_907'")
        
        exchange_id = lock_request.exchange_id
        exchange_names = {1: "NSE", 2: "BSE", 4: "MCX", 5: "NCDEX"}
        exchange_name = exchange_names.get(exchange_id, f"Exchange {exchange_id}") if exchange_id else "All Exchanges"
        
        from app.utils.lama_token_cache import (
            set_manual_lock,
            clear_manual_lock,
            clear_soft_block,
            _clear_error_907_lockout
        )
        
        if action == 'lock_permanently':
            if exchange_id:
                set_manual_lock(environment, exchange_id, user_id, lock_request.reason)
                message = f"Login permanently locked for {environment.upper()} exchange {exchange_name}"
            else:
                # Lock all exchanges for this environment
                for exch_id in [1, 2, 4, 5]:
                    set_manual_lock(environment, exch_id, user_id, lock_request.reason)
                message = f"Login permanently locked for {environment.upper()} (all exchanges)"
            
            return {
                "status": "ok",
                "message": message,
                "environment": environment,
                "exchange_id": exchange_id,
                "is_locked": True,
                "locked_at": datetime.utcnow().isoformat(),
                "locked_by": user_id
            }
        
        elif action == 'unlock_soft_block':
            if exchange_id:
                clear_soft_block(environment, exchange_id)
                message = f"Soft block cleared for {environment.upper()} exchange {exchange_name}"
            else:
                # Clear soft block for all exchanges
                for exch_id in [1, 2, 4, 5]:
                    clear_soft_block(environment, exch_id)
                message = f"Soft block cleared for {environment.upper()} (all exchanges)"
            
            return {
                "status": "ok",
                "message": message,
                "environment": environment,
                "exchange_id": exchange_id,
                "is_locked": False
            }
        
        elif action == 'unlock_manual':
            if exchange_id:
                clear_manual_lock(environment, exchange_id)
                message = f"Manual lock cleared for {environment.upper()} exchange {exchange_name}"
            else:
                # Clear manual lock for all exchanges
                for exch_id in [1, 2, 4, 5]:
                    clear_manual_lock(environment, exch_id)
                message = f"Manual lock cleared for {environment.upper()} (all exchanges)"
            
            return {
                "status": "ok",
                "message": message,
                "environment": environment,
                "exchange_id": exchange_id,
                "is_locked": False
            }
        
        elif action == 'clear_error_907':
            # Clear Error 907 cooldown - allows retry when LAMA has unlocked the account
            # NOTE: LAMA can unlock accounts anytime upon request - this is NOT always 24 hours!
            if exchange_id:
                _clear_error_907_lockout(environment, exchange_id)
                message = f"Error 907 cooldown cleared for {environment.upper()} exchange {exchange_name}. You can now retry login."
            else:
                # Clear for all exchanges (Error 907 is environment-wide anyway)
                for exch_id in [1, 2, 4, 5]:
                    _clear_error_907_lockout(environment, exch_id)
                message = f"Error 907 cooldown cleared for {environment.upper()} (all exchanges). You can now retry login."
            
            logger.info(f"[ERROR 907] Admin cleared Error 907 cooldown for {environment.upper()} {exchange_name}")
            
            return {
                "status": "ok",
                "message": message,
                "environment": environment,
                "exchange_id": exchange_id,
                "is_error_907_cleared": True,
                "note": "LAMA may still be locked - verify with LAMA support before retrying"
            }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error locking/unlocking login: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error locking/unlocking login: {str(e)}")

