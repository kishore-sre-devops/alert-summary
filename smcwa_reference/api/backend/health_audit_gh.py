import asyncio, boto3, json, logging, os
from app.collectors.aws_collector import AWSCollector
from app.collectors.es_collector import ESCollector
from app.db.db import engine, elasticsearch_config_table
from sqlalchemy import select

logging.getLogger('botocore').setLevel(logging.CRITICAL)
logging.getLogger('boto3').setLevel(logging.CRITICAL)

async def test_es_and_network():
    ROLE_ARN = "arn:aws:iam::396913716058:role/SMC-LAMA-CrossAccount-ReadOnly"
    collector = AWSCollector(role_arn=ROLE_ARN)
    
    print("\n" + "="*60)
    print("SECTION G: Elasticsearch")
    print("="*60)
    try:
        with engine.connect() as conn:
            query = select(elasticsearch_config_table)
            configs = conn.execute(query).fetchall()
        for cfg in configs:
            # id, name, server_id, host, port, username, password, scheme, ...
            print(f"\n{cfg[1]} ({cfg[3]})")
            try:
                es = ESCollector(host=cfg[3], port=cfg[4], user=cfg[5], password=cfg[6], scheme=cfg[7])
                m = es.collect_metrics({})
                print(f"  status:    {m.get('status')}")
                print(f"  qSize:     {m.get('qSize')}")
                print(f"  bandwidth: {m.get('bandwidth')}%")
                print(f"  latency:   {m.get('latency')} ms")
            except Exception as e:
                print(f"  ERROR: {e}")
    except Exception as e:
        print(f"ES ERROR: {e}")

    print("\n" + "="*60)
    print("SECTION H: Network Metrics (LBs)")
    print("="*60)
    try:
        session = collector._get_session()
        if session:
            elbv2 = session.client('elbv2')
            lbs = elbv2.describe_load_balancers()['LoadBalancers']
            for lb in lbs:
                arn = lb['LoadBalancerArn']
                name = lb['LoadBalancerName']
                print(f"\nLB: {name}")
                try:
                    if lb['Type'] == 'application':
                        m = await collector.collect_alb_network_metrics(arn)
                    else:
                        m = await collector.collect_nlb_network_metrics(arn)
                    print(f"  bandwidth:   {m.get('bandwidth', {}).get('avg') if isinstance(m.get('bandwidth'), dict) else 0.0} bytes/s")
                    print(f"  packetCount: {m.get('packetCount', {}).get('avg') if isinstance(m.get('packetCount'), dict) else 0.0}")
                except Exception as e:
                    print(f"  ERROR: {e}")
    except Exception as e:
        print(f"Network ERROR: {e}")

asyncio.run(test_es_and_network())
