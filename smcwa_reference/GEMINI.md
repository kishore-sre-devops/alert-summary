# SMC LAMA: AI Mandates & Core Logic Protections

This file defines foundational rules and "Do Not Touch" logic blocks for the SMC LAMA project. Any AI agent working on this codebase MUST strictly adhere to these mandates.

## 1. CRITICAL: Elasticsearch Mandate (LAMA V1.3 Compliance)

The collection logic for `elasticsearch` source types is foundational and must not be refactored, modified, or removed during general system updates.

### Core Rules:
- **Pick & Pass:** For Elasticsearch sources, LAMA acts as a courier. Data must be picked up from the index documents and sent to the Exchange **without any calculations** or averaging.
- **IST 5 AM Rule:** Today's index (`lama-smcYYYY.MM.DD`) is only available after 5 AM IST. Before this hour, the system MUST return all zeros to avoid regulatory violations.
- **Odiin-Trading-Logs:** These metrics are specifically extracted from ES topics. Any change that breaks this link is a critical failure.
- **Isolation:** Elasticsearch metrics MUST NOT be mixed with Prometheus/Mimir or AWS CloudWatch collection logic. They require their own dedicated branch in the scheduler.

### Protected Files:
- `api/backend/app/schedulers/application.py` (Elasticsearch branch)
- `api/backend/app/collectors/es_collector.py` (Core collection methods)
- `api/backend/app/utils/aes_encryption.py` (Password decryption for ES)

## 2. Sequence ID Integrity (704 Fix)
- Sequence IDs are independent per exchange and per environment.
- The `SequenceManager` must remain the single source of truth for increments to prevent `704` sequence errors from the LAMA Exchange.

## 3. Database IP Integrity (Resource Breakdown Fix)
- The `server_ip` field in the Database Scheduler must always store the **FULL IP address or hostname**.
- Never truncate the IP (e.g., `192.168.1.1` should NOT become `192`).
- This field is used directly for the **Resource Breakdown** display in the UI. Truncating it makes the audit logs unreadable.
- Logic in `api/backend/app/schedulers/database.py` must preserve `display_ip = dhost`.

## 4. Network Data Retention (Sparse Point Rule)
- Network metrics (Bandwidth, PacketCount) often have sparse data in 5-minute windows.
- The **Zero-Fallback Protocol** for Network must be relaxed to **1 point** (instead of the standard 5-point audit rule).
- If even a single point is available, it must be sent to the Exchange rather than being forced to 0.0.
- This ensures that peaks and intermittent packet errors are captured in the aggregated results.

## 5. Application Metric Integrity (Case Sensitivity & Historical Keys)
- Application metrics from Elasticsearch must be matched **case-insensitively** (e.g., `Throughput`, `throughput`, and `THROUGHPUT` all map to the LAMA `throughput` key).
- `historicalThroughput` and `historicalLatency` must always be included in the `raw` payload and aggregation, even as zeros, to ensure they are visible in the LAMA reports for all servers.
- The `aggregate_application_fleet` function must include these historical keys in its statistical aggregation logic.

## 6. Daily Historical Application Audit (7 AM IST)
- A specialized scheduler MUST run once daily at **7:00 AM IST** to calculate 21-day historical metrics.
- **Elasticsearch:** Must query all indices from the last 21 days (`lama-smc*`) and calculate true `min`, `max`, `avg`, and `med`. This is NOT a "Pick & Pass" operation.
- **Mimir/AWS:** Must perform 21-day PromQL aggregations (`avg_over_time`, etc.).
- This report ensures LAMA V1.3 audit compliance for long-term historical performance.
- The 5-minute real-time scheduler will continue to send "Safe Zeros" for these keys to maintain report structure.

---
*Last Updated: 23/03/2026*
