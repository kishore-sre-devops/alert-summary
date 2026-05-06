# api/backend/app/routes/lama_diagnostics.py
"""
LAMA Exchange API Diagnostics endpoint
Provides detailed information about headers and API responses for troubleshooting
"""

from datetime import datetime

from fastapi import APIRouter, HTTPException, Depends, Request
from sqlalchemy.orm import Session
from app.db.db import get_db
from app.utils.permissions import require_admin, get_current_user
from app.utils.lama_exchange import get_exchange_credentials
from app.utils.lama_exchange_api import get_user_agent_for_environment
from app.utils.lama_exchange_api import LAMA_UAT_LOGIN_URL, LAMA_PROD_LOGIN_URL
import logging
from typing import Dict, Any

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/headers/{environment}")
def get_lama_headers(environment: str, request: Request, db: Session = Depends(get_db)):
    """
    Get the exact headers that will be sent to LAMA Exchange API for a given environment
    Admin only - for troubleshooting
    """
    require_admin(request)
    
    if environment not in ['prod', 'uat']:
        raise HTTPException(status_code=400, detail="Environment must be 'prod' or 'uat'")
    
    # Get API URL
    api_url = LAMA_PROD_LOGIN_URL if environment == 'prod' else LAMA_UAT_LOGIN_URL
    
    # Headers that will be sent (as per lama_exchange_api.py)
    # CRITICAL FIX: Both UAT and PROD use Linux browser User-Agent (matching Postman working request)
    # LAMA tech team requires Cookie header to be sent as blank
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Accept-Language": "en-US,en;q=0.9",
        "User-Agent": get_user_agent_for_environment(environment),
        "Referer": api_url,
        "Cookie": ""  # LAMA tech team requirement: send blank cookie
    }
    
    return {
        "environment": environment.upper(),
        "api_url": api_url,
        "headers": headers,
        "timeout": {
            "connect": 10.0,
            "read": 60.0,
            "write": 10.0,
            "pool": 10.0
        },
        "ssl_verify": True,
        "http_version": "HTTP/1.1"
    }


@router.post("/test-connection/{environment}")
def test_lama_connection(environment: str, request: Request, db: Session = Depends(get_db)):
    """
    Get request details that will be sent to LAMA Exchange API (headers, payload format)
    Admin only - for troubleshooting
    
    CRITICAL: This endpoint does NOT call the actual LAMA Exchange login API
    Per LAMA API Specification V1.2:
    - Login only once per 24 hours (handled by scheduler)
    - Single token (not refresh token)
    - Actual login is performed only by scheduler when token is expired/missing
    
    This endpoint only shows what headers and payload format will be sent.
    """
    require_admin(request)
    
    if environment not in ['prod', 'uat']:
        raise HTTPException(status_code=400, detail="Environment must be 'prod' or 'uat'")
    
    # Get credentials from database directly (bypass enabled check for diagnostics)
    from app.db.db import engine, lama_config_table
    from sqlalchemy import select
    
    try:
        with engine.connect() as conn:
            query = select(lama_config_table).where(
                lama_config_table.c.environment == environment
            )
            result = conn.execute(query).fetchone()
            
            if not result:
                raise HTTPException(
                    status_code=404,
                    detail=f"{environment.upper()} credentials not found. Please configure credentials first."
                )
            
            # Row access: id, environment, enabled, lama_api_url, member_id, login_id, password, secret_key, created_at, updated_at, unique_environment, exchange_ids
            # Note: We get credentials even if exchange is disabled (for diagnostics/testing)
            credentials = {
                'member_id': result[4] or '',
                'login_id': result[5] or '',
                'password': result[6] or '',
                'secret_key': result[7] or '',
            }
            
            # Check if credentials are empty
            if not credentials['member_id'] or not credentials['login_id'] or not credentials['password'] or not credentials['secret_key']:
                raise HTTPException(
                    status_code=404,
                    detail=f"{environment.upper()} credentials are incomplete. Please configure all credentials (Member ID, Login ID, Password, Secret Key) first."
                )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving {environment.upper()} credentials: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Error retrieving credentials: {str(e)}"
        )
    
    # Get API URL
    api_url = LAMA_PROD_LOGIN_URL if environment == 'prod' else LAMA_UAT_LOGIN_URL
    
    # Prepare headers (same as in lama_exchange_api.py)
    # CRITICAL FIX: Both UAT and PROD use Linux browser User-Agent (matching Postman working request)
    # LAMA tech team requires Cookie header to be sent as blank
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Accept-Language": "en-US,en;q=0.9",
        "User-Agent": get_user_agent_for_environment(environment),
        "Referer": api_url,
        "Cookie": ""  # LAMA tech team requirement: send blank cookie
    }
    
    # Build request details FIRST (always return these immediately)
    request_details = {
        "method": "POST",
        "url": api_url,
        "headers": headers,
        "payload": {
            "memberId": credentials['member_id'],
            "loginId": credentials['login_id'],
            "password": "[AES_ENCRYPTED - Length: " + str(len(credentials['password']) * 2) + " chars]"
        },
        "timeout": {
            "connect": 10.0,
            "read": 60.0,
            "write": 10.0,
            "pool": 10.0
        }
    }
    
    # CRITICAL: Per LAMA API Specification V1.2 - Login only once per 24 hours
    # Diagnostics endpoint does NOT call actual login API
    # Actual login is handled by scheduler when token is expired/missing
    # This endpoint only shows request details (headers, payload format)
    
    # Check if token exists in cache (for information only)
    from app.utils.lama_token_cache import check_token_expiration
    from app.utils.lama_exchange import get_enabled_exchanges
    
    token_status = {
        "cached_token_exists": False,
        "token_valid": False,
        "time_remaining_hours": 0,
        "note": "Login is performed only by scheduler (once per 24 hours)"
    }
    
    # Check token status for first enabled exchange (for information)
    enabled_exchanges = get_enabled_exchanges(environment)
    if enabled_exchanges:
        exchange_id = enabled_exchanges[0]
        needs_refresh, time_remaining = check_token_expiration(environment, exchange_id)
        token_status["cached_token_exists"] = not needs_refresh or time_remaining > 0
        token_status["token_valid"] = not needs_refresh
        token_status["time_remaining_hours"] = round(time_remaining / 3600, 2) if time_remaining > 0 else 0
    
    # Return request details (no actual API call)
    response_data = {
        "environment": environment.upper(),
        "api_url": api_url,
        "request": request_details,
        "token_status": token_status,
        "response": {
            "success": True,
            "status_code": 200,
            "message": f"{environment.upper()} LAMA Exchange request details (no actual API call - login handled by scheduler)",
            "error_type": None,
            "response_data": {
                "note": "This endpoint shows request format only. Actual login is performed by scheduler once per 24 hours as per LAMA API Specification V1.2"
            }
        }
    }
    
    return response_data


@router.get("/login-lock-status/{environment}")
def get_login_lock_status(environment: str, exchange_id: int = None, request: Request = None, db: Session = Depends(get_db)):
    """
    Check status of login locks - diagnostic endpoint to detect stuck locks
    Admin only - for troubleshooting login issues
    
    This endpoint checks if login locks are stuck, which could prevent login.
    Locks are in-memory and automatically released when threads complete.
    
    Args:
        environment: 'prod' or 'uat'
        exchange_id: Optional - Exchange ID (1=NSE, 2=BSE, 4=MCX, 5=NCDEX). If not provided, checks all exchanges
    """
    if request:
        require_admin(request)
    
    if environment not in ['prod', 'uat']:
        raise HTTPException(status_code=400, detail="Environment must be 'prod' or 'uat'")
    
    if exchange_id and exchange_id not in [1, 2, 4, 5]:
        raise HTTPException(status_code=400, detail="Exchange ID must be 1 (NSE), 2 (BSE), 4 (MCX), or 5 (NCDEX)")
    
    try:
        from app.utils.lama_token_cache import check_login_lock_status
        
        lock_status = check_login_lock_status(environment=environment, exchange_id=exchange_id)
        
        return {
            "environment": environment.upper(),
            "exchange_id": exchange_id if exchange_id else "all",
            "lock_status": lock_status,
            "recommendation": "If locks are held, check if login is actually in progress. If login is stuck (>60s), consider restarting the API container."
        }
        
    except Exception as e:
        logger.error(f"Error checking login lock status: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error checking login lock status: {str(e)}")


@router.post("/release-stuck-locks/{environment}")
def release_stuck_locks(environment: str, exchange_id: int = None, request: Request = None, db: Session = Depends(get_db)):
    """
    Release potentially stuck login locks - USE WITH EXTREME CAUTION
    Admin only - for troubleshooting login issues
    
    WARNING: Only use if locks are confirmed stuck and preventing login.
    This function only removes locks that are NOT currently held.
    It cannot force-release locks that are actively held by threads.
    
    Args:
        environment: 'prod' or 'uat'
        exchange_id: Optional - Exchange ID (1=NSE, 2=BSE, 4=MCX, 5=NCDEX). If not provided, releases all unlocked locks
    """
    if request:
        require_admin(request)
    
    if environment not in ['prod', 'uat']:
        raise HTTPException(status_code=400, detail="Environment must be 'prod' or 'uat'")
    
    if exchange_id and exchange_id not in [1, 2, 4, 5]:
        raise HTTPException(status_code=400, detail="Exchange ID must be 1 (NSE), 2 (BSE), 4 (MCX), or 5 (NCDEX)")
    
    try:
        from app.utils.lama_token_cache import release_stuck_login_locks
        
        result = release_stuck_login_locks(environment=environment, exchange_id=exchange_id)
        
        return {
            "environment": environment.upper(),
            "exchange_id": exchange_id if exchange_id else "all",
            "result": result,
            "note": "Only unlocked locks were released. Locks that are actively held cannot be force-released."
        }
        
    except Exception as e:
        logger.error(f"Error releasing stuck locks: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error releasing stuck locks: {str(e)}")


@router.get("/self-health")
def get_self_health(component: str = None, environment: str = None, request: Request = None):
    """
    Retrieve the latest self-healing control plane snapshot.
    Admin only - for monitoring overall automation status.
    """
    if request:
        require_admin(request)
    
    try:
        from app.utils.health_control_plane import get_health_snapshot, get_last_run_timestamp
        
        snapshot = get_health_snapshot(component_name=component, environment=environment)
        last_probe = get_last_run_timestamp()
        return {
            "timestamp": datetime.utcnow().isoformat(),
            "last_probe_at": last_probe.isoformat() if last_probe else None,
            "component_filter": component,
            "environment_filter": environment,
            "components": snapshot
        }
    except Exception as e:
        logger.error(f"Error fetching self-health snapshot: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error fetching health snapshot: {str(e)}")


@router.post("/self-health/run")
def run_self_health(request: Request = None):
    """
    Force-run all self-healing probes and return their results.
    Admin only - helpful for troubleshooting before/after change.
    """
    if request:
        require_admin(request)
    
    try:
        from app.utils.health_control_plane import run_health_checks_once
        
        records = run_health_checks_once(trigger="manual-api")
        return {
            "timestamp": datetime.utcnow().isoformat(),
            "components": [record.to_dict() for record in records]
        }
    except Exception as e:
        logger.error(f"Error running self-health probes: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error running health probes: {str(e)}")

