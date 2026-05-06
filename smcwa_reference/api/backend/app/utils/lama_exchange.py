"""
Utility functions for LAMA Exchange API integration
Checks if exchange is enabled before making API calls
"""
from sqlalchemy import select
from app.db.db import engine, lama_config_table, lama_exchange_config_table
from app.utils.lama_exchange_constants import EXCHANGE_ID_NSE
from app.utils.aes_encryption import decrypt_password
import logging

logger = logging.getLogger(__name__)

def get_base_url(environment: str) -> str:
    """
    Get LAMA Exchange base API URL for the given environment.
    """
    try:
        with engine.connect() as conn:
            query = select(lama_config_table.c.lama_api_url).where(
                lama_config_table.c.environment == environment
            )
            result = conn.execute(query).fetchone()
            if result and result[0]:
                return result[0].rstrip('/')
            
            # Fallback to hardcoded defaults if not in DB
            if environment == 'prod':
                return "https://lama.nseindia.com/api/V1"
            return "https://lama.uat.nseindia.com/api/V1"
    except Exception as e:
        logger.error(f"Error getting base URL for {environment}: {e}")
        return "https://lama.uat.nseindia.com/api/V1"

def get_active_configs() -> list:
    """
    Get list of all active environment configurations.
    Returns list of dicts with environment and lama_api_url.
    """
    try:
        with engine.connect() as conn:
            query = select(
                lama_config_table.c.environment,
                lama_config_table.c.lama_api_url
            ).where(
                lama_config_table.c.enabled == True
            )
            results = conn.execute(query).fetchall()
            return [{"environment": row[0], "lama_api_url": row[1]} for row in results]
    except Exception as e:
        logger.error(f"Error getting active configs: {e}", exc_info=True)
        return []

def get_active_environments() -> list:
    """
    Get list of all environments that have LAMA exchange enabled.
    Used by schedulers to determine which environments to process.
    """
    try:
        with engine.connect() as conn:
            query = select(lama_config_table.c.environment).where(
                lama_config_table.c.enabled == True
            )
            results = conn.execute(query).fetchall()
            return [row[0] for row in results]
    except Exception as e:
        logger.error(f"Error getting active environments: {e}", exc_info=True)
        return ['uat'] # Safe default

def is_exchange_enabled(environment: str) -> bool:
    """
    Check if LAMA exchange is enabled for the given environment
    
    Args:
        environment: 'prod' or 'uat'
    
    Returns:
        bool: True if enabled, False otherwise
    """
    try:
        with engine.connect() as conn:
            query = select(lama_config_table).where(
                lama_config_table.c.environment == environment
            )
            result = conn.execute(query).fetchone()
            
            if result:
                # Row access: id, environment, enabled, member_id, login_id, password, secret_key, ...
                enabled = result[2]  # enabled column is at index 2
                enabled_value = bool(enabled) if enabled is not None else False
                logger.debug(f"[EXCHANGE_CHECK] {environment.upper()} enabled status: {enabled_value} (raw value: {enabled})")
                return enabled_value
            
            logger.warning(f"[EXCHANGE_CHECK] No configuration found for {environment.upper()} in lama_config table")
            return False
    except Exception as e:
        logger.error(f"[EXCHANGE_CHECK] ❌ Error checking exchange enabled status for {environment}: {e}", exc_info=True)
        logger.warning(f"[EXCHANGE_CHECK] ⚠️  Database error - cannot verify enabled status. Proceeding with login attempt (may be database issue)")
        # CRITICAL FIX: Don't block login on database errors - return True to allow login attempt
        # If exchange is actually disabled, login will fail with 401/801, which is acceptable
        # Blocking on database errors causes silent failures when exchange is actually enabled
        return True  # ✅ Allow login attempt on database errors

def get_exchange_credentials(environment: str) -> dict:
    """
    Get LAMA exchange credentials for the given environment
    
    Args:
        environment: 'prod' or 'uat'
    
    Returns:
        dict: Contains member_id, login_id, password, secret_key, or None if not found
    """
    try:
        with engine.connect() as conn:
            query = select(lama_config_table).where(
                lama_config_table.c.environment == environment
            )
            result = conn.execute(query).fetchone()
            
            if result:
                # Row access: id, environment, enabled, lama_api_url, member_id, login_id, password, secret_key, ...
                enabled = result[2]
                if not enabled:
                    return None
                
                # CORRECT FLOW: Password stored in DB is already AES-encrypted (for LAMA API use)
                # User entered plain text (e.g., @Smcltd12345), we encrypted it and stored it
                # We should return the encrypted password AS-IS for API calls (don't decrypt)
                # The encrypted password is what LAMA API expects
                stored_password = result[6] or ''
                secret_key = result[7] or ''
                
                # CRITICAL: Password in DB is already encrypted for LAMA API
                # We use it directly - NO decryption needed
                # The encrypted password is what we send to LAMA API
                password_for_api = stored_password  # Use encrypted password as-is
                logger.debug(f"[CREDENTIALS] Using stored encrypted password as-is for {environment} (length: {len(password_for_api) if password_for_api else 0})")
                logger.info(f"[CREDENTIALS] Password from DB is already encrypted for LAMA API - using directly (no decryption)")
                
                return {
                    'member_id': result[4] or '',
                    'login_id': result[5] or '',
                    'password': password_for_api,  # Encrypted password (use as-is for LAMA API)
                    'secret_key': secret_key,
                }
            
            return None
    except Exception as e:
        logger.error(f"Error getting exchange credentials for {environment}: {e}", exc_info=True)
        return None

def get_enabled_exchanges(environment: str) -> list:
    """
    Get list of enabled exchange IDs for the given environment
    
    Args:
        environment: 'prod' or 'uat'
    
    Returns:
        list: List of enabled exchange IDs (e.g., [1] for NSE only, or [1, 2, 4, 5] for all)
              Defaults to [EXCHANGE_ID_NSE] for UAT and [] for PROD if not configured
    """
    try:
        with engine.connect() as conn:
            query = select(lama_exchange_config_table.c.exchange_id).where(
                lama_exchange_config_table.c.environment == environment,
                lama_exchange_config_table.c.enabled == True
            )
            results = conn.execute(query).fetchall()
            enabled_exchange_ids = [row[0] for row in results]
            
            if not enabled_exchange_ids:
                logger.warning(f"No exchanges enabled for {environment.upper()} in lama_exchange_config. "
                              f"Defaulting to NSE only for UAT, and none for PROD.")
                if environment == 'uat':
                    return [EXCHANGE_ID_NSE]
                else:
                    return []
            return enabled_exchange_ids
    except Exception as e:
        logger.error(f"Error getting enabled exchanges for {environment}: {e}", exc_info=True)
        if environment == 'uat':
            return [EXCHANGE_ID_NSE]  # Fallback to NSE for UAT on error
        else:
            return []  # Fallback to no exchanges for PROD on error

