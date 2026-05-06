import sys
import os
sys.path.append('/app')
import boto3
from app.db.db import engine
from sqlalchemy import text
from app.collectors.aws_collector import AWSCollector
from datetime import datetime, timedelta

def check_ecs_metrics():
    with engine.connect() as conn:
        query = text("""
            SELECT id, name, config 
            FROM metric_sources 
            WHERE type = 'ecs' AND enabled = TRUE
            ORDER BY name ASC
        """)
        sources = conn.execute(query).fetchall()

    results = []

    for s_id, s_name, config in sources:
        # Check if the source belongs to one of the 3 specified accounts
        if not any(acc in s_name for acc in ['SMC-TRADING-PROD', 'SMC-TRADING-MIDDLEWARE-PROD', 'SMC-PRE-TRADING-PROD']):
            continue

        role_arn = config.get('role_arn')
        region = config.get('region', 'ap-south-1')
        tg_arn = config.get('targetGroupArn')
        
        if not tg_arn or not role_arn:
            results.append({
                'service': s_name,
                'status': 'No TargetGroup ARN or Role ARN configured',
                'metrics': {}
            })
            continue

        try:
            tg_suffix = tg_arn.split(':targetgroup/')[-1]
            tg_dimension = f"targetgroup/{tg_suffix}"
            
            collector = AWSCollector(role_arn=role_arn, region=region)
            session = collector._get_session()
            if not session:
                results.append({
                    'service': s_name,
                    'status': 'Failed to assume role',
                    'metrics': {}
                })
                continue
                
            cw = session.client('cloudwatch')
            
            # Dynamically discover dimensions
            res = cw.list_metrics(
                Namespace='AWS/ApplicationELB',
                MetricName='RequestCount',
                Dimensions=[{'Name': 'TargetGroup', 'Value': tg_dimension}]
            )
            
            exact_dims = None
            for m in res.get('Metrics', []):
                dim_names = [d['Name'] for d in m['Dimensions']]
                if 'TargetGroup' in dim_names and 'LoadBalancer' in dim_names and len(dim_names) == 2:
                    exact_dims = m['Dimensions']
                    break
                    
            if not exact_dims:
                exact_dims = [{'Name': 'TargetGroup', 'Value': tg_dimension}]

            end = datetime.utcnow()
            start = end - timedelta(minutes=5)

            def get_stat(metric, stat='Sum'):
                try:
                    r = cw.get_metric_statistics(
                        Namespace='AWS/ApplicationELB',
                        MetricName=metric,
                        Dimensions=exact_dims,
                        StartTime=start,
                        EndTime=end,
                        Period=60,
                        Statistics=[stat]
                    )
                    points = r.get('Datapoints', [])
                    if not points: return "No Data"
                    points.sort(key=lambda x: x['Timestamp'])
                    return points[-1][stat]
                except Exception as e: 
                    return f"Error"

            # Pull the 4 LAMA keys
            req_count = get_stat('RequestCount', 'Sum')
            resp_time = get_stat('TargetResponseTime', 'Average')
            fail_5xx = get_stat('HTTPCode_Target_5XX_Count', 'Sum')
            fail_4xx = get_stat('HTTPCode_Target_4XX_Count', 'Sum')

            throughput = req_count / 60.0 if isinstance(req_count, (int, float)) else req_count
            latency = resp_time * 1000.0 if isinstance(resp_time, (int, float)) else resp_time
            
            # Format output
            metrics_data = {
                'app_throughput': f"{throughput:.2f} req/s" if isinstance(throughput, float) else str(throughput),
                'app_latency': f"{latency:.2f} ms" if isinstance(latency, float) else str(latency),
                'app_failure_trade_api (5xx)': str(fail_5xx),
                'app_failure_authentication (4xx)': str(fail_4xx)
            }

            results.append({
                'service': s_name,
                'status': 'Success',
                'metrics': metrics_data
            })
            
        except Exception as e:
            results.append({
                'service': s_name,
                'status': f"Error: {str(e)}",
                'metrics': {}
            })

    # Print results in a neat format
    print("=" * 110)
    print(f"{'ECS Application Service':<65} | {'Metric Key':<35} | {'Value'}")
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
    check_ecs_metrics()
