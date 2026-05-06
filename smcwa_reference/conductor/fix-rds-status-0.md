# Plan: Fix RDS Status 0 by Switching to Real-Time Mimir Collection

## Objective
Remove the hardcoded 10-minute lag in the Mimir collector to ensure LAMA matches Grafana's real-time visibility for RDS metrics.

## Root Cause
The `MimirCollector` in `api/backend/app/collectors/mimir_collector.py` has a hardcoded 600-second (10-minute) `lag_seconds` for Cloud sources. This causes LAMA to query a stale window (10-15 minutes ago), while the fresh data (confirmed as "UP" by the user) exists in the 0-5 minute window.

## Proposed Solution
Modify the collector to remove the 10-minute delay and fetch data ending at the current time (`now`).

## Implementation Steps
1.  **Modify `api/backend/app/collectors/mimir_collector.py`**:
    - Locate the `fetch_metric_stats` method.
    - Remove the `lag_seconds = 600` logic for cloud sources.
    - Set `end_time = now` (current UTC).
    - Set `start_time = end_time - timedelta(minutes=window_minutes + 1)`.

## Verification Plan
1.  **Test Script**: Create and run `api/backend/test_realtime_rds.py` to confirm it now fetches the same non-zero values seen in Grafana.
2.  **Dashboard Check**: Confirm RDS status in the LAMA UI changes from 0 to 1 (online).
