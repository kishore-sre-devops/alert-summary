import os
import sys
import json
from sqlalchemy import create_engine, text
from datetime import datetime

# Add parent directory to path to import app modules
sys.path.append(os.path.join(os.getcwd(), 'api/backend'))

from app.db.db import DATABASE_URL

def trace_alerts():
    try:
        engine = create_engine(DATABASE_URL)
        with engine.connect() as conn:
            print(f"Tracing Exchange Alerts for 29-12-2025...\n")
            
            # Query transactions for today (2025-12-29)
            # The user provided times like 12:30, 12:35 etc. in IST.
            # Database stores in UTC. 12:30 IST is 07:00 UTC.
            
            query = text("""
                SELECT sent_at, metrics_sent, exchange_id
                FROM exchange_transactions 
                WHERE metric_type = 'network' 
                  AND sent_at >= '2025-12-29 06:00:00'
                  AND sent_at <= '2025-12-29 08:30:00'
                ORDER BY sent_at ASC
            """)
            
            rows = conn.execute(query).fetchall()
            print(f"Found {len(rows)} transactions in the target time window.\n")
            
            found_culprits = []
            
            for row in rows:
                sent_at = row[0]
                data = row[1]
                exchange_id = row[2]
                
                # Original metrics contains the per-server breakdown before aggregation
                original_metrics = data.get('original_metrics', [])
                
                for m in original_metrics:
                    server_name = m.get('server_name')
                    server_ip = m.get('server_ip')
                    metric_name = m.get('name')
                    
                    is_match = False
                    reason = ""
                    
                    if metric_name == 'packetCount' and m.get('value') == 80:
                        is_match = True
                        reason = f"packetCount = 80"
                    
                    if metric_name == 'bandwidth' and m.get('max') == 100:
                        is_match = True
                        reason = f"bandwidth max = 100"
                        
                    if is_match:
                        found_culprits.append({
                            "time_utc": sent_at.strftime('%H:%M:%S'),
                            "server": server_name,
                            "ip": server_ip,
                            "reason": reason,
                            "exchange_id": exchange_id
                        })

            if found_culprits:
                print(f"{ 'TIME (UTC)':<10} | { 'SERVER':<40} | { 'IP':<15} | { 'ALERT REASON':<20}")
                print("-" * 90)
                # Filter duplicates to show unique servers per time slot
                seen = set()
                for c in found_culprits:
                    key = (c['time_utc'][:5], c['server'], c['reason'])
                    if key not in seen:
                        print(f"{c['time_utc']:<10} | {c['server']:<40} | {c['ip']:<15} | {c['reason']:<20}")
                        seen.add(key)
            else:
                print("No servers found with matching alert values (80 or 100) in the raw data logs.")
                
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    trace_alerts()