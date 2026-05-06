"""
Metric Sources Routes
CRUD operations for managing generic data sources and their queries.
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from sqlalchemy import select, delete, update, text
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta, timezone
import httpx
import logging
import time
from app.db.db import (
    get_db, engine, metric_sources_table, metric_queries_table, 
    server_status_table, application_status_table, database_status_table,
    lama_exchange_server_selection_table
)
from app.utils.permissions import require_role
from app.utils.aes_encryption import encrypt_password
from app.connectors.prometheus import PrometheusConnector
import ipaddress

logger = logging.getLogger(__name__)
router = APIRouter(tags=["metric-sources"])

def _is_ip_address(s: str) -> bool:
    """Checks if the given string is a valid IP address."""
    try:
        ipaddress.ip_address(s)
        return True
    except ValueError:
        return False

# --- Pydantic Models ---

class TargetDiscoveryRequest(BaseModel):
    url: str
    use_iam: bool = False
    role_arn: Optional[str] = None
    region: Optional[str] = 'ap-south-1'
    account_filter: Optional[List[str]] = None  # Filter by account IDs e.g. ["396913716058"]

class ServerOnboardItem(BaseModel):
    name: str
    ip: str
    environment: str
    metric_source: Optional[str] = "auto"
    detected_os: Optional[str] = "Linux"
    os_name: Optional[str] = None
    detected_apps: Optional[List[str]] = []
    source_id: Optional[int] = None
    location_id: Optional[int] = 1
    resource_type: Optional[str] = "server"  # server, ec2, ecs, rds
    account_id: Optional[str] = None
    ecs_cluster: Optional[str] = None
    ecs_service: Optional[str] = None
    send_hardware_metrics: Optional[bool] = True
    send_network_metrics: Optional[bool] = True
    send_application_metrics: Optional[bool] = False
    send_database_metrics: Optional[bool] = False

class OnboardDiscoveredRequest(BaseModel):
    servers: List[ServerOnboardItem]
    metric_source: Optional[str] = "auto"
    source_id: Optional[int] = None
    location_id: Optional[int] = 1

@router.post("/discover-targets")
async def discover_targets(data: TargetDiscoveryRequest, request: Request):
    """Query a Prometheus URL to discover active targets"""
    require_role(request, ['admin'])
    
    url = data.url.rstrip('/')

    # Get auth headers if needed
    auth_headers = {}
    if data.use_iam:
        connector = PrometheusConnector({
            "url": url,
            "use_iam": data.use_iam,
            "role_arn": data.role_arn,
            "region": data.region
        })
        auth_headers = connector._get_auth_headers()

    async def try_get_targets(base_url):
        # LAMA V2.0 Robust Discovery: Use 6-hour lookback on metadata to catch intermittent cloud targets
        now = int(time.time())
        start = now - (6 * 3600)
        api_url = f"{base_url}/api/v1/series?match[]={{__name__=~'.*'}}&start={start}"
        query_url = f"{base_url}/api/v1/query?query=up"

        async with httpx.AsyncClient(timeout=20.0) as client:
            # 1. Try Metadata Series API (Primary - best for all accounts/intermittent targets)
            try:
                resp = await client.get(api_url, headers=auth_headers)
                if resp.status_code == 200:
                    series = resp.json().get('data', [])
                    if series:
                        targets = []
                        seen_inst = set()
                        for s in series:
                            inst = s.get('instance') or s.get('__address__')
                            if not inst or inst in seen_inst: continue
                            seen_inst.add(inst)
                            targets.append({
                                'labels': s,
                                'discoveredLabels': {'__address__': inst},
                                'health': 'unknown' # Series API doesn't have live health
                            })
                        return targets, True
            except Exception as e:
                logger.debug(f"Series API discovery failed: {e}")

            # 2. Try 'up' Query Fallback
            try:
                resp = await client.get(query_url, headers=auth_headers)
                if resp.status_code == 200:
                    q_data = resp.json()
                    targets = []
                    for r in q_data.get('data', {}).get('result', []):
                        metric = r.get('metric', {})
                        instance = metric.get('instance')
                        if instance:
                            targets.append({
                                'labels': metric,
                                'discoveredLabels': {'__address__': instance},
                                'health': 'up' if float(r.get('value', [0, 0])[1]) > 0 else 'down'
                            })
                    if targets:
                        return targets, True
            except Exception as e:
                logger.debug(f"'up' query fallback failed: {e}")

        return [], False

    try:
        # Try original URL
        active_targets, success = await try_get_targets(url)

        # If failed and /prometheus not in URL, try appending it
        if not success and '/prometheus' not in url:
            logger.info(f"Retrying with /prometheus prefix for {url}")
            active_targets, success = await try_get_targets(f"{url}/prometheus")
            if success:
                url = f"{url}/prometheus" # Update base URL for subsequent hostname queries

        if not success:
            raise HTTPException(status_code=404, detail="Could not find Prometheus/Mimir API at provided URL (tried with and without /prometheus prefix)")

        # --- STEP 1: Build account_id -> account_name map from configured CloudWatch sources ---
        account_name_map = {}  # account_id -> source name
        cluster_account_map = {}  # ecs_cluster_name -> account_id
        try:
            with engine.connect() as conn:
                cw_sources = conn.execute(select(metric_sources_table).where(
                    metric_sources_table.c.type.in_(['cloudwatch', 'aws'])
                )).fetchall()
                for src in cw_sources:
                    src_dict = dict(src._mapping)
                    role_arn = (src_dict.get('config') or {}).get('role_arn', '')
                    # Extract account ID from ARN: arn:aws:iam::ACCOUNT_ID:role/...
                    if role_arn:
                        arn_parts = role_arn.split(':')
                        acc_id = next((p for p in arn_parts if p.isdigit() and len(p) == 12), None)
                        if acc_id:
                            account_name_map[acc_id] = src_dict['name']
        except Exception as e:
            logger.warning(f"Failed to load account name map: {e}")

        # --- STEP 2: Build resource -> account_id map from all available AWS metadata ---
        resource_account_map = {} # {resource_name: account_id}
        async with httpx.AsyncClient(timeout=20.0) as client:
            try:
                meta_query = '{__name__=~"aws_(ecs|applicationelb|rds|ec2)_.*", account_id!=""}'
                start_time = int(datetime.utcnow().timestamp() - 21600)
                resp_meta = await client.get(f"{url}/api/v1/series", params={"match[]": meta_query, "start": start_time}, headers=auth_headers)
                if resp_meta.status_code == 200:
                    for s in resp_meta.json().get('data', []):
                        acc_id = s.get('account_id')
                        if not acc_id: continue
                        for key in ['ecs_cluster_name', 'ecs_service_name', 'dimension_ServiceName', 'dimension_ClusterName', 'db_instance_identifier', 'instance_id']:
                            val = s.get(key)
                            if val: resource_account_map[val] = acc_id
            except Exception as e:
                logger.warning(f"Failed to build resource-account map: {e}")

        # --- STEP 3: Map Instances to Hostnames via additional queries ---
        hostname_map = {}
        os_name_map = {}
        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                # Query node_uname_info (Linux)
                resp_linux = await client.get(f"{url}/api/v1/query?query=node_uname_info", headers=auth_headers)
                if resp_linux.status_code == 200:
                    for r in resp_linux.json().get('data', {}).get('result', []):
                        inst = r['metric'].get('instance')
                        nodename = r['metric'].get('nodename')
                        if inst and nodename:
                            hostname_map[inst] = nodename
                            if ':' in inst:
                                hostname_map[inst.split(':')[0]] = nodename

                # Query node_os_info (Linux OS Name)
                resp_linux_os = await client.get(f"{url}/api/v1/query?query=node_os_info", headers=auth_headers)
                if resp_linux_os.status_code == 200:
                    for r in resp_linux_os.json().get('data', {}).get('result', []):
                        inst = r['metric'].get('instance')
                        os_name = r['metric'].get('pretty_name') or r['metric'].get('name')
                        if inst and os_name:
                            os_name_map[inst] = os_name
                            if ':' in inst:
                                os_name_map[inst.split(':')[0]] = os_name

                # Query windows_cs_hostname (Windows)
                resp_win = await client.get(f"{url}/api/v1/query?query=windows_cs_hostname", headers=auth_headers)
                if resp_win.status_code == 200:
                    for r in resp_win.json().get('data', {}).get('result', []):
                        inst = r['metric'].get('instance')
                        hostname = r['metric'].get('hostname') or r['metric'].get('fqdn')
                        if inst and hostname:
                            hostname_map[inst] = hostname
                            if ':' in inst:
                                hostname_map[inst.split(':')[0]] = hostname

                # Fallback: Query windows_os_info for job names if hostname missing OR generic
                resp_win_os = await client.get(f"{url}/api/v1/query?query=windows_os_info", headers=auth_headers)
                if resp_win_os.status_code == 200:
                     for r in resp_win_os.json().get('data', {}).get('result', []):
                        inst = r['metric'].get('instance')
                        job_name = r['metric'].get('job')
                        prod_name = r['metric'].get('product') # OS Name
                        if inst and prod_name:
                             os_name_map[inst] = prod_name
                             if ':' in inst:
                                 os_name_map[inst.split(':')[0]] = prod_name

                        if inst and job_name:
                             ip = inst.split(':')[0]
                             current_name_for_inst = hostname_map.get(inst)
                             current_name_for_ip = hostname_map.get(ip)
                             if (not current_name_for_inst or _is_ip_address(current_name_for_inst)) and job_name.lower() != 'unknown':
                                 hostname_map[inst] = job_name
                             if (not current_name_for_ip or _is_ip_address(current_name_for_ip)) and ip and job_name.lower() != 'unknown':
                                 hostname_map[ip] = job_name
            except Exception as e:
                print(f"Warning: Failed to fetch hostname mappings: {e}")

        # --- STEP 4: Build discovered list with account info ---
        discovered = []
        seen = set()
        account_filter_set = set(data.account_filter) if data.account_filter else None

        for t in active_targets:
            instance = t.get('discoveredLabels', {}).get('__address__')
            if not instance:
                instance = t.get('labels', {}).get('instance')
            
            if instance and instance not in seen:
                seen.add(instance)
                labels = t.get('labels', {})
                ip = instance.split(':')[0]
                job = labels.get('job', 'unknown').lower()
                
                # --- Resolve account_id ---
                account_id = labels.get('account_id') or labels.get('aws_account_id') or labels.get('account')
                if not account_id:
                    ecs_service = labels.get('ecs_service_name') or labels.get('service_name')
                    ecs_cluster = labels.get('ecs_cluster_name') or labels.get('cluster_name') or labels.get('cluster')
                    inst_id = labels.get('instance_id')
                    account_id = (resource_account_map.get(ecs_service) or resource_account_map.get(ecs_cluster) or resource_account_map.get(inst_id) or '')
                if not account_id:
                    account_id = labels.get('dimension_LinkedAccount') or ''
                
                account_name = account_name_map.get(account_id, '')

                # --- Apply account filter ---
                if account_filter_set and account_id not in account_filter_set:
                    continue

                # --- Detect resource type ---
                ecs_service = labels.get('ecs_service_name', '')
                ecs_cluster = labels.get('ecs_cluster_name', '')
                if ecs_service or ecs_cluster:
                    resource_type = 'ecs'
                elif account_id:
                    resource_type = 'ec2'
                else:
                    resource_type = 'server'

                # Intelligent OS/App Detection
                detected_os = "Linux"
                detected_apps = []
                
                if 'windows' in job or ':9182' in instance:
                    detected_os = "Windows"
                elif 'node' in job or 'linux' in job or ':9100' in instance:
                    detected_os = "Linux"
                    
                if 'postgres' in job or ':9187' in instance:
                    detected_apps.append("postgres")
                if 'mysql' in job or ':9104' in instance:
                    detected_apps.append("mysql")
                if 'mssql' in job:
                    detected_apps.append("mssql")
                if 'redis' in job or ':9121' in instance:
                    detected_apps.append("redis")
                if 'mongo' in job or ':9216' in instance:
                    detected_apps.append("mongodb")
                if 'elastic' in job or ':9114' in instance:
                    detected_apps.append("elasticsearch")
                if 'clickhouse' in job or ':9116' in instance:
                    detected_apps.append("clickhouse")
                if 'kafka' in job or ':9308' in instance:
                    detected_apps.append("kafka")
                if 'rabbit' in job or ':9419' in instance:
                    detected_apps.append("rabbitmq")
                if 'nginx' in job or ':9113' in instance:
                    detected_apps.append("nginx")
                
                # Build display name: prefer ECS service name, then hostname, then instance
                display_name = ecs_service or hostname_map.get(instance) or hostname_map.get(ip) or instance
                detected_os_name = os_name_map.get(instance) or os_name_map.get(ip)
                    
                discovered.append({
                    "instance": instance,
                    "name": display_name,
                    "ip": ip,
                    "job": job,
                    "health": t.get('health', 'unknown'),
                    "detected_os": detected_os,
                    "os_name": detected_os_name,
                    "detected_apps": detected_apps,
                    "account_id": account_id,
                    "account_name": account_name,
                    "resource_type": resource_type,
                    "ecs_cluster": ecs_cluster,
                    "ecs_service": ecs_service,
                })

        # --- STEP 5: Append RDS targets from YACE (not in `up` metric) ---
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                # Use 6-hour lookback for RDS info to catch sparse YACE metrics
                start_time = int(datetime.utcnow().timestamp() - 21600)
                resp_rds = await client.get(f"{url}/api/v1/series", params={"match[]": '{__name__="aws_rds_info"}', "start": start_time}, headers=auth_headers)
                if resp_rds.status_code == 200:
                    for m in resp_rds.json().get('data', []):
                        arn = m.get('name', '')
                        parts = arn.split(':')
                        if len(parts) < 6:
                            continue
                        acc_id = parts[4]
                        db_id = parts[-1].split('/')[-1] if '/' in parts[-1] else parts[-1]

                        if account_filter_set and acc_id not in account_filter_set:
                            continue

                        if db_id in seen:
                            continue
                        seen.add(db_id)

                        is_replica = 'replica' in db_id.lower()
                        discovered.append({
                            "instance": db_id,
                            "name": db_id,
                            "ip": db_id,
                            "job": "yace/rds",
                            "health": "up",
                            "detected_os": "AWS RDS",
                            "os_name": m.get('tag_project_name', ''),
                            "detected_apps": ["rds-replica" if is_replica else "rds"],
                            "account_id": acc_id,
                            "account_name": account_name_map.get(acc_id, ''),
                            "resource_type": "rds",
                            "ecs_cluster": "",
                            "ecs_service": "",
                        })
        except Exception as e:
            logger.warning(f"Failed to discover RDS from YACE: {e}")

        # Build account summary for UI
        account_summary = {}
        for t in discovered:
            acc = t.get('account_id', '')
            if acc:
                if acc not in account_summary:
                    account_summary[acc] = {"name": t.get('account_name', ''), "count": 0, "types": {}}
                account_summary[acc]["count"] += 1
                rt = t.get('resource_type', 'unknown')
                account_summary[acc]["types"][rt] = account_summary[acc]["types"].get(rt, 0) + 1

        return {
            "status": "success",
            "targets": discovered,
            "accounts": account_summary,
            "filter_applied": data.account_filter or []
        }
            
    except Exception as e:
        logger.error(f"Discovery error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to discover targets: {str(e)}")

@router.post("/onboard-discovered-servers")
def onboard_discovered_servers(data: OnboardDiscoveredRequest, request: Request):
    """Onboard multiple discovered servers/services/databases into the system"""
    require_role(request, ['admin'])
    
    import threading
    from app.utils.lgtm_provider import lgtm_provider
    from app.db.db import lama_exchange_server_selection_table, database_config_table, application_status_table, database_status_table
    from sqlalchemy import insert
    
    onboarded_count = 0
    errors = []
    batch_metric_source = data.metric_source or "auto"
    batch_location_id = data.location_id or 1
    new_server_ids = []

    try:
        for server in data.servers:
            item_metric_source = server.metric_source if server.metric_source and server.metric_source != "auto" else batch_metric_source
            item_location_id = server.location_id or batch_location_id
            item_source_id = server.source_id or data.source_id
            resource_type = server.resource_type or "server"

            try:
              with engine.begin() as conn:
                if resource_type == "ecs":
                    # --- AI-Driven ECS Placement based on metric availability ---
                    # Hardware/Network metrics → server_status (Servers/Hardware dashboard)
                    # Application metrics → application_status (Application dashboard)
                    # Both → appears on BOTH dashboards
                    svc_name = server.ecs_service or server.name
                    cluster_name = server.ecs_cluster or ""
                    has_hw = getattr(server, 'send_hardware_metrics', False) or getattr(server, 'send_network_metrics', False)
                    has_app = getattr(server, 'send_application_metrics', False)

                    # Hardware/Network → server_status (Servers page)
                    if has_hw:
                        existing_srv = conn.execute(select(server_status_table.c.id).where(
                            (server_status_table.c.name == svc_name) |
                            (server_status_table.c.ip == server.ip)
                        ).where(server_status_table.c.environment == server.environment)).fetchone()

                        if not existing_srv:
                            res = conn.execute(server_status_table.insert().values(
                                name=svc_name, ip=server.ip, environment=server.environment,
                                status='online', os_type='ECS', location_id=3,
                                source_id=item_source_id,
                                created_at=datetime.utcnow(), updated_at=datetime.utcnow()
                            ))
                            srv_id = res.inserted_primary_key[0]
                            if server.environment in ['prod', 'uat']:
                                conn.execute(insert(lama_exchange_server_selection_table).values(
                                    environment=server.environment, server_id=srv_id,
                                    enabled=True, metric_source=item_metric_source,
                                    created_at=datetime.utcnow(), updated_at=datetime.utcnow()
                                ))
                        else:
                            conn.execute(update(server_status_table).where(
                                server_status_table.c.id == existing_srv[0]
                            ).values(status='online', last_seen=datetime.utcnow(), source_id=item_source_id))

                    # Application metrics → application_status (Application page)
                    if has_app:
                        existing_app = conn.execute(select(application_status_table.c.id).where(
                            (application_status_table.c.name == svc_name) |
                            (application_status_table.c.ip == server.ip)
                        ).where(application_status_table.c.environment == server.environment)).fetchone()

                        if not existing_app:
                            conn.execute(insert(application_status_table).values(
                                name=svc_name, environment=server.environment,
                                status='online', location_id=3, source_id=item_source_id,
                                ip=server.ip, cpu=0, memory=0,
                                created_at=datetime.utcnow(), last_seen=datetime.utcnow()
                            ))
                        else:
                            conn.execute(update(application_status_table).where(
                                application_status_table.c.id == existing_app[0]
                            ).values(ip=server.ip, status='online', last_seen=datetime.utcnow(), source_id=item_source_id))

                    # Create metric_sources entry for ECS (scheduler reads from here)
                    existing_ms = conn.execute(select(metric_sources_table.c.id).where(
                        metric_sources_table.c.config.op('->>')('service') == svc_name,
                        metric_sources_table.c.environment == server.environment,
                        metric_sources_table.c.type == 'ecs'
                    )).fetchone()

                    if not existing_ms:
                        ms_config = {
                            "type": "ecs", "cluster": cluster_name, "service": svc_name,
                            "account_id": server.account_id or "",
                            "send_hardware_metrics": server.send_hardware_metrics,
                            "send_network_metrics": server.send_network_metrics,
                            "send_application_metrics": server.send_application_metrics,
                            "send_database_metrics": server.send_database_metrics,
                        }
                        conn.execute(insert(metric_sources_table).values(
                            name=svc_name, type='ecs', config=ms_config,
                            environment=server.environment, enabled=True, location_id=3,
                            created_at=datetime.utcnow()
                        ))
                    onboarded_count += 1

                elif resource_type == "rds":
                    # --- RDS → database_status + database_config ---
                    db_id = server.name
                    base_id = db_id.split('.')[0]
                    is_replica = 'replica' in db_id.lower()

                    existing_db = conn.execute(select(database_status_table.c.id).where(
                        (database_status_table.c.name == db_id) |
                        (database_status_table.c.external_id == db_id) |
                        (database_status_table.c.name == base_id) |
                        (database_status_table.c.external_id == base_id)
                    ).where(database_status_table.c.environment == server.environment)).fetchone()

                    if not existing_db:
                        existing_cfg = conn.execute(select(database_config_table.c.id).where(
                            (database_config_table.c.host == db_id) |
                            (database_config_table.c.host == base_id)
                        )).fetchone()
                        
                        if not existing_cfg:
                            res = conn.execute(insert(database_status_table).values(
                                name=db_id, engine='postgresql', environment=server.environment,
                                status='online', location_id=3, source_id=item_source_id,
                                external_id=db_id,
                                created_at=datetime.utcnow(), last_seen=datetime.utcnow()
                            ))
                            conn.execute(insert(database_config_table).values(
                                host=db_id, port=5432, database='postgres',
                                username='aws_cloudwatch_managed', password='N/A',
                                db_type='postgresql',
                                enabled=True, is_replication=is_replica
                            ))
                        else:
                            conn.execute(update(database_status_table).where(
                                (database_status_table.c.external_id == db_id) |
                                (database_status_table.c.external_id == base_id)
                            ).values(status='online', last_seen=datetime.utcnow(), source_id=item_source_id))
                    else:
                        conn.execute(update(database_status_table).where(
                            database_status_table.c.id == existing_db[0]
                        ).values(status='online', last_seen=datetime.utcnow(), source_id=item_source_id))
                    onboarded_count += 1

                else:
                    # --- EC2 / On-Prem Server → server_status ---
                    check_query = select(server_status_table.c.id).where(server_status_table.c.ip == server.ip)
                    existing = conn.execute(check_query).fetchone()

                    if existing:
                        server_id = existing[0]
                        update_vals = {"updated_at": datetime.utcnow(), "status": "online", "last_seen": datetime.utcnow()}
                        if server.os_name: update_vals["os_name"] = server.os_name
                        if item_source_id: update_vals["source_id"] = item_source_id
                        if item_location_id: update_vals["location_id"] = item_location_id
                        # Update name if current is just an IP
                        current_name = conn.execute(select(server_status_table.c.name).where(server_status_table.c.id == server_id)).scalar()
                        if current_name and (_is_ip_address(current_name.split(':')[0]) or current_name == server.ip) and not _is_ip_address(server.name.split(':')[0]):
                            update_vals["name"] = server.name
                        conn.execute(update(server_status_table).where(server_status_table.c.id == server_id).values(**update_vals))
                    else:
                        os_type = server.detected_os or 'Linux'
                        result = conn.execute(server_status_table.insert().values(
                            name=server.name, ip=server.ip, environment=server.environment,
                            status='online', os_type=os_type, os_name=server.os_name,
                            source_id=item_source_id, location_id=item_location_id,
                            created_at=datetime.utcnow(), updated_at=datetime.utcnow()
                        ))
                        server_id = result.inserted_primary_key[0]
                        new_server_ids.append((server_id, server.ip, os_type))
                        onboarded_count += 1

                    # Enable for exchange submission
                    if server.environment in ['prod', 'uat']:
                        sel_exists = conn.execute(select(lama_exchange_server_selection_table.c.id).where(
                            lama_exchange_server_selection_table.c.server_id == server_id,
                            lama_exchange_server_selection_table.c.environment == server.environment
                        )).fetchone()
                        if not sel_exists:
                            conn.execute(insert(lama_exchange_server_selection_table).values(
                                environment=server.environment, server_id=server_id,
                                enabled=True, metric_source=item_metric_source,
                                created_at=datetime.utcnow(), updated_at=datetime.utcnow()
                            ))

                    # AI: If server has application metrics, also add to application_status
                    if getattr(server, 'send_application_metrics', False):
                        existing_app = conn.execute(select(application_status_table.c.id).where(
                            (application_status_table.c.name == server.name) |
                            (application_status_table.c.ip == server.ip)
                        ).where(application_status_table.c.environment == server.environment)).fetchone()
                        if not existing_app:
                            conn.execute(insert(application_status_table).values(
                                name=server.name, environment=server.environment,
                                status='online', location_id=item_location_id, source_id=item_source_id,
                                ip=server.ip, cpu=0, memory=0,
                                created_at=datetime.utcnow(), last_seen=datetime.utcnow()
                            ))

                    # Auto-configure detected database apps
                    if server.detected_apps:
                        for app in server.detected_apps:
                            supported_dbs = {
                                'postgres': 5432, 'mysql': 3306, 'mssql': 1433,
                                'redis': 6379, 'mongodb': 27017, 'elasticsearch': 9200,
                                'clickhouse': 8123
                            }
                            if app in supported_dbs:
                                unique_key = f"{server_id}_{app}"
                                db_exists = conn.execute(select(database_config_table.c.id).where(
                                    database_config_table.c.unique_server_db == unique_key
                                )).fetchone()
                                if not db_exists:
                                    try:
                                        conn.execute(insert(database_config_table).values(
                                            server_id=server_id, db_type=app, host=server.ip,
                                            port=supported_dbs[app], database='auto_discovered',
                                            username='prometheus_exporter', password=encrypt_password('dummy'),
                                            enabled=True, created_at=datetime.utcnow(), updated_at=datetime.utcnow(),
                                            unique_server_db=unique_key
                                        ))
                                    except Exception as db_err:
                                        logger.warning(f"Failed to auto-configure {app}: {db_err}")

            except Exception as item_err:
                logger.error(f"Failed to onboard {server.name}: {item_err}")
                errors.append(f"{server.name}: {str(item_err)}")

        return {
            "status": "success",
            "message": f"Successfully onboarded {onboarded_count} resource(s).",
            "errors": errors
        }
    except Exception as e:
        logger.error(f"Error onboarding servers: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to onboard: {str(e)}")

# --- Existing Endpoints ---

class MetricSourceCreate(BaseModel):
    name: str
    type: str
    config: Dict[str, Any]
    environment: str
    enabled: bool = True
    location_id: Optional[int] = 1
    historical_precalculated: bool = False

class MetricSourceUpdate(BaseModel):
    name: Optional[str] = None
    config: Optional[Dict[str, Any]] = None
    enabled: Optional[bool] = None
    location_id: Optional[int] = None
    historical_precalculated: Optional[bool] = None

class MetricQueryCreate(BaseModel):
    source_id: int
    location_id: Optional[int] = 1
    metric_name: str
    index_name: Optional[str] = None
    query_payload: str
    value_field: Optional[str] = None
    warning_threshold: Optional[float] = None
    critical_threshold: Optional[float] = None
    enabled: bool = True

from app.utils.environment import get_active_environment

@router.get("/metric-sources")
def list_sources(environment: str = Depends(get_active_environment), request: Request = None):
    require_role(request, ['admin', 'user'])
    with engine.connect() as conn:
        query = select(metric_sources_table).where(metric_sources_table.c.environment == environment)
        results = conn.execute(query).fetchall()
        return [dict(r._mapping) for r in results]

@router.post("/metric-sources")
def create_source(source: MetricSourceCreate, request: Request):
    require_role(request, ['admin'])
    if 'password' in source.config:
        source.config['password'] = encrypt_password(source.config['password'])
    with engine.connect() as conn:
        query = metric_sources_table.insert().values(
            name=source.name, type=source.type, config=source.config,
            environment=source.environment, enabled=source.enabled, location_id=source.location_id,
            historical_precalculated=source.historical_precalculated
        ).returning(metric_sources_table)
        result = conn.execute(query).fetchone()
        conn.commit()
        try:
            from app.utils.lgtm_provider import lgtm_provider
            lgtm_provider.reload_sources()
        except Exception: pass
        return dict(result._mapping)

@router.put("/metric-sources/{source_id}")
def update_source(source_id: int, source: MetricSourceUpdate, request: Request):
    require_role(request, ['admin'])
    values = source.dict(exclude_unset=True)
    if 'config' in values and 'password' in values['config']:
        values['config']['password'] = encrypt_password(values['config']['password'])
    with engine.connect() as conn:
        query = update(metric_sources_table).where(metric_sources_table.c.id == source_id).values(**values).returning(metric_sources_table)
        result = conn.execute(query).fetchone()
        conn.commit()
        if not result: raise HTTPException(status_code=404, detail="Source not found")
        try:
            from app.utils.lgtm_provider import lgtm_provider
            lgtm_provider.reload_sources()
        except Exception: pass
        return dict(result._mapping)

@router.delete("/metric-sources/{source_id}")
def delete_source(source_id: int, request: Request):
    require_role(request, ['admin'])
    with engine.begin() as conn:
        # AUTOMATION: Clean up linked entries from status tables that point to this source
        # 1. Clean up application_status and its server selection
        apps = conn.execute(select(application_status_table.c.id).where(application_status_table.c.source_id == source_id)).fetchall()
        app_ids = [a[0] for a in apps]
        if app_ids:
            conn.execute(delete(lama_exchange_server_selection_table).where(
                (lama_exchange_server_selection_table.c.server_id.in_(app_ids)) & 
                (lama_exchange_server_selection_table.c.metric_source == 'application')
            ))
            conn.execute(delete(application_status_table).where(application_status_table.c.source_id == source_id))

        # 2. Clean up server_status and its server selection
        srvs = conn.execute(select(server_status_table.c.id).where(server_status_table.c.source_id == source_id)).fetchall()
        srv_ids = [s[0] for s in srvs]
        if srv_ids:
            conn.execute(delete(lama_exchange_server_selection_table).where(
                (lama_exchange_server_selection_table.c.server_id.in_(srv_ids)) & 
                (lama_exchange_server_selection_table.c.metric_source != 'application')
            ))
            conn.execute(delete(server_status_table).where(server_status_table.c.source_id == source_id))

        # 3. Clean up database_status
        conn.execute(delete(database_status_table).where(database_status_table.c.source_id == source_id))

        # Finally delete the source itself
        query = delete(metric_sources_table).where(metric_sources_table.c.id == source_id)
        conn.execute(query)
        
        try:
            from app.utils.lgtm_provider import lgtm_provider
            lgtm_provider.reload_sources()
        except Exception: pass
        return {"success": True}

class AWSResourceSelection(BaseModel):
    selected_ids: Optional[Dict[str, List[str]]] = None
    config_override: Optional[Dict[str, Any]] = None

@router.get("/metric-sources/{source_id}/discover-aws")
def discover_aws_resources_endpoint(source_id: int, request: Request):
    require_role(request, ['admin'])
    from app.utils.aws_discovery import get_all_discovered_resources
    with engine.connect() as conn:
        query = select(metric_sources_table).where(metric_sources_table.c.id == source_id)
        src = conn.execute(query).fetchone()
        if not src: raise HTTPException(status_code=404, detail="Source not found")
        return get_all_discovered_resources(src[3])

@router.post("/metric-sources/{source_id}/sync-aws")
def sync_aws_source(source_id: int, data: AWSResourceSelection, request: Request):
    require_role(request, ['admin'])
    from app.utils.aws_discovery import sync_aws_resources
    with engine.connect() as conn:
        query = select(metric_sources_table).where(metric_sources_table.c.id == source_id)
        src = conn.execute(query).fetchone()
        if not src: raise HTTPException(status_code=404, detail="Source not found")
        if src[2].lower() not in ['cloudwatch', 'aws']: raise HTTPException(status_code=400, detail="Only AWS sources can be synced")
        try:
            sync_aws_resources(source_id, src[3], src[4], data.selected_ids, config_override=data.config_override)
            return {"status": "success", "message": "Selected AWS resources synced successfully"}
        except Exception as e: raise HTTPException(status_code=500, detail=f"Sync failed: {str(e)}")

@router.get("/metric-sources/{source_id}/queries")
def list_queries(source_id: int, request: Request):
    require_role(request, ['admin'])
    with engine.connect() as conn:
        query = select(metric_queries_table).where(metric_queries_table.c.source_id == source_id)
        results = conn.execute(query).fetchall()
        return [dict(r._mapping) for r in results]

@router.post("/metric-queries")
def create_or_update_query(query_data: MetricQueryCreate, request: Request):
    require_role(request, ['admin'])
    with engine.connect() as conn:
        existing = conn.execute(select(metric_queries_table.c.id).where(
            metric_queries_table.c.source_id == query_data.source_id,
            metric_queries_table.c.metric_name == query_data.metric_name
        )).fetchone()
        if existing:
            query = update(metric_queries_table).where(metric_queries_table.c.id == existing[0]).values(
                index_name=query_data.index_name, query_payload=query_data.query_payload,
                value_field=query_data.value_field, warning_threshold=query_data.warning_threshold,
                critical_threshold=query_data.critical_threshold, enabled=query_data.enabled,
                updated_at=datetime.utcnow()
            ).returning(metric_queries_table)
        else:
            query = metric_queries_table.insert().values(
                source_id=query_data.source_id, metric_name=query_data.metric_name,
                index_name=query_data.index_name, query_payload=query_data.query_payload,
                value_field=query_data.value_field, warning_threshold=query_data.warning_threshold,
                critical_threshold=query_data.critical_threshold, enabled=query_data.enabled
            ).returning(metric_queries_table)
        result = conn.execute(query).fetchone()
        conn.commit()
        return dict(result._mapping)


# --- Environment Promotion ---

class PromoteRequest(BaseModel):
    target_environment: str  # 'uat' or 'prod'

@router.post("/metric-sources/promote")
def promote_all_sources(req: PromoteRequest, request: Request):
    """
    Clone ALL metric sources (+ their queries) from the opposite environment to target.
    Exchange config (lama_config) stays separate per environment — only sources are cloned.
    Existing sources in target environment are untouched; duplicates (by name) are skipped.
    """
    require_role(request, ['admin'])
    target = req.target_environment.lower()
    if target not in ('uat', 'prod'):
        raise HTTPException(status_code=400, detail="target_environment must be 'uat' or 'prod'")
    source_env = 'prod' if target == 'uat' else 'uat'

    cloned, skipped = [], []
    with engine.begin() as conn:
        # Get existing names in target to avoid duplicates
        existing = {r[0] for r in conn.execute(
            select(metric_sources_table.c.name).where(metric_sources_table.c.environment == target)
        ).fetchall()}

        sources = conn.execute(
            select(metric_sources_table).where(metric_sources_table.c.environment == source_env)
        ).fetchall()

        for src in sources:
            src_dict = dict(src._mapping)
            if src_dict['name'] in existing:
                skipped.append(src_dict['name'])
                continue

            old_id = src_dict.pop('id')
            src_dict.pop('created_at', None)
            src_dict.pop('updated_at', None)
            src_dict['environment'] = target

            new_row = conn.execute(
                metric_sources_table.insert().values(**src_dict).returning(metric_sources_table.c.id)
            ).fetchone()
            new_id = new_row[0]

            # Clone linked metric_queries
            queries = conn.execute(
                select(metric_queries_table).where(metric_queries_table.c.source_id == old_id)
            ).fetchall()
            for q in queries:
                q_dict = dict(q._mapping)
                q_dict.pop('id')
                q_dict.pop('created_at', None)
                q_dict.pop('updated_at', None)
                q_dict['source_id'] = new_id
                conn.execute(metric_queries_table.insert().values(**q_dict))

            cloned.append(src_dict['name'])

    return {"cloned": cloned, "skipped": skipped, "source": source_env, "target": target}


@router.put("/metric-sources/{source_id}/environment")
def switch_source_environment(source_id: int, req: PromoteRequest, request: Request):
    """Switch a single source to a different environment. Also moves linked status entries."""
    require_role(request, ['admin'])
    target = req.target_environment.lower()
    if target not in ('uat', 'prod'):
        raise HTTPException(status_code=400, detail="target_environment must be 'uat' or 'prod'")
    with engine.begin() as conn:
        row = conn.execute(select(metric_sources_table).where(metric_sources_table.c.id == source_id)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Source not found")
        src = dict(row._mapping)
        old_env = src['environment']
        # Move the source itself
        result = conn.execute(
            update(metric_sources_table)
            .where(metric_sources_table.c.id == source_id)
            .values(environment=target, updated_at=datetime.utcnow())
            .returning(metric_sources_table)
        ).fetchone()
        # Move linked application_status
        conn.execute(text("UPDATE application_status SET environment = :target WHERE source_id = :sid AND environment = :old"),
                     {"target": target, "sid": source_id, "old": old_env})
        # Move linked database_status
        conn.execute(text("UPDATE database_status SET environment = :target WHERE source_id = :sid AND environment = :old"),
                     {"target": target, "sid": source_id, "old": old_env})
        # Move linked server_status
        conn.execute(text("UPDATE server_status SET environment = :target WHERE source_id = :sid AND environment = :old"),
                     {"target": target, "sid": source_id, "old": old_env})
        return dict(result._mapping)


# ============================================================================
# AI METRIC PROBE — Auto-discover available metrics per target from Mimir
# ============================================================================

class ProbeTargetRequest(BaseModel):
    url: str  # Mimir URL
    target: str  # IP, hostname, service name, or DB identifier
    resource_type: Optional[str] = "server"  # server, ec2, ecs, rds
    ecs_cluster: Optional[str] = None
    ecs_service: Optional[str] = None

@router.post("/probe-target-metrics")
async def probe_target_metrics(data: ProbeTargetRequest, request: Request):
    """AI-driven metric probe: queries Mimir to discover what's available for a target"""
    require_role(request, ['admin', 'user'])

    url = data.url.rstrip("/")
    if "prometheus" not in url and "9009" in url:
        url = f"{url}/prometheus"

    target = data.target
    # Build search patterns (same logic as MimirCollector._get_patterns)
    patterns = [target]
    if "ip-" in target and "." in target:
        patterns.append(target.split('.')[0])
    import re as _re
    ip_parts = _re.findall(r'\d+', target)
    if len(ip_parts) >= 4:
        patterns.extend([".".join(ip_parts[:4]), "ip-" + "-".join(ip_parts[:4])])
    # For ECS service names, also try the service name directly
    if data.ecs_service:
        patterns.insert(0, data.ecs_service)

    labels = ["service_name", "ecs_service_name", "job", "instance", "instance_id", "nodename"]

    async def count_series(client, query):
        """Returns series count for a query, 0 if not found"""
        try:
            resp = await client.post(f"{url}/api/v1/query", data={"query": query}, timeout=8.0)
            if resp.status_code == 200:
                results = resp.json().get("data", {}).get("result", [])
                if results:
                    # For count() queries, return the count value
                    val = float(results[0].get("value", [0, 0])[1])
                    return int(val)
            return 0
        except:
            return 0

    # LAMA V1.3 metric probes — keys & descriptions from LAMA_Api_Specification_Document_V1.3.pdf + Metrics.xlsx
    # Hardware: cpu (CPU Utilization %), memory (Memory Utilization %), disk (Disk Utilization %), uptime (Uptime in minutes)
    hardware_probes = {
        "cpu": {"linux": "node_cpu_seconds_total", "windows": "windows_cpu_time_total", "lama_key": "cpu", "unit": "%"},
        "memory": {"linux": "node_memory_MemTotal_bytes", "windows": "windows_cs_physical_memory_bytes", "lama_key": "memory", "unit": "%"},
        "disk": {"linux": "node_filesystem_size_bytes", "windows": "windows_logical_disk_size_bytes", "lama_key": "disk", "unit": "%"},
        "uptime": {"linux": "node_boot_time_seconds", "windows": "windows_system_boot_time_timestamp", "lama_key": "uptime", "unit": "minutes"},
    }
    # Network: bandwidth (Bandwidth Utilization %), latency (Network Latency ms), packetCount (Packet Error Count), lookupCount (DNS Lookup Failure Count)
    network_probes = {
        "bandwidth": {"linux": "node_network_receive_bytes_total", "windows": "windows_net_bytes_total", "lama_key": "bandwidth", "unit": "%"},
        "latency": {"linux": "probe_icmp_duration_seconds", "windows": "probe_icmp_duration_seconds", "lama_key": "latency", "unit": "ms"},
        "packetCount": {"linux": "node_network_receive_errs_total", "windows": "windows_net_packets_received_errors_total", "lama_key": "packetCount", "unit": "count"},
        "lookupCount": {"linux": "probe_dns_lookup_time_seconds", "windows": "windows_dns_recursive_query_failures_total", "lama_key": "lookupCount", "unit": "count"},
    }
    # Application: throughput (Requests/Second E2E), latency (Response Time ms E2E)
    application_probes = {
        "throughput": {"metric": "http_requests_total", "alt": "application_requests_total", "lama_key": "throughput", "unit": "req/s"},
        "latency": {"metric": "http_request_duration_seconds_bucket", "alt": "http_request_duration_seconds_count", "lama_key": "latency", "unit": "ms"},
    }
    # Database: status (Replication Status 1=Up/0=Down), qSize (Replication Queue Size), bandwidth (Replication Bandwidth %), latency (Replication Latency ms)
    database_probes = {
        "status": {"metric": "aws_rds_replica_lag_average", "lama_key": "status", "unit": "bool"},
        "qSize": {"metric": "aws_rds_disk_queue_depth_average", "lama_key": "qSize", "unit": "count"},
        "bandwidth": {"metric": "aws_rds_network_receive_throughput_average", "lama_key": "bandwidth", "unit": "%"},
        "latency": {"metric": "aws_rds_replica_lag_average", "lama_key": "latency", "unit": "ms"},
    }

    result = {"hardware": {}, "network": {}, "application": {}, "database": {}}
    detected_os = "linux"

    async with httpx.AsyncClient(timeout=10.0) as client:
        # Phase 1: Find which label+pattern combo works (same as MimirCollector sequential discovery)
        active_label = None
        active_pattern = None
        for p in patterns:
            for l in labels:
                q = f'count(node_cpu_seconds_total{{{l}=~".*{p}.*"}})'
                c = await count_series(client, q)
                if c > 0:
                    active_label, active_pattern = l, p
                    detected_os = "linux"
                    break
                # Try Windows
                q_win = f'count(windows_cpu_time_total{{{l}=~".*{p}.*"}})'
                c_win = await count_series(client, q_win)
                if c_win > 0:
                    active_label, active_pattern = l, p
                    detected_os = "windows"
                    break
            if active_label:
                break

        # Phase 2: Probe each category
        pat = f".*{active_pattern}.*" if active_pattern else f".*{target}.*"
        lbl = active_label or "instance"

        # Hardware
        for key, probe in hardware_probes.items():
            metric = probe[detected_os]
            q = f'count({metric}{{{lbl}=~"{pat}"}})'
            series = await count_series(client, q)
            result["hardware"][key] = {"available": series > 0, "series": series, "metric": metric, "lama_key": probe["lama_key"], "unit": probe["unit"]}

        # Network
        for key, probe in network_probes.items():
            metric = probe[detected_os]
            q = f'count({metric}{{{lbl}=~"{pat}"}})'
            series = await count_series(client, q)
            result["network"][key] = {"available": series > 0, "series": series, "metric": metric, "lama_key": probe["lama_key"], "unit": probe["unit"]}

        # Application (uses service/job labels, not instance)
        for key, probe in application_probes.items():
            series = 0
            for m in [probe["metric"], probe.get("alt", "")]:
                if not m:
                    continue
                for al in ["service", "job", "service_name", lbl]:
                    q = f'count({m}{{{al}=~"{pat}"}})'
                    s = await count_series(client, q)
                    if s > 0:
                        series = s
                        break
                if series > 0:
                    break
            result["application"][key] = {"available": series > 0, "series": series, "metric": probe["metric"], "lama_key": probe["lama_key"], "unit": probe["unit"]}

        # Database (RDS targets — try both YACE label variants + count_over_time for staleness)
        if data.resource_type == "rds":
            for key, probe in database_probes.items():
                series = 0
                # YACE uses dimension_DBInstanceIdentifier, older configs use db_instance_identifier
                for lbl in ["dimension_DBInstanceIdentifier", "db_instance_identifier", "name"]:
                    # Use count_over_time to handle Mimir staleness (instant query returns 0 if no scrape in 5min)
                    q = f'count(count_over_time({probe["metric"]}{{{lbl}=~".*{target}.*"}}[1h]))'
                    s = await count_series(client, q)
                    if s > 0:
                        series = s
                        break
                result["database"][key] = {"available": series > 0, "series": series, "metric": probe["metric"], "lama_key": probe["lama_key"], "unit": probe["unit"]}
        else:
            result["database"] = None  # N/A for non-DB targets

        # Phase 3: Detect custom LAMA Python exporters (localhost:8000/8001/8021 style)
        # These expose pre-computed metrics like throughput_avg, latency_avg, bandwidth_avg, db_status etc.
        # Try instance label match for custom metrics
        custom_instance_pat = f".*{target}.*"
        custom_lama_probes = {
            "application": {
                "throughput": {"metrics": ["throughput_avg", "throughput_max"], "lama_key": "throughput", "unit": "req/s"},
                "latency": {"metrics": ["latency_avg", "latency_max"], "lama_key": "latency", "unit": "ms"},
                "failureTradeApi": {"metrics": ["failureTradeApi", "failuretradeapi"], "lama_key": "failureTradeApi", "unit": "count"},
                "failureAuth": {"metrics": ["failureAuthentication", "failureauthentication"], "lama_key": "failureAuthentication", "unit": "count"},
                "historicalThroughput": {"metrics": ["historicalThroughput_avg", "historicalThroughput_min"], "lama_key": "historicalThroughput", "unit": "req/s"},
                "historicalLatency": {"metrics": ["historicalLatency_avg", "historicalLatency_min"], "lama_key": "historicalLatency", "unit": "ms"},
            },
            "network": {
                "bandwidth": {"metrics": ["bandwidth_avg", "bandwidth_max"], "lama_key": "bandwidth", "unit": "%"},
                "latency": {"metrics": ["network_latency_avg", "network_latency_max"], "lama_key": "latency", "unit": "ms"},
                "packetCount": {"metrics": ["packetcount", "packetCount"], "lama_key": "packetCount", "unit": "count"},
                "lookupCount": {"metrics": ["lookupcount", "lookupCount"], "lama_key": "lookupCount", "unit": "count"},
            },
            "database": {
                "db_status": {"metrics": ["db_status"], "lama_key": "status", "unit": "bool"},
                "db_qSize": {"metrics": ["db_qsize_avg", "db_qsize_max"], "lama_key": "qSize", "unit": "count"},
                "db_latency": {"metrics": ["db_latency_avg", "db_latency_max"], "lama_key": "latency", "unit": "ms"},
                "db_bandwidth": {"metrics": ["db_bandwidth_avg", "db_bandwidth_max"], "lama_key": "bandwidth", "unit": "%"},
            },
        }
        for cat, probes_map in custom_lama_probes.items():
            for key, probe in probes_map.items():
                # Skip if standard probe already found this category+key
                existing = result.get(cat, {})
                if isinstance(existing, dict):
                    matching_key = next((k for k, v in existing.items() if v.get("available") and v.get("lama_key") == probe["lama_key"]), None)
                    if matching_key:
                        continue
                # Try each metric variant
                for m in probe["metrics"]:
                    q = f'count({m}{{instance=~"{custom_instance_pat}"}})'
                    s = await count_series(client, q)
                    if s > 0:
                        if result.get(cat) is None:
                            result[cat] = {}
                        result[cat][key] = {"available": True, "series": s, "metric": m, "lama_key": probe["lama_key"], "unit": probe["unit"], "source": "lama-exporter"}
                        break
                else:
                    # Not found via any variant
                    if result.get(cat) is None:
                        result[cat] = {}
                    if key not in (result.get(cat) or {}):
                        result[cat][key] = {"available": False, "series": 0, "metric": probe["metrics"][0], "lama_key": probe["lama_key"], "unit": probe["unit"]}

    # Build summary
    hw_available = any(v["available"] for v in result["hardware"].values()) if result["hardware"] else False
    net_available = any(v["available"] for v in result["network"].values()) if result["network"] else False
    app_available = any(v["available"] for v in result["application"].values()) if result["application"] else False
    db_available = any(v["available"] for v in result["database"].values()) if result.get("database") else False

    return {
        "target": target,
        "resource_type": data.resource_type,
        "detected_os": detected_os,
        "discovery_label": active_label,
        "discovery_pattern": active_pattern,
        "found": active_label is not None or data.resource_type == "rds",
        "categories": {
            "hardware": {"available": hw_available, "recommended": hw_available, "metrics": result["hardware"]},
            "network": {"available": net_available, "recommended": net_available, "metrics": result["network"]},
            "application": {"available": app_available, "recommended": app_available, "metrics": result["application"]},
            "database": {"available": db_available, "recommended": db_available, "metrics": result["database"]} if result.get("database") is not None else None,
        }
    }


# ============================================================================
# ALLOWED ACCOUNTS — Filter which AWS accounts' metrics are sent to LAMA
# ============================================================================

class AllowedAccountsUpdate(BaseModel):
    allowed_accounts: List[Dict[str, str]]  # [{"account_id": "396913716058", "name": "SMC-PRE-TRADING-PROD"}]

class MetricFlagsUpdate(BaseModel):
    send_hardware_metrics: Optional[bool] = None
    send_network_metrics: Optional[bool] = None
    send_application_metrics: Optional[bool] = None
    send_database_metrics: Optional[bool] = None

class QueryExplorerTargetsRequest(BaseModel):
    source_id: int

class QueryExplorerMetricsRequest(BaseModel):
    source_id: int
    target_id: str
    resource_type: str  # server, ecs, rds, ec2

class QueryExplorerRunRequest(BaseModel):
    source_id: int
    query: str
    range_minutes: Optional[int] = 60
    start_time: Optional[str] = None # ISO string
    end_time: Optional[str] = None   # ISO string

@router.put("/metric-sources/{source_id}/metric-flags")
def update_metric_flags(source_id: int, data: MetricFlagsUpdate, request: Request):
    """Update which metric categories are enabled for a source (used by schedulers)"""
    require_role(request, ['admin'])
    with engine.begin() as conn:
        row = conn.execute(select(metric_sources_table).where(metric_sources_table.c.id == source_id)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Source not found")
        config = dict(dict(row._mapping).get("config") or {})
        for field in ["send_hardware_metrics", "send_network_metrics", "send_application_metrics", "send_database_metrics"]:
            val = getattr(data, field)
            if val is not None:
                config[field] = val
        conn.execute(update(metric_sources_table).where(metric_sources_table.c.id == source_id).values(config=config, updated_at=datetime.utcnow()))
    return {"status": "ok", "config": {k: config.get(k) for k in ["send_hardware_metrics", "send_network_metrics", "send_application_metrics", "send_database_metrics"]}}

@router.get("/metric-sources/{source_id}/discover-accounts")
async def discover_accounts(source_id: int, request: Request):
    """Auto-discover AWS accounts from Mimir via YACE _info metrics and ec2-metrics job"""
    require_role(request, ['admin'])
    with engine.connect() as conn:
        row = conn.execute(select(metric_sources_table).where(metric_sources_table.c.id == source_id)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Source not found")
    src = dict(row._mapping)
    url = (src.get("config") or {}).get("url", "").rstrip("/")
    if not url:
        raise HTTPException(status_code=400, detail="Source has no URL configured")

    # Ensure /prometheus suffix for Mimir
    base_url = url
    if "prometheus" not in base_url and "9009" in base_url:
        base_url = f"{base_url}/prometheus"

    accounts = {}  # account_id -> {name, clusters[], ec2_count, ecs_count, rds_count}

    async with httpx.AsyncClient(timeout=15.0) as client:
        # 1. PRIMARY: Fetch all known account_id values from Mimir metadata
        try:
            resp_vals = await client.get(f"{base_url}/api/v1/label/account_id/values")
            if resp_vals.status_code == 200:
                for acc_id in resp_vals.json().get("data", []):
                    if acc_id:
                        accounts[acc_id] = {"account_id": acc_id, "name": f"Account {acc_id}", "clusters": [], "ecs_count": 0, "rds_count": 0, "ec2_count": 0}
        except Exception as e:
            logger.warning(f"Label values discovery failed: {e}")

        # 2. ENRICHMENT: Get counts from active targets
        try:
            target_resp = await client.get(f"{base_url}/api/v1/targets")
            if target_resp.status_code == 200:
                active_targets = target_resp.json().get("data", {}).get("activeTargets", [])
                for t in active_targets:
                    labels = t.get("labels", {})
                    acc_id = labels.get("account_id") or labels.get("aws_account_id")
                    if acc_id:
                        if acc_id not in accounts:
                            accounts[acc_id] = {"account_id": acc_id, "name": f"Account {acc_id}", "clusters": [], "ecs_count": 0, "rds_count": 0, "ec2_count": 0}
                        
                        job = labels.get("job", "").lower()
                        if "ec2" in job: accounts[acc_id]["ec2_count"] += 1
                        elif "ecs" in job: accounts[acc_id]["ecs_count"] += 1
                        
                        cluster = labels.get("ecs_cluster_name") or labels.get("cluster_name")
                        if cluster and cluster not in accounts[acc_id]["clusters"]:
                            accounts[acc_id]["clusters"].append(cluster)
        except Exception as e:
            logger.warning(f"Target enrichment failed: {e}")

    if not accounts and ("10.215.33.196" in url or src.get("location_id") in [1, 2]):
        accounts["onprem"] = {"account_id": "onprem", "name": "On-Prem Datacenter", "clusters": [], "ecs_count": 0, "rds_count": 0, "ec2_count": 1}

    # Merge with existing allowed_accounts names (preserve user-given names)
    existing = (src.get("config") or {}).get("allowed_accounts", [])
    name_map = {a["account_id"]: a.get("name", "") for a in existing if isinstance(a, dict)}
    for acc_id, info in accounts.items():
        if acc_id in name_map and name_map[acc_id]:
            info["name"] = name_map[acc_id]

    return {"accounts": sorted(accounts.values(), key=lambda x: x["account_id"])}

@router.put("/metric-sources/{source_id}/allowed-accounts")
def update_allowed_accounts(source_id: int, data: AllowedAccountsUpdate, request: Request):
    """Set which AWS accounts are allowed for metric collection from this Mimir source"""
    require_role(request, ['admin'])
    with engine.begin() as conn:
        row = conn.execute(select(metric_sources_table).where(metric_sources_table.c.id == source_id)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Source not found")
        config = dict(dict(row._mapping).get("config") or {})
        config["allowed_accounts"] = [{"account_id": a["account_id"], "name": a.get("name", "")} for a in data.allowed_accounts]
        conn.execute(update(metric_sources_table).where(metric_sources_table.c.id == source_id).values(config=config, updated_at=datetime.utcnow()))
    return {"status": "ok", "allowed_accounts": config["allowed_accounts"]}

@router.put("/metric-sources/{source_id}/historical-precalculated")
def toggle_historical_precalculated(source_id: int, request: Request):
    """Toggle the historical_precalculated flag for a source (UI toggle)."""
    require_role(request, ['admin'])
    with engine.begin() as conn:
        current = conn.execute(
            select(metric_sources_table.c.historical_precalculated)
            .where(metric_sources_table.c.id == source_id)
        ).scalar()
        if current is None:
            raise HTTPException(status_code=404, detail="Source not found")
        new_val = not bool(current)
        conn.execute(
            update(metric_sources_table)
            .where(metric_sources_table.c.id == source_id)
            .values(historical_precalculated=new_val, updated_at=datetime.utcnow())
        )
        return {"id": source_id, "historical_precalculated": new_val}

# ============================================================================
# QUERY EXPLORER — Smart No-Code PromQL Builder
# ============================================================================

@router.post("/query-explorer/targets")
async def get_query_explorer_targets(data: QueryExplorerTargetsRequest, request: Request):
    """Fetch all discoverable targets for a specific source with metadata."""
    require_role(request, ['admin', 'user'])
    
    with engine.connect() as conn:
        row = conn.execute(select(metric_sources_table).where(metric_sources_table.c.id == data.source_id)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Source not found")
    
    src = dict(row._mapping)
    config = src.get("config") or {}
    url = config.get("url", "").rstrip("/")
    if not url:
        raise HTTPException(status_code=400, detail="Source has no URL")
        
    # Use existing discovery logic internally
    discovery_data = TargetDiscoveryRequest(
        url=url,
        use_iam=config.get("use_iam", False),
        role_arn=config.get("role_arn"),
        region=config.get("region", "ap-south-1")
    )
    
    # We call our own discover_targets logic but return a simplified target list
    from fastapi import Request as _Request
    try:
        res = await discover_targets(discovery_data, request)
        targets = res.get("targets", [])
        
        # Flatten and categorize
        explorer_targets = []
        for t in targets:
            rtype = t.get("resource_type", "server")
            name = t.get("name") or t.get("instance") or t.get("ecs_service") or "Unknown"
            explorer_targets.append({
                "id": t.get("instance"),
                "name": name,
                "type": rtype,
                "account": t.get("account_name") or t.get("account_id"),
                "labels": t.get("labels", {})
            })
            
        return {"targets": sorted(explorer_targets, key=lambda x: x["name"])}
    except Exception as e:
        logger.error(f"Explorer target discovery failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/query-explorer/metrics")
async def get_query_explorer_metrics(data: QueryExplorerMetricsRequest, request: Request):
    """Fetch available metric names for a specific target/resource type."""
    require_role(request, ['admin', 'user'])
    
    with engine.connect() as conn:
        row = conn.execute(select(metric_sources_table).where(metric_sources_table.c.id == data.source_id)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Source not found")
    
    src = dict(row._mapping)
    config = src.get("config") or {}
    url = config.get("url", "").rstrip("/")
    if "prometheus" not in url and "9009" in url:
        url = f"{url}/prometheus"
        
    # Build match pattern based on type
    match_query = ""
    if data.resource_type == "rds":
        match_query = f'{{dimension_DBInstanceIdentifier=~".*{data.target_id}.*"}}'
    elif data.resource_type == "ecs":
        match_query = f'{{ecs_service_name=~".*{data.target_id}.*"}}'
    else:
        # Default instance based filtering
        match_query = f'{{instance=~".*{data.target_id}.*"}}'

    connector = PrometheusConnector(config)
    auth_headers = connector._get_auth_headers()
    
    async with httpx.AsyncClient(timeout=20.0) as client:
        # Use series API to find all metric names associated with this target
        now = int(time.time())
        start = now - 3600 # 1 hour lookback
        api_url = f"{url}/api/v1/series"
        params = {"match[]": match_query, "start": start}
        
        try:
            resp = await client.get(api_url, params=params, headers=auth_headers)
            if resp.status_code == 200:
                series = resp.json().get("data", [])
                metric_names = set()
                for s in series:
                    name = s.get("__name__")
                    if name: metric_names.add(name)
                
                return {"metrics": sorted(list(metric_names))}
            return {"metrics": []}
        except Exception as e:
            logger.error(f"Metric discovery failed: {e}")
            return {"metrics": []}

@router.post("/query-explorer/run")
async def run_query_explorer(data: QueryExplorerRunRequest, request: Request):
    """Execute a PromQL query against the source."""
    require_role(request, ['admin', 'user'])
    
    with engine.connect() as conn:
        row = conn.execute(select(metric_sources_table).where(metric_sources_table.c.id == data.source_id)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Source not found")
            
    src = dict(row._mapping)
    config = src.get("config") or {}
    url = config.get("url", "").rstrip("/")
    if "prometheus" not in url and "9009" in url:
        url = f"{url}/prometheus"
        
    connector = PrometheusConnector(config)
    auth_headers = connector._get_auth_headers()
    
    # We always use range query for the explorer to show a graph
    now_dt = datetime.now(timezone.utc)
    
    if data.start_time and data.end_time:
        try:
            start = datetime.fromisoformat(data.start_time.replace('Z', '+00:00'))
            end = datetime.fromisoformat(data.end_time.replace('Z', '+00:00'))
        except ValueError:
            # Fallback for older format
            start = now_dt - timedelta(minutes=data.range_minutes)
            end = now_dt
    else:
        end = now_dt
        start = now_dt - timedelta(minutes=data.range_minutes)
    
    params = {
        "query": data.query,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "step": "60s"
    }
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            # Try range query first
            resp = await client.get(f"{url}/api/v1/query_range", params=params, headers=auth_headers)
            if resp.status_code == 200:
                return resp.json()
                
            # Fallback to instant query if range fails (or if query is scalar)
            resp = await client.get(f"{url}/api/v1/query", params={"query": data.query}, headers=auth_headers)
            return resp.json()
        except Exception as e:
            logger.error(f"Query execution failed: {e}")
            raise HTTPException(status_code=500, detail=str(e))
