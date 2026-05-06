# API Endpoints Reference

## Overview

The FastAPI backend exposes RESTful endpoints for all operations. All endpoints require JWT authentication (via `Authorization: Bearer <token>` header) except login and password reset.

**Base URL:** `/api/v1`

---

## Authentication

| Method | Endpoint | Access | Description |
|---|---|---|---|
| POST | `/auth/login` | Public | Login with AES-256 encrypted password, returns JWT token |
| POST | `/auth/logout` | Authenticated | Invalidate session (deletes Redis key) |
| POST | `/auth/reset-password` | Public | Password reset flow |
| POST | `/auth/change-password` | Authenticated | Change own password (verify old password first) |
| GET | `/auth/users` | Admin | List all users (passwords excluded) |
| POST | `/auth/users` | Admin | Create new user (bcrypt hashed) |
| PUT | `/auth/users/{id}` | Admin | Update user name/phone/role |
| DELETE | `/auth/users/{id}` | Admin | Delete user (cannot delete default admin) |

---

## Servers

| Method | Endpoint | Access | Description |
|---|---|---|---|
| GET | `/servers` | Authenticated | List all servers with latest status |
| GET | `/servers/{id}` | Authenticated | Server details with current metrics |
| GET | `/servers/{id}/metrics` | Authenticated | Server metrics from Prometheus (with `?range=1h/6h/24h`) |
| POST | `/servers` | Admin | Register new server |
| DELETE | `/servers/{id}` | Admin | Remove server |

---

## Metrics (ClickHouse)

| Method | Endpoint | Access | Description |
|---|---|---|---|
| GET | `/metrics/hardware` | Authenticated | CPU, Memory, Disk usage across fleet |
| GET | `/metrics/network` | Authenticated | Bandwidth, Latency, Packet Loss |
| GET | `/metrics/application` | Authenticated | Throughput, Latency, Error rates |
| GET | `/metrics/database` | Authenticated | Replication status, Queue Size |

---

## Exchange Activity

| Method | Endpoint | Access | Description |
|---|---|---|---|
| GET | `/exchange/activity` | Authenticated | Exchange connectivity status (NSE/BSE/MCX/NCDEX) |
| GET | `/exchange/errors` | Authenticated | Connectivity errors and failure logs |

---

## Alerts

| Method | Endpoint | Access | Description |
|---|---|---|---|
| GET | `/alerts` | Authenticated | Alert history with filters (date, severity, server) |
| GET | `/alerts/thresholds` | Authenticated | Currently configured thresholds |
| POST | `/alerts/thresholds` | Admin | Update threshold values |

---

## Configuration

| Method | Endpoint | Access | Description |
|---|---|---|---|
| GET | `/config` | Admin | Current system configuration |
| POST | `/config` | Admin | Update configuration |
| GET | `/config/database` | Admin | Database connection configs |
| POST | `/config/database` | Admin | Add/update database config |
| GET | `/config/metric-sources` | Admin | Registered metric sources (ECS, Prometheus, ES) |

---

## Scheduler & Diagnostics

| Method | Endpoint | Access | Description |
|---|---|---|---|
| GET | `/scheduler/status` | Authenticated | Current scheduler job statuses and last run times |
| GET | `/scheduler/logs` | Authenticated | Scheduler execution logs with filters |
| GET | `/diagnostics/lama` | Admin | LAMA Exchange connectivity diagnostics |
| GET | `/dashboard/summary` | Authenticated | Dashboard summary (server counts, alert counts, health) |

---

## Response Format

All endpoints return JSON:

```json
// Success
{
  "status": "success",
  "data": { ... }
}

// Error
{
  "status": "error",
  "message": "Description of what went wrong",
  "code": 400
}
```

---

## Authentication Header

All protected endpoints require:

```
Authorization: Bearer <jwt_token>
```

Token is obtained from `POST /auth/login` and expires after 24 hours.
