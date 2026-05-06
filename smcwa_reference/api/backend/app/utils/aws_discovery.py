"""
AWS Resource Discovery Utility
Handles discovery of EC2 instances and RDS databases using boto3.
"""

import boto3
import logging
import json
from datetime import datetime, timezone
from typing import List, Dict, Any
from sqlalchemy import select, insert, update, text
from app.db.db import engine, server_status_table, database_config_table, lama_exchange_server_selection_table, metric_sources_table, metric_queries_table, application_status_table, database_status_table, aws_ignore_list_table

logger = logging.getLogger(__name__)

def get_aws_client(resource_type: str, config: Dict[str, Any]):
    """Create a boto3 client using provided config (Keys, Instance Profile, or AssumeRole)"""
    region = config.get('region', 'ap-south-1')
    access_key = config.get('access_key')
    secret_key = config.get('secret_key')
    role_arn = config.get('role_arn')
    
    try:
        # Case 1: Keys provided
        if access_key and secret_key:
            return boto3.client(
                resource_type,
                region_name=region,
                aws_access_key_id=access_key,
                aws_secret_access_key=secret_key
            )
        
        # Case 2: Role ARN provided (AssumeRole)
        if role_arn:
            sts = boto3.client('sts', region_name=region)
            try:
                assumed = sts.assume_role(
                    RoleArn=role_arn,
                    RoleSessionName='LamaCrossAccountSession',
                    ExternalId='SMC-LAMA-OBSERVABILITY'
                )
                creds = assumed['Credentials']
                return boto3.client(
                    resource_type,
                    region_name=region,
                    aws_access_key_id=creds['AccessKeyId'],
                    aws_secret_access_key=creds['SecretAccessKey'],
                    aws_session_token=creds['SessionToken']
                )
            except Exception as e:
                logger.error(f"Failed to assume role {role_arn}: {e}")
                raise e
                
        # Case 3: Default (Instance Profile / Env Vars)
        return boto3.client(resource_type, region_name=region)
        
    except Exception as e:
        logger.error(f"Failed to create AWS client: {e}")
        raise e

def discover_ec2_instances(config: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Discover running EC2 instances"""
    try:
        ec2 = get_aws_client('ec2', config)
        response = ec2.describe_instances(
            Filters=[{'Name': 'instance-state-name', 'Values': ['running']}]
        )
        
        instances = []
        for reservation in response.get('Reservations', []):
            for instance in reservation.get('Instances', []):
                name = ""
                for tag in instance.get('Tags', []):
                    if tag['Key'] == 'Name':
                        name = tag['Value']
                        break
                
                instances.append({
                    "id": instance['InstanceId'],
                    "name": name or instance['InstanceId'],
                    # LAMA V2.0 Update: Use PrivateDnsName (Mimir format) instead of raw IP
                    "ip": instance.get('PrivateDnsName') or instance.get('PrivateIpAddress', '0.0.0.0'),
                    "type": instance['InstanceType'],
                    "state": instance['State']['Name']
                })
        return instances
    except Exception as e:
        logger.error(f"Error discovering EC2 instances: {e}")
        return []

def discover_rds_instances(config: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Discover RDS database instances"""
    try:
        rds = get_aws_client('rds', config)
        response = rds.describe_db_instances()
        
        databases = []
        if 'DBInstances' in response:
            # Filter for available instances only
            active_dbs = [db for db in response['DBInstances'] if db.get('DBInstanceStatus') == 'available']
            for db in active_dbs:
                databases.append({
                    "id": db.get('DBInstanceIdentifier'),
                    "engine": db.get('Engine'),
                    "status": db.get('DBInstanceStatus'),
                    "endpoint": db.get('Endpoint', {}).get('Address'),
                    "ip": db.get('Endpoint', {}).get('Address'), # Aligning key name for UI
                    "port": db.get('Endpoint', {}).get('Port'),
                    "name": db.get('DBName') or db.get('DBInstanceIdentifier'),
                    "master_id": db.get('ReadReplicaSourceDBInstanceIdentifier')
                })
        return databases
    except Exception as e:
        logger.error(f"Error discovering RDS instances: {e}")
        return []

def discover_ecs_services(config: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Discover ECS services and their associated load balancers"""
    try:
        ecs = get_aws_client('ecs', config)
        clusters = ecs.list_clusters().get('clusterArns', [])
        region = config.get('region', 'ap-south-1')
        
        services = []
        for cluster_arn in clusters:
            cluster_name = cluster_arn.split('/')[-1]
            service_arns = ecs.list_services(cluster=cluster_arn).get('serviceArns', [])
            
            if service_arns:
                response = ecs.describe_services(cluster=cluster_arn, services=service_arns)
                for svc in response.get('services', []):
                    # FETCH LOAD BALANCER ARNs (LAMA V2.0 PRO)
                    alb_arn = None
                    nlb_arn = None
                    tg_arn = None
                    lb_dns = None
                    lb_name = None
                    lb_list = svc.get('loadBalancers', [])
                    if lb_list:
                        tg_arn = lb_list[0].get('targetGroupArn')
                        # Attempt to find the ALB/NLB ARN that owns this Target Group
                        if tg_arn:
                            try:
                                elbv2 = get_aws_client('elbv2', config)
                                tg_desc = elbv2.describe_target_groups(TargetGroupArns=[tg_arn])
                                if tg_desc['TargetGroups'] and tg_desc['TargetGroups'][0].get('LoadBalancerArns'):
                                    lb_arn = tg_desc['TargetGroups'][0]['LoadBalancerArns'][0]
                                    
                                    # NEW: Fetch LB DNS and Name for UI visibility
                                    lb_desc = elbv2.describe_load_balancers(LoadBalancerArns=[lb_arn])
                                    if lb_desc['LoadBalancers']:
                                        lb_info = lb_desc['LoadBalancers'][0]
                                        lb_dns = lb_info.get('DNSName')
                                        lb_name = lb_info.get('LoadBalancerName')

                                    if ":loadbalancer/net/" in lb_arn:
                                        nlb_arn = lb_arn
                                    else:
                                        alb_arn = lb_arn
                            except: pass
                    
                    # FETCH DYNAMIC TASK DNS (Mimir format)
                    task_dns = "Pending Discovery"
                    try:
                        tasks_resp = ecs.list_tasks(cluster=cluster_arn, serviceName=svc['serviceName'], desiredStatus='RUNNING')
                        task_arns = tasks_resp.get('taskArns', [])
                        if task_arns:
                            task_desc = ecs.describe_tasks(cluster=cluster_arn, tasks=[task_arns[0]])
                            task = task_desc['tasks'][0]
                            for attachment in task.get('attachments', []):
                                if attachment.get('type') == 'ElasticNetworkInterface':
                                    for detail in attachment.get('details', []):
                                        if detail.get('name') == 'privateIPv4Address':
                                            ip = detail.get('value')
                                            task_dns = f"ip-{ip.replace('.', '-')}.{region}.compute.internal"
                                            break
                    except: pass
                    
                    services.append({
                        "id": svc['serviceArn'],
                        "name": f"{cluster_name}/{svc['serviceName']}",
                        "serviceName": svc['serviceName'],
                        "clusterName": cluster_name,
                        "ip": lb_dns or task_dns, # Use LB DNS if available, else Task DNS
                        "targetGroupArn": tg_arn,
                        "albArn": alb_arn,
                        "nlbArn": nlb_arn,
                        "lbName": lb_name,
                        "status": svc['status']
                    })
        return services
    except Exception as e:
        logger.error(f"Error discovering ECS services: {e}")
        return []

def get_all_discovered_resources(config: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
    """
    Unified Discovery: Returns all available resources for review
    without saving them to the database.
    """
    return {
        "ec2": discover_ec2_instances(config),
        "rds": discover_rds_instances(config),
        "ecs": discover_ecs_services(config)
    }

def sync_aws_resources(source_id: int, config: Dict[str, Any], environment: str, selected_ids: Dict[str, List[str]] = None, config_override: Dict[str, Any] = None):
    """
    Sync selected AWS resources to LAMA database.
    If selected_ids is None, syncs everything (Legacy behavior).
    selected_ids format: {"ec2": ["i-123"], "rds": ["db-456"], "ecs": ["cluster/svc"]}
    """
    logger.info(f"Starting AWS resource sync for source {source_id} ({environment})")
    
    # Get source name for prefixing
    source_name = "AWS"
    with engine.connect() as conn:
        source_res = conn.execute(select(metric_sources_table.c.name).where(metric_sources_table.c.id == source_id)).fetchone()
        if source_res:
            source_name = source_res[0]
            
    name_prefix = f"[{source_name}] "
    
    # Apply global overrides to the base config
    base_ms_config = config.copy()
    if config_override:
        base_ms_config.update(config_override)
    
    # 1. Process EC2
    ec2_instances = discover_ec2_instances(config)
    
    with engine.connect() as conn:
        # LAMA V1.3: Filter out ignored resources
        ignore_q = select(aws_ignore_list_table.c.external_id).where(aws_ignore_list_table.c.resource_type == 'ec2')
        ignored_ids = [r[0] for r in conn.execute(ignore_q).fetchall()]
        ec2_instances = [inst for inst in ec2_instances if inst['id'] not in ignored_ids]

    if selected_ids and "ec2" in selected_ids:
        ec2_instances = [i for i in ec2_instances if i['id'] in selected_ids["ec2"]]
    
    with engine.begin() as conn:
        for inst in ec2_instances:
            check_query = select(server_status_table.c.id).where(
                (server_status_table.c.external_id == inst['id'])
            )
            existing_s = conn.execute(check_query).fetchone()
            
            raw_display_name = inst['name'] if inst['name'] else inst['id']
            display_name = f"{name_prefix}{raw_display_name}"
            
            if not existing_s:
                logger.info(f"Creating new server_status entry for EC2: {display_name}")
                res = conn.execute(insert(server_status_table).values(
                    name=display_name, ip=inst['ip'], environment=environment,
                    status='online', os_type='Linux', location_id=3, 
                    external_id=inst['id'], source_id=source_id,
                    created_at=datetime.now(timezone.utc), last_seen=datetime.now(timezone.utc)
                ))
                server_id = res.inserted_primary_key[0]
                conn.execute(insert(lama_exchange_server_selection_table).values(
                    environment=environment, server_id=server_id, enabled=True, metric_source='aws'
                ))
            else:
                server_id = existing_s[0]
                logger.info(f"Updating existing server_status entry {server_id} for EC2: {display_name}")
                conn.execute(update(server_status_table).where(
                    server_status_table.c.id == server_id
                ).values(name=display_name, ip=inst['ip'], location_id=3, external_id=inst['id'], source_id=source_id, status='online', last_seen=datetime.now(timezone.utc)))

    # 2. Discover RDS
    rds_instances = discover_rds_instances(config)
    
    with engine.connect() as conn:
        # LAMA V1.3: Filter out ignored resources
        ignore_q = select(aws_ignore_list_table.c.external_id).where(aws_ignore_list_table.c.resource_type == 'rds')
        ignored_ids = [r[0] for r in conn.execute(ignore_q).fetchall()]
        rds_instances = [db for db in rds_instances if db['id'] not in ignored_ids]

    if selected_ids and "rds" in selected_ids:
        rds_instances = [db for db in rds_instances if db['id'] in selected_ids["rds"]]
    logger.info(f"Discovered {len(rds_instances)} RDS instances")
    
    with engine.begin() as conn:
        for db in rds_instances:
            check_s = select(database_status_table.c.id).where(
                (database_status_table.c.external_id == db['id'])
            )
            existing_s = conn.execute(check_s).fetchone()
            
            display_name = f"{name_prefix}{db['id']}"
            # DETECT REPLICA: Use metadata (master_id exists) or name pattern
            is_rep = True if db.get('master_id') or 'replica' in db['id'].lower() else False
            
            if not existing_s:
                logger.info(f"Creating new database_status entry for RDS: {display_name} (Replica={is_rep})")
                res = conn.execute(insert(database_status_table).values(
                    name=display_name, engine=db['engine'], environment=environment,
                    status='online', location_id=3, source_id=source_id,
                    external_id=db['id'], created_at=datetime.now(timezone.utc), last_seen=datetime.now(timezone.utc)
                ))
                
                # AUTOMATION: Also add to database_config so it shows up in Database Config UI
                conn.execute(insert(database_config_table).values(
                    host=db['endpoint'],
                    port=db['port'],
                    database=db['name'],
                    username='aws_managed',
                    password='N/A',
                    db_type='postgresql' if 'postgres' in db['engine'] else 'mysql',
                    environment=environment,
                    enabled=True,
                    is_replication=is_rep
                ))
            else:
                db_id = existing_s[0]
                logger.info(f"Updating existing database_status entry {db_id} for RDS: {display_name}")
                conn.execute(update(database_status_table).where(
                    database_status_table.c.id == db_id
                ).values(name=display_name, location_id=3, external_id=db['id'], source_id=source_id, engine=db['engine'], status='online', last_seen=datetime.now(timezone.utc)))
                
                # Update config to sync is_replication
                conn.execute(update(database_config_table).where(
                    database_config_table.c.host == db['endpoint']
                ).values(is_replication=is_rep))

    # 3. Discover ECS
    ecs_services = discover_ecs_services(config)
    
    with engine.connect() as conn:
        # LAMA V1.3: Filter out ignored resources
        ignore_q = select(aws_ignore_list_table.c.external_id).where(aws_ignore_list_table.c.resource_type == 'ecs')
        ignored_ids = [r[0] for r in conn.execute(ignore_q).fetchall()]
        ecs_services = [svc for svc in ecs_services if svc['id'] not in ignored_ids]

    if selected_ids and "ecs" in selected_ids:
        ecs_services = [s for s in ecs_services if s['id'] in selected_ids["ecs"]]
    logger.info(f"Discovered {len(ecs_services)} ECS services")
    
    with engine.begin() as conn:
        for svc in ecs_services:
            # ENHANCED DISPLAY NAME: Add ALB/NLB info to the service name
            base_name = svc['name']
            service_name = svc['serviceName']
            lb_info = ""
            if svc.get('lbName'):
                lb_type = "NLB" if svc.get('nlbArn') else "ALB"
                lb_info = f" ({lb_type}: {svc['lbName']})"
            
            # LAMA V1.3: Check if a surgical metric_source exists for this service
            # If it does, we MUST use that name to prevent dashboard duplicates
            check_surgical = conn.execute(select(metric_sources_table.c.name).where(
                (metric_sources_table.c.name == service_name) |
                (metric_sources_table.c.config.op('->>')('service') == service_name),
                metric_sources_table.c.environment == environment,
                metric_sources_table.c.type == 'ecs'
            )).fetchone()

            if check_surgical:
                display_name = check_surgical[0]
                logger.info(f"Using surgical name for ECS status: {display_name}")
            else:
                display_name = f"{name_prefix}{base_name}{lb_info}"
            
            logger.info(f"Processing ECS service: {display_name} (ID: {svc['id']})")
            check_s = select(application_status_table.c.id).where(
                (application_status_table.c.external_id == svc['id']) |
                (application_status_table.c.name == display_name)
            )
            existing_s = conn.execute(check_s).fetchone()
            if not existing_s:
                logger.info(f"Creating new application_status entry for ECS: {display_name}")
                res = conn.execute(insert(application_status_table).values(
                    name=display_name, environment=environment,
                    status='online', location_id=3, source_id=source_id,
                    external_id=svc['id'], # Primary ID is ARN
                    ip=svc.get('ip'), # Sync the dynamic DNS ID
                    cpu=0, memory=0, # Placeholders
                    created_at=datetime.now(timezone.utc), last_seen=datetime.now(timezone.utc)
                ))
                app_id = res.inserted_primary_key[0]
                # Note: Skip lama_exchange_server_selection for ECS - FK requires server_status.id
                # ECS targets are tracked via metric_sources table instead
            else:
                app_id = existing_s[0]
                logger.info(f"Updating existing application_status entry {app_id} for ECS: {display_name}")
                conn.execute(update(application_status_table).where(
                    application_status_table.c.id == app_id
                ).values(name=display_name, location_id=3, external_id=svc['id'], source_id=source_id, 
                         ip=svc.get('ip'), # Update the IP to the latest DNS ID
                         status='online', last_seen=datetime.now(timezone.utc)))

            # LAMA V1.3: Add to Application Metrics Tab
            # Check for existing metric source using the prefixed name or service name
            prefixed_ms_name = f"{name_prefix}{svc['serviceName']}"
            check_ms = select(metric_sources_table.c.id).where(
                (metric_sources_table.c.name == prefixed_ms_name) | 
                (metric_sources_table.c.name == svc['serviceName']),
                metric_sources_table.c.environment == environment
            )
            existing_ms = conn.execute(check_ms).fetchone()
            
            if not existing_ms:
                ms_config = base_ms_config.copy()
                ms_config['type'] = 'ecs'
                ms_config['cluster'] = svc['clusterName']
                ms_config['service'] = svc['serviceName']
                ms_config['targetGroupArn'] = svc.get('targetGroupArn')
                ms_config['albArn'] = svc.get('albArn')
                ms_config['nlbArn'] = svc.get('nlbArn')
                
                res_ms = conn.execute(insert(metric_sources_table).values(
                    name=prefixed_ms_name, type='ecs', config=ms_config,
                    environment=environment, enabled=True, location_id=3,
                    created_at=datetime.now(timezone.utc)
                ))
                ms_id = res_ms.inserted_primary_key[0]
                
                # Add standard queries (V2.0 PRO Update: Use correct LB namespaces)
                standard_queries = []
                if svc.get('albArn'):
                    alb_dim = "/".join(svc['albArn'].split("/")[-3:])
                    tg_dim = "/".join(svc['targetGroupArn'].split("/")[-2:]) if svc.get('targetGroupArn') else None
                    
                    standard_queries.append(("throughput", {"Namespace": "AWS/ApplicationELB", "MetricName": "RequestCount", "Dimensions": [{"Name": "LoadBalancer", "Value": alb_dim}, {"Name": "TargetGroup", "Value": tg_dim}] if tg_dim else [{"Name": "LoadBalancer", "Value": alb_dim}], "Period": 300, "Stat": "Sum"}))
                    if tg_dim:
                        standard_queries.append(("latency", {"Namespace": "AWS/ApplicationELB", "MetricName": "TargetResponseTime", "Dimensions": [{"Name": "LoadBalancer", "Value": alb_dim}, {"Name": "TargetGroup", "Value": tg_dim}], "Period": 300, "Stat": "Average"}))
                elif svc.get('nlbArn'):
                    nlb_dim = "/".join(svc['nlbArn'].split("/")[-3:])
                    standard_queries.append(("throughput", {"Namespace": "AWS/NetworkELB", "MetricName": "NewFlowCount", "Dimensions": [{"Name": "LoadBalancer", "Value": nlb_dim}], "Period": 300, "Stat": "Sum"}))
                
                for q_name, q_payload in standard_queries:
                    conn.execute(insert(metric_queries_table).values(
                        source_id=ms_id, metric_name=q_name, query_payload=json.dumps(q_payload),
                        value_field="Average" if q_name == "latency" else "Sum", enabled=True
                    ))
            else:
                ms_id = existing_ms[0]
                # UPDATE config with latest LB ARNs
                ms_config = base_ms_config.copy()
                ms_config['type'] = 'ecs'
                ms_config['cluster'] = svc['clusterName']
                ms_config['service'] = svc['serviceName']
                ms_config['targetGroupArn'] = svc.get('targetGroupArn')
                ms_config['albArn'] = svc.get('albArn')
                ms_config['nlbArn'] = svc.get('nlbArn')
                
                conn.execute(update(metric_sources_table).where(
                    metric_sources_table.c.id == ms_id
                ).values(name=prefixed_ms_name, config=ms_config, location_id=3))

                # REFRESH QUERIES: Delete old ones and insert correct ones
                conn.execute(text("DELETE FROM metric_queries WHERE source_id = :sid"), {"sid": ms_id})
                
                standard_queries = []
                if svc.get('albArn'):
                    alb_dim = "/".join(svc['albArn'].split("/")[-3:])
                    tg_dim = "/".join(svc['targetGroupArn'].split("/")[-2:]) if svc.get('targetGroupArn') else None
                    standard_queries.append(("throughput", {"Namespace": "AWS/ApplicationELB", "MetricName": "RequestCount", "Dimensions": [{"Name": "LoadBalancer", "Value": alb_dim}, {"Name": "TargetGroup", "Value": tg_dim}] if tg_dim else [{"Name": "LoadBalancer", "Value": alb_dim}], "Period": 300, "Stat": "Sum"}))
                    if tg_dim:
                        standard_queries.append(("latency", {"Namespace": "AWS/ApplicationELB", "MetricName": "TargetResponseTime", "Dimensions": [{"Name": "LoadBalancer", "Value": alb_dim}, {"Name": "TargetGroup", "Value": tg_dim}], "Period": 300, "Stat": "Average"}))
                elif svc.get('nlbArn'):
                    nlb_dim = "/".join(svc['nlbArn'].split("/")[-3:])
                    standard_queries.append(("throughput", {"Namespace": "AWS/NetworkELB", "MetricName": "NewFlowCount", "Dimensions": [{"Name": "LoadBalancer", "Value": nlb_dim}], "Period": 300, "Stat": "Sum"}))
                
                for q_name, q_payload in standard_queries:
                    conn.execute(insert(metric_queries_table).values(
                        source_id=ms_id, metric_name=q_name, query_payload=json.dumps(q_payload),
                        value_field="Average" if q_name == "latency" else "Sum", enabled=True
                    ))
    
    logger.info(f"AWS resource sync completed for source {source_id}")
