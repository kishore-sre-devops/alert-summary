# api/backend/app/utils/lama_exchange_api.py
"""
LAMA Exchange API integration utilities
Handles login API calls to UAT and PROD LAMA Exchange endpoints
"""

import httpx
import logging
import urllib3
import time
import json
import sys
import os
import threading
from typing import Dict, Optional, Tuple, List
from datetime import datetime, timedelta, timezone
from app.utils.aes_encryption import encrypt_password
from app.db.db import engine, exchange_transactions_table, DATABASE_URL
from app.utils.nse_timestamp import get_nse_timestamp_ms
from app.utils.lama_exchange_constants import (
    DEFAULT_EXCHANGE_ID, 
    DEFAULT_APPLICATION_ID,
    validate_exchange_id,
    validate_application_id
)
from sqlalchemy import select, text, func, and_

# Suppress SSL warnings when verification is disabled (for testing)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = logging.getLogger(__name__)

# Import scheduler logger functions (optional - only if scheduler_name is provided)
try:
    from app.utils.scheduler_logger import log_sequence_id, log_metrics_sent
except ImportError:
    # Scheduler logger not available - logging will be skipped
    log_sequence_id = None
    log_metrics_sent = None

# CRITICAL FIX #1: In-memory locks for sequence ID calculation to prevent race condition
# Multiple schedulers calculating sequence ID simultaneously could get the same ID
# Lock key: (environment, exchange_id, metric_type)
_seq_id_locks: Dict[tuple, threading.Lock] = {}
_seq_id_lock_manager = threading.Lock()

# User-Agent header - Per LAMA API Specification V1.2:
# CRITICAL FIX: Postman uses full browser User-Agent strings, not simplified ones
# Postman working request uses: Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36...
# UAT and PROD both work with Linux browser User-Agent (matching Postman)
DEFAULT_USER_AGENT_LINUX = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
DEFAULT_USER_AGENT_MAC = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

# Get User-Agent from environment variable, or use Linux default
# Set LAMA_USER_AGENT environment variable to override (e.g., for local testing)
# Examples:
#   export LAMA_USER_AGENT="mac"  # Use MacBook User-Agent
#   export LAMA_USER_AGENT="Mozilla/5.0 (Windows NT 10.0; Win64; x64)..."  # Custom User-Agent
user_agent_override = os.getenv("LAMA_USER_AGENT", "").strip()
if user_agent_override.lower() == "mac":
    DEFAULT_USER_AGENT = DEFAULT_USER_AGENT_MAC
elif user_agent_override:
    DEFAULT_USER_AGENT = user_agent_override  # Use custom User-Agent from env
else:
    DEFAULT_USER_AGENT = DEFAULT_USER_AGENT_LINUX  # Default: Linux

# Valid metric keys per metric type (as per LAMA Exchange API specification)
VALID_METRIC_KEYS = {
    'hardware': ['cpu', 'memory', 'disk', 'uptime'],
    'network': ['bandwidth', 'latency', 'packetCount', 'lookupCount'],
    'database': ['status', 'qSize', 'bandwidth', 'latency'],
    'application': ['throughput', 'latency', 'historicalThroughput', 'historicalLatency', 'failureTradeApi', 'failureAuthentication']
}


def get_user_agent_for_environment(environment: str) -> str:
    """
    Get User-Agent header based on environment.
    
    CRITICAL FIX: Postman uses full browser User-Agent strings that work for both UAT and PROD.
    Postman working request shows: Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36...
    Both UAT and PROD work with Linux browser User-Agent (matching Postman behavior).
    
    Can be overridden via environment variables:
    - LAMA_USER_AGENT_UAT: User-Agent for UAT environment
    - LAMA_USER_AGENT_PROD: User-Agent for PROD environment
    - LAMA_USER_AGENT: Global override (if set, used for both)
    
    Args:
        environment: 'uat' or 'prod'
        
    Returns:
        User-Agent string (full browser User-Agent matching Postman)
    """
    # Check for global override first
    global_override = os.getenv("LAMA_USER_AGENT", "").strip()
    if global_override:
        if global_override.lower() in ["mac", "macintosh"]:
            return DEFAULT_USER_AGENT_MAC
        elif global_override.lower() == "linux":
            return DEFAULT_USER_AGENT_LINUX
        else:
            return global_override  # Custom User-Agent
    
    # Check for environment-specific override
    if environment.lower() == 'uat':
        uat_override = os.getenv("LAMA_USER_AGENT_UAT", "").strip()
        if uat_override:
            if uat_override.lower() in ["mac", "macintosh"]:
                return DEFAULT_USER_AGENT_MAC
            elif uat_override.lower() == "linux":
                return DEFAULT_USER_AGENT_LINUX
            else:
                return uat_override  # Custom User-Agent
        # CRITICAL FIX: UAT uses Linux browser User-Agent (matching Postman working request)
        return DEFAULT_USER_AGENT_LINUX
    elif environment.lower() == 'prod':
        prod_override = os.getenv("LAMA_USER_AGENT_PROD", "").strip()
        if prod_override:
            if prod_override.lower() in ["mac", "macintosh"]:
                return DEFAULT_USER_AGENT_MAC
            elif prod_override.lower() == "linux":
                return DEFAULT_USER_AGENT_LINUX
            else:
                return prod_override  # Custom User-Agent
        # Default: PROD uses Linux browser User-Agent (matching Postman)
        return DEFAULT_USER_AGENT_LINUX
    else:
        # Unknown environment, use default (Linux browser User-Agent for server deployments)
        return DEFAULT_USER_AGENT_LINUX


def validate_payload_structure(payload: dict) -> Tuple[bool, str]:
    """
    Validate payload structure before sending (Error 603 prevention)
    
    Args:
        payload: The payload dictionary to validate
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    try:
        # Check required top-level fields
        required_fields = ['memberId', 'exchangeId', 'sequenceId', 'timestamp', 'payload']
        for field in required_fields:
            if field not in payload:
                return False, f"Missing required field: {field}"
        
        # Validate payload is a list
        if not isinstance(payload.get('payload'), list):
            return False, "payload must be a list"
        
        # Validate payload length ≤ 5 (Error 710 prevention)
        payload_array = payload.get('payload', [])
        if len(payload_array) > 5:
            return False, f"payload array contains {len(payload_array)} objects (max 5 allowed for Error 710 compliance)"
        
        # Validate each record in payload array
        for idx, record in enumerate(payload_array):
            if not isinstance(record, dict):
                return False, f"payload[{idx}] must be a dictionary"
            
            if 'applicationId' not in record:
                return False, f"payload[{idx}] missing required field: applicationId"
            
            if 'metricData' not in record:
                return False, f"payload[{idx}] missing required field: metricData"
            
            if not isinstance(record.get('metricData'), list):
                return False, f"payload[{idx}].metricData must be a list"
        
        return True, "Payload structure is valid"
    except Exception as e:
        return False, f"Payload validation error: {str(e)}"



def _normalize_metric(metric: dict) -> dict:
    """
    Normalizes a metric dictionary to a standard format for validation.
    Handles both Legacy format: {"name": "cpu", "avg": 10, ...}
    And Final V1.2 format: {"key": "cpu", "value": {"avg": 10, ...}} or {"key": "cpu", "value": 10}
    """
    if not isinstance(metric, dict): return {}
    
    name = metric.get("name") or metric.get("key", "")
    val = metric.get("value")
    
    # Standardize to Legacy-like flat format for easier validation
    norm = {"name": name}
    if isinstance(val, dict):
        norm.update(val)
    elif val is not None:
        norm["value"] = val
    else:
        # Already flat or missing value
        for k in ["min", "max", "avg", "med", "value"]:
            if k in metric: norm[k] = metric[k]
            
    return norm


def validate_metric_keys(metrics: List[dict], metric_type: str) -> Tuple[bool, str, List[dict]]:
    """
    Validate metric keys against LAMA Exchange specification (Error 707 prevention)
    
    Args:
        metrics: List of metric dictionaries
        metric_type: Type of metrics ('hardware', 'network', 'database', 'application')
        
    Returns:
        Tuple of (is_valid, error_message, valid_metrics)
        - valid_metrics: List of metrics with valid keys (invalid ones removed)
    """
    if metric_type not in VALID_METRIC_KEYS:
        return False, f"Unknown metric_type: {metric_type}", []
    
    valid_keys = VALID_METRIC_KEYS[metric_type]
    valid_metrics = []
    invalid_keys = []
    
    for metric in metrics:
        norm = _normalize_metric(metric)
        metric_name = norm.get("name", "")
        if metric_name in valid_keys:
            valid_metrics.append(metric)
        else:
            invalid_keys.append(metric_name if metric_name else "Unknown")
    
    if invalid_keys:
        return False, f"Invalid metric keys: {', '.join(invalid_keys)}. Valid keys for {metric_type}: {', '.join(valid_keys)}", valid_metrics
    
    return True, "All metric keys are valid", valid_metrics


def validate_metric_values(metrics: List[dict]) -> Tuple[bool, str, List[dict]]:
    """
    Validate metric values (type, range, format) - Error 708 prevention
    
    Args:
        metrics: List of metric dictionaries
        
    Returns:
        Tuple of (is_valid, error_message, valid_metrics)
        - valid_metrics: List of metrics with valid values (invalid ones removed)
    """
    valid_metrics = []
    invalid_metrics = []
    
    for metric in metrics:
        norm = _normalize_metric(metric)
        metric_name = norm.get("name", "")
        
        simple_value_metrics = ["packetCount", "lookupCount", "status", "failureTradeApi", "failureAuthentication", "log"]
        
        if metric_name in simple_value_metrics:
            # Check for value in norm
            if "value" in norm or "avg" in norm:
                valid_metrics.append(metric)
            else:
                invalid_metrics.append(f"{metric_name}: missing value")
        else:
            required_fields = ['min', 'max', 'avg', 'med']
            missing = [f for f in required_fields if f not in norm]
            if missing:
                invalid_metrics.append(f"{metric_name}: missing {missing}")
            else:
                valid_metrics.append(metric)
    
    if invalid_metrics:
        return False, f"Invalid metric values: {', '.join(invalid_metrics[:5])}", valid_metrics
    
    return True, "All metric values are valid", valid_metrics


def validate_null_blank_fields(metrics: List[dict]) -> Tuple[bool, str, List[dict]]:
    """
    Validate no null/blank values in required fields (Error 901 prevention)
    
    Args:
        metrics: List of metric dictionaries
        
    Returns:
        Tuple of (is_valid, error_message, valid_metrics)
        - valid_metrics: List of metrics with no null/blank values (invalid ones removed)
    """
    valid_metrics = []
    invalid_metrics = []
    
    for metric in metrics:
        norm = _normalize_metric(metric)
        metric_name = norm.get("name", "")
        if not metric_name:
            invalid_metrics.append("Blank metric name")
            continue
            
        # Check all available fields in norm for nulls
        has_null = False
        for k, v in norm.items():
            if v is None or (isinstance(v, str) and v.strip() == ""):
                invalid_metrics.append(f"{metric_name}: null {k}")
                has_null = True
                break
        if not has_null:
            valid_metrics.append(metric)
    
    if invalid_metrics:
        return False, f"Null/blank values found: {', '.join(invalid_metrics[:5])}", valid_metrics
    
    return True, "No null/blank values found", valid_metrics


def check_duplicate_records(environment: str, exchange_id: int, metric_type: str, payload: dict, lookback_minutes: int = 5) -> Tuple[bool, str]:
    """
    Check for duplicate records (Error 709 prevention)
    
    Args:
        environment: 'prod' or 'uat'
        exchange_id: Exchange ID
        metric_type: Metric type
        payload: The payload to check
        lookback_minutes: How many minutes to look back for duplicates
        
    Returns:
        Tuple of (has_duplicates, error_message)
    """
    try:
        lookback_time = datetime.now() - timedelta(minutes=lookback_minutes)
        
        with engine.connect() as conn:
            # Query recent successful transactions with same payload structure
            query = text(""" -- Global History Anchor

                SELECT metrics_sent->'lama_v1_2_payload' as payload_data
                FROM exchange_transactions
                WHERE environment = :environment
                  AND exchange_id = :exchange_id
                  AND metric_type = :metric_type
                  AND status = 'success'
                  AND sent_at > :lookback_time
                ORDER BY sent_at DESC
                LIMIT 10
            """)
            
            results = conn.execute(query, {
                'environment': environment,
                'exchange_id': exchange_id,
                'metric_type': metric_type,
                'lookback_time': lookback_time
            }).fetchall()
            
            # Compare payload structure (simplified - compare key fields)
            current_payload_str = json.dumps(payload.get('payload', []), sort_keys=True)
            
            for row in results:
                if row[0]:
                    try:
                        stored_payload = row[0]
                        if isinstance(stored_payload, dict):
                            stored_payload_str = json.dumps(stored_payload.get('payload', []), sort_keys=True)
                            if current_payload_str == stored_payload_str:
                                return True, "Duplicate payload detected in recent transactions"
                    except:
                        continue
            
            return False, "No duplicates found"
    except Exception as e:
        logger.warning(f"Error checking duplicates: {e}")
        return False, f"Error checking duplicates: {str(e)}"

# LAMA Exchange API Endpoints
LAMA_UAT_BASE_URL = "https://lama.uat.nseindia.com/api/V1"
LAMA_PROD_BASE_URL = "https://lama.nseindia.com/api/V1"

LAMA_UAT_LOGIN_URL = f"{LAMA_UAT_BASE_URL}/auth/login"
LAMA_PROD_LOGIN_URL = f"{LAMA_PROD_BASE_URL}/auth/login"

# Metrics endpoints (based on API specification)
LAMA_UAT_METRICS_HARDWARE_URL = f"{LAMA_UAT_BASE_URL}/metrics/hardware"
LAMA_PROD_METRICS_HARDWARE_URL = f"{LAMA_PROD_BASE_URL}/metrics/hardware"

LAMA_UAT_METRICS_NETWORK_URL = f"{LAMA_UAT_BASE_URL}/metrics/network"
LAMA_PROD_METRICS_NETWORK_URL = f"{LAMA_PROD_BASE_URL}/metrics/network"

LAMA_UAT_METRICS_DATABASE_URL = f"{LAMA_UAT_BASE_URL}/metrics/database"
LAMA_PROD_METRICS_DATABASE_URL = f"{LAMA_PROD_BASE_URL}/metrics/database"

LAMA_UAT_METRICS_APPLICATION_URL = f"{LAMA_UAT_BASE_URL}/metrics/application"
LAMA_PROD_METRICS_APPLICATION_URL = f"{LAMA_PROD_BASE_URL}/metrics/application"

LAMA_UAT_LOGOUT_URL = f"{LAMA_UAT_BASE_URL}/auth/logout"
LAMA_PROD_LOGOUT_URL = f"{LAMA_PROD_BASE_URL}/auth/logout"


def call_lama_exchange_login(
    environment: str,
    member_id: str,
    login_id: str,
    password: str,
    secret_key: str
) -> Dict[str, any]:
    """
    Call LAMA Exchange Login API with encrypted credentials
    
    Args:
        environment: 'prod' or 'uat'
        member_id: Member ID
        login_id: Login ID
        password: Plain text password (will be encrypted)
        secret_key: Secret key
        
    Returns:
        Dict with 'success' (bool), 'message' (str), and optional 'response_data'
    """
    if environment not in ['prod', 'uat']:
        return {
            "success": False,
            "message": f"Invalid environment: {environment}. Must be 'prod' or 'uat'"
        }
    
    # Determine API endpoint
    api_url = LAMA_PROD_LOGIN_URL if environment == 'prod' else LAMA_UAT_LOGIN_URL
    
    try:
        # CORRECT FLOW: Password received here is already encrypted (from DB)
        # User entered plain text in config, we encrypted it and stored in DB
        # We read encrypted password from DB and use it directly for API call
        # NO encryption needed here - password is already encrypted for LAMA API
        encrypted_password = password  # Password from DB is already encrypted - use as-is
        logger.info(f"[LOGIN] Using encrypted password from DB as-is (length: {len(encrypted_password)}) - no encryption needed")
        logger.info(f"[LOGIN] Password is already AES-encrypted and ready for LAMA API call")
        
        # Prepare request payload as per LAMA Exchange API document
        # Note: secretKey is used for encryption but NOT included in the payload
        payload = {
            "memberId": member_id,
            "loginId": login_id,
            "password": encrypted_password  # AES-ECB encrypted and Base64 encoded
        }
        
        logger.info(f"Calling {environment.upper()} LAMA Exchange Login API: {api_url}")
        logger.info(f"Request payload: memberId={member_id}, loginId={login_id}, password=[AES_ENCRYPTED]")
        logger.info(f"Note: secretKey used for encryption but NOT included in request payload (as per API spec)")
        logger.debug(f"Encrypted password (first 20 chars): {encrypted_password[:20]}...")
        logger.debug(f"Full payload keys: {list(payload.keys())}")
        
        # Make HTTP POST request
        # CRITICAL FIX: Match Postman behavior - disable SSL verification for both UAT and PROD (like metrics sending)
        # Postman typically has SSL verification disabled, and LAMA APIs may have certificate issues
        # Use HTTP/1.1 (HTTP/2 requires h2 package)
        # Increased timeout for login (UAT API may be slow)
        import os
        # Disable SSL verification for both UAT and PROD to match Postman behavior
        # LAMA Exchange APIs may have certificate issues in both environments
        ssl_verify = True  # Always enable SSL verification for security
        
        # Increased timeout for login - UAT API may be slow but should respond within 60s
        # connect=15s (network connection), read=60s (response), write=15s, pool=15s
        timeout_config = httpx.Timeout(connect=15.0, read=60.0, write=15.0, pool=15.0)
        
        # Log request details for troubleshooting
        logger.info(f"Request configuration: SSL_VERIFY={ssl_verify}, Timeout={timeout_config.read}s, HTTP/1.1")
        logger.info(f"Request URL: {api_url}")
        logger.info(f"Request method: POST")
        logger.info(f"Request payload size: {len(str(payload))} bytes")
        
        with httpx.Client(
            timeout=timeout_config, 
            verify=ssl_verify,  # Disabled for UAT (matches Postman)
            http2=False,  # Use HTTP/1.1 (HTTP/2 requires h2 package)
            follow_redirects=True
        ) as client:
            # Prepare headers as per LAMA Exchange API requirements
            # LAMA tech team requires Cookie header to be sent as blank
            # CRITICAL FIX: Use Linux browser User-Agent for both UAT and PROD (matching Postman working request)
            headers = {
                "Content-Type": "application/json",
                "Accept": "application/json",
                "Accept-Language": "en-US,en;q=0.9",
                "User-Agent": get_user_agent_for_environment(environment),
                "Referer": api_url,
                "Cookie": ""  # LAMA tech team requirement: send blank cookie
            }
            logger.info(f"Request headers: {headers}")
            
            # Log before sending request
            logger.info(f"[REQUEST SENT] {environment.upper()} LAMA Exchange Login API - {api_url}")
            logger.info(f"[REQUEST SENT] Payload: {payload}")
            request_timestamp = datetime.utcnow()
            
            try:
                response = client.post(
                    api_url,
                    json=payload,
                    headers=headers
                )
                response_timestamp = datetime.utcnow()
                request_duration = (response_timestamp - request_timestamp).total_seconds()
                logger.info(f"[RESPONSE RECEIVED] Status: {response.status_code}, Duration: {request_duration:.2f}s")
            except Exception as req_ex:
                logger.error(f"[REQUEST FAILED] {environment.upper()} LAMA Exchange Login API error: {str(req_ex)}")
                logger.error(f"[REQUEST FAILED] Exception type: {type(req_ex).__name__}")
                raise
            
            logger.info(f"Response status: {response.status_code}")
            logger.info(f"Response headers: {dict(response.headers)}")
            logger.info(f"Response size: {len(response.content)} bytes")
            
            # ENHANCED: Capture complete response body BEFORE parsing JSON
            # httpx caches response content, but read text first to ensure we have complete body
            response_body_text = ""
            try:
                response_body_text = response.text if response.text else ""
                # Log response body (truncated for logging, but full body stored in DB)
                response_text_preview = response_body_text[:1000] if response_body_text else ""
                logger.info(f"Response body (first 1000 chars): {response_text_preview}")
                # Also print to stderr for immediate visibility
                print(f"[LOGIN RESPONSE] Status: {response.status_code}, Body: {response_text_preview}", file=sys.stderr, flush=True)
            except Exception as e:
                logger.warning(f"Could not read response body: {e}")
                print(f"[LOGIN RESPONSE] Could not read response body: {e}", file=sys.stderr, flush=True)
            
            # Check response status
            if response.status_code == 200:
                response_data = response.json() if response.content else {}
                
                # CRITICAL: Per LAMA API Specification V1.2, login is ONLY successful if responseCode = 601
                # HTTP 200 alone is NOT sufficient - must check responseCode in response body
                response_code = response_data.get("responseCode") or response_data.get("response_code")
                response_desc = response_data.get("responseDesc") or response_data.get("response_desc") or ""
                
                # Check if responseCode is 601 (success per LAMA API spec)
                if response_code == 601 or response_code == "601":
                    logger.info(f"[SUCCESS] {environment.upper()} LAMA Exchange Login successful (responseCode: 601)")
                    # Extract token from response (per API spec)
                    token = (
                        response_data.get("token") or
                        response_data.get("accessToken") or
                        response_data.get("access_token") or
                        response_data.get("authToken") or
                        response_data.get("auth_token") or
                        response_data.get("sessionToken") or
                        response_data.get("session_token")
                    )
                    
                    if not token:
                        # CRITICAL FIX: If responseCode = 601 but token is missing, login is NOT successful
                        error_detail = "Login returned responseCode 601 but no token found in response"
                        logger.error(f"[ERROR] {error_detail}")
                        logger.error(f"[ERROR] Response data keys: {list(response_data.keys())}")
                        logger.error(f"[ERROR] Full response: {json.dumps(response_data, indent=2)}")
                        
                        # Log as failed transaction (responseCode 601 but no token = failure)
                        _log_exchange_transaction(
                            environment=environment,
                            api_url=api_url,
                            payload=payload,
                            status="failed",
                            error_message=error_detail,
                            sent_at=request_timestamp,
                            response_data=response_data,
                            status_code=200,  # HTTP status
                            request_headers=headers,
                            response_headers=dict(response.headers),
                            response_body=response_body_text,
                            metric_type="login"
                        )
                        return {
                            "success": False,
                            "message": error_detail,
                            "response_data": response_data,
                            "status_code": 200,  # HTTP status
                            "response_code": 601,  # LAMA responseCode
                            "token": None  # No token available
                        }
                    
                    # CRITICAL: Validate token is non-empty string
                    if not isinstance(token, str) or len(token.strip()) == 0:
                        error_detail = f"Login returned invalid token (type: {type(token)}, length: {len(token) if isinstance(token, str) else 'N/A'})"
                        logger.error(f"[ERROR] {error_detail}")
                        logger.error(f"[ERROR] Token value (first 50 chars): {str(token)[:50] if token else 'None'}")
                        
                        # Log as failed transaction
                        _log_exchange_transaction(
                            environment=environment,
                            api_url=api_url,
                            payload=payload,
                            status="failed",
                            error_message=error_detail,
                            sent_at=request_timestamp,
                            response_data=response_data,
                            status_code=200,
                            request_headers=headers,
                            response_headers=dict(response.headers),
                            response_body=response_body_text,
                            metric_type="login"
                        )
                        return {
                            "success": False,
                            "message": error_detail,
                            "response_data": response_data,
                            "status_code": 200,
                            "response_code": 601,
                            "token": None
                        }
                    
                    # Log successful transaction
                    _log_exchange_transaction(
                        environment=environment,
                        api_url=api_url,
                        payload=payload,
                        status="success",
                        sent_at=request_timestamp,
                        response_data=response_data,
                        status_code=200,
                        request_headers=headers,
                        response_headers=dict(response.headers),
                        response_body=response_body_text,
                        metric_type="login"
                    )
                    return {
                        "success": True,
                        "message": f"{environment.upper()} LAMA Exchange Login successful (responseCode: 601)",
                        "response_data": response_data,
                        "status_code": 200,
                        "token": token  # Include token in return value
                    }
                else:
                    # HTTP 200 but responseCode != 601 - login failed per LAMA API spec
                    error_detail = f"Login failed: responseCode {response_code} (expected 601)"
                    if response_desc:
                        error_detail += f" - {response_desc}"
                    
                    # CRITICAL: Detect Error 907 (Password attempt Limit Exceeded)
                    # Per LAMA API Specification V1.2: Account locks after 5 invalid password attempts
                    is_error_907 = (response_code == 907 or response_code == "907")
                    if is_error_907:
                        logger.error(f"[ERROR 907] ⚠️  Password attempt Limit Exceeded for {environment.upper()}")
                        logger.error(f"[ERROR 907] ⚠️  Per LAMA API spec: Account locks after 5 invalid password attempts")
                        logger.error(f"[ERROR 907] ⚠️  Response: {response_desc if response_desc else 'Password attempt Limit Exceeded'}")
                        logger.error(f"[ERROR 907] ⚠️  Full response: {json.dumps(response_data, indent=2)}")
                    else:
                        logger.error(f"[FAILED] {environment.upper()} LAMA Exchange Login failed: {error_detail}")
                        logger.error(f"[FAILED] HTTP status: 200, but responseCode: {response_code} (not 601)")
                        logger.error(f"[FAILED] Full response: {json.dumps(response_data, indent=2)}")
                    
                    # Log as failed transaction (HTTP 200 but responseCode != 601)
                    _log_exchange_transaction(
                        environment=environment,
                        api_url=api_url,
                        payload=payload,
                        status="failed",
                        error_message=error_detail,
                        sent_at=request_timestamp,
                        response_data=response_data,
                        status_code=200,  # HTTP status is 200, but responseCode indicates failure
                        request_headers=headers,
                        response_headers=dict(response.headers),
                        response_body=response_body_text,
                        metric_type="login"
                    )
                    return {
                        "success": False,
                        "message": error_detail,
                        "response_data": response_data,
                        "status_code": 200,  # HTTP status
                        "response_code": response_code  # LAMA API responseCode (e.g., 907)
                    }
            elif response.status_code == 401:
                response_body_text = response.text if response.text else ""
                response_data = response.json() if response.content else {}
                
                # CRITICAL FIX: Extract responseCode from response body even for HTTP 401
                response_code = None
                response_desc = ""
                try:
                    if isinstance(response_data, dict):
                        response_code = response_data.get("responseCode") or response_data.get("response_code")
                        response_desc = response_data.get("responseDesc") or response_data.get("response_desc") or ""
                except Exception:
                    pass
                
                error_detail = "Authentication failed (401)"
                if response_code:
                    error_detail += f" - responseCode: {response_code}"
                if response_desc:
                    error_detail += f" - {response_desc}"
                
                # CRITICAL: Detect Error 907 (Password attempt Limit Exceeded) in HTTP 401 response
                is_error_907 = (response_code == 907 or response_code == "907")
                if is_error_907:
                    logger.error(f"[ERROR 907] ⚠️  Password attempt Limit Exceeded for {environment.upper()} (HTTP 401)")
                    logger.error(f"[ERROR 907] ⚠️  Per LAMA API spec: Account locks after 5 invalid password attempts")
                    logger.error(f"[ERROR 907] ⚠️  Response: {response_desc if response_desc else 'Password attempt Limit Exceeded'}")
                    logger.error(f"[ERROR 907] ⚠️  Full response: {json.dumps(response_data, indent=2)}")
                else:
                    logger.warning(f"[FAILED] {environment.upper()} LAMA Exchange Login failed: {error_detail}")
                    logger.warning(f"[FAILED] Full response: {json.dumps(response_data, indent=2)}")
                
                _log_exchange_transaction(
                    environment=environment,
                    api_url=api_url,
                    payload=payload,
                    status="failed",
                    error_message=error_detail,
                    sent_at=request_timestamp,
                    response_data=response_data,
                    status_code=401,
                    request_headers=headers,
                    response_headers=dict(response.headers),
                    response_body=response_body_text,
                    metric_type="login"
                )
                return {
                    "success": False,
                    "message": f"{environment.upper()} LAMA Exchange Login failed: {error_detail}",
                    "status_code": 401,
                    "response_code": response_code,  # Include responseCode if available (e.g., 907)
                    "response_data": response_data
                }
            elif response.status_code == 400:
                error_detail = "Bad request"
                error_code = None
                response_data = {}
                try:
                    # Parse JSON from already-read response body text
                    try:
                        error_data = json.loads(response_body_text) if response_body_text else {}
                    except:
                        # Fallback to response.json() if parsing fails
                        error_data = response.json() if response.content else {}
                    # Check for Error 706 or other error codes in response
                    # LAMA Exchange API uses "responseCode" field (not "errorCode")
                    error_code = error_data.get("responseCode") or error_data.get("errorCode") or error_data.get("error_code") or error_data.get("code")
                    error_detail = error_data.get("responseDesc") or error_data.get("message") or error_data.get("error") or error_data.get("detail", "Bad request")
                    response_data = error_data
                    
                    # CRITICAL: Detect Error 907 (Password attempt Limit Exceeded) in HTTP 400 response
                    if error_code == 907 or error_code == "907":
                        logger.error(f"[ERROR 907] ⚠️  Password attempt Limit Exceeded for {environment.upper()} (HTTP 400)")
                        logger.error(f"[ERROR 907] ⚠️  Per LAMA API spec: Account locks after 5 invalid password attempts")
                        logger.error(f"[ERROR 907] ⚠️  Response: {error_detail}")
                        logger.error(f"[ERROR 907] ⚠️  Full response: {json.dumps(error_data, indent=2)}")
                        error_detail = f"Error 907: Password attempt Limit Exceeded - {error_detail}"
                    # Log Error 706 specifically
                    elif error_code == 706 or error_code == "706":
                        logger.error(f"[ERROR 706] Invalid request - UAT API rejected the request format")
                        logger.error(f"[ERROR 706] Response: {json.dumps(error_data, indent=2)}")
                        logger.error(f"[ERROR 706] This usually indicates:")
                        logger.error(f"[ERROR 706]   1. UAT credentials may be invalid or not activated")
                        logger.error(f"[ERROR 706]   2. UAT-specific validation requirements not met")
                        logger.error(f"[ERROR 706]   3. Request format issue (but PROD works with same format)")
                        error_detail = f"Error 706: Invalid request - {error_detail}"
                        if error_data.get("errors"):
                            logger.error(f"[ERROR 706] Additional errors: {error_data.get('errors')}")
                    else:
                        logger.error(f"[400 ERROR DETAIL] Error Code: {error_code}, Full error response: {json.dumps(error_data, indent=2)}")
                except Exception as json_err:
                    response_text = response_body_text[:1000] if response_body_text else ""
                    response_data = {"raw_response": response_text}
                    error_detail = f"Bad request - Response: {response_text[:200]}"
                    logger.error(f"[400 ERROR] Could not parse JSON response: {json_err}")
                    logger.error(f"[400 ERROR] Raw response text: {response_text}")
                
                logger.warning(f"[FAILED] {environment.upper()} LAMA Exchange Login failed: {error_detail} (400)")
                logger.error(f"[400 ERROR] Request URL: {api_url}")
                logger.error(f"[400 ERROR] Request payload keys: {list(payload.keys())}")
                logger.error(f"[400 ERROR] memberId: {payload.get('memberId', 'MISSING')}")
                logger.error(f"[400 ERROR] loginId: {payload.get('loginId', 'MISSING')}")
                logger.error(f"[400 ERROR] password length: {len(payload.get('password', ''))}")
                logger.error(f"[400 ERROR] Headers sent: {headers}")
                _log_exchange_transaction(
                    environment=environment,
                    api_url=api_url,
                    payload=payload,
                    status="failed",
                    error_message=error_detail,
                    sent_at=request_timestamp,
                    response_data=response_data,
                    status_code=400,
                    request_headers=headers,
                    response_headers=dict(response.headers),
                    response_body=response_body_text,
                    metric_type="login"
                )
                return {
                    "success": False,
                    "message": f"{environment.upper()} LAMA Exchange Login failed: {error_detail}",
                    "status_code": 400,
                    "response_code": error_code,  # Include responseCode (e.g., 706, 701, 702, 703)
                    "response_data": response_data
                }
            elif response.status_code == 503:
                # HTTP 503: Service Unavailable - server is temporarily overloaded or under maintenance
                response_data = {}
                try:
                    error_data = json.loads(response_body_text) if response_body_text else {}
                    response_data = error_data
                    error_detail = error_data.get("message", error_data.get("error", "Service Unavailable (503)"))
                except:
                    response_data = {"raw_response": response_body_text[:500] if response_body_text else ""}
                    error_detail = "Service Unavailable (503) - server temporarily unable to handle requests"
                logger.warning(f"[503 SERVICE UNAVAILABLE] {environment.upper()} LAMA Exchange Login failed: {error_detail}")
                _log_exchange_transaction(
                    environment=environment,
                    api_url=api_url,
                    payload=payload,
                    status="failed",
                    error_message=error_detail,
                    sent_at=request_timestamp,
                    response_data=response_data,
                    status_code=503,
                    request_headers=headers,
                    response_headers=dict(response.headers),
                    response_body=response_body_text,
                    metric_type="login"
                )
                return {
                    "success": False,
                    "message": f"{environment.upper()} LAMA Exchange Login failed: Service Unavailable (503) - server temporarily overloaded or under maintenance",
                    "status_code": 503,
                    "error_type": "service_unavailable"
                }
            elif response.status_code == 504:
                # HTTP 504: Gateway Timeout - server acting as gateway/proxy didn't receive timely response
                response_data = {}
                try:
                    error_data = json.loads(response_body_text) if response_body_text else {}
                    response_data = error_data
                    error_detail = error_data.get("message", error_data.get("error", "Gateway Timeout (504)"))
                except:
                    response_data = {"raw_response": response_body_text[:500] if response_body_text else ""}
                    error_detail = "Gateway Timeout (504) - upstream server did not respond in time"
                logger.warning(f"[504 GATEWAY TIMEOUT] {environment.upper()} LAMA Exchange Login failed: {error_detail}")
                _log_exchange_transaction(
                    environment=environment,
                    api_url=api_url,
                    payload=payload,
                    status="failed",
                    error_message=error_detail,
                    sent_at=request_timestamp,
                    response_data=response_data,
                    status_code=504,
                    request_headers=headers,
                    response_headers=dict(response.headers),
                    response_body=response_body_text,
                    metric_type="login"
                )
                return {
                    "success": False,
                    "message": f"{environment.upper()} LAMA Exchange Login failed: Gateway Timeout (504) - server gateway timeout",
                    "status_code": 504,
                    "error_type": "gateway_timeout"
                }
            else:
                error_detail = f"HTTP {response.status_code}"
                try:
                    # Parse JSON from already-read response body text
                    try:
                        error_data = json.loads(response_body_text) if response_body_text else {}
                    except:
                        # Fallback to response.json() if parsing fails
                        error_data = response.json() if response.content else {}
                    error_detail = error_data.get("message", error_data.get("error", error_detail))
                    response_data = error_data
                except:
                    response_data = {"raw_response": response_body_text[:500] if response_body_text else ""}
                logger.warning(f"[FAILED] {environment.upper()} LAMA Exchange Login failed: {error_detail} ({response.status_code})")
                _log_exchange_transaction(
                    environment=environment,
                    api_url=api_url,
                    payload=payload,
                    status="failed",
                    error_message=error_detail,
                    sent_at=request_timestamp,
                    response_data=response_data,
                    status_code=response.status_code,
                    request_headers=headers,
                    response_headers=dict(response.headers),
                    response_body=response_body_text,
                    metric_type="login"
                )
                return {
                    "success": False,
                    "message": f"{environment.upper()} LAMA Exchange Login failed: {error_detail}",
                    "status_code": response.status_code
                }
                
    except httpx.TimeoutException as e:
        logger.error(f"[REQUEST FAILED] {environment.upper()} LAMA Exchange Login API timeout: {str(e)}")
        logger.error(f"[REQUEST FAILED] Timeout details - URL: {api_url}, This usually means the server took too long to respond")
        logger.warning(f"[TIMEOUT] NOTE: This is a CLIENT-SIDE timeout (no HTTP response received). If server was returning HTTP 503/504, you would see those status codes instead.")
        # Log transaction for timeout (no response body available on timeout)
        # ENHANCED: Create complete payload with all details for timeout errors
        safe_payload = {
            "memberId": payload.get("memberId", ""),
            "loginId": payload.get("loginId", ""),
            "password": payload.get("password", ""),  # Already encrypted
            "password_encryption_note": "AES-ECB encrypted + Base64 encoded (safe to store)",
            "secretKey_note": "Used for password encryption but not included in request payload (per LAMA API spec)"
        }
        _log_exchange_transaction(
            environment=environment,
            api_url=api_url,
            payload=safe_payload,
            status="timeout",
            error_message=f"Client-side timeout: {str(e)} (no HTTP response received - server may be returning 503/504)",
            sent_at=request_timestamp if 'request_timestamp' in locals() else datetime.utcnow(),
            status_code=None,  # Explicitly None for client-side timeout (no HTTP response received)
            request_headers=headers if 'headers' in locals() else None,
            response_headers=None,  # No response headers on timeout
            response_body=None,  # No response body on timeout
            metric_type="login"
        )
        return {
            "success": False,
            "message": f"{environment.upper()} LAMA Exchange Login API timeout - client timeout expired (no HTTP response). Server may be returning HTTP 503 (Service Unavailable) or 504 (Gateway Timeout).",
            "error_type": "timeout",
            "note": "If server responds with HTTP 503/504, you will see those status codes instead of timeout"
        }
    except httpx.RemoteProtocolError as e:
        logger.error(f"[REQUEST FAILED] {environment.upper()} LAMA Exchange Login API - Server disconnected without sending a response: {str(e)}")
        logger.error(f"[REQUEST FAILED] Connection error details - URL: {api_url}, This usually indicates the server closed the connection unexpectedly")
        logger.error(f"[REQUEST FAILED] Possible causes: CDN/proxy rejection, server overload, network interruption, or API server down")
        # Log transaction for connection error (no response body available)
        # ENHANCED: Create complete payload with all details for connection errors
        safe_payload = {
            "memberId": payload.get("memberId", ""),
            "loginId": payload.get("loginId", ""),
            "password": payload.get("password", ""),  # Already encrypted
            "password_encryption_note": "AES-ECB encrypted + Base64 encoded (safe to store)",
            "secretKey_note": "Used for password encryption but not included in request payload (per LAMA API spec)"
        }
        _log_exchange_transaction(
            environment=environment,
            api_url=api_url,
            payload=safe_payload,
            status="timeout",  # Use "timeout" status for dashboard display consistency
            error_message=f"Server disconnected without sending a response: {str(e)}",
            sent_at=request_timestamp if 'request_timestamp' in locals() else datetime.utcnow(),
            status_code=None,  # Explicitly None for connection error (no HTTP response)
            request_headers=headers if 'headers' in locals() else None,
            response_headers=None,  # No response headers on connection error
            response_body=None,  # No response body on connection error
            metric_type="login"
        )
        return {
            "success": False,
            "message": f"{environment.upper()} LAMA Exchange Login API - Server disconnected without sending a response. The server may be down, unreachable, or rejecting connections.",
            "error_type": "connection_error"
        }
    except httpx.ConnectError as e:
        logger.error(f"[REQUEST FAILED] {environment.upper()} LAMA Exchange Login API connection error: {str(e)}")
        logger.error(f"[REQUEST FAILED] Connection error details - URL: {api_url}, This usually means the server is unreachable")
        # Log transaction for connection error (no response body available)
        # ENHANCED: Create complete payload with all details for connection errors
        safe_payload = {
            "memberId": payload.get("memberId", ""),
            "loginId": payload.get("loginId", ""),
            "password": payload.get("password", ""),  # Already encrypted
            "password_encryption_note": "AES-ECB encrypted + Base64 encoded (safe to store)",
            "secretKey_note": "Used for password encryption but not included in request payload (per LAMA API spec)"
        }
        _log_exchange_transaction(
            environment=environment,
            api_url=api_url,
            payload=safe_payload,
            status="timeout",  # Use "timeout" status for dashboard display consistency
            error_message=f"Connection error: {str(e)}",
            sent_at=request_timestamp if 'request_timestamp' in locals() else datetime.utcnow(),
            status_code=None,  # Explicitly None for connection error (no HTTP response)
            request_headers=headers if 'headers' in locals() else None,
            response_headers=None,  # No response headers on connection error
            response_body=None,  # No response body on connection error
            metric_type="login"
        )
        return {
            "success": False,
            "message": f"{environment.upper()} LAMA Exchange Login API connection error - server unreachable. Check network connectivity and firewall settings.",
            "error_type": "connection_error"
        }
    except Exception as e:
        # Catch any other unexpected errors
        logger.error(f"[REQUEST FAILED] {environment.upper()} LAMA Exchange Login API unexpected error: {str(e)}")
        logger.error(f"[REQUEST FAILED] Exception type: {type(e).__name__}")
        logger.exception("Full exception traceback:")
        # Log transaction for unexpected error
        # ENHANCED: Create complete payload with all details for unexpected errors
        safe_payload = {
            "memberId": payload.get("memberId", ""),
            "loginId": payload.get("loginId", ""),
            "password": payload.get("password", ""),  # Already encrypted
            "password_encryption_note": "AES-ECB encrypted + Base64 encoded (safe to store)",
            "secretKey_note": "Used for password encryption but not included in request payload (per LAMA API spec)"
        }
        _log_exchange_transaction(
            environment=environment,
            api_url=api_url,
            payload=safe_payload,
            status="timeout",  # Use "timeout" status for dashboard display consistency
            error_message=f"Unexpected error: {str(e)}",
            sent_at=request_timestamp if 'request_timestamp' in locals() else datetime.utcnow(),
            status_code=None,  # Explicitly None for unexpected error (no HTTP response)
            request_headers=headers if 'headers' in locals() else None,
            response_headers=None,  # No response headers on unexpected error
            response_body=None,  # No response body on unexpected error
            metric_type="login"
        )
        return {
            "success": False,
            "message": f"{environment.upper()} LAMA Exchange Login API unexpected error: {str(e)}",
            "error_type": "unknown_error"
        }


def call_lama_exchange_logout(
    environment: str,
    member_id: str,
    login_id: str,
    auth_token: str
) -> Dict[str, any]:
    """
    Call LAMA Exchange Logout API to close the current session
    
    Args:
        environment: 'prod' or 'uat'
        member_id: Member ID
        login_id: Login ID
        auth_token: Authentication token from login
        
    Returns:
        Dict with 'success' (bool), 'message' (str), and optional 'response_data'
    """
    if environment not in ['prod', 'uat']:
        return {
            "success": False,
            "message": f"Invalid environment: {environment}. Must be 'prod' or 'uat'"
        }
    
    # Determine API endpoint
    api_url = LAMA_PROD_LOGOUT_URL if environment == 'prod' else LAMA_UAT_LOGOUT_URL
    
    try:
        # Prepare request payload as per LAMA Exchange API document
        payload = {
            "memberId": member_id,
            "loginId": login_id
        }
        
        logger.info(f"Calling {environment.upper()} LAMA Exchange Logout API: {api_url}")
        logger.info(f"Request payload: memberId={member_id}, loginId={login_id}")
        
        # Make HTTP POST request
        import os
        # Disable SSL verification for both UAT and PROD to match Postman behavior
        # LAMA Exchange APIs may have certificate issues in both environments
        ssl_verify = True  # Always enable SSL verification for security
        # Reduced timeouts for faster failure detection when server disconnects
        # connect=15s (network connection), read=30s (response - fail fast if server disconnects), write=15s, pool=15s
        # Note: Reduced from 300s to 30s to prevent hanging when UAT API server disconnects
        timeout_config = httpx.Timeout(connect=15.0, read=30.0, write=15.0, pool=15.0)
        
        with httpx.Client(
            timeout=timeout_config, 
            verify=ssl_verify,
            http2=False,
            follow_redirects=True
        ) as client:
            # Prepare headers as per LAMA Exchange API requirements
            # Logout requires Authorization header with session token
            # LAMA tech team requires Cookie header to be sent as blank
            headers = {
                "Content-Type": "application/json",
                "Accept": "application/json",
                "Accept-Language": "en-US,en;q=0.9",
                "User-Agent": get_user_agent_for_environment(environment),
                "Referer": api_url,
                "Authorization": f"Bearer {auth_token}",
                "Cookie": ""  # LAMA tech team requirement: send blank cookie
            }
            logger.info(f"Request headers: {headers}")
            
            logger.info(f"[REQUEST SENT] {environment.upper()} LAMA Exchange Logout API - {api_url}")
            request_timestamp = datetime.utcnow()
            
            try:
                response = client.post(
                    api_url,
                    json=payload,
                    headers=headers
                )
                response_timestamp = datetime.utcnow()
                request_duration = (response_timestamp - request_timestamp).total_seconds()
                logger.info(f"[RESPONSE RECEIVED] Status: {response.status_code}, Duration: {request_duration:.2f}s")
            except Exception as req_ex:
                logger.error(f"[REQUEST FAILED] {environment.upper()} LAMA Exchange Logout API error: {str(req_ex)}")
                raise
            
            logger.info(f"Response status: {response.status_code}")
            
            # ENHANCED: Capture complete response body for logging
            response_body_text = response.text if response.text else ""
            
            # Check response status
            if response.status_code == 200:
                response_data = response.json() if response.content else {}
                logger.info(f"[SUCCESS] {environment.upper()} LAMA Exchange Logout API call successful")
                
                # Log transaction
                _log_exchange_transaction(
                    environment=environment,
                    api_url=api_url,
                    payload=payload,
                    status="success",
                    sent_at=request_timestamp,
                    response_data=response_data,
                    status_code=200,
                    request_headers=headers,
                    response_headers=dict(response.headers),
                    response_body=response_body_text,
                    metric_type="logout"
                )
                
                return {
                    "success": True,
                    "message": f"{environment.upper()} LAMA Exchange Logout successful",
                    "response_data": response_data,
                    "status_code": 200
                }
            elif response.status_code == 401:
                response_body_text = response.text if response.text else ""
                response_data = response.json() if response.content else {}
                logger.warning(f"[FAILED] {environment.upper()} LAMA Exchange Logout failed: Unauthorized (401)")
                _log_exchange_transaction(
                    environment=environment,
                    api_url=api_url,
                    payload=payload,
                    status="failed",
                    error_message="Unauthorized - Invalid token",
                    sent_at=request_timestamp,
                    response_data=response_data,
                    status_code=401,
                    request_headers=headers,
                    response_headers=dict(response.headers),
                    response_body=response_body_text,
                    metric_type="logout"
                )
                return {
                    "success": False,
                    "message": f"{environment.upper()} LAMA Exchange Logout failed: Unauthorized token",
                    "status_code": 401
                }
            elif response.status_code == 400:
                error_detail = "Bad request"
                try:
                    # Parse JSON from already-read response body text
                    try:
                        error_data = json.loads(response_body_text) if response_body_text else {}
                    except:
                        # Fallback to response.json() if parsing fails
                        error_data = response.json() if response.content else {}
                    error_detail = error_data.get("message", error_data.get("error", "Bad request"))
                    response_data = error_data
                except:
                    response_data = {"raw_response": response_body_text[:500] if response_body_text else ""}
                logger.warning(f"[FAILED] {environment.upper()} LAMA Exchange Logout failed: {error_detail} (400)")
                _log_exchange_transaction(
                    environment=environment,
                    api_url=api_url,
                    payload=payload,
                    status="failed",
                    error_message=error_detail,
                    sent_at=request_timestamp,
                    response_data=response_data,
                    status_code=400,
                    request_headers=headers,
                    response_headers=dict(response.headers),
                    response_body=response_body_text,
                    metric_type="logout"
                )
                return {
                    "success": False,
                    "message": f"{environment.upper()} LAMA Exchange Logout failed: {error_detail}",
                    "status_code": 400
                }
            else:
                error_detail = f"HTTP {response.status_code}"
                try:
                    # Parse JSON from already-read response body text
                    try:
                        error_data = json.loads(response_body_text) if response_body_text else {}
                    except:
                        # Fallback to response.json() if parsing fails
                        error_data = response.json() if response.content else {}
                    error_detail = error_data.get("message", error_data.get("error", error_detail))
                    response_data = error_data
                except:
                    response_data = {"raw_response": response_body_text[:500] if response_body_text else ""}
                logger.warning(f"[FAILED] {environment.upper()} LAMA Exchange Logout failed: {error_detail} ({response.status_code})")
                _log_exchange_transaction(
                    environment=environment,
                    api_url=api_url,
                    payload=payload,
                    status="failed",
                    error_message=error_detail,
                    sent_at=request_timestamp,
                    response_data=response_data,
                    status_code=response.status_code,
                    request_headers=headers,
                    response_headers=dict(response.headers),
                    response_body=response_body_text,
                    metric_type="logout"
                )
                return {
                    "success": False,
                    "message": f"{environment.upper()} LAMA Exchange Logout failed: {error_detail}",
                    "status_code": response.status_code
                }
                
    except httpx.TimeoutException as e:
        logger.error(f"[REQUEST FAILED] {environment.upper()} LAMA Exchange Logout API timeout: {str(e)}")
        logger.error(f"[REQUEST FAILED] Timeout details - URL: {api_url}, This usually means the server took too long to respond")
        # Log transaction for timeout
        # ENHANCED: Create complete payload with all details for timeout errors
        safe_payload = payload.copy() if payload else {}
        _log_exchange_transaction(
            environment=environment,
            api_url=api_url,
            payload=safe_payload,
            status="timeout",
            error_message=f"Request timeout: {str(e)}",
            sent_at=request_timestamp if 'request_timestamp' in locals() else datetime.utcnow(),
            status_code=None,  # Explicitly None for timeout (no HTTP response)
            request_headers=headers if 'headers' in locals() else None,
            response_headers=None,  # No response headers on timeout
            response_body=None,  # No response body on timeout
            metric_type="logout"
        )
        return {
            "success": False,
            "message": f"{environment.upper()} LAMA Exchange Logout API timeout - please check your network connection. The server may be slow or unreachable.",
            "error_type": "timeout"
        }
    except httpx.ConnectError as e:
        logger.error(f"[REQUEST FAILED] {environment.upper()} LAMA Exchange Logout API connection error: {str(e)}")
        logger.error(f"[REQUEST FAILED] Connection error details - URL: {api_url}, This usually means the server is unreachable")
        # Log transaction for connection error
        # ENHANCED: Create complete payload with all details for connection errors
        safe_payload = payload.copy() if payload else {}
        _log_exchange_transaction(
            environment=environment,
            api_url=api_url,
            payload=safe_payload,
            status="connection_error",
            error_message=f"Connection error: {str(e)}",
            sent_at=request_timestamp if 'request_timestamp' in locals() else datetime.utcnow(),
            status_code=None,  # Explicitly None for connection error (no HTTP response)
            request_headers=headers if 'headers' in locals() else None,
            response_headers=None,  # No response headers on connection error
            response_body=None,  # No response body on connection error
            metric_type="logout"
        )
        return {
            "success": False,
            "message": f"{environment.upper()} LAMA Exchange Logout API connection error - unable to reach server: {str(e)}",
            "error_type": "connection"
        }
    except httpx.RequestError as e:
        logger.error(f"[REQUEST FAILED] {environment.upper()} LAMA Exchange Logout API request error: {e}")
        logger.error(f"[REQUEST FAILED] Request error details - URL: {api_url}, Error: {str(e)}")
        # Log transaction for request error
        _log_exchange_transaction(
            environment=environment,
            api_url=api_url,
            payload=payload,
            status="request_error",
            error_message=f"Request error: {str(e)}",
            sent_at=datetime.utcnow(),
            request_headers=headers if 'headers' in locals() else None,
            metric_type="logout"
        )
        return {
            "success": False,
            "message": f"{environment.upper()} LAMA Exchange Logout API request error: {str(e)}",
            "error_type": "request_error"
        }
    except Exception as e:
        logger.error(f"[ERROR] Unexpected error in {environment.upper()} LAMA Exchange Logout API: {e}", exc_info=True)
        # Log transaction for general error
        _log_exchange_transaction(
            environment=environment,
            api_url=api_url,
            payload=payload,
            status="error",
            error_message=f"Error: {str(e)}",
            sent_at=datetime.utcnow(),
            request_headers=headers if 'headers' in locals() else None,
            metric_type="logout"
        )
        return {
            "success": False,
            "message": f"Unexpected error during {environment.upper()} LAMA Exchange Logout: {str(e)}",
            "error_type": "unexpected_error"
        }


def get_next_sequence_id(environment: str, member_id: str, exchange_id: int, metric_type: str = None, expected_seq_id_hint: int = None, scheduler_name: str = None) -> int:
    """
    THREAD-SAFE Sequence ID Generator — zero 704 design.
    
    Sequence counter is GLOBAL per (environment, metric_type) — shared across
    all exchanges (NSE, BSE, MCX, NCDEX).
    
    On first call (after restart): seeds cache from MAX(all 601s, all 704 hints) in DB.
    Every subsequent call: pure cache increment, no DB query.
    """
    import threading
    if not hasattr(get_next_sequence_id, "_locks"):
        get_next_sequence_id._locks = {}
        get_next_sequence_id._manager_lock = threading.Lock()
        get_next_sequence_id._last_issued = {}
        get_next_sequence_id._seeded = set()

    m_type = metric_type if metric_type else "global"
    lock_key = (environment.lower(), m_type)

    with get_next_sequence_id._manager_lock:
        if lock_key not in get_next_sequence_id._locks:
            get_next_sequence_id._locks[lock_key] = threading.Lock()
        lock = get_next_sequence_id._locks[lock_key]

    exchange_name = {1: "NSE", 2: "BSE", 4: "MCX", 5: "NCDEX"}.get(exchange_id, f"Exch-{exchange_id}")

    with lock:
        # Priority 1: 704 hint from exchange — always trust it
        if expected_seq_id_hint:
            get_next_sequence_id._last_issued[lock_key] = expected_seq_id_hint
            logger.info(f"[SEQ_ID] {exchange_name} {m_type}: 704 hint → {expected_seq_id_hint}")
            return expected_seq_id_hint

        # Priority 2: Seed cache from DB on first call (survives container restart)
        if lock_key not in get_next_sequence_id._seeded:
            try:
                from app.db.db import engine
                with engine.connect() as conn:
                    row = conn.execute(text("""
                        SELECT GREATEST(
                            COALESCE((SELECT MAX(CAST(sequence_id AS INTEGER))
                                      FROM exchange_transactions
                                      WHERE environment = :env AND metric_type = :mtype
                                        AND sequence_id ~ '^[0-9]+$$' AND status_code = 601), 0),
                            COALESCE((SELECT MAX(CAST(exchange_response->>'expectedSequenceId' AS INTEGER))
                                      FROM exchange_transactions
                                      WHERE environment = :env AND metric_type = :mtype
                                        AND status_code = 704
                                        AND exchange_response->>'expectedSequenceId' IS NOT NULL), 0)
                        )
                    """), {"env": environment.lower(), "mtype": m_type}).scalar()
                    seed = int(row) if row else 0
                    get_next_sequence_id._last_issued[lock_key] = seed
                    get_next_sequence_id._seeded.add(lock_key)
                    logger.info(f"[SEQ_ID] 🔑 {m_type}: Seeded from DB → {seed}")
            except Exception as e:
                logger.error(f"[SEQ_ID] {m_type}: Seed error: {e}")
                get_next_sequence_id._seeded.add(lock_key)

        # Priority 3: Atomic increment from cache
        cached_id = get_next_sequence_id._last_issued.get(lock_key, 0)
        next_id = cached_id + 1
        get_next_sequence_id._last_issued[lock_key] = next_id
        logger.info(f"[SEQ_ID] {exchange_name} {m_type}: {cached_id} → {next_id}")
        return next_id


def rollback_sequence_id(environment: str, metric_type: str):
    """Roll back sequence cache by 1 after a failed send (503, timeout, etc).
    Called when exchange did NOT consume the sequence (non-601, non-704)."""
    m_type = metric_type if metric_type else "global"
    lock_key = (environment.lower(), m_type)
    if hasattr(get_next_sequence_id, "_last_issued"):
        current = get_next_sequence_id._last_issued.get(lock_key, 0)
        if current > 0:
            get_next_sequence_id._last_issued[lock_key] = current - 1


def update_sequence_cache_after_704(environment: str, exchange_id: int, metric_type: str, hinted_seq_id: int):
    """Update process cache after 704 — only move FORWARD, never rewind."""
    m_type = metric_type if metric_type else "global"
    lock_key = (environment.lower(), m_type)
    exchange_name = {1: "NSE", 2: "BSE", 4: "MCX", 5: "NCDEX"}.get(exchange_id, f"Exch-{exchange_id}")

    if hasattr(get_next_sequence_id, "_last_issued"):
        current = get_next_sequence_id._last_issued.get(lock_key, 0)
        # CRITICAL: Only move forward. Never rewind — other sends may have already incremented past this.
        if hinted_seq_id > current:
            get_next_sequence_id._last_issued[lock_key] = hinted_seq_id
            logger.info(f"[SEQ_ID] {exchange_name} {m_type}: Cache advanced {current} → {hinted_seq_id} (704 hint)")
        else:
            logger.info(f"[SEQ_ID] {exchange_name} {m_type}: Ignoring 704 hint {hinted_seq_id} (cache already at {current})")

def _log_exchange_transaction(
    environment: str,
    api_url: str,
    payload: dict,
    status: str,
    error_message: str = None,
    sent_at: datetime = None,
    response_data: dict = None,
    status_code: int = None,
    request_headers: dict = None,
    response_headers: dict = None,
    response_body: str = None,
    metric_type: str = "login"
):
    """Helper function to log exchange transactions to database"""
    try:
        with engine.connect() as conn:
            # ENHANCED: Store complete payload with all details
            # Password is already encrypted (AES-ECB + Base64), safe to store
            complete_payload = payload.copy()
            
            # Add metadata about password encryption (for display clarity)
            if "password" in complete_payload:
                # Password is already encrypted, safe to store as-is
                complete_payload["password_encryption_note"] = "AES-ECB encrypted + Base64 encoded (safe to store)"
            
            # Note: secretKey is used for encryption but NOT sent in request payload
            if metric_type in ["login"]:
                complete_payload["secretKey_note"] = "Used for password encryption but not included in request payload (per LAMA API spec)"
            
            # Include complete request headers and metadata
            if request_headers:
                complete_payload["request_headers"] = request_headers
                complete_payload["request_url"] = api_url
                complete_payload["request_method"] = "POST"
            
            # ENHANCED: Store complete response body and headers
            enhanced_response_data = response_data.copy() if response_data else {}
            
            # Store complete response body (for debugging and analysis)
            if response_body:
                enhanced_response_data["response_body_raw"] = response_body
                # Try to parse as JSON if possible
                try:
                    import json
                    enhanced_response_data["response_body_json"] = json.loads(response_body)
                except:
                    pass  # Keep as raw text if not JSON
            
            if response_headers:
                enhanced_response_data["response_headers"] = response_headers
            
            insert_query = exchange_transactions_table.insert().values(
                environment=environment,
                server_id=None,
                server_name="LOGIN_REQUEST" if metric_type == "login" else "LOGOUT_REQUEST",
                server_ip=None,
                member_id=payload.get("memberId"),
                instance_id=None,
                metric_type=metric_type,
                metrics_sent=complete_payload,  # Complete payload with all details
                sequence_id=None,
                record_type='sent',
                exchange_response=enhanced_response_data if enhanced_response_data else None,
                status=status,
                status_code=status_code,
                error_message=error_message,
                sent_at=sent_at or datetime.now(timezone.utc),
                response_received_at=datetime.now(timezone.utc) if enhanced_response_data else None
            )
            conn.execute(insert_query)
            conn.commit()
            logger.debug(f"{metric_type.title()} transaction logged: Status={status}, Environment={environment}")
    except Exception as e:
        logger.error(f"Failed to log exchange transaction: {e}", exc_info=True)
        # Don't fail the main operation if transaction logging fails


def can_send_to_exchange(environment: str, exchange_id: int, metric_type: str, location_id: int = None) -> tuple:
    """
    Check if we can send to this exchange (not blocked by 705 prevention).
    V1.3 update: Scopes checking to specific location_id to allow multiple sites in one cycle.
    
    Returns:
        (True, None) if can send
        (False, reason) if blocked
    """
    try:
        with engine.connect() as conn:
            # Base query components
            where_clause = "environment = :environment AND metric_type = :metric_type AND exchange_id = :exchange_id AND status = 'success'"
            params = {
                "environment": environment,
                "metric_type": metric_type,
                "exchange_id": exchange_id
            }

            # Scoping by location_id (CRITICAL for multi-site LAMA V1.3)
            # Use IS NOT DISTINCT FROM for NULL-safe comparison in PostgreSQL
            if location_id is not None:
                where_clause += " AND (location_id = :location_id OR (location_id IS NULL AND :location_id = 1))"
                params["location_id"] = location_id

            last_sent_query = text(f""" -- Global History Anchor

                SELECT sent_at
                FROM exchange_transactions
                WHERE {where_clause}
                ORDER BY sent_at DESC
                LIMIT 1
            """)
            
            result = conn.execute(last_sent_query, params).fetchone()
            
            if result and result[0]:
                last_sent_time = result[0]
                # FIX: PostgreSQL (Asia/Kolkata) stores timestamps in IST. 
                # Comparing with utcnow() causes a ~5.5 hour mismatch.
                time_since_last = datetime.now() - last_sent_time
                min_interval = timedelta(minutes=4, seconds=50)
                if time_since_last < min_interval:
                    minutes_remaining = (min_interval - time_since_last).total_seconds() / 60
                    return (False, f"705 prevention for loc_{location_id}: {minutes_remaining:.1f}min remaining")

            # NEW: Stuck Loop Protection (704 Storm Circuit Breaker)
            # If we see 3+ 704 errors in the last 2 minutes for this SPECIFIC location/metric, 
            # the system is likely in a drift state. Pause for 1 cycle.
            storm_where = "environment = :environment AND exchange_id = :exchange_id AND metric_type = :metric_type AND status_code = 704 AND sent_at > (NOW() - INTERVAL '2 minutes')"
            storm_params = {"environment": environment, "exchange_id": exchange_id, "metric_type": metric_type}
            
            if location_id is not None:
                storm_where += " AND (location_id = :location_id OR (location_id IS NULL AND :location_id = 1))"
                storm_params["location_id"] = location_id

            storm_query = text(f"""
                SELECT COUNT(*)
                FROM exchange_transactions
                WHERE {storm_where}
            """)
            storm_count = conn.execute(storm_query, storm_params).scalar()

            if storm_count >= 3:
                logger.critical(f"[CIRCUIT BREAKER] 🚨 704 Storm detected for {metric_type} at loc_{location_id} ({storm_count} errors in 2m). Pausing sending for this cycle.")
                return (False, f"Circuit Breaker: 704 Storm ({storm_count} errors) for loc_{location_id}")

            return (True, None)
    except Exception as e:
        logger.warning(f"[705_CHECK] Error checking 705 status: {e}")
        return (True, None)  # Allow send on error


def send_metrics_to_lama_exchange(
    environment: str,
    member_id: str,
    instance_id: str,
    metrics: list,
    auth_token: str = None,
    metric_type: str = "hardware",
    server_id: int = None,
    server_name: str = None,
    server_ip: str = None,
    exchange_id: int = None,
    application_id: int = None,
    sequence_id: int = None,
    sent_at: datetime = None,
    nse_timestamp: int = None,
    expected_seq_id_hint: Optional[int] = None,
    scheduler_name: str = None,
    skip_705_check: bool = False,
    stored_metrics: List[dict] = None,
    location_id: int = None,
    batched_payload: List[dict] = None
) -> Dict[str, any]:
    """
    Send metrics data to LAMA Exchange API and track transaction
    
    CRITICAL: This function applies the same logic for ALL metric types and BOTH environments:
    - Metric Types: 'hardware' (System), 'network', 'database', 'application'
    - Environments: 'prod' (PROD), 'uat' (UAT)
    - Success Determination: ONLY responseCode 601 = SUCCESS, all other codes = FAILED
    - Response Codes: All response codes are captured and stored for audit purposes
    
    Args:
        environment: 'prod' or 'uat' (applies to both PROD and UAT)
        member_id: Member ID
        instance_id: Server instance ID (IP or server name)
        metrics: List of metric dictionaries with 'name', 'min', 'max', 'avg', 'med'
        auth_token: Optional authentication token (if not provided, will login first)
        metric_type: Type of metrics - 'hardware' (System), 'network', 'database', or 'application'
                     All metric types use the same success determination logic (responseCode 601)
        server_id: Server ID for tracking
        server_name: Server name for tracking
        server_ip: Server IP for tracking
        scheduler_name: Optional scheduler name for logging (e.g., 'Hardware-Scheduler', 'Network-Scheduler')
        
    Returns:
        Dict with 'success' (bool), 'message' (str), and 'transaction_id' (int)
        - success=True only if responseCode == 601
        - success=False for all other response codes (602, 603, 704, 708, 801, etc.)
    """
    if environment not in ['prod', 'uat']:
        return {
            "success": False,
            "message": f"Invalid environment: {environment}. Must be 'prod' or 'uat'"
        }
    
    if metric_type not in ['hardware', 'network', 'database', 'application']:
        return {
            "success": False,
            "message": f"Invalid metric_type: {metric_type}. Must be 'hardware', 'network', 'database', or 'application'"
        }
    
    # Determine API endpoint based on metric type
    endpoint_map = {
        'hardware': (LAMA_PROD_METRICS_HARDWARE_URL, LAMA_UAT_METRICS_HARDWARE_URL),
        'network': (LAMA_PROD_METRICS_NETWORK_URL, LAMA_UAT_METRICS_NETWORK_URL),
        'database': (LAMA_PROD_METRICS_DATABASE_URL, LAMA_UAT_METRICS_DATABASE_URL),
        'application': (LAMA_PROD_METRICS_APPLICATION_URL, LAMA_UAT_METRICS_APPLICATION_URL)
    }
    
    api_url = endpoint_map[metric_type][0] if environment == 'prod' else endpoint_map[metric_type][1]
    
    # If no auth token provided, we need to login first
    # For now, we'll assume the token is passed or we'll need to implement token caching
    if not auth_token:
        logger.warning(f"No auth token provided for {environment.upper()} metrics send. Token management needed.")
        # TODO: Implement token caching/management
    
    # Set defaults for V1.2 parameters
    if exchange_id is None:
        exchange_id = DEFAULT_EXCHANGE_ID
    if application_id is None:
        application_id = DEFAULT_APPLICATION_ID
    # CRITICAL: Validate 5-minute interval (Error 705 prevention)
    # Per LAMA API spec: Data cannot be pushed within 5 minutes of last push
    # NOTE: Can skip this check if caller already verified (for parallel send optimization)
    if not skip_705_check:
        try:
            with engine.connect() as conn:
                # Check last successful send for this (environment, exchange_id, metric_type)
                last_sent_query = text(""" -- Global History Anchor

                    SELECT sent_at
                    FROM exchange_transactions
                    WHERE environment = :environment
                      AND metric_type = :metric_type
                      AND exchange_id = :exchange_id
                      AND status = 'success'
                    ORDER BY sent_at DESC
                    LIMIT 1
                """)
                
                last_sent_result = conn.execute(
                    last_sent_query,
                    {
                        "environment": environment,
                        "metric_type": metric_type,
                        "exchange_id": exchange_id
                    }
                ).fetchone()
                if last_sent_result and last_sent_result[0]:
                    last_sent_time = last_sent_result[0]
                    # FIX: PG stores IST — must compare with datetime.now() not utcnow()
                    time_since_last = datetime.now() - last_sent_time
                    # REDUCED from 5 minutes to 4:50 to give 10-second buffer for scheduler timing
                    min_interval = timedelta(minutes=4, seconds=50)
                    if time_since_last < min_interval:
                        minutes_remaining = (min_interval - time_since_last).total_seconds() / 60
                        logger.warning(f"[705_PREVENTION] Last successful send was {time_since_last.total_seconds():.0f}s ago (< 4:50). Waiting {minutes_remaining:.1f} minutes to prevent Error 705...")
                        return {
                            "success": False,
                            "message": f"{environment.upper()} LAMA Exchange metrics: Cannot send within 5 minutes of last push (Error 705 prevention). Last send was {time_since_last.total_seconds():.0f}s ago. Wait {minutes_remaining:.1f} minutes.",
                            "response_code": None,
                            "should_wait": True,
                            "wait_seconds": int(minutes_remaining * 60) + 10  # Add 10s buffer
                        }
        except Exception as e:
            logger.warning(f"[705_PREVENTION] Error checking last sent time: {e}, proceeding with send")
    
    # LONG-TERM FIX: Check token expiry before EACH API call (not just once)
    # Re-check token expiry even if provided (token might have expired since it was obtained)
    from app.utils.lama_token_cache import get_lama_exchange_token
    if auth_token:
        fresh_token = get_lama_exchange_token(environment, exchange_id=exchange_id, scheduler_name=scheduler_name)
        if fresh_token and fresh_token != auth_token:
            # Token was refreshed - use new token
            logger.info(f"[TOKEN] Token was refreshed during operation, using new token for {environment.upper()} exchange_id={exchange_id}")
            auth_token = fresh_token
        elif not fresh_token:
            # Token expired and login failed
            logger.error(f"[TOKEN] Token expired during operation and login failed for {environment.upper()} exchange_id={exchange_id}")
            return {
                "success": False,
                "message": "Token expired during operation and login failed",
                "error_type": "authentication_error"
            }
    
    # CRITICAL: Get sequence ID BEFORE making the API call
    # If sequence_id is not provided, get it from the database
    # This ensures we use the correct sequence ID based on previous transactions
    calculated_sequence_id = sequence_id
    reservation_id = None
    
    if calculated_sequence_id is None:
        # Get the next sequence ID by finding the MAX sequence_id sent for this specific exchange and metric type
        # CRITICAL: Sequence ID must increment per (environment, member_id, exchange_id, metric_type)
        # Each metric type (hardware, network, database, application) maintains its own independent sequence ID counter
        # If expected_seq_id_hint is provided (from Error 704 retry), use it directly
        calculated_sequence_id = get_next_sequence_id(environment, member_id, exchange_id, metric_type, expected_seq_id_hint=expected_seq_id_hint, scheduler_name=scheduler_name)
        
        # LONG-TERM FIX: Handle None return value (calculation error)
        if calculated_sequence_id is None:
            logger.error(f"❌ CRITICAL: Sequence ID calculation returned None for {environment.upper()}/exchange_id={exchange_id}/metric_type={metric_type}/member_id={member_id}")
            logger.error("This indicates a database error or calculation failure. Cannot proceed without sequence ID.")
            return {
                "success": False,
                "message": "Failed to calculate sequence ID (database error)",
                "error_type": "sequence_id_error"
            }
        
        logger.info(f"Generated sequence_id {calculated_sequence_id} for {environment.upper()}/exchange_id={exchange_id}/metric_type={metric_type}/member_id={member_id} (hint: {expected_seq_id_hint})")
        
    sequence_id = calculated_sequence_id
    
    # Validate exchange_id and application_id
    if not validate_exchange_id(exchange_id):
        logger.warning(f"Invalid exchange_id {exchange_id}, using default {DEFAULT_EXCHANGE_ID}")
        exchange_id = DEFAULT_EXCHANGE_ID
    if not validate_application_id(application_id):
        logger.warning(f"Invalid application_id {application_id}, using default {DEFAULT_APPLICATION_ID}")
        application_id = DEFAULT_APPLICATION_ID
    
    # Get exchange name for logging
    exchange_name = {1: "NSE", 2: "BSE", 4: "MCX", 5: "NCDEX"}.get(exchange_id, f"Exchange {exchange_id}")
    
    # Convert metrics from {name, min, max, avg, med} format to V1.2 {key, value} format
    # IMPORTANT: As per LAMA API v1.2 specification:
    # - Most metrics use object format: {min, max, avg, med}
    # - Some metrics use simple values (plain number or string):
    #   * Hardware/Network: packetCount, lookupCount (numeric)
    #   * Application: failureTradeApi, failureAuthentication (numeric), log (string)
    #   * Database: status (numeric)
    PLAIN_VALUE_METRICS = {
        "packetCount", "lookupCount",  # Hardware/Network
        "failureTradeApi", "failureAuthentication", "log",  # Application
        "status"  # Database
    }
    
    # Build metric_data array with both object and plain value metrics in SINGLE applicationId entry
    metric_data = []
    for metric in metrics:
        if isinstance(metric, dict):
            metric_name = metric.get("name", "")
            
            # Check if this metric should be a simple value (not an object)
            if metric_name in PLAIN_VALUE_METRICS:
                # Plain value for these specific metrics
                raw_value = metric.get("value", metric.get("avg", 0))
                if metric_name == "log":
                    # Log is a string
                    metric_data.append({
                        "key": metric_name,
                        "value": str(raw_value) if raw_value else ""
                    })
                else:
                    # Numeric plain value (failureTradeApi, failureAuthentication, status, packetCount, lookupCount)
                    metric_data.append({
                        "key": metric_name,
                        "value": int(raw_value) if raw_value else 0
                    })
            else:
                # Object format with min, max, avg, med for other metrics
                metric_min = metric.get("min", 0)
                metric_max = metric.get("max", 0)
                metric_avg = metric.get("avg", 0)
                metric_med = metric.get("med", 0)
                
                metric_data.append({
                    "key": metric_name,
                    "value": {
                        "min": float(metric_min),
                        "max": float(metric_max),
                        "avg": float(metric_avg),
                        "med": float(metric_med)
                    }
                })
    
    # Get NSE epoch timestamp (use provided or generate new)
    if nse_timestamp is None:
        nse_timestamp = get_nse_timestamp_ms()
    
    # Prepare V1.2 compliant payload structure
    # Use provided sent_at timestamp (for parallel execution) or generate new
    if sent_at is None:
        sent_at = datetime.utcnow()
    
    if batched_payload:
        # Use provided batched payload array directly
        payload = {
            "payload": batched_payload,
            "exchangeId": exchange_id,
            "memberId": member_id,
            "sequenceId": sequence_id,
            "timestamp": nse_timestamp
        }
        if location_id is not None:
            payload["locationId"] = location_id
    else:
        # Single entry payload (Legacy/Hardware/Network/Database)
        payload_item = {
            "applicationId": application_id if application_id is not None else -1,
            "metricData": metric_data
        }
            
        payload = {
            "payload": [payload_item],
            "exchangeId": exchange_id,
            "memberId": member_id,
            "sequenceId": sequence_id,
            "timestamp": nse_timestamp
        }
        if location_id is not None:
            payload["locationId"] = location_id
    
    # Skip Hardware/Network/Database - use common logic above
    if False:
        # For Hardware/Network/Database: Keep existing single-entry logic
        metric_data = []
        for metric in metrics:
            if isinstance(metric, dict):
                metric_name = metric.get("name", "")
                
                # Check if this metric should be a simple value (not an object)
                if metric_name in PLAIN_VALUE_METRICS:
                    # Plain value for these specific metrics
                    raw_value = metric.get("value", metric.get("avg", 0))
                    if metric_name == "log":
                        # Log is a string
                        metric_data.append({
                            "key": metric_name,
                            "value": str(raw_value) if raw_value else ""
                        })
                    else:
                        # Numeric plain value (failureTradeApi, failureAuthentication, status, packetCount, lookupCount)
                        metric_data.append({
                            "key": metric_name,
                            "value": int(raw_value) if raw_value else 0
                        })
                else:
                    # Object format with min, max, avg, med for other metrics
                    metric_min = metric.get("min", 0)
                    metric_max = metric.get("max", 0)
                    metric_avg = metric.get("avg", 0)
                    metric_med = metric.get("med", 0)
                    
                    metric_data.append({
                        "key": metric_name,
                        "value": {
                            "min": float(metric_min),
                            "max": float(metric_max),
                            "avg": float(metric_avg),
                            "med": float(metric_med)
                        }
                    })
        
        # Get NSE epoch timestamp (use provided or generate new)
        if nse_timestamp is None:
            nse_timestamp = get_nse_timestamp_ms()
        
        # Prepare V1.2 compliant payload structure
        # Use provided sent_at timestamp (for parallel execution) or generate new
        if sent_at is None:
            sent_at = datetime.utcnow()
        payload = {
            "payload": [
                {
                    "applicationId": application_id,
                    "metricData": metric_data
                }
            ],
            "exchangeId": exchange_id,
            "memberId": member_id,
            "sequenceId": sequence_id,
            "timestamp": nse_timestamp
        }
    
    # PRE-SEND VALIDATION (Error Prevention)
    # Validate payload structure (Error 603 prevention)
    is_valid, validation_error = validate_payload_structure(payload)
    if not is_valid:
        logger.error(f"[VALIDATION] Payload structure validation failed: {validation_error}")
        return {
            "success": False,
            "message": f"{environment.upper()} LAMA Exchange payload validation failed: {validation_error}",
            "response_code": None,
            "validation_error": True,
            "requires_admin_attention": True
        }
    
    # Track valid metrics through validation chain
    current_metrics = metrics
    
    # Validate metric keys (Error 707 prevention)
    is_valid, validation_error, current_metrics = validate_metric_keys(current_metrics, metric_type)
    if not is_valid:
        logger.warning(f"[VALIDATION] Invalid metric keys detected: {validation_error}")
        # Remove invalid metrics and continue with valid ones
        if current_metrics:
            logger.info(f"[VALIDATION] Continuing with {len(current_metrics)} valid metrics (removed invalid keys)")
        else:
            logger.error(f"[VALIDATION] No valid metrics remaining after key validation")
            return {
                "success": False,
                "message": f"{environment.upper()} LAMA Exchange validation failed: {validation_error}",
                "response_code": None,
                "validation_error": True,
                "requires_config_fix": True
            }
    
    # Validate metric values (Error 708 prevention)
    is_valid, validation_error, current_metrics = validate_metric_values(current_metrics)
    if not is_valid:
        logger.warning(f"[VALIDATION] Invalid metric values detected: {validation_error}")
        # Remove invalid metrics and continue with valid ones
        if current_metrics:
            logger.info(f"[VALIDATION] Continuing with {len(current_metrics)} valid metrics (removed invalid values)")
        else:
            logger.error(f"[VALIDATION] No valid metrics remaining after value validation")
            return {
                "success": False,
                "message": f"{environment.upper()} LAMA Exchange validation failed: {validation_error}",
                "response_code": None,
                "validation_error": True,
                "requires_config_fix": True
            }
    
    # Validate null/blank fields (Error 901 prevention)
    is_valid, validation_error, current_metrics = validate_null_blank_fields(current_metrics)
    if not is_valid:
        logger.warning(f"[VALIDATION] Null/blank values detected: {validation_error}")
        # Remove invalid metrics and continue with valid ones
        if current_metrics:
            logger.info(f"[VALIDATION] Continuing with {len(current_metrics)} valid metrics (removed null/blank values)")
        else:
            logger.error(f"[VALIDATION] No valid metrics remaining after null/blank validation")
            return {
                "success": False,
                "message": f"{environment.upper()} LAMA Exchange validation failed: {validation_error}",
                "response_code": None,
                "validation_error": True,
                "requires_config_fix": True
            }
    
    # Rebuild metric_data with validated metrics
    if current_metrics != metrics:
        logger.info(f"[VALIDATION] Rebuilding metric_data with {len(current_metrics)} validated metrics (removed {len(metrics) - len(current_metrics)} invalid)")
        metric_data = []
        for metric in current_metrics:
            metric_name = metric.get("name", "")
            # Use same PLAIN_VALUE_METRICS check as above
            if metric_name in PLAIN_VALUE_METRICS:
                raw_value = metric.get("value", metric.get("avg", 0))
                if metric_name == "log":
                    metric_data.append({
                        "key": metric_name,
                        "value": str(raw_value) if raw_value else ""
                    })
                else:
                    metric_data.append({
                        "key": metric_name,
                        "value": int(raw_value) if raw_value else 0
                    })
            else:
                metric_data.append({
                    "key": metric_name,
                    "value": {
                        "min": float(metric.get("min", 0)),
                        "max": float(metric.get("max", 0)),
                        "avg": float(metric.get("avg", 0)),
                        "med": float(metric.get("med", 0))
                    }
                })
        # Update payload with cleaned metric_data
        payload["payload"][0]["metricData"] = metric_data
    
    # Check for duplicate records (Error 709 prevention)
    has_duplicates, duplicate_error = check_duplicate_records(environment, exchange_id, metric_type, payload)
    if has_duplicates:
        logger.warning(f"[VALIDATION] Duplicate records detected: {duplicate_error}")
        # Note: We continue anyway, but log the warning. The exchange will reject if truly duplicate.
    
    # Store the original metrics list for detailed display in UI
    # Priority: 1. stored_metrics (passed breakdown) 2. current_metrics (validated metrics) 3. metrics (raw metrics)
    original_metrics_to_store = stored_metrics if stored_metrics is not None else (current_metrics if current_metrics is not None else metrics)
    
    full_metrics_payload = {
        "lama_v1_2_payload": payload,  # The V1.2 compliant payload
        "original_metrics": original_metrics_to_store
    }
    
    logger.info(f"Sending {metric_type} metrics to {environment.upper()} LAMA Exchange: {api_url}")
    logger.debug(f"V1.2 Payload: exchangeId={exchange_id}, applicationId={application_id}, sequenceId={sequence_id}, memberId={member_id}, metricData_count={len(metric_data)}")
    
    # Make HTTP POST request with V1.2 headers
    # LAMA tech team requires Cookie header to be sent as blank
    # Get User-Agent based on environment (Both UAT and PROD use Linux browser User-Agent matching Postman)
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Accept-Language": "en-US,en;q=0.9",
        "User-Agent": get_user_agent_for_environment(environment),
        "Referer": api_url,
        "Cookie": ""  # LAMA tech team requirement: send blank cookie
    }
    
    if auth_token:
        headers["Authorization"] = f"Bearer {auth_token}"

    # CRITICAL: Initialize response variables at function start (BEFORE any try-except)
    # This prevents UnboundLocalError when exceptions occur before response parsing
    transaction_id = None
    response_received_at = None
    exchange_response_data = {}
    response_code = None
    response_desc = None
    # CRITICAL: Don't reset sequence_id here - it was already calculated above if None
    # Store the calculated sequence_id before making the API call
    calculated_sequence_id = sequence_id  # This is the sequence_id we calculated or received
    status = "failed"
    status_code = None
    error_message = ""
    result = {}
    
    try:
        # Increased timeout for LAMA Exchange APIs
        # LAMA confirmed payload reaches them, but response takes >120s
        # Increased read timeout to 300s (5 minutes) to handle slow responses
        # Separate connect timeout (15s) and read timeout (60s) for better error handling
        # Note: Reduced from 300s to 60s for faster failure detection (metrics sending may take longer than login/logout)
        # Use HTTP/1.1 (HTTP/2 requires h2 package)
        # SSL verification disabled for testing (Postman often works with this)
        timeout_config = httpx.Timeout(connect=15.0, read=45.0, write=15.0, pool=15.0)
        # Use cookie jar for automatic cookie handling
        with httpx.Client(
            timeout=timeout_config, 
            verify=True,  # Enable SSL verification for security
            http2=False,  # Use HTTP/1.1 (HTTP/2 requires h2 package)
            follow_redirects=True,
            cookies={}  # Initialize cookie jar
        ) as client:
            # CRITICAL: Log request start time for debugging
            request_start_time = datetime.utcnow()
            logger.info(f"[METRICS REQUEST] Sending metrics to {environment.upper()} {exchange_name} at {request_start_time.isoformat()}")
            logger.info(f"[METRICS REQUEST] URL: {api_url}, Payload size: {len(str(payload))} bytes")
            
            # CRITICAL: Retry logic for connection issues
            # LAMA server may disconnect, but payload is received - retry to get response
            max_retries = 2
            retry_count = 0
            response = None
            
            while retry_count <= max_retries:
                try:
                    # CRITICAL: Make the request and wait for response
                    # LAMA team confirmed payload reaches them, so we need to properly wait for their response
                    if retry_count > 0:
                        logger.warning(f"[METRICS REQUEST] Retry attempt {retry_count}/{max_retries} for {environment.upper()} {exchange_name}")
                    
                    response = client.post(
                        api_url,
                        json=payload,
                        headers=headers
                    )
                    # If we get here, we have a response - break out of retry loop
                    break
                    
                except (httpx.RemoteProtocolError, httpx.ConnectError) as conn_error:
                    retry_count += 1
                    if retry_count <= max_retries:
                        error_msg = str(conn_error)
                        logger.warning(f"[METRICS REQUEST] Connection error (attempt {retry_count}): {error_msg}")
                        logger.warning(f"[METRICS REQUEST] Retrying in 2 seconds...")
                        time.sleep(2)  # Wait 2 seconds before retry
                        continue
                    else:
                        # Max retries reached, re-raise the exception
                        raise
            
            # CRITICAL: Process response (outside retry loop)
            # Explicitly read response content to ensure we wait for full response
            # This ensures httpx waits for the complete response body before we continue
            response_received_at = datetime.utcnow()
            request_duration = (response_received_at - request_start_time).total_seconds()
            logger.info(f"[METRICS RESPONSE] Response received after {request_duration:.2f}s, HTTP Status: {response.status_code}")
            
            # Read response content explicitly - this ensures we wait for the full response body
            # If response is chunked or streaming, this will wait for all chunks
            try:
                response_content = response.read()  # Use read() to ensure full response is received
                logger.debug(f"[METRICS RESPONSE] Response content length: {len(response_content)} bytes")
            except AttributeError:
                # If read() is not available, use content property
                response_content = response.content
                logger.debug(f"[METRICS RESPONSE] Response content length: {len(response_content)} bytes (using .content)")
            
            status_code = response.status_code
            logger.info(f"[METRICS RESPONSE] Full response received, parsing JSON...")
            
            # Try to parse response
            # Note: response_code and response_desc are already initialized above (before try block)
            try:
                # Parse JSON from response content
                # CRITICAL: Use response_content (already read), don't call response.json() 
                # because response stream was already consumed by response.read()
                if response_content:
                    if isinstance(response_content, bytes):
                        exchange_response_data = json.loads(response_content)
                    else:
                        # If it's already a string, parse it directly
                        exchange_response_data = json.loads(response_content)
                else:
                    exchange_response_data = {}
                    logger.warning(f"[METRICS RESPONSE] Empty response content from {environment.upper()} {exchange_name}")
                
                # Extract sequence_id from response (common fields: sequenceId, sequence_id, id, transactionId)
                response_sequence_id = (
                    exchange_response_data.get("sequenceId") or
                    exchange_response_data.get("sequence_id") or
                    exchange_response_data.get("id") or
                    exchange_response_data.get("transactionId") or
                    exchange_response_data.get("transaction_id")
                )
                # CRITICAL: Don't overwrite calculated_sequence_id with response value
                # We need to store the sequence_id we SENT, not the one from response
                # The response sequence_id is just for logging/verification
                if response_sequence_id:
                    try:
                        response_seq_int = int(response_sequence_id) if response_sequence_id else None
                        # Log if response differs from what we sent (for debugging)
                        if response_seq_int and calculated_sequence_id and response_seq_int != calculated_sequence_id:
                            logger.warning(f"[SEQ_ID] Response sequence_id ({response_seq_int}) differs from sent sequence_id ({calculated_sequence_id})")
                    except (ValueError, TypeError):
                        pass
                # Keep using calculated_sequence_id (the one we sent)
                
                # Extract responseCode from LAMA response (CRITICAL: Only 601 = SUCCESS, all others = FAILED)
                # This is per LAMA Exchange API specification - needed for audit purposes
                response_code_raw = exchange_response_data.get("responseCode") or exchange_response_data.get("response_code")
                response_desc = exchange_response_data.get("responseDesc") or exchange_response_data.get("response_desc") or exchange_response_data.get("message")
                
                if response_code_raw:
                    try:
                        response_code = int(response_code_raw)  # Convert to int for comparison
                        status_code = response_code  # Use LAMA responseCode instead of HTTP status
                    except (ValueError, TypeError):
                        response_code = None
                        status_code = response.status_code  # Fallback to HTTP status
                else:
                    response_code = None
                    status_code = response.status_code  # Fallback to HTTP status
            except Exception as parse_exception:
                # Fallback if response parsing fails completely
                logger.error(f"[METRICS RESPONSE] Failed to parse response: {parse_exception}")
                # Use response_content instead of response.text since stream was already consumed by read()
                if response_content:
                    try:
                        # Decode bytes to string if needed, then truncate
                        raw_response = response_content.decode('utf-8')[:500] if isinstance(response_content, bytes) else str(response_content)[:500]
                    except (UnicodeDecodeError, AttributeError):
                        raw_response = str(response_content)[:500]
                else:
                    raw_response = ""
                exchange_response_data = {"raw_response": raw_response}
                response_code = None
                status_code = response.status_code if response else None
            
            # CRITICAL: Per LAMA Exchange API specification, ONLY responseCode 601 = SUCCESS
            # All other response codes (602, 603, 704, 708, 801, etc.) are treated as UNSUCCESSFUL
            # This is required for audit purposes - all response codes must be captured
            
            # Special handling for Error 704 (Invalid Sequence ID)
            # Per LAMA API v1.2: When exchange returns error 704, it tells us what sequence ID it expects
            # We must extract and store this for use in the next transaction
            # SMART EXTRACTION: Check multiple sources with priority order
            expected_seq_id_from_error = None
            if response_code == 704:
                # PRIORITY 1: Check JSON response body for structured expectedSequenceId field (highest priority)
                if isinstance(exchange_response_data, dict):
                    expected_seq_id_from_json = exchange_response_data.get("expectedSequenceId") or exchange_response_data.get("expected_sequence_id") or exchange_response_data.get("expectedSequence")
                    if expected_seq_id_from_json:
                        try:
                            expected_seq_id_from_error = int(expected_seq_id_from_json)
                            logger.warning(f"[704_EXTRACT] ✅ PRIORITY 1: Found expectedSequenceId in JSON response body: {expected_seq_id_from_error} for {environment.upper()}/exchange_id={exchange_id}/metric_type={metric_type}")
                        except (ValueError, TypeError) as e:
                            logger.warning(f"[704_EXTRACT] Invalid expectedSequenceId format in JSON: {expected_seq_id_from_json}, error: {e}")
                
                # PRIORITY 2: Parse from error description/responseDesc string (fallback)
                if expected_seq_id_from_error is None and response_desc:
                    # Extract expected sequence ID from error message
                    # Format: "error : Invalid Sequence ID. The SequenceId should be 43"
                    import re
                    match = re.search(r'should be (\d+)', response_desc, re.IGNORECASE)
                    if match:
                        try:
                            expected_seq_id_from_error = int(match.group(1))
                            logger.warning(f"[704_EXTRACT] ✅ PRIORITY 2: Found expectedSequenceId in error description: {expected_seq_id_from_error} for {environment.upper()}/exchange_id={exchange_id}/metric_type={metric_type}")
                        except (ValueError, TypeError) as e:
                            logger.warning(f"[704_EXTRACT] Failed to extract expectedSequenceId from error description: {e}")
                
                # PRIORITY 3: Parse from message field in JSON response (fallback)
                if expected_seq_id_from_error is None and isinstance(exchange_response_data, dict):
                    message_text = exchange_response_data.get("message") or exchange_response_data.get("error") or exchange_response_data.get("errorMessage") or ""
                    if message_text:
                        import re
                        match = re.search(r'should be (\d+)', str(message_text), re.IGNORECASE)
                        if match:
                            try:
                                expected_seq_id_from_error = int(match.group(1))
                                logger.warning(f"[704_EXTRACT] ✅ PRIORITY 3: Found expectedSequenceId in message field: {expected_seq_id_from_error} for {environment.upper()}/exchange_id={exchange_id}/metric_type={metric_type}")
                            except (ValueError, TypeError) as e:
                                logger.warning(f"[704_EXTRACT] Failed to extract expectedSequenceId from message field: {e}")
                
                # Store extracted expectedSequenceId in exchange_response_data for scheduler use
                if expected_seq_id_from_error is not None:
                    if isinstance(exchange_response_data, dict):
                        exchange_response_data["expectedSequenceId"] = expected_seq_id_from_error
                        logger.warning(f"[704_EXTRACT] ✅ Stored expectedSequenceId {expected_seq_id_from_error} in exchange_response_data for immediate retry")
                        logger.warning(f"[704_EXTRACT] Error 704: Exchange expects sequence_id {expected_seq_id_from_error} for {environment.upper()}/exchange_id={exchange_id}/metric_type={metric_type}, but we sent {sequence_id}")
                    else:
                        exchange_response_data = {"expectedSequenceId": expected_seq_id_from_error}
                        logger.warning(f"[704_EXTRACT] ✅ Created exchange_response_data with expectedSequenceId {expected_seq_id_from_error}")
                else:
                    logger.error(f"[704_EXTRACT] ❌ Could not extract expectedSequenceId from Error 704 response for {environment.upper()}/exchange_id={exchange_id}/metric_type={metric_type}. Exchange response: {exchange_response_data}")
            
            if response_code == 601:
                status = "success"
                logger.info(f"{environment.upper()} LAMA Exchange {metric_type} metrics sent successfully (Response Code: 601)")
                
                # CRITICAL: Extract token from success response (601) if provided by exchange
                # Per LAMA API spec: Tokens can be provided in success responses
                # Each exchange may provide its own token, so we store it per exchange
                response_token = None
                if isinstance(exchange_response_data, dict):
                    response_token = (
                        exchange_response_data.get("token") or
                        exchange_response_data.get("accessToken") or
                        exchange_response_data.get("access_token") or
                        exchange_response_data.get("authToken") or
                        exchange_response_data.get("auth_token")
                    )
                
                # If token is provided in response, update cache for this specific exchange
                if response_token and exchange_id:
                    exchange_name = {1: "NSE", 2: "BSE", 4: "MCX", 5: "NCDEX"}.get(exchange_id, f"Exchange {exchange_id}")
                    logger.info(f"[TOKEN] Received new token from {environment.upper()} {exchange_name} metrics success (601) response, updating cache")
                    try:
                        from app.utils.lama_token_cache import update_token_cache
                        update_token_cache(environment, exchange_id, response_token)
                        logger.info(f"[TOKEN] Token cache updated for {environment.upper()} {exchange_name} from success response")
                    except Exception as token_error:
                        logger.warning(f"[TOKEN] Failed to update token cache from success response: {token_error}")
                
                result = {
                    "success": True,
                    "message": f"{environment.upper()} {metric_type} metrics sent successfully (Response Code: 601)",
                    "sequence_id": sequence_id,
                    "response_code": response_code,
                    "response_desc": response_desc,
                    "token_received": response_token is not None  # Indicate if token was received
                }
            elif response.status_code == 401 or response_code == 801 or response_code == 802:
                # Handle HTTP 401, LAMA Exchange error 801 (Invalid Token), and 802 (Token Expired)
                # All indicate authentication failure and require token refresh
                status = "failed"
                if response.status_code == 401:
                    error_type = "401"
                elif response_code == 802:
                    error_type = "802 (Token Expired)"
                else:
                    error_type = "801 (Invalid Token)"
                error_message = f"Authentication failed ({error_type})"
                logger.warning(f"{environment.upper()} LAMA Exchange metrics failed: {error_message}")
                
                # Automatically logout and clear token cache on 401/801/802 error
                # This ensures old/invalid/expired token is removed before retry
                # CRITICAL: Clear token for this specific exchange, not all exchanges
                exchange_name = {1: "NSE", 2: "BSE", 4: "MCX", 5: "NCDEX"}.get(exchange_id, f"Exchange {exchange_id}") if exchange_id else "Exchange"
                logger.info(f"{error_type} error detected for {environment.upper()} {exchange_name}, automatically logging out and clearing token cache...")
                try:
                    from app.utils.lama_token_cache import logout_lama_exchange, clear_token_cache
                    if exchange_id:
                        # Clear token for this specific exchange
                        logout_lama_exchange(environment, exchange_id)
                        logger.info(f"Successfully logged out and cleared token cache for {environment.upper()} {exchange_name} after {error_type} error")
                    else:
                        # Fallback: clear all exchanges in environment
                        clear_token_cache(environment)
                        logger.info(f"Cleared token cache for all exchanges in {environment.upper()} after {error_type} error")
                except Exception as logout_error:
                    logger.warning(f"Failed to logout after {error_type} error for {environment.upper()} {exchange_name}: {logout_error}")
                    # Still clear cache even if logout API fails
                    from app.utils.lama_token_cache import clear_token_cache
                    if exchange_id:
                        clear_token_cache(environment, exchange_id)
                    else:
                        clear_token_cache(environment)
                
                result = {
                    "success": False,
                    "message": f"{environment.upper()} LAMA Exchange metrics failed: {error_message}. Token cache cleared. Retry will trigger new login.",
                    "status_code": response.status_code if response.status_code == 401 else (response_code if response_code else 801),
                    "response_code": response_code,
                    "token_cleared": True  # Indicate that token was cleared for retry logic
                }
            elif response_code == 705:
                # Error 705: Invalid timestamp - Data pushed within 5 minutes of last push
                status = "failed"
                error_detail = f"Response Code: 705 - Invalid timestamp (data pushed within 5 minutes of last push)"
                if response_desc:
                    error_detail += f" - {response_desc}"
                error_message = error_detail
                logger.warning(f"{environment.upper()} LAMA Exchange metrics failed: {error_detail} (HTTP {response.status_code})")
                logger.warning(f"[705_TIMESTAMP] Error 705 detected for {environment.upper()}/exchange_id={exchange_id}/metric_type={metric_type} - Last push was too recent (< 5 minutes)")
                
                # For Error 705, we should wait before retrying
                # Store this in result so scheduler can handle it appropriately
                result = {
                    "success": False,
                    "message": f"{environment.upper()} LAMA Exchange metrics failed: {error_detail}",
                    "status_code": response_code,
                    "response_code": response_code,
                    "response_desc": response_desc,
                    "exchange_response": exchange_response_data if isinstance(exchange_response_data, dict) else {},
                    "should_wait": True,  # Indicate that retry should wait (5 minutes)
                    "wait_seconds": 300  # Wait 5 minutes (300 seconds) before retry
                }
            elif response_code == 607:
                # Error 607: Concurrent User limit exceeded
                status = "failed"
                error_detail = f"Response Code: 607 - Concurrent User limit exceeded"
                if response_desc:
                    error_detail += f" - {response_desc}"
                error_message = error_detail
                logger.warning(f"{environment.upper()} LAMA Exchange metrics failed: {error_detail} (HTTP {response.status_code})")
                logger.warning(f"[607_CONCURRENT] Error 607 detected for {environment.upper()}/exchange_id={exchange_id}/metric_type={metric_type} - Too many concurrent requests")
                
                # For Error 607, retry with exponential backoff
                result = {
                    "success": False,
                    "message": f"{environment.upper()} LAMA Exchange metrics failed: {error_detail}",
                    "status_code": response_code,
                    "response_code": response_code,
                    "response_desc": response_desc,
                    "exchange_response": exchange_response_data if isinstance(exchange_response_data, dict) else {},
                    "should_retry_with_backoff": True,  # Indicate retry with backoff
                    "backoff_seconds": 10  # Initial backoff: 10 seconds
                }
            elif response_code == 602:
                # Error 602: Partial Success - Some records succeeded, some failed
                status = "partial_success"  # Special status for partial success
                error_detail = f"Response Code: 602 - Partial Success (some records succeeded, some failed)"
                if response_desc:
                    error_detail += f" - {response_desc}"
                error_message = error_detail
                logger.warning(f"{environment.upper()} LAMA Exchange metrics partially successful: {error_detail} (HTTP {response.status_code})")
                logger.info(f"[602_PARTIAL] Error 602 detected for {environment.upper()}/exchange_id={exchange_id}/metric_type={metric_type} - Partial success, check response for details")
                
                # For Error 602, we should log it but not retry (some data was accepted)
                result = {
                    "success": False,  # Still False because not fully successful
                    "partial_success": True,  # Indicate partial success
                    "message": f"{environment.upper()} LAMA Exchange metrics partially successful: {error_detail}",
                    "status_code": response_code,
                    "response_code": response_code,
                    "response_desc": response_desc,
                    "exchange_response": exchange_response_data if isinstance(exchange_response_data, dict) else {}
                }
            elif response_code == 603:
                # Error 603: Invalid Payload - DO NOT RETRY (payload structure is wrong)
                status = "failed"
                error_detail = f"Response Code: 603 - Invalid Payload"
                if response_desc:
                    error_detail += f" - {response_desc}"
                error_message = error_detail
                logger.error(f"{environment.upper()} LAMA Exchange metrics failed: {error_detail} (HTTP {response.status_code})")
                logger.error(f"[603_PAYLOAD] Error 603 detected for {environment.upper()}/exchange_id={exchange_id}/metric_type={metric_type} - Invalid payload structure")
                logger.error(f"[603_PAYLOAD] Full payload: {json.dumps(payload, indent=2)}")
                
                # DO NOT RETRY - payload needs to be fixed by admin
                result = {
                    "success": False,
                    "message": f"{environment.upper()} LAMA Exchange metrics failed: {error_detail}",
                    "status_code": response_code,
                    "response_code": response_code,
                    "response_desc": response_desc,
                    "exchange_response": exchange_response_data if isinstance(exchange_response_data, dict) else {},
                    "should_not_retry": True,  # Critical: don't retry
                    "requires_admin_attention": True
                }
            elif response_code == 605:
                # Error 605: Something Went Wrong (Technical Error) - Retry with backoff
                status = "failed"
                error_detail = f"Response Code: 605 - Technical error (something went wrong)"
                if response_desc:
                    error_detail += f" - {response_desc}"
                error_message = error_detail
                logger.warning(f"{environment.upper()} LAMA Exchange metrics failed: {error_detail} (HTTP {response.status_code})")
                logger.warning(f"[605_TECHNICAL] Error 605 detected for {environment.upper()}/exchange_id={exchange_id}/metric_type={metric_type} - Technical error, will retry with backoff")
                
                # Retry with exponential backoff
                result = {
                    "success": False,
                    "message": f"{environment.upper()} LAMA Exchange metrics failed: {error_detail}",
                    "status_code": response_code,
                    "response_code": response_code,
                    "response_desc": response_desc,
                    "exchange_response": exchange_response_data if isinstance(exchange_response_data, dict) else {},
                    "should_retry_with_backoff": True,
                    "backoff_seconds": 30,  # Initial: 30 seconds
                    "max_retries": 3
                }
            elif response_code == 707:
                # Error 707: Invalid Metric Key - DO NOT RETRY (metric key is wrong)
                status = "failed"
                error_detail = f"Response Code: 707 - Invalid Metric Key"
                if response_desc:
                    error_detail += f" - {response_desc}"
                error_message = error_detail
                logger.error(f"{environment.upper()} LAMA Exchange metrics failed: {error_detail} (HTTP {response.status_code})")
                logger.error(f"[707_METRIC_KEY] Error 707 detected for {environment.upper()}/exchange_id={exchange_id}/metric_type={metric_type} - Invalid metric key")
                
                # DO NOT RETRY - configuration needs to be fixed
                result = {
                    "success": False,
                    "message": f"{environment.upper()} LAMA Exchange metrics failed: {error_detail}",
                    "status_code": response_code,
                    "response_code": response_code,
                    "response_desc": response_desc,
                    "exchange_response": exchange_response_data if isinstance(exchange_response_data, dict) else {},
                    "should_not_retry": True,
                    "requires_config_fix": True
                }
            elif response_code == 708:
                # Error 708: Invalid Metric Value - DO NOT RETRY (metric value is wrong)
                status = "failed"
                error_detail = f"Response Code: 708 - Invalid Metric Value"
                if response_desc:
                    error_detail += f" - {response_desc}"
                error_message = error_detail
                logger.error(f"{environment.upper()} LAMA Exchange metrics failed: {error_detail} (HTTP {response.status_code})")
                logger.error(f"[708_METRIC_VALUE] Error 708 detected for {environment.upper()}/exchange_id={exchange_id}/metric_type={metric_type} - Invalid metric value")
                
                # DO NOT RETRY - data needs to be fixed
                result = {
                    "success": False,
                    "message": f"{environment.upper()} LAMA Exchange metrics failed: {error_detail}",
                    "status_code": response_code,
                    "response_code": response_code,
                    "response_desc": response_desc,
                    "exchange_response": exchange_response_data if isinstance(exchange_response_data, dict) else {},
                    "should_not_retry": True,
                    "requires_config_fix": True
                }
            elif response_code == 709:
                # Error 709: Duplicate Record - Remove duplicates and retry
                status = "failed"
                error_detail = f"Response Code: 709 - Duplicate Record"
                if response_desc:
                    error_detail += f" - {response_desc}"
                error_message = error_detail
                logger.warning(f"{environment.upper()} LAMA Exchange metrics failed: {error_detail} (HTTP {response.status_code})")
                logger.warning(f"[709_DUPLICATE] Error 709 detected for {environment.upper()}/exchange_id={exchange_id}/metric_type={metric_type} - Duplicate record, will retry with cleaned payload")
                
                # Retry after removing duplicates (handled by validation)
                result = {
                    "success": False,
                    "message": f"{environment.upper()} LAMA Exchange metrics failed: {error_detail}",
                    "status_code": response_code,
                    "response_code": response_code,
                    "response_desc": response_desc,
                    "exchange_response": exchange_response_data if isinstance(exchange_response_data, dict) else {},
                    "should_retry": True,
                    "requires_cleanup": True  # Indicate duplicates need to be removed
                }
            elif response_code == 710:
                # Error 710: Payload Size Exceeded (> 5 records) - Should not occur with our structure
                status = "failed"
                error_detail = f"Response Code: 710 - Payload Size Exceeded (> 5 records)"
                if response_desc:
                    error_detail += f" - {response_desc}"
                error_message = error_detail
                logger.error(f"{environment.upper()} LAMA Exchange metrics failed: {error_detail} (HTTP {response.status_code})")
                logger.error(f"[710_PAYLOAD_SIZE] Error 710 detected for {environment.upper()}/exchange_id={exchange_id}/metric_type={metric_type} - Payload size exceeded")
                logger.error(f"[710_PAYLOAD_SIZE] Payload array length: {len(payload.get('payload', []))}")
                
                # This should not occur with our current structure (only 1 object in payload array)
                # But if it does, we need to split (though our structure doesn't require it)
                result = {
                    "success": False,
                    "message": f"{environment.upper()} LAMA Exchange metrics failed: {error_detail}",
                    "status_code": response_code,
                    "response_code": response_code,
                    "response_desc": response_desc,
                    "exchange_response": exchange_response_data if isinstance(exchange_response_data, dict) else {},
                    "should_not_retry": True,  # Don't retry - structure issue
                    "requires_admin_attention": True
                }
            elif response_code == 901:
                # Error 901: Not Valid Record (blank/null values) - Remove nulls and retry
                status = "failed"
                error_detail = f"Response Code: 901 - Not Valid Record (blank/null values)"
                if response_desc:
                    error_detail += f" - {response_desc}"
                error_message = error_detail
                logger.warning(f"{environment.upper()} LAMA Exchange metrics failed: {error_detail} (HTTP {response.status_code})")
                logger.warning(f"[901_NULL_VALUES] Error 901 detected for {environment.upper()}/exchange_id={exchange_id}/metric_type={metric_type} - Null/blank values, will retry with cleaned payload")
                
                # Retry after removing null/blank values (handled by validation)
                result = {
                    "success": False,
                    "message": f"{environment.upper()} LAMA Exchange metrics failed: {error_detail}",
                    "status_code": response_code,
                    "response_code": response_code,
                    "response_desc": response_desc,
                    "exchange_response": exchange_response_data if isinstance(exchange_response_data, dict) else {},
                    "should_retry": True,
                    "requires_cleanup": True  # Indicate null/blank values need to be removed
                }
            elif response_code == 704:
                # Error 704: Invalid Sequence ID - Exchange tells us what sequence ID it expects
                status = "failed"
                error_detail = f"Response Code: 704 - Invalid Sequence ID"
                if response_desc:
                    error_detail += f" - {response_desc}"
                error_message = error_detail
                logger.warning(f"{environment.upper()} LAMA Exchange metrics failed: {error_detail} (HTTP {response.status_code})")
                logger.error(f"[704_ERROR] Error 704 detected for {environment.upper()}/exchange_id={exchange_id}/metric_type={metric_type} - Exchange expects sequence_id {expected_seq_id_from_error if expected_seq_id_from_error else 'UNKNOWN'}")
                
                # CRITICAL: Ensure exchange_response contains expectedSequenceId for scheduler retry logic
                exchange_response_for_704 = exchange_response_data if isinstance(exchange_response_data, dict) else {}
                if expected_seq_id_from_error:
                    if "expectedSequenceId" not in exchange_response_for_704:
                        exchange_response_for_704["expectedSequenceId"] = expected_seq_id_from_error
                        logger.error(f"[704_ERROR] Added expectedSequenceId {expected_seq_id_from_error} to exchange_response")
                    else:
                        logger.error(f"[704_ERROR] expectedSequenceId already in exchange_response: {exchange_response_for_704.get('expectedSequenceId')}")
                else:
                    logger.error(f"[704_ERROR] WARNING: expected_seq_id_from_error is None - cannot extract from error message!")
                
                # Add responseCode and responseDesc to exchange_response for completeness
                exchange_response_for_704["responseCode"] = response_code
                exchange_response_for_704["responseDesc"] = response_desc
                
                # Create result dict with exchange_response containing expectedSequenceId
                result = {
                    "success": False,
                    "message": f"{environment.upper()} LAMA Exchange metrics failed: {error_detail}",
                    "status_code": response_code,
                    "response_code": response_code,  # CRITICAL: Must be set for scheduler to detect Error 704
                    "response_desc": response_desc,
                    "exchange_response": exchange_response_for_704  # CRITICAL: Must contain expectedSequenceId for retry
                }
                logger.error(f"[704_ERROR] Created result dict with response_code={response_code}, exchange_response keys: {list(exchange_response_for_704.keys())}")
            else:
                # All other response codes (including HTTP 200 with responseCode != 601) are treated as FAILED
                # Per LAMA Exchange specification: Only 601 = SUCCESS, all others = UNSUCCESSFUL
                status = "failed"
                
                # Build error detail with response code and description if available
                if response_code:
                    error_detail = f"Response Code: {response_code}"
                    if response_desc:
                        error_detail += f" - {response_desc}"
                    else:
                        error_detail += " (Unsuccessful - Only 601 is considered success)"
                else:
                    error_detail = f"HTTP {response.status_code}"
                    try:
                        if isinstance(exchange_response_data, dict):
                            error_detail = exchange_response_data.get("message", exchange_response_data.get("error", error_detail))
                    except:
                        pass
                
                error_message = error_detail
                logger.warning(f"{environment.upper()} LAMA Exchange metrics failed: {error_detail} (HTTP {response.status_code})")
                
                # CRITICAL: Include exchange_response in result so scheduler can extract expectedSequenceId for error 704
                # Ensure exchange_response_data is a dict and contains expectedSequenceId if error 704
                exchange_response_for_result = exchange_response_data if isinstance(exchange_response_data, dict) else {}
                if response_code == 704:
                    logger.warning(f"[704_RESULT] Error 704 detected, expected_seq_id_from_error: {expected_seq_id_from_error}")
                    logger.error(f"[704_RESULT] exchange_response_for_result type: {type(exchange_response_for_result)}, keys: {list(exchange_response_for_result.keys()) if isinstance(exchange_response_for_result, dict) else 'Not a dict'}")
                    if expected_seq_id_from_error:
                        # Double-check expectedSequenceId is in the dict
                        if "expectedSequenceId" not in exchange_response_for_result:
                            exchange_response_for_result["expectedSequenceId"] = expected_seq_id_from_error
                            logger.error(f"[704_RESULT] Added expectedSequenceId {expected_seq_id_from_error} to exchange_response_for_result")
                        else:
                            logger.error(f"[704_RESULT] expectedSequenceId already in exchange_response_for_result: {exchange_response_for_result.get('expectedSequenceId')}")
                    else:
                        logger.error(f"[704_RESULT] expected_seq_id_from_error is None, cannot add to exchange_response_for_result")
                
                # Only create result dict if not already created (for 705, 607, 602)
                if 'result' not in locals() or result is None:
                    result = {
                        "success": False,
                        "message": f"{environment.upper()} LAMA Exchange metrics failed: {error_detail}",
                        "status_code": response_code if response_code else response.status_code,
                        "response_code": response_code,
                        "response_desc": response_desc,
                        "exchange_response": exchange_response_for_result  # Include for error 704 extraction
                    }
                    if response_code == 704:
                        logger.error(f"[704_RESULT] Created result dict with response_code={response_code}, exchange_response keys: {list(exchange_response_for_result.keys()) if isinstance(exchange_response_for_result, dict) else 'Not a dict'}")
    except httpx.TimeoutException as e:
        status = "timeout"
        error_message = f"Request timeout: {str(e)}"
        logger.error(f"{environment.upper()} LAMA Exchange metrics API timeout: {str(e)}")
        logger.error(f"Timeout details - URL: {api_url}, This usually means the server took too long to respond (>300s)")
        logger.error(f"If this is UAT, check network connectivity to {api_url}")
        result = {
            "success": False,
            "message": f"{environment.upper()} LAMA Exchange metrics API timeout - server took too long to respond (>300s). Check network connectivity.",
            "response_code": None,  # No response code for timeout
            "exchange_response": {}  # Empty exchange_response for timeout
        }
    except httpx.RemoteProtocolError as e:
        status = "error"
        error_message = f"Server disconnected: {str(e)}"
        logger.error(f"{environment.upper()} LAMA Exchange metrics API - Server disconnected without sending response: {str(e)}")
        logger.warning(f"This may indicate the server received the payload but closed connection before sending response")
        logger.warning(f"LAMA team confirmed payload reaches them - this might be expected behavior for async processing")
        result = {
            "success": False,
            "message": f"{environment.upper()} LAMA Exchange metrics API - Server disconnected. Payload may have been received but response not available.",
            "response_code": None,
            "exchange_response": {}
        }
    except httpx.RequestError as e:
        status = "error"
        error_message = str(e)
        logger.error(f"{environment.upper()} LAMA Exchange metrics API request error: {e}")
        result = {
            "success": False,
            "message": f"{environment.upper()} LAMA Exchange metrics API connection error: {str(e)}",
            "response_code": None,  # No response code for request error
            "exchange_response": {}  # Empty exchange_response for request error
        }
    except Exception as e:
        status = "error"
        error_message = str(e)
        logger.error(f"{environment.upper()} LAMA Exchange metrics API error: {e}", exc_info=True)
        
        result = {
            "success": False,
            "message": f"{environment.upper()} LAMA Exchange metrics API error: {str(e)}",
            "response_code": None,  # No response code for exception
            "exchange_response": {}  # Empty exchange_response for exception
        }
    
    # Store transaction record
    try:
        with engine.connect() as conn:
            # CRITICAL: Use the final, complete payload for metrics_sent
            # This ensures locationId, memberId, exchangeId, and timestamp are visible in UI
            final_metrics_to_store = {
                "lama_v1_2_payload": payload,  # The COMPLETE V1.2/V1.3 JSON sent to Exchange
                "original_metrics": original_metrics_to_store,
                "request_headers": headers,
                "request_url": api_url
            }
            
            insert_query = exchange_transactions_table.insert().values(
                environment=environment,
                server_id=server_id,
                server_name=server_name,
                server_ip=server_ip or instance_id,
                member_id=member_id,
                instance_id=instance_id,
                metric_type=metric_type,
                metrics_sent=final_metrics_to_store,
                sequence_id=str(calculated_sequence_id) if calculated_sequence_id is not None else None,
                record_type='hint' if response_code in [704, "704"] else 'sent',
                exchange_response={
                    **(exchange_response_data if isinstance(exchange_response_data, dict) else {}),
                    "responseCode": response_code if response_code else None,
                    "responseDesc": response_desc if response_desc else None
                },
                status=status,
                status_code=status_code,
                error_message=error_message,
                sent_at=sent_at,
                response_received_at=response_received_at,
                exchange_id=exchange_id,
                location_id=location_id, # Explicitly store location_id column
                original_metrics=original_metrics_to_store
            )
            result_insert = conn.execute(insert_query)
            conn.commit()
            transaction_id = result_insert.inserted_primary_key[0] if result_insert.inserted_primary_key else None
            logger.info(f"[DB_WRITE] ✅ Stored txn id={transaction_id} exch={exchange_id} {metric_type} seq={calculated_sequence_id} status={status_code}")
    except Exception as e:
        logger.error(f"[DB_WRITE] ❌ Failed: {e}", exc_info=True)
        # Don't fail the main operation if transaction logging fails
    
    # Add transaction_id to result
    if transaction_id:
        result["transaction_id"] = transaction_id
    
    # Log metrics sent (success or failure) if scheduler_name is provided
    if scheduler_name and log_metrics_sent and exchange_id:
        try:
            send_duration_ms = int(request_duration * 1000) if 'request_duration' in locals() else None
            log_metrics_sent(
                scheduler_name=scheduler_name,
                environment=environment,
                exchange_id=exchange_id,
                metric_type=metric_type,
                success=result.get("success", False),
                response_code=response_code if 'response_code' in locals() else None,
                error_message=error_message if 'error_message' in locals() else None,
                sequence_id=calculated_sequence_id if 'calculated_sequence_id' in locals() else sequence_id,
                duration_ms=send_duration_ms
            )
        except Exception:
            pass  # Non-critical logging failure
    
    # SEQUENCE ROLLBACK: Rollback for non-consumption cases.
    # Rollback for: timeout (45s = exchange almost certainly didn't consume), 503, other non-704/706 errors.
    # Don't rollback for: 601 (success), 704 (auto-retry handles it), 706 (duplicate — seq was consumed earlier).
    if result and not result.get("success"):
        resp_code = result.get("response_code")
        if resp_code is None and status == "timeout" and calculated_sequence_id is not None:
            # Timeout with 45s read — exchange almost certainly didn't consume
            rollback_sequence_id(environment, metric_type)
            logger.info(f"[SEQ_ROLLBACK] Rolled back after timeout for {metric_type} seq={calculated_sequence_id}")
        elif resp_code is not None and resp_code not in (704, 706) and calculated_sequence_id is not None:
            rollback_sequence_id(environment, metric_type)

    # AUTO-RETRY for Error 704: If exchange told us the correct sequence, retry once immediately
    if (result and not result.get("success") and result.get("response_code") == 704):
        hint = (result.get("exchange_response") or {}).get("expectedSequenceId")
        if hint:
            hint_int = int(hint)
            logger.info(f"[704_AUTO_RETRY] Retrying with hint {hint_int} for {environment}/{exchange_id}/{metric_type}")
            retry_result = send_metrics_to_lama_exchange(
                environment=environment, member_id=member_id, instance_id=instance_id,
                metrics=metrics, auth_token=auth_token, metric_type=metric_type,
                server_id=server_id, server_name=server_name, server_ip=server_ip,
                exchange_id=exchange_id, application_id=application_id,
                sequence_id=hint_int, sent_at=datetime.now(),
                nse_timestamp=nse_timestamp, expected_seq_id_hint=hint_int,
                scheduler_name=scheduler_name,
                skip_705_check=True, stored_metrics=stored_metrics,
                location_id=location_id, batched_payload=batched_payload
            )
            # CRITICAL FIX: Force-reset cache to hint value after successful retry.
            # The cache drifts ahead because each 704 attempt increments it, but
            # update_sequence_cache_after_704() refuses to move backward.
            # We MUST reset to the consumed sequence so the next send uses hint+1.
            if retry_result and retry_result.get("success"):
                m_type = metric_type if metric_type else "global"
                lock_key = (environment.lower(), m_type)
                if hasattr(get_next_sequence_id, "_last_issued"):
                    old = get_next_sequence_id._last_issued.get(lock_key, 0)
                    get_next_sequence_id._last_issued[lock_key] = hint_int
                    logger.info(f"[SEQ_ID] Cache force-reset {old} → {hint_int} after 704 retry success")
                return retry_result

    return result



def log_calculated_metrics_only(*args, **kwargs):
    """Dummy function to satisfy imports"""
    logger.debug(f"log_calculated_metrics_only called with {len(args)} args")
    pass
