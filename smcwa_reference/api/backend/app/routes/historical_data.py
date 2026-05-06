# api/backend/app/routes/historical_data.py
"""
Historical data endpoints for viewing and exporting metrics data
Supports date range filtering and Excel export
"""

from fastapi import APIRouter, HTTPException, Depends, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import select, or_, and_, case, func
from app.db.db import get_db, engine, exchange_transactions_table, server_metrics_table, server_status_table
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Any, Dict
import pandas as pd
import io
import logging
import sys

logger = logging.getLogger(__name__)

from app.utils.environment import get_active_environment

# IST timezone offset (UTC + 5:30)
IST_OFFSET = timedelta(hours=5, minutes=30)

class ExchangeTransactionResponse(BaseModel):
    id: Any
    environment: str
    server_id: Any = None
    server_name: Optional[str] = None
    server_ip: Optional[str] = None
    member_id: Optional[str] = None
    instance_id: Optional[str] = None
    metric_type: str
    metrics_sent: Dict[str, Any]
    sequence_id: Optional[str] = None
    exchange_response: Dict[str, Any]
    status: Optional[str] = None
    status_code: Optional[int] = None
    error_message: Optional[str] = None
    sent_at: Optional[str] = None
    response_received_at: Optional[str] = None
    exchange_id: Optional[int] = None
    response_code: Optional[int] = None
    location_id: Optional[int] = None
    location_name: Optional[str] = None
    # Fields added for grouping
    exchange_name: Optional[str] = None
    grouped_count: Optional[int] = None
    metric_types: Optional[List[str]] = None

class PaginatedExchangeTransactionResponse(BaseModel):
    items: List[ExchangeTransactionResponse]
    total_count: int
    page: int
    size: int
    total_pages: int
    count: int  # For backward compatibility with existing UI if needed

def utc_to_ist_str(utc_dt):
    """Convert UTC datetime to IST formatted string for Excel export"""
    if utc_dt is None:
        return ""
    try:
        ist_dt = utc_dt + IST_OFFSET
        return ist_dt.strftime("%Y-%m-%d %H:%M:%S")
    except:
        return str(utc_dt)

from app.utils.permissions import get_current_user

router = APIRouter(dependencies=[Depends(get_current_user)])


def _extract_response_code(tx: dict) -> Optional[int]:
    """
    Extract response_code from transaction consistently.
    Checks response_code field first, then exchange_response.responseCode,
    and finally status_code if it looks like a LAMA response code (> 600).
    Returns None if not found.
    """
    tx_response_code = tx.get('response_code')
    if tx_response_code is None:
        exchange_response = tx.get('exchange_response', {})
        if isinstance(exchange_response, dict):
            tx_response_code = exchange_response.get('responseCode')
    
    # FALLBACK: Check status_code if still None
    if tx_response_code is None:
        status_code = tx.get('status_code')
        if status_code and isinstance(status_code, int) and status_code > 600:
            tx_response_code = status_code
    
    # Convert to int if it's a string number
    if tx_response_code is not None:
        if isinstance(tx_response_code, str) and tx_response_code.isdigit():
            try:
                return int(tx_response_code)
            except ValueError:
                return None
        elif isinstance(tx_response_code, int):
            return tx_response_code
    
    return None


def _determine_status_from_response_code(response_code: Optional[int], db_status: Optional[str] = None) -> str:
    """
    Determine status from response_code and database status field.
    Returns 'success' if response_code == 601, 'failed' if other code or timeout/connection error, 'error' if None and not timeout.
    
    CRITICAL: When response_code is None (timeout/connection error), check database status field.
    If database status is 'timeout', 'failed', or 'connection_error', treat as 'failed' (not 'error').
    This ensures timeout/connection errors show up when user selects "Failed" status filter.
    """
    if response_code == 601:
        return 'success'
    elif response_code is not None:
        return 'failed'
    else:
        # response_code is None - check database status to determine if it's a timeout/connection error
        if db_status and db_status.lower() in ['timeout', 'failed', 'connection_error', 'request_error', 'protocol_error', 'calculated_failed_send']:
            return 'failed'  # Timeout/connection/local-fails should be treated as 'failed' for filtering
        else:
            return 'error'  # True error (unexpected)


def _group_transactions_by_exchange(transactions: List[dict], metric_type_filter: Optional[str] = None, status_filter: Optional[str] = None) -> List[dict]:
    """
    Group transactions by exchange_id and sent_at (within 5-second window for each push cycle).
    When metric_type_filter is None: Aggregate all metric types (hardware, network, database, application) into one entry per exchange.
    When metric_type_filter is set: Show only that metric type, but still group by exchange.
    Always groups by exchange_id only (not by status) to ensure 4 records per cycle (one per exchange: NSE, BSE, MCX, NCDEX).
    When multiple transactions exist for same exchange in same cycle, sort logic prefers success over failed.
    Returns ALL push cycles within the time range (each cycle has 4 entries - one per exchange: NSE, BSE, MCX, NCDEX).
    """
    if not transactions:
        return []
    
    from collections import defaultdict
    
    # First, group transactions by push cycle (5-minute intervals)
    # Each push cycle should have transactions sent within a 5-second window
    # Group by time first (rounded to nearest 5 minutes) to identify push cycles
    time_groups = defaultdict(list)
    
    # CRITICAL: Collect login/logout errors separately to ensure they're included
    login_logout_errors = []
    
    for tx in transactions:
        tx_metric_type = tx.get('metric_type')
        is_login_logout = tx_metric_type in ['login', 'logout']
        
        tx_sent_at = tx.get('sent_at')
        if tx_sent_at:
            try:
                # DB stores IST (PostgreSQL timezone=Asia/Kolkata). Parse as-is.
                tx_time = datetime.fromisoformat(tx_sent_at)
                if tx_time.tzinfo:
                    tx_time = tx_time.replace(tzinfo=None)
                # Round to nearest 5 minutes to group push cycles
                # This matches the scheduler's 5-minute interval
                minutes = tx_time.minute
                rounded_minute = (minutes // 5) * 5
                time_key = tx_time.replace(minute=rounded_minute, second=0, microsecond=0)
                time_groups[time_key].append(tx)
            except:
                # If parsing fails but it's a login/logout error, include it separately
                if is_login_logout:
                    login_logout_errors.append(tx)
                continue
        else:
            # CRITICAL: Include login/logout errors even without sent_at (they're environment-wide errors)
            # Regular metrics need sent_at for time-based grouping, but errors should be visible
            if is_login_logout:
                login_logout_errors.append(tx)
            # Skip regular transactions without sent_at (they need timestamps for grouping)
            continue
    
    # CRITICAL: Add login/logout errors to a special time group so they're always visible
    # Use current time rounded to 5 minutes so they appear at the top
    if login_logout_errors:
        current_time = datetime.now()
        minutes = current_time.minute
        rounded_minute = (minutes // 5) * 5
        error_time_key = current_time.replace(minute=rounded_minute, second=0, microsecond=0)
        # Create a new group for login/logout errors if time_groups is empty, or use the most recent group
        if not time_groups:
            time_groups[error_time_key] = login_logout_errors
        else:
            # Add to most recent time group so they appear with recent transactions
            most_recent_time = max(time_groups.keys())
            time_groups[most_recent_time].extend(login_logout_errors)
        logger.info(f"[GROUPING] Added {len(login_logout_errors)} login/logout errors to time groups")
    
    if not time_groups:
        return []
    
    # Process each push cycle separately
    all_results = []
    
    # Sort time groups by time (most recent first)
    sorted_time_groups = sorted(time_groups.items(), key=lambda x: x[0], reverse=True)
    
    logger.info(f"[GROUPING] Processing {len(sorted_time_groups)} push cycles from {len(transactions)} transactions")
    logger.info(f"[GROUPING] Time groups: {[str(t[0]) for t in sorted_time_groups[:5]]}")
    
    if len(sorted_time_groups) == 0:
        logger.warning(f"[GROUPING] WARNING: No time groups found! This means all transactions were filtered out or had invalid sent_at")
        return []
    
    if len(sorted_time_groups) == 1:
        logger.warning(f"[GROUPING] WARNING: Only 1 time group found! This suggests all transactions are in the same 5-minute interval.")
        logger.warning(f"[GROUPING] First 10 transaction times: {[tx.get('sent_at', 'N/A')[:19] for tx in transactions[:10]]}")
    
    cycle_count = 0
    # CRITICAL FIX: Ensure we process ALL cycles, not just the first one
    # The loop should iterate through all sorted_time_groups
    logger.info(f"[GROUPING] Starting loop with {len(sorted_time_groups)} cycles, all_results initialized with length: {len(all_results)}")
    print(f"[DEBUG GROUPING] Starting loop with {len(sorted_time_groups)} cycles", file=sys.stderr, flush=True)
    print(f"[DEBUG GROUPING] all_results initialized with length: {len(all_results)}", file=sys.stderr, flush=True)
    
    # CRITICAL: Verify the loop will execute multiple times
    if len(sorted_time_groups) > 1:
        logger.info(f"[GROUPING] Multiple cycles detected: {len(sorted_time_groups)} cycles, should process all of them")
    
    # CRITICAL: Process ALL cycles - use enumerate to ensure we process every one
    # CRITICAL DEBUG: Add a simple counter to verify loop execution
    loop_counter = 0
    
    for cycle_idx, (push_cycle_time, cycle_transactions) in enumerate(sorted_time_groups):
        loop_counter += 1  # This MUST increment for every cycle
        cycle_count = cycle_idx + 1
        
        # CRITICAL: Log at the very start of each iteration
        logger.info(f"[GROUPING] ===== LOOP ITERATION {cycle_count}/{len(sorted_time_groups)} START =====")
        print(f"[DEBUG GROUPING] ===== LOOP ITERATION {cycle_count}/{len(sorted_time_groups)} START =====", file=sys.stderr, flush=True)
        print(f"[DEBUG GROUPING] Cycle time: {push_cycle_time}, Transactions: {len(cycle_transactions)}, all_results BEFORE: {len(all_results)}", file=sys.stderr, flush=True)
        
        # CRITICAL: Track if this cycle produces results
        cycle_results_before = len(all_results)
        
        # CRITICAL: Initialize cycle_result OUTSIDE try block to ensure it's always available
        cycle_result = []
        
        # CRITICAL: Verify we have transactions in this cycle
        if not cycle_transactions:
            logger.warning(f"[GROUPING] Cycle {cycle_count}: No transactions in cycle_transactions!")
            print(f"[DEBUG GROUPING] Cycle {cycle_count}: WARNING - cycle_transactions is empty!", file=sys.stderr, flush=True)
            continue
        
        # CRITICAL FIX: Process each cycle - wrap in try-except to catch any errors
        try:
            logger.info(f"[GROUPING] Processing cycle {cycle_count}/{len(sorted_time_groups)}: {push_cycle_time} with {len(cycle_transactions)} transactions")
            print(f"[DEBUG GROUPING] Processing cycle {cycle_count}/{len(sorted_time_groups)}: {push_cycle_time} with {len(cycle_transactions)} transactions", file=sys.stderr, flush=True)
            # CRITICAL DEBUG: Log sample exchange_ids for this cycle
            sample_exchange_ids = [tx.get('exchange_id', 'MISSING') for tx in cycle_transactions[:10]]
            print(f"[DEBUG GROUPING] Cycle {cycle_count} sample exchange_ids: {sample_exchange_ids}", file=sys.stderr, flush=True)
            
            # For each push cycle, group by (exchange_id, metric_type)
            # This ensures hardware and network metrics are kept separate
            grouped = defaultdict(lambda: {
                'transactions': [],
                'metric_types': set(),
                'sent_at': None
            })
            
            # Process all transactions in this cycle (they're already grouped by 5-minute interval)
            processed_count = 0
            skipped_no_exchange = 0
            skipped_no_time = 0
            
            for tx in cycle_transactions:
                tx_metric_type = tx.get('metric_type')
                exchange_id = tx.get('exchange_id')
                
                # CRITICAL: Login/logout transactions don't have exchange_id (they're environment-wide)
                # Allow them to pass through even without exchange_id
                is_login_logout = tx_metric_type in ['login', 'logout']
                
                # CRITICAL: If exchange_id is missing, try to extract it from metrics_sent (fallback)
                if not exchange_id:
                    metrics_sent = tx.get('metrics_sent', {})
                    if isinstance(metrics_sent, dict):
                        # Try direct exchangeId first (legacy format)
                        exchange_id = metrics_sent.get('exchangeId')
                        # If not found, try nested in lama_v1_2_payload
                        if not exchange_id:
                            lama_payload = metrics_sent.get('lama_v1_2_payload', {})
                            if isinstance(lama_payload, dict):
                                exchange_id = lama_payload.get('exchangeId')
                        # Convert to int if it's a string number
                        if exchange_id and isinstance(exchange_id, str) and exchange_id.isdigit():
                            exchange_id = int(exchange_id)
                        # Update tx with extracted exchange_id
                        if exchange_id:
                            tx['exchange_id'] = exchange_id
                
                # Skip only if no exchange_id AND not login/logout transaction
                if not exchange_id and not is_login_logout:
                    skipped_no_exchange += 1
                    if cycle_count <= 3:  # Log for first few cycles only
                        logger.warning(f"[GROUPING] Cycle {cycle_count}: Transaction {tx.get('id')} missing exchange_id, metrics_sent keys: {list(tx.get('metrics_sent', {}).keys()) if isinstance(tx.get('metrics_sent'), dict) else 'N/A'}")
                    continue
                
                # For login/logout transactions without exchange_id, use a special key
                if not exchange_id and is_login_logout:
                    exchange_id = f"LOGIN_LOGOUT_{tx_metric_type.upper()}"
                    tx['exchange_id'] = exchange_id  # Set a placeholder exchange_id for grouping
                
                # Parse sent_at
                tx_time = None
                if tx.get('sent_at'):
                    try:
                        tx_time = datetime.fromisoformat(tx['sent_at'])
                        if tx_time.tzinfo:
                            tx_time = tx_time.replace(tzinfo=None)
                    except:
                        pass
                
                # Include all transactions in this cycle (no time window restriction)
                # CRITICAL: For login/logout transactions, allow them even without sent_at timestamp
                # Regular metrics require sent_at for time-based grouping, but errors should still be visible
                if tx_time or is_login_logout:
                    # Apply metric_type filter if specified (tx_metric_type already set above)
                    # Skip counting and processing if filter doesn't match
                    if metric_type_filter and tx_metric_type != metric_type_filter:
                        continue
                    
                    # Only increment processed_count for transactions that pass the metric_type filter
                    processed_count += 1
                    
                    # CRITICAL: Group by (exchange_id, location_id) to allow merging of all metric types
                    # but PRESERVING different sites as distinct rows.
                    tx_location_id = tx.get('location_id')
                    group_key = (exchange_id, tx_location_id)
                    
                    if not isinstance(grouped[group_key], dict):
                        grouped[group_key] = {
                            'transactions': [],
                            'metric_types': set(),
                            'sent_at': None,
                            'exchange_id': exchange_id,
                            'location_id': tx_location_id
                        }
                    
                    grouped[group_key]['transactions'].append(tx)
                    if tx_metric_type:
                        grouped[group_key]['metric_types'].add(tx_metric_type)
                    # Only update sent_at if we have a valid timestamp
                    if tx_time:
                        if not grouped[group_key]['sent_at'] or tx_time > grouped[group_key]['sent_at']:
                            grouped[group_key]['sent_at'] = tx_time
                    elif is_login_logout and not grouped[group_key]['sent_at']:
                        # For login/logout without timestamp, use sent_at from transaction if available
                        tx_sent_at = tx.get('sent_at')
                        if tx_sent_at:
                            try:
                                parsed_time = datetime.fromisoformat(tx_sent_at)
                                if parsed_time.tzinfo:
                                    parsed_time = parsed_time.replace(tzinfo=None)
                                grouped[group_key]['sent_at'] = parsed_time
                            except:
                                # If parsing fails, use current time as fallback
                                grouped[group_key]['sent_at'] = datetime.now()
                else:
                    skipped_no_time += 1
            
            # Log details for all cycles (not just first 3) to debug time range issue
            logger.info(f"[GROUPING] Cycle {cycle_count}: Processed {processed_count}, skipped (no exchange): {skipped_no_exchange}, skipped (no time): {skipped_no_time}, grouped exchanges: {len(grouped)}")
            print(f"[DEBUG GROUPING] Cycle {cycle_count}: Processed={processed_count}, Skipped(no exchange)={skipped_no_exchange}, Skipped(no time)={skipped_no_time}, Grouped={len(grouped)}", file=sys.stderr, flush=True)
            
            # CRITICAL: Log grouped exchange IDs to see what we have
            if grouped:
                grouped_exchange_ids = list(grouped.keys())
                logger.info(f"[GROUPING] Cycle {cycle_count}: Grouped exchange IDs: {grouped_exchange_ids}")
                print(f"[DEBUG GROUPING] Cycle {cycle_count}: Grouped exchange IDs: {grouped_exchange_ids}", file=sys.stderr, flush=True)
            else:
                logger.warning(f"[GROUPING] Cycle {cycle_count}: grouped is EMPTY! This means no transactions were grouped by exchange_id.")
                print(f"[DEBUG GROUPING] Cycle {cycle_count}: WARNING - grouped is EMPTY!", file=sys.stderr, flush=True)
            
            # CRITICAL DEBUG: If this cycle has transactions but no grouped results, log why
            if len(cycle_transactions) > 0 and len(grouped) == 0:
                logger.error(f"[GROUPING] Cycle {cycle_count}: Has {len(cycle_transactions)} transactions but grouped=0! This means all transactions were filtered out.")
                logger.error(f"[GROUPING] Cycle {cycle_count}: Sample transaction exchange_ids: {[tx.get('exchange_id', 'MISSING') for tx in cycle_transactions[:5]]}")
                print(f"[DEBUG GROUPING] ERROR: Cycle {cycle_count} has {len(cycle_transactions)} transactions but grouped=0!", file=sys.stderr, flush=True)
            
            # Convert grouped data to single entry per exchange for this cycle
            # cycle_result already initialized outside try block
            exchange_map = {'1': 'NSE', '2': 'BSE', '4': 'MCX', '5': 'NCDEX'}
            
            logger.info(f"[GROUPING] Cycle {cycle_count}: Starting to process {len(grouped)} grouped exchanges into cycle_result")
            print(f"[DEBUG GROUPING] Cycle {cycle_count}: Starting to process {len(grouped)} grouped exchanges", file=sys.stderr, flush=True)
            
            for group_key, group_data in grouped.items():
                if not group_data['transactions']:
                    print(f"[DEBUG GROUPING] Cycle {cycle_count}: Group {group_key} has no transactions, skipping", file=sys.stderr, flush=True)
                    continue
                
                # Extract exchange_id from group_key (always a tuple of (exchange_id, location_id))
                exchange_id = group_key[0] if isinstance(group_key, tuple) else group_key
                tx_location_id = group_key[1] if isinstance(group_key, tuple) else group_data.get('location_id')

                # CRITICAL FIX: When status_filter is None or 'all', prefer success for grouping (best representative)
                # When status_filter is 'failed', prefer failed transactions so they're not lost
                # When status_filter is 'success', prefer success (default behavior)
                group_txs = group_data['transactions']
                
                # CRITICAL FIX: Sort by response_code == 601 (not database status)
                # This ensures we select the transaction with the correct response_code as primary
                # Database status field can be incorrect, but response_code is the source of truth
                try:
                    def get_response_code_for_sort(tx):
                        """Extract response_code for sorting - prefer response_code field, then exchange_response"""
                        tx_response_code = tx.get('response_code')
                        if tx_response_code is None:
                            exchange_response = tx.get('exchange_response', {})
                            if isinstance(exchange_response, dict):
                                tx_response_code = exchange_response.get('responseCode')
                        return tx_response_code
                    
                    # Determine if we should prefer failed transactions (when status_filter is 'failed')
                    prefer_failed = status_filter and status_filter.strip().lower() == 'failed'
                    
                    if prefer_failed:
                        # When filtering for failed, prefer failed transactions (response_code != 601)
                        # This ensures failed transactions are not lost during grouping
                        group_txs.sort(key=lambda x: (
                            get_response_code_for_sort(x) != 601 and get_response_code_for_sort(x) != '601',  # True for failed comes first
                            x.get('sent_at', '')
                        ), reverse=True)
                    else:
                        # Default: prefer success (response_code == 601) for best representative
                        group_txs.sort(key=lambda x: (
                            get_response_code_for_sort(x) == 601 or get_response_code_for_sort(x) == '601',  # True for success (601) comes first
                            x.get('sent_at', '')
                        ), reverse=True)
                except Exception as e:
                    logger.error(f"[GROUPING] Cycle {cycle_count}: Error sorting transactions for group {group_key}: {e}")
                    print(f"[DEBUG GROUPING] ERROR: Cycle {cycle_count}, Group {group_key} sort error: {e}", file=sys.stderr, flush=True)
                    # Continue with unsorted list
                    pass
                
                # CRITICAL FIX: Determine if we should show all statuses or filter by specific status
                show_all_statuses = not status_filter or (status_filter.strip().lower() if status_filter and status_filter.strip() else '') == 'all'
                status_filter_lower = status_filter.strip().lower() if status_filter and status_filter.strip() else None
                
                # CRITICAL FIX: Always prefer success over failure. Find the best single transaction to represent the group.
                # The list `group_txs` is already sorted with successes (response_code=601) coming first.
                primary_tx = None
                
                # If a specific status filter is applied (e.g., 'failed'), find the first transaction that matches it.
                if status_filter_lower and status_filter_lower != 'all':
                    for tx in group_txs:
                        # Check metric_type filter first
                        if metric_type_filter and tx.get('metric_type', '').lower() != metric_type_filter.lower():
                            continue
                            
                        tx_response_code = _extract_response_code(tx)
                        tx_db_status = tx.get('status')
                        tx_actual_status = _determine_status_from_response_code(tx_response_code, tx_db_status)
                        
                        if tx_actual_status == status_filter_lower:
                            primary_tx = tx
                            break  # Found a match, use it
                else:
                    # No status filter ('all'), so just take the best one (the first in the sorted list).
                    # We still need to respect the metric_type filter if it's set.
                    if group_txs:
                        if metric_type_filter:
                            # Find the first transaction that matches the metric type
                            for tx in group_txs:
                                if tx.get('metric_type', '').lower() == metric_type_filter.lower():
                                    primary_tx = tx
                                    break
                        else:
                            # No metric_type filter, so the first transaction is the best representative
                            primary_tx = group_txs[0]

                transactions_to_process = [primary_tx] if primary_tx else []
                
                # Process each transaction (usually 1, but 2-3 when status='all' and multiple statuses exist)
                # CRITICAL: Skip if no transactions to process (e.g., metric_type filter excluded all)
                if not transactions_to_process:
                    continue
                    
                for primary_tx in transactions_to_process:
                    print(f"[DEBUG GROUPING] Cycle {cycle_count}: Group {group_key}, primary_tx status={primary_tx.get('status')}, has metrics_sent={bool(primary_tx.get('metrics_sent'))}", file=sys.stderr, flush=True)
                    
                    # Check if this is a login/logout transaction (placeholder exchange_id)
                    is_login_logout_group = isinstance(exchange_id, str) and exchange_id.startswith('LOGIN_LOGOUT_')
                    
                    # If no metric_type filter, aggregate all metric types
                    # BUT: Skip aggregation for login/logout transactions (they don't have metrics to aggregate)
                    if not metric_type_filter and not is_login_logout_group:
                        try:
                            # Combine metrics from all metric types in the group
                            all_metrics_sent = primary_tx.get('metrics_sent', {}).copy() if primary_tx.get('metrics_sent') else {}
                            all_payloads = []
                            all_original_metrics = []
                            
                            # Track seen applicationIds and metric names to prevent 4x duplication from multiple exchanges
                            seen_payload_keys = set()
                            seen_metric_keys = set()

                            # Collect payloads and original_metrics from all transactions
                            for tx in group_txs:
                                tx_metrics_sent = tx.get('metrics_sent', {})
                                if isinstance(tx_metrics_sent, dict):
                                    # Collect payload arrays from lama_v1_2_payload
                                    if 'lama_v1_2_payload' in tx_metrics_sent:
                                        tx_payload = tx_metrics_sent['lama_v1_2_payload'].get('payload', [])
                                        for p in tx_payload:
                                            # Create a unique key for this payload entry (appId + metric keys)
                                            # This prevents adding the same data 4 times (for 4 exchanges)
                                            m_keys = ",".join(sorted([m.get('key', '') for m in p.get('metricData', [])]))
                                            p_key = f"{p.get('applicationId')}_{m_keys}"
                                            if p_key not in seen_payload_keys:
                                                all_payloads.append(p)
                                                seen_payload_keys.add(p_key)
                                    
                                    # Collect original_metrics (individual server details)
                                    if 'original_metrics' in tx_metrics_sent:
                                        for m in tx_metrics_sent['original_metrics']:
                                            # Unique key: server_ip + applicationId + metric_name
                                            # This ensures metrics from different apps on same server are NOT deduplicated
                                            m_key = f"{m.get('server_ip')}_{m.get('applicationId') or m.get('server_id')}_{m.get('name', m.get('key'))}"
                                            if m_key not in seen_metric_keys:
                                                all_original_metrics.append(m)
                                                seen_metric_keys.add(m_key)
                            
                            # Update metrics_sent with aggregated data
                            if 'lama_v1_2_payload' not in all_metrics_sent:
                                all_metrics_sent['lama_v1_2_payload'] = {}
                            
                            # Use primary transaction's lama_v1_2_payload as base, but replace payload with aggregated
                            primary_payload = primary_tx.get('metrics_sent', {}).get('lama_v1_2_payload', {})
                            if not isinstance(primary_payload, dict):
                                primary_payload = {}
                            all_metrics_sent['lama_v1_2_payload'] = {
                                'memberId': primary_payload.get('memberId'),
                                'exchangeId': primary_payload.get('exchangeId'),
                                'sequenceId': primary_payload.get('sequenceId'),
                                'timestamp': primary_payload.get('timestamp'),
                                'payload': all_payloads if all_payloads else primary_payload.get('payload', [])
                            }
                            
                            if all_original_metrics:
                                all_metrics_sent['original_metrics'] = all_original_metrics
                            
                            # Update primary transaction with aggregated metrics
                            primary_tx['metrics_sent'] = all_metrics_sent
                            primary_tx['metric_type'] = 'all'  # Indicate all metric types combined
                        except Exception as e:
                            # If aggregation fails, log error but still create the grouped transaction
                            logger.error(f"[GROUPING] Cycle {cycle_count}: Error aggregating metrics for exchange {exchange_id}: {e}")
                            print(f"[DEBUG GROUPING] ERROR: Cycle {cycle_count}, Exchange {exchange_id}: {e}", file=sys.stderr, flush=True)
                            # Continue with primary_tx as-is
                    
                    # Create grouped transaction entry
                    try:
                        # Handle exchange_name for login/logout transactions (placeholder exchange_id)
                        if is_login_logout_group:
                            # Extract the metric type from placeholder (e.g., "LOGIN_LOGOUT_LOGIN" -> "LOGIN ERROR")
                            metric_type_from_id = exchange_id.replace('LOGIN_LOGOUT_', '').lower()
                            if metric_type_from_id == 'login':
                                exchange_name = 'LOGIN ERROR'
                            elif metric_type_from_id == 'logout':
                                exchange_name = 'LOGOUT ERROR'
                            else:
                                exchange_name = 'LOGIN/LOGOUT ERROR'
                            # Use None for exchange_id in response so frontend can handle it correctly
                            response_exchange_id = None
                        else:
                            exchange_name = exchange_map.get(str(exchange_id), f'Exchange {exchange_id}')
                            response_exchange_id = exchange_id
                    
                        grouped_tx = {
                            **primary_tx,
                            'exchange_id': response_exchange_id,  # None for login/logout, actual ID for metrics
                            'exchange_name': exchange_name,
                            'location_id': primary_tx.get('location_id'),
                            'location_name': primary_tx.get('location_name'),
                            'grouped_count': len(group_txs),
                            'metric_types': sorted(list(group_data['metric_types'])),
                            'server_id': primary_tx.get('server_id'),
                            'server_name': primary_tx.get('server_name'),
                            'server_ip': primary_tx.get('server_ip'),
                            'sequence_id': primary_tx.get('sequence_id')
                        }
                        
                        cycle_result.append(grouped_tx)
                        print(f"[DEBUG GROUPING] Cycle {cycle_count}: Added exchange {exchange_id} to cycle_result, total in cycle_result: {len(cycle_result)}", file=sys.stderr, flush=True)
                    except Exception as e:
                        logger.error(f"[GROUPING] Cycle {cycle_count}: Error creating grouped_tx for exchange {exchange_id}: {e}", exc_info=True)
                        print(f"[DEBUG GROUPING] ERROR: Cycle {cycle_count}, Exchange {exchange_id} create error: {e}", file=sys.stderr, flush=True)
                        
                        # Try to create a minimal grouped_tx ONLY on failure
                        try:
                            # Handle exchange_name for login/logout transactions in minimal fallback too
                            is_login_logout_fallback = isinstance(exchange_id, str) and exchange_id.startswith('LOGIN_LOGOUT_')
                            if is_login_logout_fallback:
                                metric_type_from_id = exchange_id.replace('LOGIN_LOGOUT_', '').lower()
                                if metric_type_from_id == 'login':
                                    exchange_name_fallback = 'LOGIN ERROR'
                                elif metric_type_from_id == 'logout':
                                    exchange_name_fallback = 'LOGOUT ERROR'
                                else:
                                    exchange_name_fallback = 'LOGIN/LOGOUT ERROR'
                                response_exchange_id_fallback = None
                            else:
                                exchange_name_fallback = exchange_map.get(str(exchange_id), f'Exchange {exchange_id}')
                                response_exchange_id_fallback = exchange_id
                            
                            grouped_tx = {
                                'id': primary_tx.get('id'),
                                'environment': primary_tx.get('environment'),
                                'metric_type': primary_tx.get('metric_type', 'all'),
                                'metrics_sent': primary_tx.get('metrics_sent', {}),
                                'exchange_response': primary_tx.get('exchange_response', {}),
                                'status': primary_tx.get('status'),
                                'status_code': primary_tx.get('status_code'),
                                'response_code': primary_tx.get('response_code'),
                                'sent_at': primary_tx.get('sent_at'),
                                'exchange_id': response_exchange_id_fallback,
                                'exchange_name': exchange_name_fallback,
                                'grouped_count': len(group_txs),
                                'metric_types': sorted(list(group_data['metric_types']))
                            }
                            cycle_result.append(grouped_tx)
                            print(f"[DEBUG GROUPING] Cycle {cycle_count}: Added minimal grouped_tx for exchange {exchange_id}", file=sys.stderr, flush=True)
                        except Exception as e2:
                            logger.error(f"[GROUPING] Cycle {cycle_count}: Error creating minimal grouped_tx for exchange {exchange_id}: {e2}")
                            print(f"[DEBUG GROUPING] ERROR: Cycle {cycle_count}, Exchange {exchange_id} minimal create also failed: {e2}", file=sys.stderr, flush=True)
            
            # Sort by exchange_id (NSE=1, BSE=2, MCX=4, NCDEX=5)
            # Login/logout transactions have exchange_id=None, sort them last
            cycle_result.sort(key=lambda x: (
                x.get('exchange_id') is None,  # None values go last (True sorts after False)
                int(x.get('exchange_id', 0)) if x.get('exchange_id') and str(x.get('exchange_id', '')).isdigit() else 999
            ))
            
            logger.info(f"[GROUPING] Cycle {cycle_count}: After processing all exchanges, cycle_result length: {len(cycle_result)}")
            print(f"[DEBUG GROUPING] Cycle {cycle_count}: After processing all exchanges, cycle_result length: {len(cycle_result)}", file=sys.stderr, flush=True)
            
            # Final safety check: limit to 4 entries per cycle (one per exchange)
            # Keep only one entry per exchange_id
            # CRITICAL FIX: When status_filter is specific (success/failed/error), ONLY keep transactions matching that status
            # When status_filter is None or 'all', prefer success (best representative)
            # CRITICAL: Handle login/logout transactions (exchange_id=None) separately
            if len(cycle_result) > 4:
                exchange_map_dedup = {}
                login_logout_txs = []  # Store login/logout transactions separately
                
                # Determine status filter requirements
                show_all_statuses = not status_filter or (status_filter.strip().lower() if status_filter and status_filter.strip() else '') == 'all'
                status_filter_lower = status_filter.strip().lower() if status_filter and status_filter.strip() else None
                
                for tx in cycle_result:
                    exchange_id = tx.get('exchange_id')
                    
                    # Handle login/logout transactions (exchange_id=None) separately
                    if exchange_id is None:
                        login_logout_txs.append(tx)
                        continue
                    
                    # CRITICAL: If status filter is specific, ONLY keep transactions matching that status
                    tx_response_code = _extract_response_code(tx)
                    tx_db_status = tx.get('status')
                    tx_actual_status = _determine_status_from_response_code(tx_response_code, tx_db_status)
                    
                    if not show_all_statuses and tx_actual_status != status_filter_lower:
                        continue  # Skip this transaction - it doesn't match the status filter
                    
                    # CRITICAL FIX: Include location_id in the deduplication key.
                    # Previously, using only exchange_id caused different sites (DC, DR, Cloud)
                    # to be collapsed into a single row per exchange.
                    tx_loc_id = tx.get('location_id')
                    if metric_type_filter:
                        exchange_key = f"{exchange_id}_{tx_loc_id}_{tx.get('metric_type', 'all')}"
                    else:
                        exchange_key = f"{exchange_id}_{tx_loc_id}"

                    if exchange_key not in exchange_map_dedup:
                        exchange_map_dedup[exchange_key] = tx
                    else:
                        # If we already have a record, check if the new one is 'better' (Success vs Failure)
                        existing_tx = exchange_map_dedup[exchange_key]
                        existing_res_code = _extract_response_code(existing_tx)
                        new_res_code = _extract_response_code(tx)
                        
                        # If existing is not success (601) but new one is, replace it
                        if (existing_res_code != 601 and existing_res_code != '601') and (new_res_code == 601 or new_res_code == '601'):
                            exchange_map_dedup[exchange_key] = tx
                        # Otherwise, if both are same status, prefer more recent
                        elif (existing_res_code == new_res_code):
                            existing_time = existing_tx.get('sent_at', '')
                            tx_time = tx.get('sent_at', '')
                            if tx_time and existing_time and tx_time > existing_time:
                                exchange_map_dedup[exchange_key] = tx
                
                # Rebuild cycle_result with deduplicated regular transactions + all login/logout transactions
                cycle_result = list(exchange_map_dedup.values()) + login_logout_txs
                cycle_result.sort(key=lambda x: (
                    x.get('exchange_id') is None,  # None values go last (True sorts after False)
                    int(x.get('exchange_id', 0)) if x.get('exchange_id') and str(x.get('exchange_id', '')).isdigit() else 999
                ))
            
            # CRITICAL: Add all entries from this push cycle to the final result
            # This MUST happen for every cycle, regardless of whether cycle_result is empty
            print(f"[DEBUG GROUPING] Cycle {cycle_count}: BEFORE extend - cycle_result length={len(cycle_result)}, all_results length={len(all_results)}", file=sys.stderr, flush=True)
            
            # CRITICAL FIX: Always extend, even if cycle_result is empty (to ensure loop processes all cycles)
            # But only extend if we have results
            if cycle_result:
                all_results_before_extend = len(all_results)
                all_results.extend(cycle_result)
                all_results_after_extend = len(all_results)
                
                # Verify the extend worked
                if all_results_after_extend != all_results_before_extend + len(cycle_result):
                    logger.error(f"[GROUPING] CRITICAL: extend() failed! Before: {all_results_before_extend}, After: {all_results_after_extend}, Expected: {all_results_before_extend + len(cycle_result)}")
                    print(f"[DEBUG GROUPING] CRITICAL: extend() failed! Before: {all_results_before_extend}, After: {all_results_after_extend}", file=sys.stderr, flush=True)
                
                print(f"[DEBUG GROUPING] Cycle {cycle_count}: AFTER extend - all_results length={len(all_results)} (added {len(cycle_result)})", file=sys.stderr, flush=True)
                logger.info(f"[GROUPING] Cycle {cycle_count}/{len(sorted_time_groups)}: Added {len(cycle_result)} entries from push cycle at {push_cycle_time}, total results: {len(all_results)}")
                print(f"[DEBUG GROUPING] Cycle {cycle_count}/{len(sorted_time_groups)}: Added {len(cycle_result)} entries, total: {len(all_results)}", file=sys.stderr, flush=True)
            else:
                # Log why this cycle produced no results
                logger.warning(f"[GROUPING] Cycle {cycle_count}/{len(sorted_time_groups)}: No results produced! Processed: {processed_count}, Skipped (no exchange): {skipped_no_exchange}, Skipped (no time): {skipped_no_time}, Grouped exchanges: {len(grouped)}")
                print(f"[DEBUG GROUPING] Cycle {cycle_count}/{len(sorted_time_groups)}: No results! Processed: {processed_count}, Skipped (no exchange): {skipped_no_exchange}, Skipped (no time): {skipped_no_time}, Grouped: {len(grouped)}", file=sys.stderr, flush=True)
                # CRITICAL DEBUG: If grouped has exchanges but cycle_result is empty, something is wrong
                if len(grouped) > 0:
                    logger.error(f"[GROUPING] ERROR: Cycle {cycle_count} has {len(grouped)} grouped exchanges but cycle_result is empty!")
                    print(f"[DEBUG GROUPING] ERROR: Cycle {cycle_count} has {len(grouped)} grouped exchanges but cycle_result is empty!", file=sys.stderr, flush=True)
                    for ex_id, group_data in grouped.items():
                        logger.error(f"[GROUPING]   Exchange {ex_id}: {len(group_data['transactions'])} transactions")
                        print(f"[DEBUG GROUPING]   Exchange {ex_id}: {len(group_data['transactions'])} transactions", file=sys.stderr, flush=True)
            
            cycle_results_after = len(all_results)
            logger.info(f"[GROUPING] ===== LOOP ITERATION {cycle_count}/{len(sorted_time_groups)} END, all_results length: {len(all_results)} (added {cycle_results_after - cycle_results_before}) =====")
            print(f"[DEBUG GROUPING] ===== LOOP ITERATION {cycle_count}/{len(sorted_time_groups)} END, all_results length: {len(all_results)} (added {cycle_results_after - cycle_results_before}) =====", file=sys.stderr, flush=True)
        
        except Exception as e:
            # If processing this cycle fails, log error but continue to next cycle
            logger.error(f"[GROUPING] Cycle {cycle_count}: Exception while processing: {e}", exc_info=True)
            print(f"[DEBUG GROUPING] ERROR: Cycle {cycle_count} exception: {e}", file=sys.stderr, flush=True)
            import traceback
            print(f"[DEBUG GROUPING] Traceback: {traceback.format_exc()}", file=sys.stderr, flush=True)
            # CRITICAL: Even if exception occurred, try to save any partial results
            if cycle_result:
                try:
                    all_results.extend(cycle_result)
                    logger.info(f"[GROUPING] Cycle {cycle_count}: Recovered {len(cycle_result)} results after exception")
                    print(f"[DEBUG GROUPING] Cycle {cycle_count}: Recovered {len(cycle_result)} results after exception", file=sys.stderr, flush=True)
                except Exception as e2:
                    logger.error(f"[GROUPING] Cycle {cycle_count}: Failed to recover results: {e2}")
            # CRITICAL: Continue to next cycle - don't break the loop
            continue
    
    # Sort all results by sent_at (most recent first), then by exchange_id
    print(f"[DEBUG GROUPING] BEFORE SORT: all_results length: {len(all_results)}", file=sys.stderr, flush=True)
    all_results.sort(key=lambda x: (
        x.get('sent_at', '') or '',
        int(x.get('exchange_id', 0)) if str(x.get('exchange_id', '')).isdigit() else 999
    ), reverse=True)
    print(f"[DEBUG GROUPING] AFTER SORT: all_results length: {len(all_results)}", file=sys.stderr, flush=True)
    
    # CRITICAL: Log final state before return
    logger.info(f"[GROUPING] FINAL: loop_counter={loop_counter}, sorted_time_groups={len(sorted_time_groups)}, all_results={len(all_results)}")
    print(f"[DEBUG GROUPING] FINAL: loop_counter={loop_counter}, sorted_time_groups={len(sorted_time_groups)}, all_results={len(all_results)}", file=sys.stderr, flush=True)
    
    # CRITICAL: If loop_counter doesn't match sorted_time_groups, the loop is broken
    if loop_counter != len(sorted_time_groups):
        logger.error(f"[GROUPING] CRITICAL: loop_counter ({loop_counter}) doesn't match number of time groups ({len(sorted_time_groups)})! Loop is broken!")
        print(f"[DEBUG GROUPING] CRITICAL: loop_counter ({loop_counter}) doesn't match number of time groups ({len(sorted_time_groups)})! Loop is broken!", file=sys.stderr, flush=True)
    
    # CRITICAL: Log sample of all_results to verify it has transactions from multiple cycles
    if len(all_results) > 0:
        sample_times = [tx.get('sent_at', '')[:19] for tx in all_results[:10]]
        logger.info(f"[GROUPING] Sample sent_at times from all_results: {sample_times}")
        print(f"[DEBUG GROUPING] Sample sent_at times from all_results: {sample_times}", file=sys.stderr, flush=True)
    
    # Write final state to file
    try:
        with open('/tmp/grouping_loop_debug.txt', 'a') as debug_file:
            debug_file.write(f"\nFINAL: loop_counter={loop_counter}, sorted_time_groups={len(sorted_time_groups)}, all_results={len(all_results)}\n")
    except:
        pass
    
    # CRITICAL: Force return all_results - ensure we're not accidentally returning a subset
    logger.info(f"[GROUPING] About to return {len(all_results)} transactions")
    print(f"[DEBUG GROUPING] About to return {len(all_results)} transactions", file=sys.stderr, flush=True)
    
    if len(all_results) < len(sorted_time_groups) * 2:
        logger.warning(f"[GROUPING] WARNING: Expected at least {len(sorted_time_groups) * 2} transactions (2 exchanges × {len(sorted_time_groups)} cycles), but got {len(all_results)}")
        logger.warning(f"[GROUPING] This suggests some cycles are not producing results. Check logs above for skipped transactions.")
        print(f"[DEBUG GROUPING] WARNING: Expected {len(sorted_time_groups) * 4} but got {len(all_results)}")
    
    # CRITICAL FIX: If we only got results from one cycle, check if all cycles were processed
    if len(all_results) == 4 and len(sorted_time_groups) > 1:
        logger.error(f"[GROUPING] CRITICAL ERROR: Only got 4 transactions (1 cycle) but {len(sorted_time_groups)} cycles were found!")
        logger.error(f"[GROUPING] This means the loop is not processing all cycles. Checking cycle processing...")
        # Force process all cycles by ensuring the loop completes
        # This is a safety check - the loop should already process all cycles
        processed_cycles = cycle_count
        logger.error(f"[GROUPING] Loop processed {processed_cycles} cycles out of {len(sorted_time_groups)}")
        print(f"[DEBUG GROUPING] CRITICAL ERROR: Loop processed {processed_cycles} cycles but only got {len(all_results)} results!")
        print(f"[DEBUG GROUPING] This suggests cycles after the first are not producing results.")
        # CRITICAL DEBUG: Log details about each cycle to understand why they're not producing results
        for idx, (cycle_time, cycle_txs) in enumerate(sorted_time_groups[:5]):  # Log first 5 cycles
            logger.error(f"[GROUPING] Cycle {idx+1} details: time={cycle_time}, transactions={len(cycle_txs)}")
            if cycle_txs:
                sample_tx = cycle_txs[0]
                logger.error(f"[GROUPING] Cycle {idx+1} sample: exchange_id={sample_tx.get('exchange_id', 'MISSING')}, sent_at={sample_tx.get('sent_at', 'MISSING')[:19] if sample_tx.get('sent_at') else 'MISSING'}, metric_type={sample_tx.get('metric_type', 'MISSING')}")
    
    return all_results


@router.get("/exchange-transactions-summary")
def get_exchange_transactions_summary(
    start_date: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    start_time: Optional[str] = Query(None, description="Start time (HH:MM:SS)"),
    end_time: Optional[str] = Query(None, description="End time (HH:MM:SS)"),
    environment: str = Depends(get_active_environment),
    location_id: Optional[int] = Query(None, description="Filter by location ID (1=DC, 2=DR, 3=Cloud)"),
    db: Session = Depends(get_db)
):
    """
    Get a summary of exchange transactions with date and time range filtering.
    """
    try:
        query = select(
            exchange_transactions_table.c.metric_type,
            func.count(exchange_transactions_table.c.id).label("total"),
            func.sum(case((exchange_transactions_table.c.status == 'success', 1), else_=0)).label("success"),
            func.sum(case((exchange_transactions_table.c.status != 'success', 1), else_=0)).label("failed")
        ).group_by(exchange_transactions_table.c.metric_type)

        if location_id is not None:
            query = query.where(exchange_transactions_table.c.location_id == location_id)

        # NOTE: Frontend sends UTC times. Database stores IST (PostgreSQL timezone=Asia/Kolkata).
        IST_OFFSET = timedelta(hours=5, minutes=30)

        if start_date:
            try:
                if start_time:
                    start_dt = datetime.strptime(f"{start_date} {start_time}", "%Y-%m-%d %H:%M:%S") + IST_OFFSET
                else:
                    start_dt = datetime.strptime(start_date, "%Y-%m-%d")
                query = query.where(exchange_transactions_table.c.sent_at >= start_dt)
            except ValueError as e:
                raise HTTPException(status_code=400, detail=f"Invalid start_date/start_time format: {str(e)}. Use YYYY-MM-DD for date and HH:MM:SS for time")

        if end_date:
            try:
                if end_time:
                    end_dt = datetime.strptime(f"{end_date} {end_time}", "%Y-%m-%d %H:%M:%S") + IST_OFFSET
                else:
                    end_dt = datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1)
                query = query.where(exchange_transactions_table.c.sent_at < end_dt)
            except ValueError as e:
                raise HTTPException(status_code=400, detail=f"Invalid end_date/end_time format: {str(e)}. Use YYYY-MM-DD for date and HH:MM:SS for time")

        # RULE 2: ALWAYS filter by environment
        query = query.where(exchange_transactions_table.c.environment == environment)

        if location_id is not None:
            query = query.where(exchange_transactions_table.c.location_id == location_id)

        query = query.where(
            exchange_transactions_table.c.metric_type.in_(['hardware', 'network', 'database', 'application'])
        )

        with engine.connect() as conn:
            results = conn.execute(query).fetchall()

            summary = {
                'hardware': {'success': 0, 'failed': 0, 'total': 0},
                'network': {'success': 0, 'failed': 0, 'total': 0},
                'application': {'success': 0, 'failed': 0, 'total': 0},
                'database': {'success': 0, 'failed': 0, 'total': 0},
            }

            for row in results:
                metric_type = row[0]
                if metric_type in summary:
                    summary[metric_type]['total'] = row[1]
                    summary[metric_type]['success'] = row[2]
                    summary[metric_type]['failed'] = row[3]

            return summary

    except HTTPException:
        raise
    except Exception as e:
        error_detail = str(e)
        logger.error(f"Error fetching exchange transactions summary: {error_detail}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error fetching transactions summary: {error_detail}")


@router.get("/exchange-transactions", response_model=PaginatedExchangeTransactionResponse)
def get_exchange_transactions(
    start_date: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    start_time: Optional[str] = Query(None, description="Start time (HH:MM:SS)"),
    end_time: Optional[str] = Query(None, description="End time (HH:MM:SS)"),
    environment: str = Depends(get_active_environment),
    metric_type: Optional[str] = Query(None, description="Filter by metric type"),
    server_id: Optional[str] = Query(None, description="Filter by server ID"),
    exchange_id: Optional[int] = Query(None, description="Filter by exchange ID (1=NSE, 2=BSE, 3=MSE, 4=MCX, 5=NCDEX)"),
    status: Optional[str] = Query(None, description="Filter by status (success/failed/error)"),
    location_id: Optional[int] = Query(None, description="Filter by location ID (1=DC, 2=DR, 3=Cloud)"),
    sequence_id_search: Optional[str] = Query(None, description="Global search by specific Sequence ID (ignores date filters)"),
    page: int = Query(1, description="Page number"),
    size: int = Query(20, description="Page size"),
    limit: Optional[int] = Query(None, description="Backward compatibility limit - if provided, sets size"),
    group_by_exchange: bool = Query(False, description="Group by exchange and show one entry per exchange per push time"),
    db: Session = Depends(get_db)
):
    """
    Get exchange transaction history with date and time range filtering
    Returns all data sent to LAMA Exchange including sequence IDs
    """
    # For backward compatibility with existing UI
    if limit is None:
        limit = size
    else:
        size = limit

    try:
        # RULE 2: ALWAYS filter by environment
        query = select(exchange_transactions_table).where(exchange_transactions_table.c.environment == environment)

        
        # Preserve the request-level exchange filter separately to avoid variable shadowing later
        requested_exchange_id = exchange_id
        
        # GLOBAL SEARCH OVERRIDE: If sequence_id_search is provided, skip date filters
        is_global_search = bool(sequence_id_search and isinstance(sequence_id_search, str) and sequence_id_search.strip())
        
        # Date and time range filtering
        # NOTE: Frontend sends UTC times. Database stores IST (PostgreSQL timezone=Asia/Kolkata
        # converts tz-aware UTC inserts to IST). We must convert UTC→IST for correct filtering.
        IST_OFFSET = timedelta(hours=5, minutes=30)
        
        if start_date and not is_global_search:
            try:
                if start_time:
                    start_dt = datetime.strptime(f"{start_date} {start_time}", "%Y-%m-%d %H:%M:%S") + IST_OFFSET
                else:
                    start_dt = datetime.strptime(start_date, "%Y-%m-%d")
                query = query.where(exchange_transactions_table.c.sent_at >= start_dt)
            except ValueError as e:
                raise HTTPException(status_code=400, detail=f"Invalid start_date/start_time format: {str(e)}. Use YYYY-MM-DD for date and HH:MM:SS for time")
        
        if end_date and not is_global_search:
            try:
                if end_time:
                    end_dt = datetime.strptime(f"{end_date} {end_time}", "%Y-%m-%d %H:%M:%S") + IST_OFFSET
                else:
                    end_dt = datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1)
                query = query.where(exchange_transactions_table.c.sent_at < end_dt)
            except ValueError as e:
                raise HTTPException(status_code=400, detail=f"Invalid end_date/end_time format: {str(e)}. Use YYYY-MM-DD for date and HH:MM:SS for time")
        
        # Apply Sequence ID Filter (Global)
        if is_global_search:
            query = query.where(exchange_transactions_table.c.sequence_id == sequence_id_search.strip())
            logger.info(f"[GLOBAL SEARCH] Searching for Sequence ID: {sequence_id_search}")
        
        # Additional filters
        if location_id is not None:
            query = query.where(exchange_transactions_table.c.location_id == location_id)
        
        # CRITICAL: Exchange Activity page shows ONLY regular metrics (hardware, network, database, application)
        # Login/logout errors are displayed on the separate "Exchange Connectivity Errors" page
        # Exclude login/logout transactions entirely from this endpoint
        query = query.where(
            exchange_transactions_table.c.metric_type.notin_(['login', 'logout'])
        )
        
        # Filter by metric type if specified
        if metric_type:
            if metric_type not in ['hardware', 'network', 'database', 'application']:
                raise HTTPException(status_code=400, detail="Invalid metric_type. Must be one of: hardware, network, database, application")
            query = query.where(exchange_transactions_table.c.metric_type == metric_type)
        
        # Filter by status if specified (explicitly check for non-empty string)
        # CRITICAL: Status filtering is done AFTER fetching results based on response_code
        # because the frontend determines success/failure based on response_code = 601,
        # not the database status column. We'll filter in Python after extracting response_code.
        # Note: We don't filter in SQL here - status filtering happens after fetching results
        
        # Filter by server_id if specified
        if server_id:
            query = query.where(exchange_transactions_table.c.server_id == server_id)
        
        if location_id is not None:
            query = query.where(exchange_transactions_table.c.location_id == location_id)
        
        # Filter by exchange_id if specified (extract from metrics_sent JSON)
        # Note: exchange_id is stored in metrics_sent JSON, so we need to extract it during query processing
        # We'll filter it after fetching results
        
        # Order by most recent first
        # CRITICAL FIX: When group_by_exchange is True, calculate limit based on time range
        # Formula: cycles × exchanges × metric_types × servers × safety_factor
        # 1 cycle = 5 minutes
        # 7 days = 2016 cycles × 4 exchanges × 4 metric types × 3 servers × 2 safety = ~193,536 records
        if group_by_exchange:
            # Calculate time range in minutes
            time_range_minutes = 15  # Default to 15 minutes if no range specified
            if start_date and end_date:
                try:
                    if start_time:
                        # CRITICAL: Frontend sends UTC, explicitly mark as UTC
                        start_dt = datetime.strptime(f"{start_date} {start_time}", "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
                    else:
                        start_dt = datetime.strptime(start_date, "%Y-%m-%d")
                    
                    if end_time:
                        # CRITICAL: Frontend sends UTC, explicitly mark as UTC
                        end_dt = datetime.strptime(f"{end_date} {end_time}", "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
                    else:
                        end_dt = datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1)
                    
                    time_range_minutes = max(1, int((end_dt - start_dt).total_seconds() / 60))
                except Exception as e:
                    logger.warning(f"[QUERY] Failed to calculate time range: {e}, using default 15 minutes")
                    time_range_minutes = 15
            
            # Calculate cycles (5-minute intervals)
            cycles = max(1, time_range_minutes // 5)
            # Calculate expected records: cycles × exchanges × metric_types × servers × safety
            # STABLE FORMULA: Account for 24+ servers in the fleet (24 * 4 types * 4 exchanges = 384 per cycle)
            expected_records = cycles * 4 * 4 * 25 * 2  # cycles × exchanges × metric_types × 25 servers × 2 safety
            # Use max of calculated, user limit * 50, or 100K minimum, capped at 1M
            query_limit = min(max(expected_records, limit * 50, 100000), 1000000)  # Cap at 1M
            logger.info(f"[QUERY] Calculated query_limit={query_limit} for {cycles} cycles ({time_range_minutes} minutes, user_limit={limit})")
        else:
            # Without grouping: use provided limit
            query_limit = limit
        
        query = query.order_by(exchange_transactions_table.c.sent_at.desc()).limit(query_limit)
        logger.debug(f"[QUERY] Using query_limit={query_limit} (group_by_exchange={group_by_exchange}, user_limit={limit})")
        
        with engine.connect() as conn:
            results = conn.execute(query).fetchall()
            
            # DIAGNOSTIC: Log status distribution in query results
            status_counts = {}
            for row in results:
                row_status = row[11] if len(row) > 11 else None
                status_counts[row_status] = status_counts.get(row_status, 0) + 1
            logger.info(f"[QUERY] Status distribution in query results: {status_counts}")
            print(f"[DEBUG QUERY] Status distribution: {status_counts}", file=sys.stderr, flush=True)
            
            # Filter out duplicate successful transactions from Error 704 retries
            # Keep only the most recent successful transaction per (environment, exchange_id, metric_type, sent_at window)
            # This prevents showing multiple retry attempts as separate successes
            seen_keys = {}  # Track (environment, exchange_id, metric_type, time_window) -> transaction
            all_transactions = []
            
            for row in results:
                # Row access: id, environment, server_id, server_name, server_ip, member_id, instance_id,
                # metric_type, metrics_sent, sequence_id, exchange_response, status, status_code,
                # error_message, sent_at, response_received_at, exchange_id
                # Column indices: 0=id, 1=environment, 2=server_id, 3=server_name, 4=server_ip,
                # 5=member_id, 6=instance_id, 7=metric_type, 8=metrics_sent, 9=sequence_id,
                # 10=exchange_response, 11=status, 12=status_code, 13=error_message,
                # 14=sent_at, 15=response_received_at, 16=exchange_id
                
                # Extract exchange_id from metrics_sent JSON
                metrics_sent = row[8] if len(row) > 8 else {}  # metrics_sent column (index 8)
                transaction_exchange_id = row[16] if len(row) > 16 else None  # Prefer dedicated column when available
                if transaction_exchange_id is None and isinstance(metrics_sent, dict):
                    # Try direct exchangeId first (legacy format)
                    transaction_exchange_id = metrics_sent.get('exchangeId')
                    # If not found, try nested in lama_v1_2_payload
                    if not transaction_exchange_id:
                        lama_payload = metrics_sent.get('lama_v1_2_payload', {})
                        if isinstance(lama_payload, dict):
                            transaction_exchange_id = lama_payload.get('exchangeId')
                    # Convert to int if it's a string number
                    if transaction_exchange_id and isinstance(transaction_exchange_id, str) and transaction_exchange_id.isdigit():
                        transaction_exchange_id = int(transaction_exchange_id)
                
                # Extract location_id (index 17) and map to name
                loc_id = row[17] if len(row) > 17 else None
                loc_map = {1: "DC", 2: "DR", 3: "AWS"}
                loc_name = loc_map.get(loc_id, "N/A")

                # Extract response code
                exchange_response = row[10] if len(row) > 10 else {}  # exchange_response column (index 10)
                response_code = None
                if isinstance(exchange_response, dict):
                    response_code = exchange_response.get('responseCode')
                
                # Extract status (do NOT shadow request-level status filter)
                tx_status = row[11] if len(row) > 11 else None  # status column (index 11)
                sent_at = row[14] if len(row) > 14 else None  # sent_at column (index 14)
                
                # Create a time window key (round to nearest minute to group retries from same cycle)
                time_window = None
                if sent_at:
                    time_window = sent_at.replace(second=0, microsecond=0)
                
                # For successful transactions (601), check if we've already seen a success for this (exchange, metric_type, time_window)
                # CRITICAL: When group_by_exchange is True, we want to keep all metric types so they can be combined
                # Only filter duplicates if group_by_exchange is False
                if not group_by_exchange and tx_status == 'success' and response_code == 601 and transaction_exchange_id and time_window:
                    key = (row[1], transaction_exchange_id, row[7], time_window)  # (environment, exchange_id, metric_type, time_window)
                    if key in seen_keys:
                        # Skip duplicate - we already have a success for this exchange/metric_type in this time window
                        continue
                    seen_keys[key] = row
                
                # Convert row to dict for response
                # Row access: id, environment, server_id, server_name, server_ip, member_id, instance_id,
                # metric_type, metrics_sent, sequence_id, exchange_response, status, status_code,
                # error_message, sent_at, response_received_at
                all_transactions.append({
                    "id": row[0],
                    "environment": row[1],
                    "server_id": row[2],
                    "server_name": row[3] or "",
                    "server_ip": row[4] or "",
                    "member_id": row[5] or "",
                    "instance_id": row[6] or "",
                    "metric_type": row[7],
                    "metrics_sent": row[8] if row[8] else {},
                    "sequence_id": row[9] or "",
                    "exchange_response": row[10] if row[10] else {},
                    "status": tx_status,
                    "status_code": row[12],
                    "error_message": row[13] or "",
                    "sent_at": (row[14].isoformat()) if row[14] else None,
                    "response_received_at": (row[15].isoformat()) if row[15] else None,
                    "exchange_id": transaction_exchange_id,  # CRITICAL: Add exchange_id for grouping - must be present!
                    "response_code": response_code,  # CRITICAL: Add response_code for status filtering
                    "location_id": loc_id,
                    "location_name": loc_name
                })
            
            # CRITICAL: Apply status filter based on response_code (not database status column)
            # Frontend determines success/failure based on response_code = 601, not database status
            # NOTE: This filter is only applied when group_by_exchange is False
            # When group_by_exchange is True, status filter is applied AFTER grouping (line 921)
            if status and status.strip() and not group_by_exchange:
                status_filter_value = status.strip().lower()
                filtered_transactions = []
                for tx in all_transactions:
                    response_code = _extract_response_code(tx)
                    db_status = tx.get('status')  # Get database status field for timeout/connection errors
                    actual_status = _determine_status_from_response_code(response_code, db_status)
                    
                    # Apply filter
                    if status_filter_value == 'success' and actual_status == 'success':
                        filtered_transactions.append(tx)
                    elif status_filter_value == 'failed' and actual_status == 'failed':
                        filtered_transactions.append(tx)
                    elif status_filter_value == 'error' and actual_status == 'error':
                        filtered_transactions.append(tx)
                
                all_transactions = filtered_transactions
                logger.info(f"[FILTER] Applied status filter '{status}' (group_by_exchange=False): {len(all_transactions)} transactions match")
            
            # If group_by_exchange is True, group transactions by exchange and time
            if group_by_exchange:
                # Debug: Check time distribution of ALL transactions being passed to grouping
                from collections import defaultdict
                time_dist = defaultdict(int)
                exchange_id_count = 0
                missing_exchange_id = 0
                
                # Filter by exchange_id if specified (before grouping)
                if requested_exchange_id is not None:
                    all_transactions = [
                        tx for tx in all_transactions 
                        if tx.get('exchange_id') == requested_exchange_id
                    ]
                    logger.info(f"[FILTER] Filtered to exchange_id={requested_exchange_id}: {len(all_transactions)} transactions")
                
                for tx in all_transactions:
                    # Check exchange_id presence
                    if tx.get('exchange_id'):
                        exchange_id_count += 1
                    else:
                        missing_exchange_id += 1
                    
                    sent_at = tx.get('sent_at', '')
                    if sent_at:
                        try:
                            tx_time = datetime.fromisoformat(sent_at)
                            if tx_time.tzinfo:
                                tx_time = tx_time.replace(tzinfo=None)
                            minutes = tx_time.minute
                            rounded_minute = (minutes // 5) * 5
                            time_key = tx_time.replace(minute=rounded_minute, second=0, microsecond=0)
                            time_dist[time_key] += 1
                        except:
                            pass
                
                logger.info(f"[GROUPING] About to group {len(all_transactions)} transactions across {len(time_dist)} push cycles")
                logger.info(f"[GROUPING] Exchange ID stats: {exchange_id_count} have exchange_id, {missing_exchange_id} missing")
                if len(time_dist) > 0:
                    sorted_dist = sorted(time_dist.items(), key=lambda x: x[0], reverse=True)
                    logger.info(f"[GROUPING] Time distribution (first 10): {dict(sorted_dist[:10])}")
                    logger.info(f"[GROUPING] Expected result: {len(time_dist)} cycles × 4 exchanges = {len(time_dist) * 4} transactions")
                
                # CRITICAL: Verify what we're passing to grouping function
                # Check if all_transactions has transactions from multiple cycles
                test_time_groups = defaultdict(int)
                for tx in all_transactions:
                    sent_at = tx.get('sent_at', '')
                    if sent_at:
                        try:
                            tx_time = datetime.fromisoformat(sent_at)
                            if tx_time.tzinfo:
                                tx_time = tx_time.replace(tzinfo=None)
                            minutes = tx_time.minute
                            rounded_minute = (minutes // 5) * 5
                            time_key = tx_time.replace(minute=rounded_minute, second=0, microsecond=0)
                            test_time_groups[time_key] += 1
                        except:
                            pass
                
                logger.info(f"[GROUPING] Transactions being passed to grouping function: {len(all_transactions)} transactions across {len(test_time_groups)} push cycles")
                if len(test_time_groups) == 1:
                    logger.error(f"[GROUPING] CRITICAL: Only 1 push cycle in input! This means the query is only returning one cycle's transactions.")
                    logger.error(f"[GROUPING] This is the root cause - the query needs to return transactions from ALL cycles, not just the most recent one.")
                    # FIX: The query is ordering by sent_at DESC, which returns most recent first
                    # But if the limit is too small or there's a filter, it might only return one cycle
                    # Let's check the actual query results
                    logger.error(f"[GROUPING] Query returned {len(all_transactions)} transactions, but they're all from the same 5-minute interval.")
                    logger.error(f"[GROUPING] First transaction time: {all_transactions[0].get('sent_at', 'N/A')[:19] if all_transactions else 'N/A'}")
                    logger.error(f"[GROUPING] Last transaction time: {all_transactions[-1].get('sent_at', 'N/A')[:19] if all_transactions else 'N/A'}")
                elif len(test_time_groups) > 1:
                    logger.info(f"[GROUPING] Good: Input has {len(test_time_groups)} push cycles, grouping function should process all of them.")
                    sorted_test = sorted(test_time_groups.items(), key=lambda x: x[0], reverse=True)
                    logger.info(f"[GROUPING] Cycle distribution: {dict(sorted_test[:5])}")
                
                # CRITICAL DEBUG: Print to stdout to bypass logging issues
                print(f"[DEBUG] About to call grouping function with {len(all_transactions)} transactions")
                print(f"[DEBUG] Time distribution shows {len(test_time_groups)} push cycles")
                if len(test_time_groups) > 1:
                    sorted_test = sorted(test_time_groups.items(), key=lambda x: x[0], reverse=True)
                    print(f"[DEBUG] First 5 cycles: {dict(sorted_test[:5])}")
                
                # CRITICAL FIX: Pass status filter to grouping function so it can prefer the right transactions
                # When status='failed', grouping will prefer failed transactions so they're not lost
                # When status='all' or None, grouping will prefer success (best representative)
                # Final status filtering still happens after grouping (line 1005)
                transactions = _group_transactions_by_exchange(all_transactions, metric_type, status)
                print(f"[DEBUG] Grouping function returned {len(transactions)} transactions")
                logger.info(f"[GROUPING] After grouping: {len(transactions)} transactions (expected: {len(time_dist) * 4})")
                
                # CRITICAL: Apply status filter AFTER grouping (not during grouping)
                # This ensures all 4 exchanges are shown per cycle, then filter final results
                # CRITICAL FIX: Only apply filter if status is NOT 'all' or None
                if status and status.strip() and status.strip().lower() != 'all':
                    status_filter_value = status.strip().lower()
                    original_count = len(transactions)
                    filtered_transactions = []
                    for tx in transactions:
                        # CRITICAL: Use standardized response_code extraction
                        response_code = _extract_response_code(tx)
                        db_status = tx.get('status')  # Get database status field for timeout/connection errors
                        actual_status = _determine_status_from_response_code(response_code, db_status)
                        
                        # Apply filter - only include transactions that match the filter
                        if status_filter_value == 'success' and actual_status == 'success':
                            filtered_transactions.append(tx)
                        elif status_filter_value == 'failed' and actual_status == 'failed':
                            filtered_transactions.append(tx)
                        elif status_filter_value == 'error' and actual_status == 'error':
                            filtered_transactions.append(tx)
                    
                    transactions = filtered_transactions
                    logger.info(f"[FILTER] Applied status filter '{status}' AFTER grouping: {len(transactions)}/{original_count} transactions match")
                    print(f"[DEBUG] Applied status filter '{status}' AFTER grouping: {len(transactions)}/{original_count} transactions match", file=sys.stderr, flush=True)
                else:
                    # Status is 'all' or None - show all transactions (grouping already returned both success and failed)
                    logger.info(f"[FILTER] Status filter is 'all' or None - showing all transactions: {len(transactions)} transactions")
                    print(f"[DEBUG] Status filter is 'all' or None - showing all transactions: {len(transactions)}", file=sys.stderr, flush=True)
                
                # DIAGNOSTIC: Log status distribution in grouped results
                grouped_status_counts = {}
                for tx in transactions:
                    tx_status = tx.get('status')
                    grouped_status_counts[tx_status] = grouped_status_counts.get(tx_status, 0) + 1
                logger.info(f"[GROUPING] Status distribution in grouped results: {grouped_status_counts}")
                print(f"[DEBUG GROUPING] Status distribution after grouping: {grouped_status_counts}", file=sys.stderr, flush=True)
                
                # CRITICAL FIX: Apply internal limit AFTER grouping (Issue 3)
                # Sort by sent_at descending (most recent first)
                if transactions:
                    transactions.sort(key=lambda x: x.get('sent_at', '') or '', reverse=True)
                
                if len(transactions) < len(time_dist) * 2:
                    logger.warning(f"[GROUPING] WARNING: Only got {len(transactions)} transactions but expected at least {len(time_dist) * 2}")
                    logger.warning(f"[GROUPING] This suggests the grouping function is not processing all cycles correctly!")
                    print(f"[DEBUG] WARNING: Expected {len(time_dist) * 4} transactions but got {len(transactions)}")
            else:
                # Not grouping: filter by exchange_id if specified
                if requested_exchange_id is not None:
                    transactions = [
                        tx for tx in all_transactions 
                        if tx.get('exchange_id') == requested_exchange_id
                    ]
                else:
                    transactions = all_transactions
                
                # Sort by sent_at descending (most recent first)
                if transactions:
                    transactions.sort(key=lambda x: x.get('sent_at', '') or '', reverse=True)
            
            # PAGINATION LOGIC:
            total_count = len(transactions)
            offset = (page - 1) * size
            paginated_transactions = transactions[offset:offset + size]
            
            import math
            total_pages = math.ceil(total_count / size) if size > 0 else 0
            
            return {
                "items": paginated_transactions,
                "total_count": total_count,
                "page": page,
                "size": size,
                "total_pages": total_pages,
                "count": total_count # For backward compatibility
            }
            
    except HTTPException:
        raise
    except Exception as e:
        error_detail = str(e)
        logger.error(f"Error fetching exchange transactions: {error_detail}", exc_info=True)
        logger.error(f"Request params: start_date={start_date}, end_date={end_date}, start_time={start_time}, end_time={end_time}, environment={environment}, metric_type={metric_type}, status={status}")
        raise HTTPException(status_code=500, detail=f"Error fetching transactions: {error_detail}")



@router.get("/bulk-server-metrics")
def get_bulk_server_metrics(
    server_id: int,
    metric_names: List[str] = Query(..., description="List of metric names"),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    start_time: Optional[str] = Query(None),
    end_time: Optional[str] = Query(None),
    step: str = Query("1m", description="Aggregation step/interval, e.g., '10s', '1m', '5m', '1h'."),
    include_interfaces: bool = Query(False, description="Whether to include per-interface metrics")
):
    """
    Fetch and aggregate multiple metrics for a server in a single ClickHouse query.
    Highly optimized for the Server Details page using time-based aggregation.
    """
    start_request_time = datetime.now()
    logger.info(f"Bulk metrics request for server {server_id} with step {step} received (include_interfaces={include_interfaces}).")

    try:
        # Robust date parsing
        try:
            end_dt = datetime.now()
            start_dt = end_dt - timedelta(hours=24)
            if start_date:
                start_dt_str = f"{start_date} {start_time or '00:00:00'}"
                start_dt = datetime.strptime(start_dt_str, "%Y-%m-%d %H:%M:%S")
            if end_date:
                end_dt_str = f"{end_date} {end_time or '23:59:59'}"
                end_dt = datetime.strptime(end_dt_str, "%Y-%m-%d %H:%M:%S")
        except (ValueError, TypeError) as e:
            logger.warning(f"Invalid date/time format provided: {e}")
            raise HTTPException(status_code=400, detail=f"Invalid date/time format. Use YYYY-MM-DD and HH:MM:SS. Error: {e}")

        # Robust step parsing
        try:
            interval_value = int("".join(filter(str.isdigit, step)))
            interval_unit = "".join(filter(str.isalpha, step)).upper()
            if not interval_value or not interval_unit:
                raise ValueError("Step must contain a number and a unit (s, m, h).")

            if interval_unit == 'S': ch_interval_unit = 'SECOND'
            elif interval_unit == 'M': ch_interval_unit = 'MINUTE'
            elif interval_unit == 'H': ch_interval_unit = 'HOUR'
            else: raise ValueError(f"Invalid interval unit: {interval_unit}. Must be 's', 'm', or 'h'.")
        except (ValueError, TypeError) as e:
            logger.warning(f"Invalid step parameter: {step}. Error: {e}")
            raise HTTPException(status_code=400, detail=f"Invalid step parameter: '{step}'. Must be like '10s', '5m', '1h'.")

        # 1. Execute ClickHouse Query
        try:
            from app.routes.metrics import get_clickhouse_client
            client = get_clickhouse_client()
            if not client:
                raise Exception("ClickHouse client is not available.")
                
            time_diff = (end_dt - start_dt).total_seconds()
            
            # CRITICAL FIX: For short ranges (<= 1 hour), return RAW data without aggregation
            # This ensures no data points are hidden by bucket misalignment, fixing "blank graph" issues
            if time_diff <= 3600:
                table = "lama.server_metrics"
                ch_query = f"""
                    SELECT
                        metric_name,
                        value,
                        ts,
                        interface_name
                    FROM {table}
                    WHERE server_id = %(server_id)s
                    AND metric_name IN %(metric_names)s
                    AND ts BETWEEN %(start_dt)s AND %(end_dt)s
                    ORDER BY ts ASC
                """
                
                params = {
                    'server_id': server_id,
                    'metric_names': metric_names,
                    'start_dt': start_dt,
                    'end_dt': end_dt,
                }
                
                logger.info(f"Executing ClickHouse RAW query for short range ({time_diff}s)...")
                query_start_time = datetime.now()
                ch_result = client.query(ch_query, parameters=params)
                query_duration = (datetime.now() - query_start_time).total_seconds()
                logger.info(f"ClickHouse RAW query finished in {query_duration:.2f}s, returned {len(ch_result.result_rows)} rows.")

                metrics = []
                for row in ch_result.result_rows:
                    # Row: metric_name, value, ts, interface_name
                    ts = row[2]
                    if isinstance(ts, datetime):
                        ts_str = ts.isoformat()
                        if ts.tzinfo is None:
                            # ClickHouse stores naive datetimes that are actually IST (+05:30)
                            ts_str += "+05:30"
                    else:
                        ts_str = str(ts)
                    
                    metric_obj = {
                        "metric_name": row[0],
                        "value": float(row[1]),
                        "timestamp": ts_str
                    }
                    if include_interfaces:
                        metric_obj["interface_name"] = row[3]
                    
                    metrics.append(metric_obj)
                
                total_request_time = (datetime.now() - start_request_time).total_seconds()
                logger.info(f"Total request processed in {total_request_time:.2f}s.")
                return {"metrics": metrics, "source": "clickhouse_raw_high_res"}

            # Logic for > 1 hour (Aggregation)
            use_hourly = time_diff > (6 * 3600) # Use pre-aggregated hourly data for ranges > 6 hours
            
            # CRITICAL: server_metrics_hourly does NOT have interface_name. 
            # If include_interfaces=True, we MUST use raw table even for long ranges to get device breakdown.
            # This is acceptable for per-server queries as ClickHouse handles it efficiently.
            if include_interfaces:
                table = "lama.server_metrics"
                use_hourly = False 
            else:
                table = "lama.server_metrics_hourly" if use_hourly else "lama.server_metrics"
            
            # CRITICAL FIX: Use MAX for all metrics to ensure "Flash" peaks are never lost during aggregation.
            # This allows the UI charts to match the LAMA Fleet Max values exactly.
            if use_hourly:
                value_expression = "max(max_value)"
            else:
                value_expression = "max(value)"
            
            group_by_clause = "time_bucket, metric_name"
            select_interface = ""
            if include_interfaces:
                group_by_clause += ", interface_name"
                select_interface = ", interface_name"

            ch_query = f"""
                SELECT
                    metric_name,
                    {value_expression} as aggregated_value,
                    toStartOfInterval(ts, INTERVAL {interval_value} {ch_interval_unit}) as time_bucket
                    {select_interface}
                FROM {table}
                WHERE server_id = %(server_id)s
                AND metric_name IN %(metric_names)s
                AND ts BETWEEN %(start_dt)s AND %(end_dt)s
                GROUP BY {group_by_clause}
                ORDER BY time_bucket ASC
            """
            
            params = {
                'server_id': server_id,
                'metric_names': metric_names,
                'start_dt': start_dt,
                'end_dt': end_dt,
            }
            
            logger.info(f"Executing ClickHouse AGGREGATED query on table {table} with step {step} (include_interfaces={include_interfaces})...")
            query_start_time = datetime.now()
            ch_result = client.query(ch_query, parameters=params)
            query_duration = (datetime.now() - query_start_time).total_seconds()
            logger.info(f"ClickHouse query finished in {query_duration:.2f}s, returned {len(ch_result.result_rows)} rows.")

            metrics = []
            for row in ch_result.result_rows:
                # Row: metric_name, value, bucket_ts, [interface_name]
                ts = row[2]
                
                # Ensure we have a valid datetime object
                if isinstance(ts, datetime):
                    ts_str = ts.isoformat()
                    if ts.tzinfo is None:
                        ts_str += "+05:30"
                else:
                    ts_str = str(ts)
                
                metric_obj = {
                    "metric_name": row[0],
                    "value": float(row[1]),
                    "timestamp": ts_str
                }
                if include_interfaces:
                    metric_obj["interface_name"] = row[3]
                
                metrics.append(metric_obj)
            
            total_request_time = (datetime.now() - start_request_time).total_seconds()
            logger.info(f"Total request processed in {total_request_time:.2f}s.")
            return {"metrics": metrics, "source": f"clickhouse_aggregated_{'hourly' if use_hourly else 'raw'}"}

        except Exception as e:
            logger.error(f"Bulk ClickHouse aggregated fetch failed: {e}", exc_info=True)
            # Do not fallback to a slow method, return a proper error
            raise HTTPException(status_code=500, detail="Failed to query metrics from the database.")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in bulk metrics processing: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/server-metrics")
def get_server_metrics_history(
    start_date: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    start_time: Optional[str] = Query(None, description="Start time (HH:MM:SS)"),
    end_time: Optional[str] = Query(None, description="End time (HH:MM:SS)"),
    server_id: Optional[int] = Query(None, description="Filter by server ID"),
    metric_name: Optional[str] = Query(None, description="Filter by metric name"),
    limit: int = Query(10000, description="Maximum number of records"),
    db: Session = Depends(get_db)
):
    """
    Get historical server metrics with date and time range filtering.
    Uses ClickHouse for high-performance retrieval and downsampling.
    """
    try:
        # Parse dates to calculate range
        start_dt = None
        end_dt = datetime.now()
        
        if start_date:
            try:
                start_dt_str = f"{start_date} {start_time}" if start_time else f"{start_date} 00:00:00"
                start_dt = datetime.strptime(start_dt_str, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid start_date/time format")
        
        if end_date:
            try:
                end_dt_str = f"{end_date} {end_time}" if end_time else f"{end_date} 23:59:59"
                end_dt = datetime.strptime(end_dt_str, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid end_date/time format")

        # 1. Try ClickHouse first
        try:
            from app.routes.metrics import get_clickhouse_client
            client = get_clickhouse_client()
            if client:
                # Decide if we use raw or hourly summary
                time_diff = (end_dt - (start_dt or end_dt - timedelta(days=1))).total_seconds()
                use_hourly = time_diff > (6 * 3600) # Use hourly if range > 6 hours
                
                table = "lama.server_metrics_hourly" if use_hourly else "lama.server_metrics"
                
                # PRO-GRAFANA FIX: Use MAX aggregation.
                if use_hourly:
                    value_expression = "max(max_value)"
                else:
                    value_expression = "max(value)"
                
                ch_query = f"SELECT server_id, metric_name, {value_expression}, ts FROM {table} WHERE 1=1"
                if server_id:
                    ch_query += f" AND server_id = {int(server_id)}"
                if metric_name:
                    ch_query += f" AND metric_name = '{metric_name}'"
                if start_dt:
                    ch_query += f" AND ts >= '{start_dt.strftime('%Y-%m-%d %H:%M:%S')}'"
                if end_dt:
                    ch_query += f" AND ts <= '{end_dt.strftime('%Y-%m-%d %H:%M:%S')}'"
                
                ch_query += f" GROUP BY server_id, metric_name, ts ORDER BY ts DESC LIMIT {int(limit)}"
                
                ch_result = client.query(ch_query)
                metrics = []
                for row in ch_result.result_rows:
                    ts = row[3]
                    ts_str = ts.isoformat()
                    # ClickHouse stores naive datetimes that are actually IST (+05:30)
                    if ts.tzinfo is None and not ts_str.endswith(('Z', '+05:30')):
                         ts_str += '+05:30'
                    metrics.append({
                        "server_id": row[0],
                        "metric_name": row[1],
                        "value": float(row[2]),
                        "timestamp": ts_str
                    })
                
                if metrics:
                    return {"count": len(metrics), "metrics": metrics, "source": "clickhouse"}
        except Exception as e:
            logger.warning(f"ClickHouse query failed: {e}")

        # 2. Fallback to PostgreSQL
        query = select(
            server_metrics_table.c.id,
            server_metrics_table.c.server_id,
            server_status_table.c.name.label("server_name"),
            server_status_table.c.ip.label("server_ip"),
            server_metrics_table.c.metric_name,
            server_metrics_table.c.value,
            server_metrics_table.c.ts
        ).select_from(
            server_metrics_table.join(
                server_status_table,
                server_metrics_table.c.server_id == server_status_table.c.id
            )
        )
        
        if start_dt: query = query.where(server_metrics_table.c.ts >= start_dt)
        if end_dt: query = query.where(server_metrics_table.c.ts < end_dt)
        if server_id: query = query.where(server_metrics_table.c.server_id == server_id)
        if metric_name: query = query.where(server_metrics_table.c.metric_name == metric_name)
        
        query = query.order_by(server_metrics_table.c.ts.desc()).limit(limit)
        
        with engine.connect() as conn:
            results = conn.execute(query).fetchall()
            metrics = []
            for row in results:
                metrics.append({
                    "id": row[0],
                    "server_id": row[1],
                    "server_name": row[2] or "",
                    "server_ip": row[3] or "",
                    "metric_name": row[4],
                    "value": float(row[5]) if row[5] is not None else 0.0,
                    "timestamp": (row[6].isoformat()) if row[6] else None
                })
            return {"count": len(metrics), "metrics": metrics, "source": "postgresql"}
            
    except Exception as e:
        logger.error(f"Error fetching server metrics: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/multi-alert-trends")
async def get_multi_alert_trends(
    requests: List[Dict[str, Any]],
    window_minutes: int = Query(30, description="Minutes leading up to the alert")
):
    """
    Fetch historical trend data for multiple alerts in a single batch request.
    Takes a list of {alert_id, server_id, metric_name, timestamp}.
    Returns a mapping of alert_id -> list of data points.
    """
    if not requests:
        return {}

    try:
        from app.routes.metrics import get_clickhouse_client
        client = get_clickhouse_client()
        if not client:
            raise Exception("ClickHouse client not available")

        # Construct a massive UNION ALL query to get all trends in one database pass
        # This is the most professional/performant way to handle multi-window queries
        subqueries = []
        for i, req in enumerate(requests):
            alert_id = req.get('alert_id')
            server_id = int(req.get('server_id'))
            metric_raw = req.get('metric_name', '')
            
            # FIX: Strip prefixes to match server_metrics table (e.g. 'hardware.cpu' -> 'cpu')
            for prefix in ['hardware.', 'network.', 'database.', 'application.']:
                if metric_raw.startswith(prefix):
                    metric_raw = metric_raw.replace(prefix, '', 1)
                    break
            
            # Professional Interface/Partition Splitting
            # If metric_raw is 'disk.C:' -> name='disk', interface='C:'
            if '.' in metric_raw:
                metric_name, interface_name = metric_raw.split('.', 1)
                interface_clause = f"AND interface_name = '{interface_name}'"
            else:
                metric_name = metric_raw
                # FIX: Explicitly target aggregate (NULL interface) if no interface specified
                # This prevents fetching multiple partition rows for the same timestamp
                interface_clause = "AND interface_name IS NULL"

            # Parse alert timestamp (Frontend sends UTC 'Z')
            try:
                # 1. Parse as UTC aware
                dt_str = req.get('timestamp').replace('Z', '+00:00') 
                alert_utc = datetime.fromisoformat(dt_str)
                
                # 2. Convert to IST (UTC + 5:30)
                # DB stores metrics in local IST time, so we must query in IST
                ist_offset = timedelta(hours=5, minutes=30)
                alert_ist = alert_utc.astimezone(timezone(ist_offset))
                
                # 3. Make naive for SQL query comparison
                alert_ts = alert_ist.replace(tzinfo=None)
            except:
                continue

            start_ts = alert_ts - timedelta(minutes=window_minutes)
            
            subqueries.append(f"""
                SELECT 
                    {alert_id} as alert_id,
                    value,
                    ts
                FROM lama.server_metrics
                WHERE server_id = {server_id}
                AND metric_name = '{metric_name}'
                {interface_clause}
                AND ts BETWEEN '{start_ts.strftime('%Y-%m-%d %H:%M:%S')}' AND '{alert_ts.strftime('%Y-%m-%d %H:%M:%S')}'
            """)

        if not subqueries:
            return {}

        full_query = " UNION ALL ".join(subqueries) + " ORDER BY alert_id, ts ASC"
        
        ch_result = client.query(full_query)
        
        # Group results by alert_id
        trends = {}
        for row in ch_result.result_rows:
            a_id = str(row[0])
            if a_id not in trends:
                trends[a_id] = []
            
            trends[a_id].append({
                "value": float(row[1]),
                "timestamp": row[2].isoformat()
            })
            
        return trends

    except Exception as e:
        logger.error(f"Multi-alert trend fetch failed: {e}", exc_info=True)
        # Return empty object rather than failing the whole page
        return {}


@router.get("/exchange-transactions/{transaction_id}/servers")
def get_transaction_server_details(
    transaction_id: int,
    environment: str = Depends(get_active_environment), # NEW: Mandatory environment isolation
    db: Session = Depends(get_db)
):
    """
    Get all server details for a specific exchange transaction.
    Groups all servers that were sent to the same exchange at the same timestamp.
    Returns server-level data (IP, metrics) for the transaction.
    """
    try:
        with engine.connect() as conn:
            # First, get the selected transaction to get exchange_id, sent_at, metric_type, environment
            # RULE 1: Enforce environment isolation - transaction must belong to the active environment
            query_transaction = select(exchange_transactions_table).where(
                exchange_transactions_table.c.id == transaction_id,
                exchange_transactions_table.c.environment == environment
            )
            result_transaction = conn.execute(query_transaction).fetchone()
            
            if not result_transaction:
                raise HTTPException(status_code=404, detail=f"Transaction {transaction_id} not found in {environment} environment")
            
            # Extract transaction details
            # Row access: id, environment, server_id, server_name, server_ip, member_id, instance_id,
            # metric_type, metrics_sent, sequence_id, exchange_response, status, status_code,
            # error_message, sent_at, response_received_at
            tx_env = result_transaction[1]
            tx_sent_at = result_transaction[14]
            tx_metric_type = result_transaction[7]
            tx_metrics_sent = result_transaction[8] if result_transaction[8] else {}
            
            # Get exchange_id from column 16 (if available) or fallback to JSON
            tx_exchange_id = result_transaction[16] if len(result_transaction) > 16 and result_transaction[16] is not None else None
            if not tx_exchange_id and isinstance(tx_metrics_sent, dict):
                tx_exchange_id = tx_metrics_sent.get('lama_v1_2_payload', {}).get('exchangeId') or tx_metrics_sent.get('exchangeId')
            
            if not tx_exchange_id:
                raise HTTPException(status_code=400, detail="Transaction does not have exchange ID")
            
            # Find all transactions with the same exchange_id, environment, and push cycle
            minutes = tx_sent_at.minute
            rounded_minute = (minutes // 5) * 5
            cycle_time = tx_sent_at.replace(minute=rounded_minute, second=0, microsecond=0)
            
            # 5-minute cycle window with buffer
            time_window_start = cycle_time - timedelta(seconds=60)
            time_window_end = cycle_time + timedelta(minutes=5, seconds=60)
            
            # Broad query to include all metric types for this exchange cycle
            # RULE 2: ALWAYS filter by environment even in broad cycle query
            query_servers = select(exchange_transactions_table).where(
                exchange_transactions_table.c.environment == environment,
                exchange_transactions_table.c.sent_at >= time_window_start,
                exchange_transactions_table.c.sent_at <= time_window_end
            ).order_by(exchange_transactions_table.c.metric_type.asc(), exchange_transactions_table.c.server_ip.asc())
            
            results = conn.execute(query_servers).fetchall()
            
            # Aggregated results containers
            servers_by_key = {}  # {(type, key): {name, ip, metrics: []}}
            aggregated_summary = []
            seen_agg_keys = set()
            seen_server_metrics = set()

            # Define regular metric types that should be grouped together ONLY in aggregated view ('all')
            REGULAR_METRIC_TYPES = ['hardware', 'network', 'database', 'application']

            for row in results:
                # row[8] is metrics_sent JSON
                metrics_sent = row[8] if isinstance(row[8], dict) else {}
                lama_payload = metrics_sent.get('lama_v1_2_payload', {})
                row_metric_type = row[7]
                
                # Get exchange_id from column 16 (if available) or fallback to JSON
                exchange_id = row[16] if len(row) > 16 and row[16] is not None else None
                if not exchange_id:
                    exchange_id = lama_payload.get('exchangeId') or metrics_sent.get('exchangeId')
                
                # Compare as integers to be safe
                try:
                    if exchange_id is not None and tx_exchange_id is not None:
                        if int(exchange_id) != int(tx_exchange_id):
                            continue
                    elif exchange_id != tx_exchange_id:
                        continue
                except (ValueError, TypeError):
                    if exchange_id != tx_exchange_id:
                        continue
                
                # CRITICAL: Determine if this row should be included in the details
                # 1. If primary is 'all' (aggregated cycle), include all regular metrics
                # 2. Otherwise, include ONLY the exact same metric type as the clicked row
                should_include = False
                if tx_metric_type == 'all':
                    should_include = row_metric_type in REGULAR_METRIC_TYPES
                else:
                    should_include = (row_metric_type == tx_metric_type)
                
                if not should_include:
                    continue

                # 1. Collect aggregated metrics for the summary section
                payload_array = lama_payload.get('payload', [])
                for p_item in payload_array:
                    app_id = p_item.get('applicationId')
                    m_data = p_item.get('metricData', [])
                    for m in m_data:
                        m_key = m.get('key')
                        m_val = m.get('value')
                        
                        # Add to summary if not already there (unique by appId + key)
                        summary_key = f"{app_id}_{m_key}"
                        if summary_key not in seen_agg_keys:
                            seen_agg_keys.add(summary_key)
                            agg_obj = {"name": m_key, "app_id": app_id}
                            if isinstance(m_val, dict):
                                agg_obj.update({"type": "statistical", **m_val})
                            else:
                                agg_obj.update({"type": "numeric", "value": m_val})
                            aggregated_summary.append(agg_obj)

                # 2. Collect per-server/per-app details
                # Use dedicated column (index 19) if populated, otherwise fallback to JSON
                orig_metrics = row[19] if len(row) > 19 and row[19] is not None else metrics_sent.get('original_metrics', [])
                
                # Case A: Hardware/Network/DB/App (have original_metrics)
                if orig_metrics:
                    # NEW: Check if this is the new 'detailed_metrics' nested format
                    # original_metrics: [{"name": "cpu", "detailed_metrics": [...]}, ...]
                    all_individual_metrics = []
                    is_nested = any('detailed_metrics' in m for m in orig_metrics if isinstance(m, dict))
                    
                    if is_nested:
                        for m_group in orig_metrics:
                            if isinstance(m_group, dict) and 'detailed_metrics' in m_group:
                                all_individual_metrics.extend(m_group['detailed_metrics'])
                    else:
                        all_individual_metrics = orig_metrics

                    for m in all_individual_metrics:
                        # Extract server info
                        s_name = m.get('serviceName') or m.get('server_name')
                        s_id = m.get('applicationId') or m.get('server_id')
                        s_ip = m.get('server_ip') or row[4] or "combined"
                        
                        if row_metric_type == 'application' and s_name:
                            key = f"app_{s_id}_{s_name}"
                        else:
                            key = f"{row_metric_type}_{s_id}_{s_name}_{s_ip}"
                        
                        if key not in servers_by_key:
                            # Use s_ip if it looks like an IP address, otherwise use ID
                            display_ip = s_ip
                            if row_metric_type == 'application' and (not s_ip or s_ip == 'combined' or 'ecs:' in s_ip):
                                display_ip = f"ID: {s_id}"
                            
                            servers_by_key[key] = {
                                "server_name": s_name or f"Source {s_id or s_ip}", 
                                "ip": display_ip, 
                                "metrics": []
                            }

                        # If it's the standard metric format (hardware/network/db)
                        m_name = m.get('name', m.get('key', ''))
                        if m_name:
                            metric_id = f"{key}_{m_name}"
                            if metric_id in seen_server_metrics: continue
                            seen_server_metrics.add(metric_id)

                            if isinstance(m, dict) and ('min' in m or 'max' in m or any(isinstance(v, dict) for v in m.values())):
                                # Handle statistical object
                                servers_by_key[key]["metrics"].append({
                                    "name": m_name, "type": "statistical",
                                    "min": m.get('min'), "max": m.get('max'), 
                                    "avg": m.get('avg'), "med": m.get('med'),
                                    "worst_case_source": m.get('worst_case_source'),
                                    "applicationId": m.get('applicationId') or s_id,
                                    "serviceName": m.get('serviceName') or s_name,
                                    "server_ip": m.get('server_ip') or s_ip
                                })
                            else:
                                # Look for statistical data in common application metric keys
                                m_val = m.get('value', 0)
                                if isinstance(m_val, dict) and ('min' in m_val):
                                    servers_by_key[key]["metrics"].append({
                                        "name": m_name, "type": "statistical", **m_val,
                                        "applicationId": m.get('applicationId') or s_id,
                                        "serviceName": m.get('serviceName') or s_name,
                                        "server_ip": m.get('server_ip') or s_ip
                                    })
                                else:
                                    # Fallback to numeric value
                                    if m_name in m and isinstance(m[m_name], dict):
                                        servers_by_key[key]["metrics"].append({
                                            "name": m_name, "type": "statistical", **m[m_name],
                                            "applicationId": m.get('applicationId') or s_id,
                                            "serviceName": m.get('serviceName') or s_name,
                                            "server_ip": m.get('server_ip') or s_ip
                                        })
                                    else:
                                        servers_by_key[key]["metrics"].append({
                                            "name": m_name, "type": "numeric", "value": m.get(m_name, m.get('value', 0)),
                                            "applicationId": m.get('applicationId') or s_id,
                                            "serviceName": m.get('serviceName') or s_name,
                                            "server_ip": m.get('server_ip') or s_ip
                                        })
                        else:
                            # Application format where keys are metric names
                            for k, v in m.items():
                                if k in ['applicationId', 'serviceName', 'server_name', 'server_ip', 'server_id', 'timestamp']:
                                    continue
                                
                                metric_id = f"{key}_{k}"
                                if metric_id in seen_server_metrics: continue
                                seen_server_metrics.add(metric_id)

                                if isinstance(v, dict) and ('min' in v or 'max' in v):
                                    servers_by_key[key]["metrics"].append({
                                        "name": k, "type": "statistical", **v
                                    })
                                else:
                                    servers_by_key[key]["metrics"].append({
                                        "name": k, "type": "numeric", "value": v
                                    })
                
                # Case B: Application (ONLY IF Case A didn't find original_metrics)
                elif row_metric_type == 'application' and not servers_by_key:
                    for p_item in payload_array:
                        app_id = p_item.get('applicationId')
                        # Map to friendly names
                        app_name = {
                            1: "Sanjay-API", 
                            2: "Research-Tool", 
                            3: "Algo-API", 
                            4: "Munshi-API", 
                            5: "Dispatcher-API",
                            -1: "Background-Daemon"
                        }.get(app_id, f"App {app_id}")
                        
                        key = f"app_{app_id}_{app_name}"
                        
                        if key not in servers_by_key:
                            servers_by_key[key] = {"server_name": app_name, "ip": f"ID: {app_id}", "metrics": []}
                        
                        for m in p_item.get('metricData', []):
                            m_name = m.get('key')
                            m_val = m.get('value')
                            
                            metric_id = f"{key}_{m_name}"
                            if metric_id in seen_server_metrics: continue
                            seen_server_metrics.add(metric_id)

                            if isinstance(m_val, dict):
                                servers_by_key[key]["metrics"].append({
                                    "name": m_name, 
                                    "type": "statistical", 
                                    **m_val,
                                    "worst_case_source": m.get('worst_case_source')
                                })
                            else:
                                servers_by_key[key]["metrics"].append({"name": m_name, "type": "numeric", "value": m_val})


            # 3. Post-Process: Enrich summary with 'worst_case_source' from details if missing
            for agg in aggregated_summary:
                if agg.get("type") == "statistical" and not agg.get("worst_case_source"):
                    # Find which individual source had this max value
                    max_val = agg.get("max")
                    metric_name = agg.get("name")
                    for s_data in servers_by_key.values():
                        for m in s_data["metrics"]:
                            if m.get("name") == metric_name and m.get("max") == max_val:
                                # Fix: use s_data['server_name'] to match initialization
                                agg["worst_case_source"] = f"{s_data.get('server_name')} ({s_data.get('ip')})"
                                break
                        if agg.get("worst_case_source"): break

            # Format final response
            final_servers = []
            for s_data in servers_by_key.values():
                m_strings = []
                for m in s_data["metrics"]:
                    if m["type"] == "statistical":
                        m_strings.append(f"{m['name']}: {m['avg']} (avg)")
                    else:
                        m_strings.append(f"{m['name']}: {m['value']}")
                
                final_servers.append({
                    "server_name": s_data.get("server_name"),
                    "ip": s_data.get("ip"),
                    "details": ", ".join(m_strings),
                    "metrics": s_data["metrics"],
                    "time": tx_sent_at.isoformat()
                })

            return {
                "count": len(final_servers),
                "exchange_name": {1: "NSE", 2: "BSE", 4: "MCX", 5: "NCDEX"}.get(tx_exchange_id, "Unknown"),
                "metric_type": tx_metric_type,
                "timestamp": tx_sent_at.isoformat(),
                "servers": final_servers,
                "aggregated_metrics": aggregated_summary
            }
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching transaction server details: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error fetching server details: {str(e)}")


@router.get("/recent-exchange-data")
def get_recent_exchange_data(
    minutes: int = Query(5, description="Last N minutes of data"),
    environment: str = Depends(get_active_environment),
    db: Session = Depends(get_db)
):
    """
    Get recent data sent to exchange (last N minutes) - for real-time visibility
    """
    try:
        cutoff_time = datetime.now() - timedelta(minutes=minutes)
        
        # RULE 2: ALWAYS filter by environment
        query = select(exchange_transactions_table).where(
            and_(
                exchange_transactions_table.c.sent_at >= cutoff_time,
                exchange_transactions_table.c.environment == environment
            )
        ).order_by(exchange_transactions_table.c.sent_at.desc())
        
        with engine.connect() as conn:
            results = conn.execute(query).fetchall()
            
            transactions = []
            for row in results:
                # Row access: id, environment, server_id, server_name, server_ip, member_id, instance_id,
                # metric_type, metrics_sent, sequence_id, exchange_response, status, status_code,
                # error_message, sent_at, response_received_at
                transactions.append({
                    "id": row[0],
                    "environment": row[1],
                    "server_name": row[3] or "",
                    "server_ip": row[4] or "",
                    "metric_type": row[7],
                    "metrics_sent": row[8] if row[8] else {},
                    "sequence_id": row[9] or "",
                    "status": row[11],
                    "status_code": row[12],
                    "error_message": row[13] or "",
                    "sent_at": (row[14].isoformat()) if row[14] else None
                })
            
            return {
                "count": len(transactions),
                "time_range_minutes": minutes,
                "transactions": transactions
            }
            
    except Exception as e:
        logger.error(f"Error fetching recent exchange data: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error fetching recent data: {str(e)}")


@router.get("/export/excel")
def export_to_excel(
    start_date: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    start_time: Optional[str] = Query(None, description="Start time (HH:MM:SS)"),
    end_time: Optional[str] = Query(None, description="End time (HH:MM:SS)"),
    environment: str = Depends(get_active_environment),
    location_id: Optional[int] = Query(None, description="Filter by location ID (1=DC, 2=DR, 3=Cloud)"),
    data_type: str = Query("all", description="Data type: all, exchange, metrics, or both"),
    db: Session = Depends(get_db)
):
    """
    Export historical data to Excel format with date and time filtering
    Creates separate sheets for exchange transactions and server metrics
    Supports both date-only and date+time filtering
    """
    try:
        output = io.BytesIO()
        
        try:
            # CRITICAL: Ensure at least one sheet is always created
            sheet_created = False
            logger.info(f"[EXCEL_EXPORT] Starting Excel export with data_type={data_type}, start_date={start_date}, start_time={start_time}, end_date={end_date}, end_time={end_time}, environment={environment}")
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                # IMMEDIATELY create a default sheet to ensure at least one exists
                # This MUST succeed or the ExcelWriter will fail on exit
                default_df = pd.DataFrame([{"Status": "Processing..."}])
                default_df.to_excel(writer, sheet_name="Exchange Transactions", index=False)
                sheet_created = True
                logger.info(f"[EXCEL_EXPORT] Created default sheet")
                # Sheet 1: Exchange Transactions
                logger.info(f"[EXCEL_EXPORT] Checking if data_type '{data_type}' is in ['all', 'exchange', 'both']: {data_type in ['all', 'exchange', 'both']}")
                if data_type in ['all', 'exchange', 'both']:
                    logger.info(f"[EXCEL_EXPORT] Processing exchange transactions...")
                    exchange_data = []
                    
                    try:
                        # RULE 2: ALWAYS filter by environment
                        query = select(exchange_transactions_table).where(
                            exchange_transactions_table.c.environment == environment
                        )

                        if location_id is not None:
                            query = query.where(exchange_transactions_table.c.location_id == location_id)
                        
                        # Parse start datetime (date + optional time)
                        if start_date:
                            try:
                                if start_time:
                                    # CRITICAL: Frontend sends UTC, but database stores without timezone
                                    # Convert to naive datetime for comparison (database stores in UTC but without timezone info)
                                    start_dt = datetime.strptime(f"{start_date} {start_time}", "%Y-%m-%d %H:%M:%S")
                                    # Remove timezone for comparison with database (which stores naive UTC)
                                    if start_dt.tzinfo:
                                        start_dt = start_dt.replace(tzinfo=None)
                                else:
                                    start_dt = datetime.strptime(start_date, "%Y-%m-%d")
                                query = query.where(exchange_transactions_table.c.sent_at >= start_dt)
                            except ValueError as e:
                                raise HTTPException(status_code=400, detail=f"Invalid start_date/start_time format: {str(e)}")
                        
                        # Parse end datetime (date + optional time)
                        if end_date:
                            try:
                                if end_time:
                                    # CRITICAL: Frontend sends UTC, but database stores without timezone
                                    # Convert to naive datetime for comparison
                                    end_dt = datetime.strptime(f"{end_date} {end_time}", "%Y-%m-%d %H:%M:%S")
                                    # Remove timezone for comparison with database (which stores naive UTC)
                                    if end_dt.tzinfo:
                                        end_dt = end_dt.replace(tzinfo=None)
                                else:
                                    end_dt = datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1)
                                query = query.where(exchange_transactions_table.c.sent_at < end_dt)
                            except ValueError as e:
                                raise HTTPException(status_code=400, detail=f"Invalid end_date/end_time format: {str(e)}")
                        
                        query = query.order_by(exchange_transactions_table.c.sent_at.desc())
                        
                        with engine.connect() as conn:
                            results = conn.execute(query).fetchall()
                            logger.info(f"[EXCEL_EXPORT] Found {len(results)} transactions for export (start_date={start_date}, start_time={start_time}, end_date={end_date}, end_time={end_time}, environment={environment})")
                            
                            for row in results:
                                try:
                                    # Extract metrics from correct JSON structure
                                    metrics_sent = row[8] if row[8] else {}
                                    
                                    # Format dates in IST for Excel display
                                    sent_at_str = utc_to_ist_str(row[14])
                                    response_received_at_str = utc_to_ist_str(row[15])
                                    
                                    # PREFERRED: Extract from original_metrics (has individual server data)
                                    metrics_list = []
                                    if isinstance(metrics_sent, dict):
                                        original_metrics = metrics_sent.get('original_metrics', [])
                                        if original_metrics and isinstance(original_metrics, list) and len(original_metrics) > 0:
                                            # Use original_metrics - each item has server_name, server_ip, and metric data
                                            metrics_list = original_metrics
                                    
                                    # FALLBACK: If original_metrics not available, extract from lama_v1_2_payload structure
                                    if not metrics_list:
                                        if isinstance(metrics_sent, dict):
                                            lama_payload = metrics_sent.get('lama_v1_2_payload', {})
                                            if isinstance(lama_payload, dict):
                                                payload_array = lama_payload.get('payload', [])
                                                
                                                # CRITICAL FIX: Navigate to metricData array (payload[0].metricData[])
                                                if payload_array and isinstance(payload_array, list) and len(payload_array) > 0:
                                                    first_payload = payload_array[0]
                                                    if isinstance(first_payload, dict):
                                                        metric_data = first_payload.get('metricData', [])
                                                        
                                                        if metric_data and isinstance(metric_data, list):
                                                            # Transform metricData to match original_metrics structure
                                                            for md in metric_data:
                                                                if isinstance(md, dict):
                                                                    metric_name = md.get('key', '')
                                                                    value_obj = md.get('value', {})
                                                                    
                                                                    # Handle different value structures
                                                                    if isinstance(value_obj, dict):
                                                                        # Object format with min/max/avg/med
                                                                        metrics_list.append({
                                                                            "name": metric_name,
                                                                            "min": value_obj.get("min", ""),
                                                                            "max": value_obj.get("max", ""),
                                                                            "avg": value_obj.get("avg", ""),
                                                                            "med": value_obj.get("med", ""),
                                                                            "server_name": row[3] or "",  # Use transaction-level as fallback
                                                                            "server_ip": row[4] or ""
                                                                        })
                                                                    else:
                                                                        # Plain value (e.g., packetCount, status, failureTradeApi)
                                                                        metrics_list.append({
                                                                            "name": metric_name,
                                                                            "min": value_obj,
                                                                            "max": value_obj,
                                                                            "avg": value_obj,
                                                                            "med": value_obj,
                                                                            "server_name": row[3] or "",
                                                                            "server_ip": row[4] or ""
                                                                        })
                                    
                                    # Create a row for each metric (each metric = one server)
                                    if metrics_list and isinstance(metrics_list, list):
                                        for metric in metrics_list:
                                            if isinstance(metric, dict):
                                                # Use individual server info from metric if available, otherwise fallback to transaction-level
                                                server_name = metric.get('server_name', row[3] or "")
                                                server_ip = metric.get('server_ip', row[4] or "")
                                                
                                                # Extract min/max/avg/med values
                                                min_val = metric.get("min", "")
                                                max_val = metric.get("max", "")
                                                avg_val = metric.get("avg", "")
                                                med_val = metric.get("med", "")
                                                
                                                exchange_data.append({
                                                    "Transaction ID": row[0],
                                                    "Environment": row[1],
                                                    "Server Name": server_name,  # Individual server name
                                                    "Server IP": server_ip,       # Individual server IP
                                                    "Member ID": row[5] or "",
                                                    "Instance ID": row[6] or "",
                                                    "Metric Type": row[7],
                                                    "Metric Name": metric.get("name", ""),
                                                    "Min": min_val,
                                                    "Max": max_val,
                                                    "Avg": avg_val,
                                                    "Med": med_val,
                                                    "Sequence ID": row[9] or "",
                                                    "Status": row[11],
                                                    "Status Code": row[12] or "",
                                                    "Error Message": row[13] or "",
                                                    "Sent At": sent_at_str,
                                                    "Response Received At": response_received_at_str
                                                })
                                    else:
                                        # No metrics found, still create a row with transaction info
                                        exchange_data.append({
                                            "Transaction ID": row[0],
                                            "Environment": row[1],
                                            "Server Name": row[3] or "",
                                            "Server IP": row[4] or "",
                                            "Member ID": row[5] or "",
                                            "Instance ID": row[6] or "",
                                            "Metric Type": row[7],
                                            "Metric Name": "",
                                            "Min": "",
                                            "Max": "",
                                            "Avg": "",
                                            "Med": "",
                                            "Sequence ID": row[9] or "",
                                            "Status": row[11],
                                            "Status Code": row[12] or "",
                                            "Error Message": row[13] or "",
                                            "Sent At": sent_at_str,
                                            "Response Received At": response_received_at_str
                                        })
                                except Exception as row_error:
                                    # Log error but continue processing other rows
                                    logger.warning(f"[EXCEL_EXPORT] Error processing transaction row {row[0] if len(row) > 0 else 'unknown'}: {str(row_error)}", exc_info=True)
                                    # Still create a basic row with transaction info
                                    try:
                                        sent_at_str = utc_to_ist_str(row[14])
                                        response_received_at_str = utc_to_ist_str(row[15])
                                        exchange_data.append({
                                            "Transaction ID": row[0],
                                            "Environment": row[1],
                                            "Server Name": row[3] or "",
                                            "Server IP": row[4] or "",
                                            "Member ID": row[5] or "",
                                            "Instance ID": row[6] or "",
                                            "Metric Type": row[7],
                                            "Metric Name": f"ERROR: {str(row_error)[:50]}",
                                            "Min": "",
                                            "Max": "",
                                            "Avg": "",
                                            "Med": "",
                                            "Sequence ID": row[9] or "",
                                            "Status": row[11],
                                            "Status Code": row[12] or "",
                                            "Error Message": row[13] or f"Export error: {str(row_error)[:100]}",
                                            "Sent At": sent_at_str,
                                            "Response Received At": response_received_at_str
                                        })
                                    except:
                                        pass  # Skip this row if we can't even create a basic row
                    
                    except Exception as query_error:
                        logger.error(f"[EXCEL_EXPORT] Error executing query: {query_error}", exc_info=True)
                        # Still create a sheet with error message
                        exchange_data = []
                    
                    logger.info(f"[EXCEL_EXPORT] Processed {len(exchange_data)} rows for Excel export")
                    # Always create a sheet - either with data or with a message
                    try:
                        if exchange_data:
                            df_exchange = pd.DataFrame(exchange_data)
                            df_exchange.to_excel(writer, sheet_name="Exchange Transactions", index=False)
                            logger.info(f"[EXCEL_EXPORT] Created Exchange Transactions sheet with {len(exchange_data)} rows")
                            sheet_created = True
                        else:
                            # No data found - create a sheet with a message to avoid "At least one sheet must be visible" error
                            logger.info(f"[EXCEL_EXPORT] No exchange data found, creating empty sheet with message")
                            empty_df = pd.DataFrame([{"Message": f"No exchange transactions found for the specified time range (start_date={start_date}, start_time={start_time}, end_date={end_date}, end_time={end_time}, environment={environment})"}])
                            empty_df.to_excel(writer, sheet_name="Exchange Transactions", index=False)
                            logger.info(f"[EXCEL_EXPORT] Empty Exchange Transactions sheet created successfully")
                            sheet_created = True
                    except Exception as sheet_error:
                        logger.error(f"[EXCEL_EXPORT] Error creating Exchange Transactions sheet: {sheet_error}", exc_info=True)
                        # Last resort: create a minimal sheet
                        try:
                            minimal_df = pd.DataFrame([{"Error": f"Failed to create sheet: {str(sheet_error)[:200]}"}])
                            minimal_df.to_excel(writer, sheet_name="Exchange Transactions", index=False)
                            sheet_created = True
                        except Exception as minimal_error:
                            logger.error(f"[EXCEL_EXPORT] Even minimal sheet creation failed: {minimal_error}", exc_info=True)
                            raise  # Re-raise if even minimal sheet creation fails
                
                # Ensure at least one sheet exists before context exits
                if not sheet_created and data_type in ['all', 'exchange', 'both']:
                    logger.warning(f"[EXCEL_EXPORT] No sheet created for exchange data, creating emergency sheet")
                    try:
                        emergency_df = pd.DataFrame([{"Error": "No data found and sheet creation failed"}])
                        emergency_df.to_excel(writer, sheet_name="Exchange Transactions", index=False)
                        sheet_created = True
                    except Exception as emergency_error:
                        logger.error(f"[EXCEL_EXPORT] Emergency sheet creation also failed: {emergency_error}", exc_info=True)
                        raise
                
                # Sheet 2: Server Metrics
                if data_type in ['all', 'metrics', 'both']:
                    metrics_data = []
                    
                    query = select(
                        server_metrics_table.c.id,
                        server_metrics_table.c.server_id,
                        server_status_table.c.name.label("server_name"),
                        server_status_table.c.ip.label("server_ip"),
                        server_metrics_table.c.metric_name,
                        server_metrics_table.c.value,
                        server_metrics_table.c.ts
                    ).select_from(
                        server_metrics_table.join(
                            server_status_table,
                            server_metrics_table.c.server_id == server_status_table.c.id
                        )
                    )
                    
                    # RULE 2: ALWAYS filter by environment
                    query = query.where(server_status_table.c.environment == environment)
                    
                    if location_id is not None:
                        query = query.where(server_status_table.c.location_id == location_id)

                    # Parse start datetime (date + optional time) for server metrics
                    if start_date:
                        try:
                            if start_time:
                                # CRITICAL: Frontend sends UTC, but database stores without timezone
                                # Convert to naive datetime for comparison
                                start_dt = datetime.strptime(f"{start_date} {start_time}", "%Y-%m-%d %H:%M:%S")
                                # Remove timezone for comparison with database (which stores naive UTC)
                                if start_dt.tzinfo:
                                    start_dt = start_dt.replace(tzinfo=None)
                            else:
                                start_dt = datetime.strptime(start_date, "%Y-%m-%d")
                            query = query.where(server_metrics_table.c.ts >= start_dt)
                        except ValueError as e:
                            raise HTTPException(status_code=400, detail=f"Invalid start_date/start_time format: {str(e)}")
                    
                    # Parse end datetime (date + optional time) for server metrics
                    if end_date:
                        try:
                            if end_time:
                                # CRITICAL: Frontend sends UTC, but database stores without timezone
                                # Convert to naive datetime for comparison
                                end_dt = datetime.strptime(f"{end_date} {end_time}", "%Y-%m-%d %H:%M:%S")
                                # Remove timezone for comparison with database (which stores naive UTC)
                                if end_dt.tzinfo:
                                    end_dt = end_dt.replace(tzinfo=None)
                            else:
                                end_dt = datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1)
                            query = query.where(server_metrics_table.c.ts < end_dt)
                        except ValueError as e:
                            raise HTTPException(status_code=400, detail=f"Invalid end_date/end_time format: {str(e)}")
                    
                    query = query.order_by(server_metrics_table.c.ts.desc()).limit(100000)  # Limit for Excel
                    
                    with engine.connect() as conn:
                        results = conn.execute(query).fetchall()
                        
                        for row in results:
                            # Format timestamp properly (YYYY-MM-DD HH:MM:SS)
                            timestamp_str = ""
                            if row[6]:
                                try:
                                    timestamp_str = row[6].strftime("%Y-%m-%d %H:%M:%S")
                                except:
                                    timestamp_str = str(row[6])
                            
                            metrics_data.append({
                                "ID": row[0],
                                "Server ID": row[1],
                                "Server Name": row[2] or "",
                                "Server IP": row[3] or "",
                                "Metric Name": row[4],
                                "Value": float(row[5]) if row[5] is not None else 0.0,
                                "Timestamp": timestamp_str
                            })
                    
                    if metrics_data:
                        df_metrics = pd.DataFrame(metrics_data)
                        df_metrics.to_excel(writer, sheet_name="Server Metrics", index=False)
                        sheet_created = True
                    elif data_type in ['all', 'metrics', 'both']:
                        # No metrics data but metrics sheet was requested - create empty sheet with message
                        empty_df = pd.DataFrame([{"Message": f"No server metrics found for the specified time range (start_date={start_date}, start_time={start_time}, end_date={end_date}, end_time={end_time}, environment={environment})"}])
                        empty_df.to_excel(writer, sheet_name="Server Metrics", index=False)
                        sheet_created = True
                
                # Final check: ensure at least one sheet exists
                if not sheet_created:
                    logger.warning(f"[EXCEL_EXPORT] No sheets created at all, creating emergency default sheet")
                    emergency_df = pd.DataFrame([{"Error": "No data found for the specified filters"}])
                    emergency_df.to_excel(writer, sheet_name="No Data", index=False)
        except Exception as excel_error:
            logger.error(f"Error creating Excel file: {excel_error}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"Error creating Excel file: {str(excel_error)}")
        
        # Check if any data was written
        output.seek(0)
        excel_data = output.read()
        
        if not excel_data or len(excel_data) == 0:
            # If no data, create a minimal Excel file with a message
            try:
                output_empty = io.BytesIO()
                with pd.ExcelWriter(output_empty, engine='openpyxl') as writer_empty:
                    empty_df = pd.DataFrame([{"Message": "No data found for the specified filters."}])
                    empty_df.to_excel(writer_empty, sheet_name="No Data", index=False)
                output_empty.seek(0)
                excel_data = output_empty.read()
            except Exception as empty_excel_error:
                logger.error(f"Error creating empty Excel file: {empty_excel_error}", exc_info=True)
                raise HTTPException(status_code=500, detail=f"Error creating Excel file: {str(empty_excel_error)}")
        
        if not excel_data:
            raise HTTPException(status_code=500, detail="Failed to generate Excel file")
        
        # Generate filename with date and time if provided
        filename = f"lama_historical_data"
        if start_date:
            filename += f"_{start_date}"
            if start_time:
                filename += f"_{start_time.replace(':', '-')}"
        if end_date:
            filename += f"_to_{end_date}"
            if end_time:
                filename += f"_{end_time.replace(':', '-')}"
        filename += ".xlsx"
        
        return StreamingResponse(
            io.BytesIO(excel_data),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error exporting to Excel: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error exporting data: {str(e)}")

