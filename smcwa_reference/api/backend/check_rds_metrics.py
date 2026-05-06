import sys
import os
import asyncio
sys.path.append('/app')
import boto3
from app.db.db import engine
from sqlalchemy import text
from app.collectors.aws_collector import AWSCollector
from datetime import datetime, timedelta

async def check_rds_metrics():
    with engine.connect() as conn:
        # Fetch configured metric sources that have CloudWatch/AWS credentials
        query = text("""
            SELECT id, name, config 
            FROM metric_sources 
            WHERE (type = 'cloudwatch' OR type = 'aws') AND enabled = TRUE
            ORDER BY name ASC
        """)
        sources = conn.execute(query).fetchall()

        # Fetch configured RDS databases
        db_query = text("""
            SELECT external_id, name, source_id
            FROM database_status
            WHERE name LIKE '%SMC-PRE-TRADING-PROD%' 
               OR name LIKE '%SMC-TRADING-MIDDLEWARE-PROD%' 
               OR name LIKE '%SMC-TRADING-PROD%'
            ORDER BY name ASC
        """)
        dbs = conn.execute(db_query).fetchall()

    # Map sources by ID for quick lookup
    source_map = {s.id: s for s in sources}

    results = []

    for db_external_id, db_name, source_id in dbs:
        if source_id not in source_map:
            results.append({
                'service': db_name,
                'status': f'Source ID {source_id} not found or disabled',
                'metrics': {}
            })
            continue

        src_id, src_name, config = source_map[source_id]
        role_arn = config.get('role_arn')
        region = config.get('region', 'ap-south-1')
        
        if not role_arn:
            results.append({
                'service': db_name,
                'status': 'No Role ARN configured on source',
                'metrics': {}
            })
            continue

        try:
            collector = AWSCollector(role_arn=role_arn, region=region)
            # Use the actual metric collection method used by LAMA
            metrics = await collector.collect_rds_database_metrics(db_external_id, window_minutes=5)
            
            # Format output
            def fmt(stat_dict, unit=''):
                if not isinstance(stat_dict, dict) or 'avg' not in stat_dict:
                    return str(stat_dict)
                val = stat_dict['avg']
                return f"{val:.2f} {unit}" if val > 0 else "0.00 " + unit

            metrics_data = {
                'bandwidth (CPU Utilization)': fmt(metrics.get('bandwidth'), '%'),
                'qSize (Connections / Lag s)': fmt(metrics.get('qSize')),
                'latency (Disk Queue / Lag ms)': fmt(metrics.get('latency')),
                'status (1=Up, 0=Down)': str(metrics.get('status'))
            }

            results.append({
                'service': db_name,
                'status': 'Success',
                'metrics': metrics_data
            })
            
        except Exception as e:
            results.append({
                'service': db_name,
                'status': f"Error: {str(e)}",
                'metrics': {}
            })

    # Print results in a neat format
    print("=" * 110)
    print(f"{'RDS Database Instance':<65} | {'Metric Key':<35} | {'Value'}")
    print("=" * 110)
    
    for r in results:
        service_name = r['service'][:63]
        if r['status'] != 'Success':
            print(f"{service_name:<65} | {'Status':<35} | {r['status']}")
            print("-" * 110)
            continue
            
        first = True
        for m_key, m_val in r['metrics'].items():
            if first:
                print(f"{service_name:<65} | {m_key:<35} | {m_val}")
                first = False
            else:
                print(f"{'':<65} | {m_key:<35} | {m_val}")
        print("-" * 110)

if __name__ == "__main__":
    asyncio.run(check_rds_metrics())
