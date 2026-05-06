# System Architecture

## Overview

SMC LAMA is a containerized microservices platform for monitoring trading system health across NSE, BSE, MCX, and NCDEX exchanges. All services run via Docker Compose on a single host.

---

## Architecture Diagram

```
                                ┌──────────────────┐
                                │   USER BROWSER   │
                                │  (React 18 UI)   │
                                └────────┬─────────┘
                                         │ HTTPS (443)
                                         ▼
┌─────────────────────────────────────────────────────────────────────┐
│                          NGINX PROXY                                │
│                  (SSL Termination + Routing)                        │
│                                                                     │
│   /           → React Static Files (UI)                            │
│   /api/*      → FastAPI Backend (Port 8000)                        │
│   /grafana/*  → Grafana Dashboards (Port 3000)                     │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
        ┌──────────────────┼──────────────────┐
        ▼                  ▼                  ▼
 ┌──────────────┐  ┌──────────────┐  ┌──────────────┐
 │  LAMA API    │  │LAMA SCHEDULER│  │   GRAFANA    │
 │ FastAPI/     │  │ APScheduler  │  │              │
 │ Gunicorn     │  │              │  │ Pre-built    │
 │              │  │ Metrics      │  │ Dashboards   │
 │ REST API     │  │ Collection   │  │ Custom       │
 │ Auth         │  │ Alert Check  │  │ Queries      │
 │ Validation   │  │ ECS Metrics  │  │ Real-time    │
 └──────┬───────┘  └──────┬───────┘  └──────────────┘
        └────────┬─────────┘
                 │
   ┌─────────────┼─────────────┬─────────────┐
   ▼             ▼             ▼             ▼
┌────────┐ ┌──────────┐ ┌────────┐ ┌────────────┐
│Postgres│ │ClickHouse│ │ Redis  │ │Prometheus/ │
│        │ │          │ │        │ │  Mimir     │
│ Users  │ │ Metrics  │ │Sessions│ │            │
│ Config │ │ Logs     │ │ Cache  │ │ DC/DR      │
│ Alerts │ │TimeSeries│ │ Tokens │ │ Metrics    │
└────────┘ └──────────┘ └────────┘ └────────────┘
```

---

## Component Responsibilities

| Container | Technology | Port | Purpose |
|---|---|---|---|
| `lama_nginx` | nginx:alpine | 80, 443 | SSL termination, reverse proxy, React static files |
| `lama_api` | Python 3.11 / FastAPI | 8000 | REST API, authentication, business logic |
| `lama_scheduler` | Python 3.11 / APScheduler | internal | Background jobs: metrics, alerts, exchange sync |
| `lama_grafana` | Grafana 10 | 3000 | Pre-built dashboards, custom PromQL queries |
| `lama_postgres` | PostgreSQL 15 | 5432 | Users, server config, alert rules, exchange credentials |
| `lama_clickhouse` | ClickHouse 24 | 8123 | High-speed time-series: server metrics, logs, alert history |
| `lama_redis` | Redis 7 | 6379 | Session tokens, metric cache, hot store for dashboard |

---

## Database Roles

| Database | Stores | TTL |
|---|---|---|
| **PostgreSQL** | Users, server_status, database_config, metric_sources, exchange_transactions, alert_config | Permanent |
| **ClickHouse** | server_metrics (raw 30d), server_metrics_hourly (aggregated 2yr), alert_history, scheduler_logs | Auto-TTL |
| **Redis** | JWT sessions, LAMA Exchange tokens, sequence IDs, server hot store metrics | In-memory |

---

## Network

All containers share the `lama-net` Docker bridge network. External access is only through Nginx on ports 80/443.
