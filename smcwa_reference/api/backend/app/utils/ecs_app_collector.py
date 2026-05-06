
import boto3
import logging
from datetime import datetime, timedelta
from app.db.db import engine, clickhouse_client
from sqlalchemy import text
from app.collectors.aws_collector import AWSCollector

logger = logging.getLogger(__name__)

def collect_ecs_app_metrics():
    """
    High-frequency (1m) collector for ECS Application Metrics via CloudWatch ALB/NLB metrics.
    Ensures app_throughput, app_latency, and app_failure keys are populated in ClickHouse.
    """
    try:
        with engine.connect() as conn:
            # Get only ECS sources that have ALB or TargetGroup ARNs
            query = text("""
                SELECT id, name, config, environment 
                FROM metric_sources 
                WHERE type = 'ecs' AND enabled = TRUE
            """)
            sources = conn.execute(query).fetchall()

        for s_id, s_name, config, env in sources:
            role_arn = config.get('role_arn')
            region = config.get('region', 'ap-south-1')
            tg_arn = config.get('targetGroupArn')
            alb_arn = config.get('alb_arn') or config.get('albArn')
            
            if not tg_arn or not role_arn:
                continue

            # Parse TargetGroup and LoadBalancer IDs for CloudWatch dimensions
            # Format: targetgroup/name/id -> name/id
            try:
                # TargetGroup dimension needs 'targetgroup/' prefix for CloudWatch
                tg_suffix = tg_arn.split(':targetgroup/')[-1]
                tg_dimension = f"targetgroup/{tg_suffix}"
                
                collector = AWSCollector(role_arn=role_arn, region=region)
                session = collector._get_session()
                if not session: continue
                
                cw = session.client('cloudwatch')
                
                # Dynamically discover the exact dimensions for this TargetGroup
                # We need both TargetGroup and LoadBalancer dimensions (without AvailabilityZone)
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
                        
                # Fallback to just TargetGroup if dynamic discovery didn't find LoadBalancer
                if not exact_dims:
                    exact_dims = [{'Name': 'TargetGroup', 'Value': tg_dimension}]

                # STABILITY FIX: Shift window back by 90s to ensure data has 'landed' in CloudWatch
                end = datetime.utcnow() - timedelta(seconds=90)
                start = end - timedelta(minutes=3) 

                def get_stat(metric, stat='Sum'):
                    try:
                        res = cw.get_metric_statistics(
                            Namespace='AWS/ApplicationELB',
                            MetricName=metric,
                            Dimensions=exact_dims,
                            StartTime=start,
                            EndTime=end,
                            Period=60,
                            Statistics=[stat]
                        )
                        points = res.get('Datapoints', [])
                        if not points: return 0.0
                        # Return the most recent datapoint
                        points.sort(key=lambda x: x['Timestamp'])
                        return float(points[-1][stat])
                    except: return 0.0

                # Pull the 4 LAMA keys
                throughput = round(get_stat('RequestCount', 'Sum') / 60.0, 2) # Requests per second
                latency = round(get_stat('TargetResponseTime', 'Average') * 1000.0, 2) # Seconds to Milliseconds
                fail_5xx = int(get_stat('HTTPCode_Target_5XX_Count', 'Sum'))
                fail_4xx = int(get_stat('HTTPCode_Target_4XX_Count', 'Sum'))

                # Write to ClickHouse for 5-minute aggregation
                if clickhouse_client:
                    ts = datetime.utcnow()
                    data = [[
                        int(s_id), 'app_throughput', float(throughput), None, ts
                    ], [
                        int(s_id), 'app_latency', float(latency), None, ts
                    ], [
                        int(s_id), 'app_failure_trade_api', float(fail_5xx), None, ts
                    ], [
                        int(s_id), 'app_failure_authentication', float(fail_4xx), None, ts
                    ]]
                    
                    clickhouse_client.insert('lama.server_metrics', data, 
                                           column_names=['server_id', 'metric_name', 'value', 'interface_name', 'ts'])
                    
                    logger.info(f"✅ Synced ECS App Metrics for {s_name}: Thp={throughput}, Lat={latency}")
            except Exception as inner_e:
                logger.error(f"Error processing ECS source {s_name}: {inner_e}")

    except Exception as e:
        logger.error(f"Error in collect_ecs_app_metrics: {e}")
