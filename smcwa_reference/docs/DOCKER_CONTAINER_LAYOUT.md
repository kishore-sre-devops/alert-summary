# Docker Container Layout

## Overview

LAMA runs as 7 Docker containers managed by `docker-compose.yml`. Each service has specific port mappings, volume mounts, and health checks. All containers share the `lama-net` bridge network.

---

## Container Diagram

```
docker-compose.yml
┌─────────────────────────────────────────────────────────────────┐
│                                                                 │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌────┐ │
│  │ lama_nginx   │  │  lama_api    │  │lama_scheduler│  │graf│ │
│  │ Port: 80,443 │  │ Port: 8000   │  │  (internal)  │  │ana │ │
│  │ nginx:alpine │  │ python:3.11  │  │ python:3.11  │  │3000│ │
│  └──────────────┘  └──────────────┘  └──────────────┘  └────┘ │
│                                                                 │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐         │
│  │lama_postgres │  │lama_click    │  │ lama_redis   │         │
│  │ Port: 5432   │  │house: 8123   │  │ Port: 6379   │         │
│  │ postgres:15  │  │clickhouse:24 │  │ redis:7      │         │
│  └──────────────┘  └──────────────┘  └──────────────┘         │
└─────────────────────────────────────────────────────────────────┘
```

---

## Container Details

| Container | Image | Ports | Depends On | Restart |
|---|---|---|---|---|
| `lama_nginx` | Custom (React build + nginx:alpine) | 80, 443 | lama_api | unless-stopped |
| `lama_api` | Custom (python:3.11 + FastAPI) | 8000 | postgres, redis, clickhouse | unless-stopped |
| `lama_scheduler` | Custom (python:3.11 + APScheduler) | — (internal) | postgres, redis, clickhouse | unless-stopped |
| `lama_grafana` | grafana:10 | 3000 | — | unless-stopped |
| `lama_postgres` | postgres:15 | 5432 | — | unless-stopped |
| `lama_clickhouse` | clickhouse:24 | 8123 | — | unless-stopped |
| `lama_redis` | redis:7 | 6379 | — | unless-stopped |

---

## Volume Mounts

| Mount | Container | Path Inside Container | Purpose |
|---|---|---|---|
| `./api/backend` | lama_api, lama_scheduler | `/app` | Python application code |
| `./ui/build` | lama_nginx | `/usr/share/nginx/html` | React production build |
| `./certificates` | lama_nginx | `/etc/nginx/ssl` | SSL certificates |
| `pgdata` (named) | lama_postgres | `/var/lib/postgresql/data` | Persistent DB storage |
| `clickhouse_data` (named) | lama_clickhouse | `/var/lib/clickhouse` | Persistent metrics storage |

---

## Health Checks

| Container | Check | Interval |
|---|---|---|
| `lama_nginx` | `curl -f http://localhost/` | 30s |
| `lama_postgres` | `pg_isready` | 10s |
| `lama_clickhouse` | `wget --spider http://localhost:8123/ping` | 10s |
| `lama_redis` | `redis-cli ping` | 10s |
| `lama_scheduler` | Heartbeat file `/tmp/scheduler_heartbeat` touched every 1 min | 60s |

---

## Environment Variables

Key environment variables (from `.env`):

| Variable | Used By | Purpose |
|---|---|---|
| `POSTGRES_USER` | postgres, api, scheduler | Database username |
| `POSTGRES_PASSWORD` | postgres, api, scheduler | Database password |
| `POSTGRES_DB` | postgres, api, scheduler | Database name |
| `REDIS_URL` | api, scheduler | Redis connection string |
| `CLICKHOUSE_HOST` | api, scheduler | ClickHouse hostname |
| `ACTIVE_ENVIRONMENT` | scheduler | `uat` or `prod` — determines which exchange config to use |
| `TZ` | all | `Asia/Kolkata` — IST timezone |

---

## Network

All containers are on the `lama-net` Docker bridge network. Only Nginx exposes ports externally (80/443). Inter-container communication uses container names as hostnames (e.g., `postgres:5432`, `redis:6379`).
