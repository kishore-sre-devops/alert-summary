# LAMA V1.3 Location ID Strategy & Research

## Overview
The LAMA API Specification V1.3 introduces an optional `locationId` field (Numeric 6) for all metrics endpoints. While currently optional, this document outlines the research and implementation strategy for when it becomes mandatory.

## Configuration Mapping
As confirmed with the project stakeholders, the following mapping will be used:
*   **Location ID `1`**: **DC** (Data Center - Primary)
*   **Location ID `2`**: **DR** (Disaster Recovery)
*   **Location ID `3`**: **Cloud** (AWS/Azure/GCP)

## Current Architecture vs. V1.3 Requirement
### 1. The Aggregation Challenge
*   **Current (Fleet-Wide):** The system calculates a single "Worst Case" (Max) value across all servers in an environment and sends one payload per Exchange.
*   **Required (Location-Bifurcation):** To use `locationId`, we must move to **Location-Wise Aggregation**.
*   **Strategy:** Group servers by `location_id`, calculate the Max value for each bucket, and send up to 3 separate API calls per Exchange (one for DC, one for DR, one for Cloud).

### 2. Sequence ID Conflict (Error 704 Prevention)
*   **Challenge:** The `sequence_id_reservations` table currently tracks uniqueness at the `(environment, member_id, exchange_id, metric_type)` level.
*   **Solution:** When bifurcating by location, the database constraint and the reservation logic must be updated to include `location_id`.
    *   `NSE-DC` metrics must have a separate sequence stream from `NSE-DR` metrics.

## Implementation Roadmap (Deferred)
*   **Database:** Add `location_id` column to `server_status`, `database_config`, and `metric_queries`.
*   **Backend:** Update Pydantic models in `servers.py` and `database_config.py`.
*   **Schedulers:** Update `Hardware-Scheduler`, `Network-Scheduler`, `Database-Scheduler`, and `Application-Scheduler` to implement the "Group-by-Location" logic.
*   **UI:** Add Location dropdowns (DC/DR/Cloud) in Server, Database, and Application configuration dialogs.

## Current Status
**DEFERRED.** As of March 2026, the `locationId` field is optional. To maintain system stability and avoid complex re-engineering of the sequence ID logic, the implementation is on hold until the Exchange mandates the field.
