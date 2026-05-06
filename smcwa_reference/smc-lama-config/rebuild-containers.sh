#!/bin/bash
# Rebuild and restart containers with latest code
# Run this on your office server after transferring updated code

echo "=========================================="
echo "SMC-LAMA Container Rebuild Script"
echo "=========================================="
echo ""

# Get the directory where script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

# FORCE LOAD .ENV (Fixes the 502/Password Mismatch issue permanently)
if [ -f .env ]; then
    echo "Loading configuration from .env file..."
    export $(grep -v '^#' .env | xargs)
else
    echo "❌ ERROR: .env file not found in $(pwd)"
    echo "Please create it first: cp env.example .env"
    exit 1
fi

# Step 0: Pre-flight checks (SSL Certificates)
echo "Step 0: Checking SSL certificates..."
if [ ! -f "certificates/fullchain.crt" ] || [ ! -f "certificates/wildcard_smcindiaonline_com.key" ]; then
    echo "⚠️  WARNING: SSL certificates missing in smc-lama-config/certificates/"
    echo "Nginx may fail to start. Please ensure fullchain.crt and wildcard_smcindiaonline_com.key exist."
    # Don't exit here, as the user might be using HTTP for testing, but warn loudly.
fi

echo "Current directory: $(pwd)"
echo ""

# Step 1: Stop all containers
echo "Step 1: Stopping all containers..."
docker compose down
echo ""

# Step 2: Rebuild API, Nginx and Scheduler containers with latest code
echo "Step 2: Rebuilding API, Nginx and Scheduler containers with latest code..."
echo "This may take a few minutes..."
docker compose build --no-cache nginx api scheduler
echo ""

# Step 3 is now part of the docker build for nginx

# Step 4: Start all containers
echo "Step 4: Starting all containers..."
docker compose up -d
echo ""

# Step 4.1: Initialize ClickHouse Schema
echo "Step 4.1: Initializing ClickHouse Schema..."

# Wait for ClickHouse to be ready (Native protocol port 9000)
echo "Waiting for ClickHouse to start..."
for i in {1..30}; do
    if docker exec lama_clickhouse clickhouse-client --query "SELECT 1" >/dev/null 2>&1; then
        echo "ClickHouse is ready!"
        break
    fi
    echo -n "."
    sleep 1
    if [ $i -eq 30 ]; then
        echo "Timed out waiting for ClickHouse"
    fi
done

docker exec lama_clickhouse clickhouse-client --query "CREATE DATABASE IF NOT EXISTS lama"
docker exec lama_clickhouse clickhouse-client --query "CREATE TABLE IF NOT EXISTS lama.server_metrics (server_id UInt32, metric_name String, value Float64, interface_name Nullable(String), ts DateTime DEFAULT now()) ENGINE = ReplacingMergeTree() PARTITION BY toYYYYMM(ts) ORDER BY (server_id, metric_name, interface_name, ts) TTL ts + INTERVAL 30 DAY"
docker exec lama_clickhouse clickhouse-client --query "CREATE TABLE IF NOT EXISTS lama.server_metrics_hourly (server_id UInt32, metric_name String, interface_name Nullable(String), ts DateTime, min_value SimpleAggregateFunction(min, Float64), max_value SimpleAggregateFunction(max, Float64), sum_value SimpleAggregateFunction(sum, Float64), count SimpleAggregateFunction(sum, UInt64)) ENGINE = AggregatingMergeTree() PARTITION BY toYYYYMM(ts) ORDER BY (server_id, metric_name, interface_name, ts) TTL ts + INTERVAL 730 DAY"
docker exec lama_clickhouse clickhouse-client --query "CREATE MATERIALIZED VIEW IF NOT EXISTS lama.server_metrics_hourly_mv TO lama.server_metrics_hourly AS SELECT server_id, metric_name, interface_name, toStartOfHour(ts) as ts, min(value) as min_value, max(value) as max_value, sum(value) as sum_value, count(*) as count FROM lama.server_metrics GROUP BY server_id, metric_name, interface_name, ts"
echo "ClickHouse schema initialized."
echo ""

# Step 5: Wait for services to be ready
echo "Step 5: Waiting for services to start..."
sleep 10
echo ""

# Step 6: Check container status
echo "Step 6: Container Status:"
docker ps --filter "name=lama" --format "table {{.Names}}\t{{.Status}}"
echo ""

# Step 7: Check API health
echo "Step 7: Checking API health..."
sleep 5
curl -s http://localhost:8000/health 2>&1 | head -3 || echo "API not ready yet"
echo ""

# Step 8: Show nginx logs
echo "Step 8: Recent Nginx logs:"
docker logs lama_nginx --tail 10 2>&1
echo ""

# Step 9: Show API logs
echo "Step 9: Recent API logs:"
docker logs lama_api --tail 10 2>&1
echo ""

echo "=========================================="
echo "Rebuild Complete!"
echo "=========================================="
echo ""
echo "Next steps:"
echo "1. Check container status: docker ps --filter 'name=lama'"
echo "2. Check API logs: docker logs lama_api --tail 50"
echo "3. Check nginx logs: docker logs lama_nginx --tail 50"
echo "4. Test the application: https://smclama.smcindiaonline.com"
echo ""

