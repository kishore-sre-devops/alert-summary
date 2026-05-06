import asyncio
import json
from sqlalchemy import text
from app.db.db import engine
from app.collectors.aws_collector import AWSCollector
from app.collectors.es_collector import ESCollector

async def run_audit():
    ROLE_ARN = "arn:aws:iam::396913716058:role/SMC-LAMA-CrossAccount-ReadOnly"
    aws = AWSCollector(role_arn=ROLE_ARN)
    
    print("\n=== SECTION G: Elasticsearch ===")
    try:
        with engine.connect() as conn:
            # Querying elasticsearch_config
            res = conn.execute(text("SELECT id, environment, host, port, username, password FROM elasticsearch_config")).fetchall()
            for r in res:
                print(f"\nES: {r[1]} ({r[2]}:{r[3]})")
                try:
                    es = ESCollector(host=r[2], port=r[3], user=r[4], password=r[5])
                    health = await es.get_cluster_health()
                    print(f"  status: {health.get('status')}")
                    app = await es.collect_application_metrics()
                    print(f"  throughput: {app.get('throughput')}")
                    print(f"  latency: {app.get('latency')} ms")
                except Exception as e:
                    print(f"  ERROR: {e}")
    except Exception as e:
        print(f"ES SECTION ERROR: {e}")

    print("\n=== SECTION H: Network (LBs) ===")
    try:
        session = aws._get_session()
        if session:
            elbv2 = session.client('elbv2')
            lbs = elbv2.describe_load_balancers()['LoadBalancers']
            for lb in lbs:
                name = lb['LoadBalancerName']
                arn = lb['LoadBalancerArn']
                print(f"\nLB: {name}")
                try:
                    if lb['Type'] == 'application': m = await aws.collect_alb_network_metrics(arn)
                    else: m = await aws.collect_nlb_network_metrics(arn)
                    
                    def get_val(d, key):
                        if isinstance(d.get(key), dict): return d[key].get('avg', 0.0)
                        return d.get(key, 0.0)
                    
                    print(f"  bandwidth:   {get_val(m, 'bandwidth')} bytes/s")
                    print(f"  latency:     {get_val(m, 'latency')} ms")
                    print(f"  packetCount: {get_val(m, 'packetCount')}")
                except Exception as e:
                    print(f"  ERROR: {e}")
    except Exception as e:
        print(f"NETWORK SECTION ERROR: {e}")

if __name__ == '__main__':
    asyncio.run(run_audit())
