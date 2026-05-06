# Plan: Smart LAMA Query Explorer (No-Code PromQL Builder)

## Objective
Create a dedicated "Query Explorer" page that allows users to query Mimir/Prometheus without needing to know PromQL. It will automatically generate the correct queries based on the selected target and its resource type (Server, EC2, ECS, RDS).

## Backend Enhancements (`api/backend/app/routes/metric_sources.py`)
1.  **GET `/v1/query-explorer/targets`**:
    - Returns a list of all discovered targets from the environment's sources.
    - Each target will include metadata: `name`, `id`, `type` (server, ecs, rds, ec2), and `source_id`.
2.  **POST `/v1/query-explorer/run`**:
    - Proxies the final PromQL query to the correct Mimir/Prometheus source.
    - Handles authentication/SigV4 automatically.

## Frontend Development (`ui/src/pages/QueryExplorer.jsx`)
1.  **Smart Query Builder Component**:
    - **Step 1: Target Selector**: A searchable dropdown (Autocomplete) to find any server or cloud resource.
    - **Step 2: Smart Metric Selector**: Based on the target's type, show a human-readable list of metrics (e.g., "CPU Utilization" instead of `node_cpu_seconds_total`).
2.  **Real-Time PromQL Preview**:
    - A read-only code block that updates as the user selects options, showing the "Auto-Generated PromQL".
3.  **Visualization Window**:
    - A `Recharts` line chart for time-series data.
    - A "Data Table" view for raw points.
4.  **Sidebar Integration**:
    - Add "Query Explorer" to the **MONITORING** section in `ui/src/components/Sidebar.jsx`.

## Resource Type Templates
- **RDS**: Uses `dimension_DBInstanceIdentifier` for filtering.
- **ECS**: Uses `ecs_service_name` or `service` labels.
- **Linux/EC2**: Uses `node_exporter` metrics and `instance` labels.
- **Windows**: Uses `windows_exporter` metrics.

## Implementation Steps
1.  **Backend**: Add the target discovery and proxy query endpoints.
2.  **Frontend Layout**: Create the QueryExplorer page with a split-screen view (Controls on left, Graph on right).
3.  **Template Logic**: Implement the mapping between human-readable metrics and complex PromQL formulas.
4.  **Wiring**: Connect the UI to the backend proxy.

## Verification
1.  Select an RDS target -> Verify the generated query uses `aws_rds_*`.
2.  Select a Linux Server -> Verify the generated query uses `node_*` with the correct `instance` label.
3.  Compare the resulting graph with Grafana to ensure 100% accuracy.
