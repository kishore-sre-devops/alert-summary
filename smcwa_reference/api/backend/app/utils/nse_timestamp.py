# api/backend/app/utils/nse_timestamp.py
"""
NSE Epoch Timestamp Utilities
Converts timestamps to/from NSE epoch (milliseconds since 01-jan-1980)
"""

from datetime import datetime, timezone, timedelta
import time

# NSE Epoch: January 1, 1980, 00:00:00 UTC
# Exchange validates timestamps using UTC-based epoch (confirmed: 601 success with UTC, 705 with IST)
NSE_EPOCH = datetime(1980, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
NSE_EPOCH_TIMESTAMP = int(NSE_EPOCH.timestamp() * 1000)


def get_nse_timestamp_ms() -> int:
    """
    Get current timestamp in NSE epoch milliseconds
    
    Returns:
        Current timestamp in milliseconds since NSE epoch (01-jan-1980)
    """
    unix_timestamp_ms = int(time.time() * 1000)
    return unix_to_nse_timestamp(unix_timestamp_ms)


def unix_to_nse_timestamp(unix_timestamp_ms: int) -> int:
    """
    Convert Unix timestamp (milliseconds) to NSE timestamp (milliseconds)
    
    Args:
        unix_timestamp_ms: Unix timestamp in milliseconds
        
    Returns:
        NSE timestamp in milliseconds
    """
    return unix_timestamp_ms - NSE_EPOCH_TIMESTAMP


def nse_to_unix_timestamp(nse_timestamp_ms: int) -> int:
    """
    Convert NSE timestamp (milliseconds) to Unix timestamp (milliseconds)
    
    Args:
        nse_timestamp_ms: NSE timestamp in milliseconds
        
    Returns:
        Unix timestamp in milliseconds
    """
    return nse_timestamp_ms + NSE_EPOCH_TIMESTAMP

