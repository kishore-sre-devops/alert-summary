
import os
import sys
from datetime import datetime, timedelta
import clickhouse_connect

# Configuration
CH_HOST = os.getenv("CLICKHOUSE_HOST", "localhost")
CH_PORT = os.getenv("CLICKHOUSE_PORT", "8123")
CH_USER = os.getenv("CLICKHOUSE_USER", "default")
CH_PASSWORD = os.getenv("CLICKHOUSE_PASSWORD", "")

def get_client():
    try:
        return clickhouse_connect.get_client(
            host=CH_HOST, port=int(CH_PORT), username=CH_USER, password=CH_PASSWORD
        )
    except Exception as e:
        print(f"Failed to connect to ClickHouse: {e}")
        return None

def check_server_data(client, server_id, server_name):
    end_dt = datetime.utcnow()
    start_dt = end_dt - timedelta(minutes=15)
    
    print(f"\n--- Checking Server: {server_name} (ID: {server_id}) ---")
    
    # 1. Check RAW data count for 'memory_used_bytes'
    raw_query = f"""
        SELECT count(*), min(ts), max(ts)
        FROM lama.server_metrics
        WHERE server_id = {server_id}
        AND metric_name = 'memory_used_bytes'
        AND ts BETWEEN '{start_dt.strftime('%Y-%m-%d %H:%M:%S')}' AND '{end_dt.strftime('%Y-%m-%d %H:%M:%S')}'
    """
    raw_result = client.query(raw_query).result_rows
    raw_count = raw_result[0][0]
    
    # 2. Check Aggregated data count (Current 1m logic)
    agg_query = f"""
        SELECT count(*)
        FROM (
            SELECT
                toStartOfInterval(ts, INTERVAL 1 MINUTE) as time_bucket,
                avg(value)
            FROM lama.server_metrics
            WHERE server_id = {server_id}
            AND metric_name = 'memory_used_bytes'
            AND ts BETWEEN '{start_dt.strftime('%Y-%m-%d %H:%M:%S')}' AND '{end_dt.strftime('%Y-%m-%d %H:%M:%S')}'
            GROUP BY time_bucket
        )
    """
    agg_result = client.query(agg_query).result_rows
    agg_count = agg_result[0][0]
    
    print(f"Time Range: Last 15 Minutes")
    print(f"RAW Points found: {raw_count}")
    print(f"AGGREGATED (1m) Points found: {agg_count}")
    
    if raw_count > 0:
        first_ts = raw_result[0][1]
        last_ts = raw_result[0][2]
        print(f"Data Span: {first_ts} to {last_ts}")
        
        # Check density
        duration_sec = (last_ts - first_ts).total_seconds() if last_ts and first_ts else 0
        if duration_sec > 0:
            interval = duration_sec / raw_count
            print(f"Avg Interval: {interval:.2f} seconds")
            
    if raw_count > 0 and agg_count == 0:
        print("!! CRITICAL: Data exists but Aggregation hides it !!")
    elif raw_count == 0:
        print("!! WARNING: No data at all for this server !!")
    else:
        print(f"Status: OK (Raw: {raw_count}, Agg: {agg_count})")

def main():
    client = get_client()
    if not client: return

    # Get list of online servers to sample
    try:
        # We need to query postgres for server names, but for simplicity let's just grab active IDs from ClickHouse
        # Get top 5 servers with most data in last hour
        active_servers = client.query("""
            SELECT server_id, any(value) -- dummy agg
            FROM lama.server_metrics 
            WHERE ts > now() - INTERVAL 1 HOUR
            GROUP BY server_id
            LIMIT 10
        """).result_rows
        
        server_ids = [row[0] for row in active_servers]
        
        print(f"Found active servers in ClickHouse: {server_ids}")
        
        for sid in server_ids:
            check_server_data(client, sid, f"Server {sid}")
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()
