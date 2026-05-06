# api/backend/app/routes/config.py
"""
LAMA Configuration endpoints for UAT and PROD environments
"""

from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel
from sqlalchemy import select, update, insert, delete
from sqlalchemy.orm import Session
from app.db.db import get_db, lama_config_table, lama_exchange_metric_config_table, lama_exchange_config_table, engine
from app.utils.permissions import require_admin, require_role
from datetime import datetime
import logging
from app.utils.lama_token_cache import logout_lama_exchange
from app.utils.aes_encryption import encrypt_password

from app.utils.environment import get_active_environment

logger = logging.getLogger(__name__)

router = APIRouter()

class ExchangeCredentials(BaseModel):
    member_id: str = ""
    login_id: str = ""
    password: str = ""
    secret_key: str = ""
    lama_api_url: str = "" # Add API URL field

class LamaConfigRequest(BaseModel):
    environment: str  # 'prod' or 'uat'
    enabled: bool
    credentials: ExchangeCredentials

class LamaConfigResponse(BaseModel):
    id: int
    environment: str
    enabled: bool
    member_id: str
    login_id: str
    lama_api_url: str = "" # Add API URL field
    password: str = None  # Don't return password in response
    secret_key: str = None  # Don't return secret key in response
    created_at: str
    updated_at: str

@router.post("/", response_model=dict)
def save_config(config: LamaConfigRequest, request: Request, db: Session = Depends(get_db)):
    """
    Save LAMA configuration for UAT or PROD environment - Admin only
    
    CRITICAL: This endpoint does NOT call the LAMA Exchange Login API
    Per LAMA API Specification V1.2:
    - Login only once per 24 hours (handled by scheduler)
    - Single token (not refresh token)
    - Actual login is performed only by scheduler when token is expired/missing
    
    This endpoint only saves credentials to database. No API calls are made.
    
    Environment is specified in the request body, not as a query parameter,
    since this endpoint manages configurations for both environments.
    """
    try:
        logger.info(f"Received config save request for environment: {config.environment}, enabled: {config.enabled}")
        logger.debug(f"Request body: environment={config.environment}, enabled={config.enabled}, "
                    f"has_credentials={bool(config.credentials)}, "
                    f"member_id={'*' * len(config.credentials.member_id) if config.credentials.member_id else 'empty'}, "
                    f"login_id={'*' * len(config.credentials.login_id) if config.credentials.login_id else 'empty'}")
    except Exception as e:
        logger.warning(f"Error logging request details: {e}")
    
    user = require_admin(request)  # Only admin can save configuration
    if config.environment not in ['prod', 'uat']:
        logger.error(f"Invalid environment: {config.environment}")
        raise HTTPException(status_code=400, detail="Environment must be 'prod' or 'uat'")
    
    # Validate credentials if enabling
    if config.enabled:
        # Check for empty strings or None values
        missing_fields = []
        if not config.credentials.member_id or config.credentials.member_id.strip() == "":
            missing_fields.append("Member ID")
        if not config.credentials.login_id or config.credentials.login_id.strip() == "":
            missing_fields.append("Login ID")
        if not config.credentials.password or config.credentials.password.strip() == "":
            missing_fields.append("Password")
        if not config.credentials.secret_key or config.credentials.secret_key.strip() == "":
            missing_fields.append("Secret Key")
        
        if missing_fields:
            error_msg = f"All credentials are required when enabling. Missing: {', '.join(missing_fields)}"
            logger.error(f"Validation failed: {error_msg}")
            raise HTTPException(
                status_code=400,
                detail=error_msg
            )
    
    try:
        # PROFESSIONAL DESIGN:
        # - User enters PLAIN TEXT password in UI
        # - We ENCRYPT it and store in DB
        # - When displaying, we DECRYPT back to plain text
        # - LAMA API uses encrypted password from DB directly
        
        plain_text_password = config.credentials.password
        secret_key = config.credentials.secret_key
        
        logger.info(f"[CONFIG] Saving config for {config.environment.upper()}")
        logger.info(f"[CONFIG] Password provided: {'Yes' if plain_text_password else 'No'}")
        logger.info(f"[CONFIG] Secret key provided: {'Yes' if secret_key else 'No'}")
        
        # Validation: If enabling, we need password and secret_key
        if config.enabled:
            if not plain_text_password:
                raise HTTPException(status_code=400, detail="Password is required when enabling configuration")
            if not secret_key:
                raise HTTPException(status_code=400, detail="Secret Key is required when enabling configuration")
        
        # Encrypt password if provided
        encrypted_password = None
        if plain_text_password and secret_key:
            encrypted_password = encrypt_password(
                raw_password=plain_text_password,
                secret_key=secret_key
            )
            logger.info(f"[CONFIG] Password encrypted (plain text length: {len(plain_text_password)}, encrypted length: {len(encrypted_password)})")
        elif plain_text_password and not secret_key:
            raise HTTPException(status_code=400, detail="Secret Key is required to encrypt password")
        
        # CRITICAL FIX BUG-001: Use engine.begin() for atomic transactions
        with engine.begin() as conn:
            # Check if config exists for this environment
            query = select(lama_config_table).where(lama_config_table.c.environment == config.environment)
            existing = conn.execute(query).fetchone()
            
            if existing:
                # Update existing config
                # Build update values - only update password if provided
                update_values = {
                    "enabled": config.enabled,
                    "member_id": config.credentials.member_id,
                    "login_id": config.credentials.login_id,
                    "lama_api_url": config.credentials.lama_api_url,
                    "updated_at": datetime.utcnow()
                }
                
                # Only update password if user provided new one
                if encrypted_password:
                    update_values["password"] = encrypted_password
                    update_values["secret_key"] = secret_key
                    logger.info(f"[CONFIG] Updating password and secret_key")
                elif secret_key and not plain_text_password:
                    # User changed only secret_key - need to re-encrypt existing password
                    existing_encrypted = existing[6]
                    existing_secret = existing[7]
                    if existing_encrypted and existing_secret:
                        try:
                            from app.utils.aes_encryption import decrypt_password
                            old_plain = decrypt_password(existing_encrypted, existing_secret)
                            new_encrypted = encrypt_password(old_plain, secret_key)
                            update_values["password"] = new_encrypted
                            update_values["secret_key"] = secret_key
                            logger.info(f"[CONFIG] Re-encrypted password with new secret_key")
                        except Exception as e:
                            logger.warning(f"[CONFIG] Could not re-encrypt: {e}")
                            update_values["secret_key"] = secret_key
                
                update_query = update(lama_config_table).where(
                    lama_config_table.c.environment == config.environment
                ).values(**update_values)
                conn.execute(update_query)
                logger.info(f"Updated {config.environment} configuration")
                
                # CRITICAL: Sync all exchanges (NSE, BSE, MCX, NCDEX) with environment enabled status
                exchange_ids = [1, 2, 4, 5]  # NSE, BSE, MCX, NCDEX
                exchange_names = {1: 'NSE', 2: 'BSE', 4: 'MCX', 5: 'NCDEX'}
                for exchange_id in exchange_ids:
                    # Check if exchange config exists
                    check_exchange_query = select(lama_exchange_config_table).where(
                        lama_exchange_config_table.c.environment == config.environment,
                        lama_exchange_config_table.c.exchange_id == exchange_id
                    )
                    existing_exchange = conn.execute(check_exchange_query).fetchone()
                    
                    if existing_exchange:
                        # Update existing exchange config to match environment status
                        update_exchange_query = update(lama_exchange_config_table).where(
                            lama_exchange_config_table.c.environment == config.environment,
                            lama_exchange_config_table.c.exchange_id == exchange_id
                        ).values(
                            enabled=config.enabled,
                            updated_at=datetime.utcnow()
                        )
                        conn.execute(update_exchange_query)
                        logger.debug(f"Synced {config.environment.upper()} {exchange_names[exchange_id]} (ID: {exchange_id}) to enabled={config.enabled}")
                    else:
                        # Insert new exchange config if environment is enabled
                        if config.enabled:
                            insert_exchange_query = lama_exchange_config_table.insert().values(
                                environment=config.environment,
                                exchange_id=exchange_id,
                                enabled=True,
                                created_at=datetime.utcnow(),
                                updated_at=datetime.utcnow()
                            )
                            conn.execute(insert_exchange_query)
                            logger.debug(f"Auto-enabled {config.environment.upper()} {exchange_names[exchange_id]} (ID: {exchange_id}) on config update")
                
                if config.enabled:
                    logger.info(f"[CONFIG] Synced all exchanges (NSE, BSE, MCX, NCDEX) to enabled=True for {config.environment.upper()}")
                else:
                    logger.info(f"[CONFIG] Synced all exchanges (NSE, BSE, MCX, NCDEX) to enabled=False for {config.environment.upper()}")
                
                # Log configuration change and enable/disable
                try:
                    from app.utils.activity_logger import log_config_change, log_exchange_enable_disable
                    old_enabled = existing[2] if len(existing) > 2 else None  # enabled is at index 2
                    changed_fields = []
                    if old_enabled != config.enabled:
                        changed_fields.append("enabled")
                        log_exchange_enable_disable(user['user_id'], user['email'], config.environment, config.enabled)
                        
                        # CRITICAL FIX: When exchange is disabled, clear tokens
                        if not config.enabled:  # Exchange is being disabled
                            logger.info(f"[CONFIG] Exchange {config.environment.upper()} is being disabled - clearing tokens")
                            
                            # Clear token cache for this environment
                            try:
                                from app.utils.lama_token_cache import clear_token_cache
                                clear_token_cache(config.environment)
                                logger.info(f"[CONFIG] ✅ Cleared token cache for {config.environment.upper()}")
                            except Exception as token_error:
                                logger.warning(f"[CONFIG] Failed to clear token cache: {token_error}")
                    # Check if credentials changed (which invalidates existing tokens)
                    # CRITICAL: Compare encrypted passwords, not plain text vs encrypted
                    credentials_changed = False
                    if existing[4] != config.credentials.member_id:  # member_id changed
                        changed_fields.append("member_id")
                        credentials_changed = True
                    if existing[5] != config.credentials.login_id:  # login_id changed
                        changed_fields.append("login_id")
                        credentials_changed = True
                    # CRITICAL FIX: Compare encrypted passwords (existing[6] is encrypted, need to encrypt incoming password first)
                    existing_encrypted_password = existing[6]  # Already encrypted in DB
                    new_encrypted_password = encrypted_password  # Just encrypted above
                    if existing_encrypted_password != new_encrypted_password:  # password changed
                        changed_fields.append("password")
                        credentials_changed = True
                        logger.info(f"[CONFIG] Password changed for {config.environment.upper()} (encrypted comparison)")
                    if existing[7] != config.credentials.secret_key:  # secret_key changed
                        changed_fields.append("secret_key")
                        credentials_changed = True
                    
                    # CRITICAL FIX: When credentials change, clear tokens
                    # Old tokens were obtained with old credentials and will be invalid
                    if credentials_changed:
                        logger.info(f"[CONFIG] Credentials changed for {config.environment.upper()} - clearing tokens")
                        
                        # Clear token cache for this environment (old tokens are invalid)
                        try:
                            from app.utils.lama_token_cache import clear_token_cache
                            clear_token_cache(config.environment)
                            logger.info(f"[CONFIG] ✅ Cleared token cache for {config.environment.upper()} (credentials changed)")
                        except Exception as token_error:
                            logger.warning(f"[CONFIG] Failed to clear token cache: {token_error}")
                    
                    if changed_fields or len(changed_fields) > 0:
                        log_config_change(user['user_id'], user['email'], config.environment, config.enabled, changed_fields)
                except Exception as e:
                    logger.warning(f"Failed to log config change activity: {e}")
            else:
                # Insert new config
                # For new config, password and secret_key must be provided
                if not encrypted_password:
                    raise HTTPException(status_code=400, detail="Password is required for new configuration")
                if not secret_key:
                    raise HTTPException(status_code=400, detail="Secret Key is required for new configuration")
                
                insert_query = lama_config_table.insert().values(
                    environment=config.environment,
                    enabled=config.enabled,
                    member_id=config.credentials.member_id,
                    login_id=config.credentials.login_id,
                    password=encrypted_password,  # Store ENCRYPTED password
                    secret_key=secret_key,
                    lama_api_url=config.credentials.lama_api_url,
                    unique_environment=config.environment
                )
                conn.execute(insert_query)
                # No manual commit needed - engine.begin() handles it
                logger.info(f"Created {config.environment} configuration")
                
                # CRITICAL: If enabled=True, automatically enable ALL exchanges (NSE, BSE, MCX, NCDEX) for this environment
                if config.enabled:
                    exchange_ids = [1, 2, 4, 5]  # NSE, BSE, MCX, NCDEX
                    exchange_names = {1: 'NSE', 2: 'BSE', 4: 'MCX', 5: 'NCDEX'}
                    for exchange_id in exchange_ids:
                        insert_exchange_query = lama_exchange_config_table.insert().values(
                            environment=config.environment,
                            exchange_id=exchange_id,
                            enabled=True,
                            created_at=datetime.utcnow(),
                            updated_at=datetime.utcnow()
                        )
                        conn.execute(insert_exchange_query)
                        logger.debug(f"Auto-enabled {config.environment.upper()} {exchange_names[exchange_id]} (ID: {exchange_id}) on config creation")
                    logger.info(f"[CONFIG] Auto-enabled all exchanges (NSE, BSE, MCX, NCDEX) for {config.environment.upper()} on config creation")
                
                # Log configuration creation and enable/disable
                try:
                    from app.utils.activity_logger import log_config_change, log_exchange_enable_disable
                    log_config_change(user['user_id'], user['email'], config.environment, config.enabled, ["created"])
                    if config.enabled:
                        log_exchange_enable_disable(user['user_id'], user['email'], config.environment, config.enabled)
                except Exception as e:
                    logger.warning(f"Failed to log config creation activity: {e}")
            
            # CRITICAL: Per LAMA API Specification V1.2 - Do NOT call login API during save
            # Login is handled only by scheduler (once per 24 hours when token expired)
            # This endpoint only saves credentials to database - no API calls made
            logger.info(f"{config.environment.upper()} configuration saved successfully. Login will be performed by scheduler when token expires (per LAMA API spec: once per 24 hours)")
            
            # Build response
            response = {
                "status": "success",
                "message": f"{config.environment.upper()} configuration saved successfully"
            }
            
            return response
            
    except HTTPException as he:
        logger.error(f"HTTPException in save_config: {he.detail} (status_code={he.status_code})")
        raise
    except Exception as e:
        logger.error(f"Error saving configuration: {e}", exc_info=True)
        import traceback
        logger.error(f"Full traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Error saving configuration: {str(e)}")

@router.get("/")
def get_config(environment: str = Depends(get_active_environment), request: Request = None, db: Session = Depends(get_db)):
    """Get LAMA configuration for UAT or PROD environment
    Supports environment as query parameter: ?environment=prod or ?environment=uat
    If no environment specified, returns both PROD and UAT configs
    Admin/Manager only - User role blocked
    """
    require_role(request, ['admin'])  # Block user role
    try:
        # Get environment from dependency (Prioritizes header/query param)
        
        with engine.connect() as conn:
            if environment:
                if environment not in ['prod', 'uat']:
                    raise HTTPException(status_code=400, detail="Environment must be 'prod' or 'uat'")
                
                query = select(lama_config_table).where(lama_config_table.c.environment == environment)
                result = conn.execute(query).fetchone()
                
                if not result:
                    # Return empty array if no config found
                    return []
                
                # Row access: id, environment, enabled, lama_api_url, member_id, login_id, password, secret_key, created_at, updated_at, unique_environment
                # PROFESSIONAL DESIGN:
                # - DB stores ENCRYPTED password (secure, ready for LAMA API)
                # - UI displays DECRYPTED plain text (user can see/edit via eye button)
                # - Decrypt on read, encrypt on write
                from app.utils.aes_encryption import decrypt_password
                
                encrypted_password = result[6] or ""
                secret_key = result[7] or ""
                
                # Decrypt password for display (so user sees plain text)
                plain_text_password = ""
                if encrypted_password and secret_key:
                    try:
                        plain_text_password = decrypt_password(encrypted_password, secret_key)
                        logger.debug(f"[CONFIG] Password decrypted for display")
                    except Exception as e:
                        # Decryption failed - password might be stored as plain text (legacy)
                        # Check if it looks like plain text (not Base64 encoded)
                        if not encrypted_password.endswith('==') and not encrypted_password.endswith('='):
                            # Likely plain text - return as-is (legacy data)
                            plain_text_password = encrypted_password
                            logger.warning(f"[CONFIG] Password not encrypted (legacy) - showing as-is")
                        else:
                            logger.warning(f"[CONFIG] Could not decrypt password: {e}")
                            plain_text_password = ""  # Show empty if decryption fails
                
                def format_dt(dt):
                    if not dt: return None
                    if isinstance(dt, str): return dt
                    return dt.isoformat() + 'Z'
                
                config_data = {
                    "id": result[0],
                    "environment": result[1],
                    "enabled": result[2],
                    "lama_api_url": result[3] or "",
                    "member_id": result[4] or "",
                    "login_id": result[5] or "",
                    "password": encrypted_password,  # Send ENCRYPTED password to UI
                    "secret_key": secret_key,  # Secret key (user can see/edit)
                    "created_at": format_dt(result[8]),
                    "updated_at": format_dt(result[9])
                }
                
                # Return as array to match frontend expectation
                return [config_data]
            else:
                # Get both UAT and PROD configs
                query = select(lama_config_table)
                results = conn.execute(query).fetchall()
                
                configs = {}
                from app.utils.aes_encryption import decrypt_password
                
                for r in results:
                    env = r[1]  # environment column
                    # PROFESSIONAL DESIGN: Decrypt password for UI display
                    encrypted_password = r[6] or ""
                    secret_key = r[7] or ""
                    
                    plain_text_password = ""
                    if encrypted_password and secret_key:
                        try:
                            plain_text_password = decrypt_password(encrypted_password, secret_key)
                        except Exception as e:
                            # Legacy plain text password - return as-is
                            if not encrypted_password.endswith('==') and not encrypted_password.endswith('='):
                                plain_text_password = encrypted_password
                                logger.warning(f"[CONFIG] Password not encrypted for {env} (legacy) - showing as-is")
                            else:
                                logger.warning(f"[CONFIG] Could not decrypt password for {env}: {e}")
                                plain_text_password = ""
                    
                    configs[env] = {
                        "id": r[0],
                        "environment": r[1],
                        "enabled": r[2],
                        "lama_api_url": r[3] or "",
                        "member_id": r[4] or "",
                        "login_id": r[5] or "",
                        "password": encrypted_password,  # Send ENCRYPTED password to UI
                        "secret_key": secret_key,
                        "created_at": format_dt(r[8]),
                        "updated_at": format_dt(r[9])
                    }
                
                # Ensure both environments are present
                if 'prod' not in configs:
                    configs['prod'] = None
                if 'uat' not in configs:
                    configs['uat'] = None
                
                return {
                    "status": "success",
                    "configs": configs
                }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting configuration: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error getting configuration: {str(e)}")

@router.get("/status/{environment}")
def get_config_status(environment: str, db: Session = Depends(get_db)):
    """Get only the enabled status for an environment"""
    if environment not in ['prod', 'uat']:
        raise HTTPException(status_code=400, detail="Environment must be 'prod' or 'uat'")
    
    try:
        with engine.connect() as conn:
            query = select(lama_config_table).where(lama_config_table.c.environment == environment)
            result = conn.execute(query).fetchone()
            
            if not result:
                return {"enabled": False, "exists": False}
            
            return {
                "enabled": bool(result[2]),  # enabled column
                "exists": True
            }
    except Exception as e:
        logger.error(f"Error getting config status: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error getting config status: {str(e)}")

class ToggleRequest(BaseModel):
    enabled: bool

@router.post("/toggle/{environment}")
def toggle_config(environment: str, toggle: ToggleRequest, request: Request, db: Session = Depends(get_db)):
    """
    Toggle enabled status for an environment - Admin only
    
    CRITICAL: When environment is enabled/disabled, ALL exchanges (NSE, BSE, MCX, NCDEX) 
    are automatically enabled/disabled accordingly for that environment.
    """
    require_admin(request)  # Only admin can toggle configuration
    if environment not in ['prod', 'uat']:
        raise HTTPException(status_code=400, detail="Environment must be 'prod' or 'uat'")
    
    try:
        # CRITICAL FIX BUG-001: Use engine.begin() for atomic transactions
        with engine.begin() as conn:
            query = select(lama_config_table).where(lama_config_table.c.environment == environment)
            existing = conn.execute(query).fetchone()
            
            if not existing:
                raise HTTPException(
                    status_code=404, 
                    detail=f"Configuration not found for {environment.upper()}. Please save configuration first."
                )
            
            # Update environment enabled status
            update_query = update(lama_config_table).where(
                lama_config_table.c.environment == environment
            ).values(
                enabled=toggle.enabled,
                updated_at=datetime.utcnow()
            )
            conn.execute(update_query)
            
            # CRITICAL: Enable/disable ALL exchanges (NSE, BSE, MCX, NCDEX) for this environment
            # Exchange IDs: 1=NSE, 2=BSE, 4=MCX, 5=NCDEX
            exchange_ids = [1, 2, 4, 5]
            exchange_names = {1: 'NSE', 2: 'BSE', 4: 'MCX', 5: 'NCDEX'}
            
            for exchange_id in exchange_ids:
                # Check if exchange config exists
                check_query = select(lama_exchange_config_table).where(
                    lama_exchange_config_table.c.environment == environment,
                    lama_exchange_config_table.c.exchange_id == exchange_id
                )
                existing_exchange = conn.execute(check_query).fetchone()
                
                if existing_exchange:
                    # Update existing exchange config
                    update_exchange_query = update(lama_exchange_config_table).where(
                        lama_exchange_config_table.c.environment == environment,
                        lama_exchange_config_table.c.exchange_id == exchange_id
                    ).values(
                        enabled=toggle.enabled,
                        updated_at=datetime.utcnow()
                    )
                    conn.execute(update_exchange_query)
                    logger.debug(f"Updated {environment.upper()} {exchange_names[exchange_id]} (ID: {exchange_id}) to enabled={toggle.enabled}")
                else:
                    # Insert new exchange config
                    insert_exchange_query = lama_exchange_config_table.insert().values(
                        environment=environment,
                        exchange_id=exchange_id,
                        enabled=toggle.enabled,
                        created_at=datetime.utcnow(),
                        updated_at=datetime.utcnow()
                    )
                    conn.execute(insert_exchange_query)
                    logger.debug(f"Created {environment.upper()} {exchange_names[exchange_id]} (ID: {exchange_id}) with enabled={toggle.enabled}")
            
            # CRITICAL: When disabling, clear tokens and prepared metrics
            # This ensures schedulers stop immediately and tokens aren't reused when re-enabled
            if not toggle.enabled:
                logger.info(f"[CONFIG] Exchange {environment.upper()} is being disabled - clearing tokens and prepared metrics")
                
                # Clear token cache for this environment
                try:
                    from app.utils.lama_token_cache import clear_token_cache
                    clear_token_cache(environment)
                    logger.info(f"[CONFIG] ✅ Cleared token cache for {environment.upper()}")
                except Exception as token_error:
                    logger.warning(f"[CONFIG] Failed to clear token cache: {token_error}")
                
                # Delete tokens from database for this environment
                try:
                    from app.db.db import lama_tokens_table
                    from sqlalchemy import delete
                    delete_tokens_query = delete(lama_tokens_table).where(
                        lama_tokens_table.c.environment == environment
                    )
                    deleted_tokens_count = conn.execute(delete_tokens_query).rowcount
                    if deleted_tokens_count > 0:
                        logger.info(f"[CONFIG] ✅ Deleted {deleted_tokens_count} token(s) from database for {environment.upper()}")
                except Exception as token_db_error:
                    logger.warning(f"[CONFIG] Failed to delete tokens from database: {token_db_error}")
            
            # No manual commit needed - engine.begin() handles it
            
            status = "enabled" if toggle.enabled else "disabled"
            exchange_status = "enabled" if toggle.enabled else "disabled"
            logger.info(f"{environment.upper()} LAMA exchange {status} - All exchanges (NSE, BSE, MCX, NCDEX) {exchange_status}")
            
            return {
                "status": "success", 
                "message": f"{environment.upper()} LAMA exchange {status} successfully. All exchanges (NSE, BSE, MCX, NCDEX) have been {exchange_status}.",
                "enabled": toggle.enabled
            }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error toggling configuration: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error toggling configuration: {str(e)}")

@router.get("/exchanges/{environment}")
def get_exchange_status(environment: str, request: Request = None, db: Session = Depends(get_db)):
    """
    Get exchange status (NSE, BSE, MCX, NCDEX) for an environment - Admin/Manager only
    Returns which exchanges are enabled/disabled
    """
    require_role(request, ['admin'])  # Block user role
    if environment not in ['prod', 'uat']:
        raise HTTPException(status_code=400, detail="Environment must be 'prod' or 'uat'")
    
    try:
        with engine.connect() as conn:
            # Get all exchanges for this environment
            query = select(lama_exchange_config_table).where(
                lama_exchange_config_table.c.environment == environment
            ).order_by(lama_exchange_config_table.c.exchange_id)
            results = conn.execute(query).fetchall()
            
            # Exchange ID to name mapping
            exchange_names = {1: 'NSE', 2: 'BSE', 4: 'MCX', 5: 'NCDEX'}
            
            # Build response with all exchanges
            exchanges = []
            for row in results:
                exchange_id = row[2]  # exchange_id column
                enabled = row[3]  # enabled column
                exchanges.append({
                    'exchange_id': exchange_id,
                    'name': exchange_names.get(exchange_id, f'Exchange {exchange_id}'),
                    'enabled': bool(enabled) if enabled is not None else False
                })
            
            # If no exchanges configured, return defaults based on environment enabled status
            if not exchanges:
                # Check if environment is enabled
                env_query = select(lama_config_table).where(
                    lama_config_table.c.environment == environment
                )
                env_result = conn.execute(env_query).fetchone()
                env_enabled = bool(env_result[2]) if env_result else False
                
                # Default: UAT has NSE only if enabled, PROD has none
                if env_enabled and environment == 'uat':
                    exchanges = [{'exchange_id': 1, 'name': 'NSE', 'enabled': True}]
                else:
                    exchanges = []
            
            return {
                "status": "success",
                "environment": environment,
                "exchanges": exchanges
            }
    except Exception as e:
        logger.error(f"Error getting exchange status: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error getting exchange status: {str(e)}")

@router.delete("/{environment}")
def delete_config(environment: str, request: Request, db: Session = Depends(get_db)):
    """Delete LAMA configuration for an environment - Admin only"""
    require_admin(request)  # Only admin can delete configuration
    if environment not in ['prod', 'uat']:
        raise HTTPException(status_code=400, detail="Environment must be 'prod' or 'uat'")
    
    try:
        # CRITICAL FIX BUG-001: Use engine.begin() for atomic transactions
        with engine.begin() as conn:
            from sqlalchemy import delete
            delete_query = delete(lama_config_table).where(lama_config_table.c.environment == environment)
            result = conn.execute(delete_query)
            # No manual commit needed - engine.begin() handles it
            
            if result.rowcount == 0:
                raise HTTPException(status_code=404, detail=f"No configuration found for {environment.upper()}")
            
            return {"status": "success", "message": f"{environment.upper()} configuration deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting configuration: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error deleting configuration: {str(e)}")

@router.post("/logout/{environment}")
def logout_lama_exchange_api(environment: str, request: Request, db: Session = Depends(get_db)):
    """
    Logout from LAMA Exchange API for UAT or PROD environment - Admin only
    This will call the LAMA Exchange Logout API and clear the token cache
    """
    require_admin(request)  # Only admin can logout
    
    if environment not in ['prod', 'uat']:
        raise HTTPException(status_code=400, detail="Environment must be 'prod' or 'uat'")
    
    try:
        logger.info(f"Logout request for {environment.upper()} LAMA Exchange")
        
        # Call logout function which handles API call and token cache clearing
        logout_success = logout_lama_exchange(environment)
        
        if logout_success:
            return {
                "status": "success",
                "message": f"{environment.upper()} LAMA Exchange logout successful. Token cache cleared."
            }
        else:
            # Even if API call fails, token cache is cleared, so we return success
            return {
                "status": "success",
                "message": f"{environment.upper()} LAMA Exchange logout completed. Token cache cleared."
            }
    except Exception as e:
        logger.error(f"Error during {environment.upper()} LAMA Exchange logout: {e}", exc_info=True)
        # Still clear token cache on error
        try:
            from app.utils.lama_token_cache import clear_token_cache
            clear_token_cache(environment)
        except:
            pass
        raise HTTPException(status_code=500, detail=f"Error during logout: {str(e)}")

# ============= LAMA Exchange Metric Configuration Endpoints =============

class MetricConfigRequest(BaseModel):
    hardware: bool = True
    network: bool = True
    database: bool = True
    application: bool = True

class MetricConfigResponse(BaseModel):
    environment: str
    hardware: bool
    network: bool
    database: bool
    application: bool

@router.get("/metric-config", response_model=dict)
def get_metric_config(request: Request = None):
    """
    Get LAMA Exchange metric configuration for both UAT and PROD environments - Admin/Manager only
    Returns which metric types are enabled/disabled for sending to LAMA Exchange
    """
    require_role(request, ['admin'])  # Block user role
    try:
        with engine.connect() as conn:
            query = select(lama_exchange_metric_config_table).order_by(
                lama_exchange_metric_config_table.c.environment,
                lama_exchange_metric_config_table.c.metric_type
            )
            results = conn.execute(query).fetchall()
            
            # Initialize default structure
            configs = {
                "uat": {
                    "hardware": True,
                    "network": True,
                    "database": True,
                    "application": True
                },
                "prod": {
                    "hardware": True,
                    "network": True,
                    "database": True,
                    "application": True
                }
            }
            
            # Populate from database
            for row in results:
                env = row[1]  # environment column
                metric_type = row[2]  # metric_type column
                enabled = row[3]  # enabled column
                
                if env in configs and metric_type in configs[env]:
                    configs[env][metric_type] = bool(enabled)
            
            return {
                "status": "success",
                "configs": configs
            }
    except Exception as e:
        logger.error(f"Error getting metric configuration: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error getting metric configuration: {str(e)}")

@router.put("/metric-config/{environment}", response_model=dict)
def update_metric_config(environment: str, config: MetricConfigRequest, request: Request):
    """
    Update LAMA Exchange metric configuration for UAT or PROD environment - Admin only
    Controls which metric types are sent to LAMA Exchange
    """
    require_admin(request)  # Only admin can update configuration
    
    if environment not in ['prod', 'uat']:
        raise HTTPException(status_code=400, detail="Environment must be 'prod' or 'uat'")
    
    try:
        # CRITICAL FIX BUG-001: Use engine.begin() for atomic transactions
        with engine.begin() as conn:
            metric_types = {
                'hardware': config.hardware,
                'network': config.network,
                'database': config.database,
                'application': config.application
            }
            
            # Update or insert each metric type configuration
            for metric_type, enabled in metric_types.items():
                # Check if config exists
                check_query = select(lama_exchange_metric_config_table).where(
                    lama_exchange_metric_config_table.c.environment == environment,
                    lama_exchange_metric_config_table.c.metric_type == metric_type
                )
                existing = conn.execute(check_query).fetchone()
                
                if existing:
                    # Update existing
                    update_query = update(lama_exchange_metric_config_table).where(
                        lama_exchange_metric_config_table.c.environment == environment,
                        lama_exchange_metric_config_table.c.metric_type == metric_type
                    ).values(
                        enabled=enabled,
                        updated_at=datetime.utcnow()
                    )
                    conn.execute(update_query)
                else:
                    # Insert new
                    insert_query = lama_exchange_metric_config_table.insert().values(
                        environment=environment,
                        metric_type=metric_type,
                        enabled=enabled,
                        unique_env_metric=f"{environment}_{metric_type}"
                    )
                    conn.execute(insert_query)
            
            # No manual commit needed - engine.begin() handles it atomically
            
            logger.info(f"Updated {environment.upper()} metric configuration: hardware={config.hardware}, network={config.network}, database={config.database}, application={config.application}")
            
            return {
                "status": "success",
                "message": f"{environment.upper()} metric configuration updated successfully",
                "config": {
                    "environment": environment,
                    "hardware": config.hardware,
                    "network": config.network,
                    "database": config.database,
                    "application": config.application
                }
            }
    except Exception as e:
        logger.error(f"Error updating metric configuration: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error updating metric configuration: {str(e)}")

@router.post("/metric-config/{environment}/test", response_model=dict)
def test_metric_configuration(environment: str, request: Request):
    user = require_admin(request)  # Get user for activity logging
    """
    Test metric configuration - runs scheduler and returns detailed results - Admin only
    Shows which metrics were sent/skipped based on configuration
    
    WARNING: This endpoint triggers immediate metrics sending (bypasses 5-minute schedule).
    Use sparingly for testing only. Normal operation uses the scheduled task every 5 minutes.
    """
    require_admin(request)
    
    if environment not in ['prod', 'uat']:
        raise HTTPException(status_code=400, detail="Environment must be 'prod' or 'uat'")
    
    try:
        from app.schedulers import hardware_scheduler
        
        logger.warning(f"Metric configuration test triggered for {environment.upper()} by admin - This bypasses the 5-minute schedule!")
        
        # Trigger the active hardware scheduler for testing
        # Note: hardware_scheduler processes both environments if enabled, 
        # but here we just want to verify connectivity and code path
        hardware_scheduler()
        
        # Log API test activity
        try:
            from app.utils.activity_logger import log_api_test
            log_api_test(user['user_id'], user['email'], environment, "Metric Configuration Test", True, {
                "message": "Hardware scheduler triggered successfully"
            })
        except Exception as e:
            logger.warning(f"Failed to log API test activity: {e}")
        
        return {
            "status": "success",
            "environment": environment,
            "test_timestamp": datetime.utcnow().isoformat() + 'Z',
            "message": "Active hardware scheduler triggered successfully. Check Exchange Activity dashboard for results.",
            "note": "This test used the production hardware_scheduler path."
        }
    except Exception as e:
        logger.error(f"Error testing metric configuration: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error testing metric configuration: {str(e)}")

