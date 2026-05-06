import asyncio
import boto3
from app.collectors.aws_collector import AWSCollector

async def run_audit():
    collector = AWSCollector()
    ecs = collector.get_ecs_client()
    ec2 = collector.get_ec2_client()
    
    print("\n=== SECTION C: AWS ECS AUDIT ===")
    try:
        clusters_resp = ecs.list_clusters()
        clusters = clusters_resp.get('clusterArns', [])
        print(f"Total clusters: {len(clusters)}")
        for cluster_arn in clusters:
            cluster = cluster_arn.split('/')[-1]
            services_resp = ecs.list_services(cluster=cluster)
            services = services_resp.get('serviceArns', [])
            print(f"\nCluster: {cluster} ({len(services)} services)")
            for svc_arn in services:
                svc = svc_arn.split('/')[-1]
                print(f"  Service: {svc}")
                try:
                    cpu = await collector.get_ecs_cpu(svc, cluster)
                    mem = await collector.get_ecs_memory(svc, cluster)
                    lb = await collector.get_lb_metrics(svc, cluster)
                    print(f"    CPU: {cpu}% | MEM: {mem}% | THP: {lb.get('throughput')} req/s | LAT: {lb.get('latency')} ms")
                except Exception as e:
                    print(f"    ERROR: {e}")
    except Exception as e:
        print(f"ECS ERROR: {e}")

    print("\n=== SECTION D: AWS EC2 AUDIT ===")
    try:
        instances = ec2.describe_instances(Filters=[{'Name':'instance-state-name','Values':['running']}])
        for r in instances.get('Reservations', []):
            for i in r.get('Instances', []):
                iid = i['InstanceId']
                name = next((t['Value'] for t in i.get('Tags',[]) if t['Key']=='Name'), 'unnamed')
                try:
                    cpu = await collector.get_ec2_metric(iid, 'CPUUtilization')
                    mem = await collector.get_ec2_metric(iid, 'mem_used_percent')
                    disk = await collector.get_ec2_metric(iid, 'disk_used_percent')
                    print(f"  {name} ({iid}) -> CPU: {cpu}% | MEM: {mem}% | DISK: {disk}%")
                except Exception as e:
                    print(f"  {name} ({iid}) ERROR: {e}")
    except Exception as e:
        print(f"EC2 ERROR: {e}")

if __name__ == '__main__':
    asyncio.run(run_audit())
