import asyncio, boto3, json, logging, os, time
from datetime import datetime, timedelta
from app.collectors.aws_collector import AWSCollector
from app.collectors.mysql_collector import MySQLCollector
from app.collectors.es_collector import ESCollector
from app.db.db import engine, database_config_table, elasticsearch_config_table
from sqlalchemy import select

# Disable verbose logging to keep output clean
logging.getLogger('botocore').setLevel(logging.CRITICAL)
logging.getLogger('boto3').setLevel(logging.CRITICAL)
logging.getLogger('urllib3').setLevel(logging.CRITICAL)

async def test_all():
    ROLE_ARN = "arn:aws:iam::396913716058:role/SMC-LAMA-CrossAccount-ReadOnly"
    collector = AWSCollector(role_arn=ROLE_ARN)
    
    # --- ECS ---
    print("\n" + "="*60)
    print("SECTION C: AWS ECS")
    print("="*60)
    try:
        session = collector._get_session()
        if session:
            ecs = session.client('ecs')
            clusters = ecs.list_clusters()['clusterArns']
            for cluster_arn in clusters:
                cluster = cluster_arn.split('/')[-1]
                services = ecs.list_services(cluster=cluster)['serviceArns']
                print(f"\nCLUSTER: {cluster} ({len(services)} services)")
                for svc_arn in services:
                    svc = svc_arn.split('/')[-1]
                    print(f"  Service: {svc}")
                    try:
                        # FIXED ORDER: cluster, svc
                        m = await collector.collect_ecs_hardware_metrics(cluster, svc)
                        cpu = m.get("cpu", {}).get("avg") if m.get("cpu") else 0.0
                        mem = m.get("memory", {}).get("avg") if m.get("memory") else 0.0
                        print(f"    CPU:        {cpu}%")
                        print(f"    Memory:     {mem}%")
                    except Exception as e:
                        print(f"    ERROR: {e}")
        else:
            print("ECS ERROR: Could not get AWS session")
    except Exception as e:
        print(f"ECS ERROR: {e}")

    # --- EC2 ---
    print("\n" + "="*60)
    print("SECTION D: AWS EC2 Instances")
    print("="*60)
    try:
        session = collector._get_session()
        if session:
            ec2 = session.client('ec2')
            instances = ec2.describe_instances(Filters=[{'Name':'instance-state-name','Values':['running']}])
            for r in instances['Reservations']:
                for i in r['Instances']:
                    iid = i['InstanceId']
                    name = next((t['Value'] for t in i.get('Tags',[]) if t['Key']=='Name'), 'unnamed')
                    print(f"\n{name} ({iid})")
                    try:
                        m = await collector.collect_ec2_hardware_metrics(iid)
                        cpu = m.get("cpu", {}).get("avg") if m.get("cpu") else 0.0
                        mem = m.get("memory", {}).get("avg") if m.get("memory") else 0.0
                        disk = m.get("disk", {}).get("avg") if m.get("disk") else 0.0
                        print(f"  CPU:  {cpu:.2f}%")
                        print(f"  MEM:  {f'{mem:.2f}%' if mem > 0 else '❌ None (CWAgent?)'}")
                        print(f"  DISK: {f'{disk:.2f}%' if disk > 0 else '❌ None (CWAgent?)'}")
                    except Exception as e:
                        print(f"  ERROR: {e}")
    except Exception as e:
        print(f"EC2 ERROR: {e}")

    # --- RDS ---
    print("\n" + "="*60)
    print("SECTION E: RDS Databases")
    print("="*60)
    try:
        session = collector._get_session()
        if session:
            rds = session.client('rds')
            instances = rds.describe_db_instances()['DBInstances']
            for db in instances:
                dbid = db['DBInstanceIdentifier']
                print(f"\n{dbid} [{db['DBInstanceStatus']}]")
                try:
                    m = await collector.collect_rds_database_metrics(dbid)
                    print(f"  status:    {m.get('status')}")
                    print(f"  qSize:     {m.get('qSize', {}).get('avg') if isinstance(m.get('qSize'), dict) else 0.0} sec lag")
                    print(f"  latency:   {m.get('latency', {}).get('avg') if isinstance(m.get('latency'), dict) else 0.0} ms")
                    print(f"  bandwidth: {m.get('bandwidth', {}).get('avg') if isinstance(m.get('bandwidth'), dict) else 0.0}")
                except Exception as e:
                    print(f"  ERROR: {e}")
    except Exception as e:
        print(f"RDS ERROR: {e}")

    # --- MySQL ---
    print("\n" + "="*60)
    print("SECTION F: MySQL On-Prem")
    print("="*60)
    try:
        with engine.connect() as conn:
            query = select(database_config_table).where(database_config_table.c.db_type == 'mysql')
            configs = conn.execute(query).fetchall()
        
        for cfg in configs:
            name = cfg[1]
            host = cfg[3]
            port = cfg[4]
            user = cfg[5]
            password = cfg[6]
            database = cfg[7]
            is_repl = cfg[9]
            print(f"\n{name} ({host}:{port})")
            try:
                from app.utils.aes_encryption import decrypt_password
                from app.utils.lama_exchange import get_exchange_credentials
                creds = get_exchange_credentials("uat") or get_exchange_credentials("prod")
                secret_key = creds.get("secret_key") if creds else None
                
                plain_password = password
                if secret_key:
                    try: 
                        plain_password = decrypt_password(password, secret_key)
                    except Exception as de:
                        print(f"  Password decryption failed, trying as-is: {de}")

                mysql_collector = MySQLCollector(
                    host=host, port=port, username=user, password=plain_password,
                    database=database, is_replication=is_repl
                )
                res = await mysql_collector.collect()
                print(f"  status:    {res.get('status')}")
                print(f"  qSize:     {res.get('qSize', {}).get('avg')} sec behind")
                print(f"  bandwidth: {res.get('bandwidth', {}).get('avg')}")
                print(f"  latency:   {res.get('latency', {}).get('avg')} ms")
            except Exception as e:
                print(f"  ERROR: {e}")
    except Exception as e:
        print(f"MySQL ERROR: {e}")

    # --- Elasticsearch ---
    print("\n" + "="*60)
    print("SECTION G: Elasticsearch")
    print("="*60)
    try:
        with engine.connect() as conn:
            query = select(elasticsearch_config_table)
            configs = conn.execute(query).fetchall()

        for cfg in configs:
            name = cfg[1]
            host = cfg[3]
            port = cfg[4]
            user = cfg[5]
            password = cfg[6]
            scheme = cfg[7]
            print(f"\n{name} ({host}:{port})")
            try:
                es_collector = ESCollector(host=host, port=port, user=user, password=password, scheme=scheme)
                m = es_collector.collect_metrics({})
                print(f"  status:    {m.get('status')}")
                print(f"  qSize:     {m.get('qSize')}")
                print(f"  bandwidth: {m.get('bandwidth')}%")
                print(f"  latency:   {m.get('latency')} ms")
                
                app = es_collector.collect_application_metrics()
                print(f"  throughput:     {app.get('throughput', {}).get('avg')}")
                print(f"  app latency:    {app.get('latency', {}).get('avg')} ms")
            except Exception as e:
                print(f"  ERROR: {e}")
    except Exception as e:
        print(f"ES ERROR: {e}")

    # --- Network ---
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

asyncio.run(test_all())
