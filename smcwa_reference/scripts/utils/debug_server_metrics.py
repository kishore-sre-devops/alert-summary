
import os
import sys
from sqlalchemy import create_engine, text

# Add parent directory to path to import app modules
sys.path.append(os.path.join(os.getcwd(), 'api/backend'))

from app.db.db import DATABASE_URL

def debug_metrics():
    try:
        engine = create_engine(DATABASE_URL)
        with engine.connect() as conn:
            print("--- Finding Server ID ---")
            # Find server ID
            query = text("SELECT id, name, ip, environment FROM server_status WHERE ip = '10.247.16.220'")
            server = conn.execute(query).fetchone()
            
            if not server:
                print("Server 10.247.16.220 not found in database!")
                return
            
            server_id = server[0]
            print(f"Found Server: ID={server_id}, Name={server[1]}, IP={server[2]}, Env={server[3]}")
            
            print("\n--- Latest Raw Metrics (server_metrics table) ---")
            # Get latest metrics
            query_metrics = text(f"""
                SELECT metric_name, value, interface_name, ts 
                FROM server_metrics 
                WHERE server_id = {server_id} 
                AND ts >= NOW() - INTERVAL '30 minutes'
                ORDER BY metric_name, ts DESC
            """)
            
            rows = conn.execute(query_metrics).fetchall()
            
            # Group by metric name to show latest
            latest_metrics = {}
            for row in rows:
                name = row[0]
                if name not in latest_metrics:
                    latest_metrics[name] = row
            
            for name, row in latest_metrics.items():
                interface_val = str(row[2]) if row[2] is not None else "None"
                print(f"Metric: {name:<20} | Value: {row[1]:<10} | Interface: {interface_val:<10} | Time: {row[3]}")

            print("\n--- Checking for 'packet_count' vs 'network_throughput' ---")
            # Specifically check if we have packet counts
            packet_rows = [r for r in rows if 'packet' in r[0] or 'count' in r[0].lower()]
            if packet_rows:
                print(f"Found {len(packet_rows)} packet-related records. Top 5:")
                for r in packet_rows[:5]:
                    print(f"  {r[0]}: {r[1]} ({r[2]}) at {r[3]}")
            else:
                print("No metric with 'packet' or 'count' in name found.")

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    debug_metrics()
