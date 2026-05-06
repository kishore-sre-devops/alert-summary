"""
Activity Logger Utility
Logs admin activities for audit purposes:
- Login activities
- Exchange Configuration changes
- Exchange Enable/Disable
- API Testing Logs
"""

from datetime import datetime
from sqlalchemy import text
from app.db.db import engine, audit_logs_table
import logging

logger = logging.getLogger(__name__)

def log_activity(
    user_id: int = None,
    user_email: str = None,
    action: str = None,
    resource_type: str = None,
    resource_id: int = None,
    details: dict = None
):
    """
    Log an activity to the audit_logs table for audit purposes.
    """
    try:
        # Robustness: Ensure user_id is an int if present
        safe_user_id = int(user_id) if user_id is not None else None
        
        # Robustness: Ensure resource_id is an int if present
        safe_resource_id = None
        if resource_id is not None:
            try:
                safe_resource_id = int(resource_id)
            except (ValueError, TypeError):
                # If resource_id is not an int (e.g., passed by mistake), move it to details
                if isinstance(resource_id, dict) and not details:
                    details = resource_id
                safe_resource_id = None

        with engine.connect() as conn:
            insert_query = audit_logs_table.insert().values(
                user_id=safe_user_id,
                action=str(action) if action else "Unknown Action",
                resource_type=str(resource_type) if resource_type else None,
                resource_id=safe_resource_id,
                details=details if isinstance(details, dict) else {},
                created_at=datetime.utcnow()
            )
            conn.execute(insert_query)
            conn.commit()
            logger.debug(f"Activity logged: {action} by user {user_email or user_id}")
    except Exception as e:
        logger.error(f"Failed to log activity: {e}", exc_info=True)
        # Don't raise exception - logging failure shouldn't break the main operation

def log_login(user_id: int, user_email: str, success: bool = True, request = None):
    """Log login activity with device detection"""
    action = "Lama Credential Authentication"
    
    # Detect mobile device from header
    is_mobile = False
    if request:
        device_type = request.headers.get("X-Device-Type", "").lower()
        if device_type == "mobile":
            is_mobile = True
            
    if not success:
        action = f"{'Mobile ' if is_mobile else ''}Lama Credential Authentication Failed"
    else:
        action = f"{'Mobile ' if is_mobile else ''}Lama Credential Authentication"
        
    log_activity(
        user_id=user_id,
        user_email=user_email,
        action=action,
        resource_type="auth",
        details={"success": success, "is_mobile": is_mobile}
    )

def log_config_change(user_id: int, user_email: str, environment: str, enabled: bool = None, changed_fields: list = None):
    """Log configuration change"""
    action = "Configuration has been modified"
    details = {
        "environment": environment,
        "changed_fields": changed_fields or []
    }
    if enabled is not None:
        details["enabled"] = enabled
    log_activity(
        user_id=user_id,
        user_email=user_email,
        action=action,
        resource_type="lama_config",
        details=details
    )

def log_exchange_enable_disable(user_id: int, user_email: str, environment: str, enabled: bool):
    """Log exchange enable/disable"""
    action = "Lama Service Enabled" if enabled else "Lama Service Disabled"
    log_activity(
        user_id=user_id,
        user_email=user_email,
        action=action,
        resource_type="lama_config",
        details={"environment": environment, "enabled": enabled}
    )

def log_api_test(user_id: int, user_email: str, environment: str, test_type: str, success: bool, details: dict = None):
    """Log API testing activity"""
    action = f"API Test: {test_type} ({environment.upper()})"
    test_details = {
        "environment": environment,
        "test_type": test_type,
        "success": success
    }
    if details:
        test_details.update(details)
    log_activity(
        user_id=user_id,
        user_email=user_email,
        action=action,
        resource_type="api_test",
        details=test_details
    )

