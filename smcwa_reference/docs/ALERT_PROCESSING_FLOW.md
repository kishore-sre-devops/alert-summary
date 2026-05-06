# Alert Processing Flow

## Overview

The LAMA Scheduler continuously monitors metrics against configurable thresholds. When violations occur, alerts are stored in ClickHouse, email notifications are sent via SMTP, and push notifications are delivered to the mobile app via Firebase.

---

## Flow Diagram

```
┌────────────────────────────────────────────────────────┐
│                  LAMA SCHEDULER                         │
│               (Every 1 minute)                          │
└──────────────────────────┬─────────────────────────────┘
                           │
                           │  1. Fetch latest metrics from ClickHouse
                           ▼
┌────────────────────────────────────────────────────────┐
│                THRESHOLD CHECK                          │
│                                                         │
│  For each server:                                      │
│  ┌─────────────────────────────────────────────────┐  │
│  │  CPU Usage > 90%?        → CRITICAL Alert       │  │
│  │  Memory Usage > 85%?     → WARNING Alert        │  │
│  │  Disk Usage > 90%?       → CRITICAL Alert       │  │
│  │  Network Latency > 100ms?→ WARNING Alert        │  │
│  │  Replication Lag > 60s?  → CRITICAL Alert       │  │
│  └─────────────────────────────────────────────────┘  │
└──────────────────────────┬─────────────────────────────┘
                           │
                           │  2. If threshold violated
                           ▼
┌────────────────────────────────────────────────────────┐
│                  ALERT ACTIONS                          │
│                                                         │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐ │
│  │ Store in     │  │ Send Email   │  │Push to Mobile│ │
│  │ ClickHouse   │  │ (SMTP)       │  │ (Firebase)   │ │
│  │ alert_history│  │              │  │              │ │
│  └──────────────┘  └──────────────┘  └──────────────┘ │
└────────────────────────────────────────────────────────┘
```

---

## Default Thresholds

| Metric | Warning | Critical | Unit |
|---|---|---|---|
| CPU Usage | 80% | 90% | Percentage |
| Memory Usage | 75% | 85% | Percentage |
| Disk Usage | 80% | 90% | Percentage |
| Network Latency | 50ms | 100ms | Milliseconds |
| Replication Lag | 30s | 60s | Seconds |
| Server Down | — | 5 min no heartbeat | Minutes |

Thresholds are configurable per server via the **Thresholds** page (`/thresholds`).

---

## Alert Notification Channels

| Channel | Technology | When |
|---|---|---|
| **ClickHouse** | `alert_history` table | Every alert (for history and dashboard display) |
| **Email** | SMTP via `email_service.py` | Critical alerts, configurable recipients |
| **Mobile Push** | Firebase Cloud Messaging via `push.py` | Critical + Warning alerts to registered devices |
| **Escalation** | `escalation.py` (every 1 min) | Unacknowledged critical alerts escalate after configurable delay |

---

## Alert Lifecycle

| Stage | Action |
|---|---|
| **Detection** | Scheduler compares latest metric value against threshold |
| **Deduplication** | Same alert for same server within cooldown period is suppressed |
| **Storage** | Alert record inserted into ClickHouse `alert_history` |
| **Notification** | Email + Mobile push sent in parallel |
| **Display** | Alert appears on Dashboard, Alert History page, and Mobile app |
| **Escalation** | If not acknowledged within configured time, escalation triggers |
| **Resolution** | When metric returns to normal, auto-resolved and logged |

---

## Related UI Pages

| Page | Path | Purpose |
|---|---|---|
| Alert History | `/alert-history` | View all past alerts with filters |
| Thresholds | `/thresholds` | Configure per-server threshold values |
| Alert Config | `/alert-config` | Configure notification recipients and channels |
| Mobile Alerts | `/mobile-alerts` | Manage mobile push notification settings |
