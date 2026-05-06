# Plan: Standardize AWS Resource Identifiers for Dashboard and Activity Logs

The goal is to provide AWS Console-friendly identifiers (Instance ID, ECS Cluster/Service, RDS Identifier) across the LAMA app, ensuring consistency in both the dashboards and the LAMA activity logs (Resource Breakdown) without breaking functional backend processes (like Prometheus/Mimir collection).

## Proposed Changes

### 1. Backend: Update Server API Response
- **File:** `api/backend/app/routes/servers.py`
- **Changes:**
    - Update `ServerResponse` Pydantic model to include a `resource_id: Optional[str]` field.
    - In `list_servers` and `get_server` endpoints, populate `resource_id`:
        - For DC/DR (location_id != 3): `resource_id = ip`
        - For AWS EC2 (location_id == 3): `resource_id = external_id` (Instance ID)
        - For Databases: `resource_id = external_id` (DB Identifier) or a parsed version of the endpoint.

### 2. Schedulers: Update Hardware Activity Logging
- **File:** `api/backend/app/schedulers/hardware.py`
- **Changes:**
    - In `process_env_optimized`, update how `all_raw_metrics` are populated.
    - If `s_loc == 3` (AWS), set `server_ip` in the metric dictionary to `s_ext_id` (the Instance ID).
    - For ECS services, instead of hardcoding `server_ip: "aws"`, use a combination of `cluster_name` and `service_name`.

### 3. Schedulers: Update Database Activity Logging
- **File:** `api/backend/app/schedulers/database.py`
- **Changes:**
    - In `fetch_db_metrics_async`, update the `res` list.
    - Set `server_ip` to the `db_identifier` (RDS Instance ID) instead of the long endpoint URL.

### 4. Schedulers: Update Application Activity Logging
- **File:** `api/backend/app/schedulers/application.py`
- **Changes:**
    - Ensure that when individual application/service metrics are collected for ECS, the `server_ip` field in the breakdown is set to the Service Name or Cluster/Service identifier.

### 5. Schedulers: Update Network Activity Logging
- **File:** `api/backend/app/schedulers/network.py`
- **Changes:**
    - Align the detailed metrics for AWS resources to use Instance IDs or LB identifiers.

### 6. Core: Ensure Consistency in Activity Log Database
- **File:** `api/backend/app/utils/lama_exchange_api.py`
- **Changes:**
    - Ensure `send_metrics_to_lama_exchange` correctly uses the passed identifiers when storing the `original_metrics` (Resource Breakdown) into the `exchange_transactions` table.

## Verification Plan

### Automated Tests
- Run existing hardware and network scheduler tests to ensure no regressions in data aggregation.
- Add a unit test for the identification logic to ensure it correctly extracts IDs from AWS resources.

### Manual Verification
- **Activity Log:** Check the "Exchange Activity" page in the UI to verify that AWS resources show Instance IDs (i-xxx) or Cluster/Service names instead of DNS names or "aws".
- **Dashboard:** Verify the "Server Status" dashboard shows the new `resource_id` field (once the UI is updated to use it) or that the identification is clear.
- **LAMA API:** Confirm that the actual data payloads (the aggregated fleet values) sent to LAMA remain unchanged and accurate.
