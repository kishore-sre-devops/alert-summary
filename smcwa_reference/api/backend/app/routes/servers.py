# api/backend/app/routes/servers.py
"""
Server management endpoints: CRUD operations for servers
Now based on collector data (Prometheus, AWS) instead of agents.
"""

from fastapi import APIRouter, HTTPException, Depends, Query
from starlette.requests import Request
from pydantic import BaseModel
from sqlalchemy import select, delete, update, insert, text
from sqlalchemy.orm import Session
from app.db.db import get_db, server_status_table, server_metrics_table, engine, lama_exchange_server_selection_table
from app.utils.permissions import require_admin
from app.utils.environment import get_active_environment
from datetime import datetime, timedelta
from typing import Optional, List, Dict
from app.utils.server_down_monitor import SERVER_DOWN_THRESHOLD_MINUTES
import logging
from app.utils.hot_store import get_all_servers_hot_data, get_hot_store_server_data

logger = logging.getLogger(__name__)

router = APIRouter()

def sync_server_selection_on_environment_change(server_id: int, old_environment: str, new_environment: str, conn=None):
    """
    Sync lama_exchange_server_selection table when a server's environment changes.
    """
    def _sync_with_connection(connection):
        old_selection_query = text("""
            SELECT enabled, metric_source
            FROM lama_exchange_server_selection
            WHERE server_id = :server_id AND environment = :old_env
        """)
        old_result = connection.execute(old_selection_query, {
            "server_id": server_id,
            "old_env": old_environment
        }).fetchone()
        
        enabled_status = old_result[0] if old_result else True
        metric_source = old_result[1] if old_result and old_result[1] else "auto"
        
        delete_query = text("""
            DELETE FROM lama_exchange_server_selection
            WHERE server_id = :server_id AND environment = :old_env
        """)
        connection.execute(delete_query, {
            "server_id": server_id,
            "old_env": old_environment
        })
        
        insert_query = text("""
            INSERT INTO lama_exchange_server_selection
            (environment, server_id, enabled, metric_source, created_at, updated_at)
            VALUES (:new_env, :server_id, :enabled, :metric_source, NOW(), NOW())
            ON CONFLICT ON CONSTRAINT unique_env_server DO UPDATE
            SET enabled = :enabled, metric_source = :metric_source, updated_at = NOW()
        """)
        connection.execute(insert_query, {
            "new_env": new_environment,
            "server_id": server_id,
            "enabled": enabled_status,
            "metric_source": metric_source
        })
        
        logger.info(f"Synced server selection: Server {server_id} moved from {old_environment} to {new_environment} (enabled={enabled_status}, source={metric_source})")
    
    try:
        if conn is not None:
            _sync_with_connection(conn)
        else:
            with engine.begin() as connection:
                _sync_with_connection(connection)
    except Exception as e:
        logger.error(f"Error syncing server selection for server {server_id} environment change ({old_environment} -> {new_environment}): {e}", exc_info=True)
        if conn is not None:
            raise

class ServerCreate(BaseModel):
    name: str
    ip: str
    status: str = "offline"
    environment: str = "prod"
    os_type: str = "Linux"
    location_id: Optional[int] = 1

class ServerUpdate(BaseModel):
    """Fields an admin can manually update for a server."""
    name: str = None
    ip: str = None
    public_ip: str = None
    status: str = None
    environment: str = None
    os_type: str = None
    location_id: Optional[int] = None

class ServerResponse(BaseModel):
    id: int
    name: str
    ip: str
    resource_id: Optional[str] = None
    public_ip: Optional[str] = None
    status: str
    environment: str
    os: Optional[str] = None
    os_name: Optional[str] = None
    cpu: float
    memory: float = 0.0
    memory_total_bytes: float = 0.0
    memory_used_bytes: float = 0.0
    disk: float = 0.0
    disk_total_bytes: float = 0.0
    disk_used_bytes: float = 0.0
    uptime: float = 0.0
    network_bandwidth: float = 0.0
    network_bits_per_sec: float = 0.0
    packet_count: float = 0.0
    last_seen: str = ""
    db_status: float = 0.0
    db_qsize: float = 0.0
    db_bandwidth: float = 0.0
    db_latency: float = 0.0
    location_id: Optional[int] = 1
    external_id: Optional[str] = None
    app_throughput: float = 0.0
    app_latency: float = 0.0
    app_historical_throughput: float = 0.0
    app_historical_latency: float = 0.0
    app_failure_trade_api: float = 0.0
    app_failure_authentication: float = 0.0
    is_inactive: bool = False

class PaginatedServerResponse(BaseModel):
    items: List[ServerResponse]
    total_count: int
    page: int
    size: int
    total_pages: int
    summary: Optional[Dict[str, int]] = None

@router.get("/", response_model=PaginatedServerResponse)
def list_servers(
    environment: str = Depends(get_active_environment), 
    location_id: int = Query(None),
    page: int = Query(1), 
    size: int = Query(20), 
    search: str = Query(None),
    include_databases: bool = Query(False),
    request: Request = None, 
    db: Session = Depends(get_db)
):
    """List servers with pagination and search, based on collector data."""
    if request:
        from app.utils.permissions import get_current_user
        get_current_user(request)
    
    offset = (page - 1) * size
    
    where_clauses = []
    params = {"limit": size, "offset": offset}
    
    if environment and environment in ['prod', 'uat']:
        where_clauses.append("s.environment = :env")
        params["env"] = environment

    if location_id is not None:
        where_clauses.append("s.location_id = :location_id")
        params["location_id"] = location_id
        
    if not include_databases:
        where_clauses.append("s.os_type NOT IN ('Database', 'Lambda')")
    else:
        # If including databases, still exclude internal stuff like Lambda if not needed
        where_clauses.append("s.os_type NOT IN ('Lambda')")
        
    if search:
        where_clauses.append("(s.name ILIKE :search OR s.ip ILIKE :search OR s.public_ip ILIKE :search OR s.external_id ILIKE :search)")
        params["search"] = f"%{search}%"
        
    where_sql = "WHERE " + " AND ".join(where_clauses) if where_clauses else ""
        
    count_query = text(f"SELECT COUNT(*) FROM server_status s {where_sql}")
    total_count = db.execute(count_query, params).scalar()
    
    if include_databases:
        db_where = []
        db_count_params = {"env": environment}
        if environment:
            db_where.append("d.environment = :env")
        if location_id is not None:
            db_where.append("d.location_id = :location_id")
            db_count_params["location_id"] = location_id
            
        db_where_sql = "WHERE " + " AND ".join(db_where) if db_where else ""
        db_count_query = text(f"SELECT COUNT(*) FROM database_status d {db_where_sql}")
        total_count += db.execute(db_count_query, db_count_params).scalar()
    
    all_query = text(f"""
        SELECT 
            s.id, s.name, s.ip, s.status, s.environment, s.cpu, s.memory, s.disk,
            s.last_seen, s.location_id, s.external_id, s.os_type
        FROM server_status s
        {where_sql}
    """)
    all_rows = db.execute(all_query, params).fetchall()
    
    # If including databases, also fetch from database_status for RDS instances
    if include_databases:
        db_where = []
        db_params = {"env": environment}
        if environment:
            db_where.append("d.environment = :env")
        if location_id is not None:
            db_where.append("d.location_id = :location_id")
            db_params["location_id"] = location_id
            
        db_where_sql = "WHERE " + " AND ".join(db_where) if db_where else ""
        db_query = text(f"""
            SELECT 
                20000 + d.id as id, d.name, '0.0.0.0' as ip, d.status, d.environment, 
                d.cpu, d.memory, 0 as disk, d.last_seen, d.location_id, d.external_id, 
                'Database' as os_type
            FROM database_status d
            {db_where_sql}
        """)
        db_rows = db.execute(db_query, db_params).fetchall()
        all_rows.extend(db_rows)
    
    all_server_ids = [r.id for r in all_rows]
    hot_data_map_all = {}
    if all_server_ids:
        try:
            hot_data_map_all = get_all_servers_hot_data(all_server_ids)
        except Exception as e:
            logger.error(f"Error fetching hot data for summary: {e}")
    
    global_summary = {"total": 0, "up": 0, "down": 0, "warn": 0, "crit": 0}
    
    from app.routes.thresholds import get_hardware_thresholds_internal
    thresholds = get_hardware_thresholds_internal(db)
    
    def get_server_status(row):
        now = datetime.now()
        heartbeat_threshold = timedelta(minutes=SERVER_DOWN_THRESHOLD_MINUTES)
        
        last_seen_online = False
        ls = row.last_seen
        if ls:
            if isinstance(ls, str):
                try:
                    ls = datetime.fromisoformat(ls.replace('Z', '+00:00')).replace(tzinfo=None)
                except: pass
            if isinstance(ls, datetime) and (now - ls) < heartbeat_threshold:
                last_seen_online = True
        
        if not last_seen_online:
            return "offline", 0
            
        hot_data = hot_data_map_all.get(row.id, {})
        cpu = float(hot_data.get('cpu', row.cpu or 0))
        mem = float(hot_data.get('memory', row.memory or 0))
        disk = float(hot_data.get('disk', row.disk or 0))
        
        status = "online"
        priority = 1
        
        cpu_t = thresholds.get('cpu', {'warning': 65, 'error': 69})
        mem_t = thresholds.get('memory', {'warning': 65, 'error': 69})
        disk_t = thresholds.get('disk', {'warning': 65, 'error': 69})
        
        if cpu >= cpu_t['error'] or mem >= mem_t['error'] or disk >= disk_t['error']:
            status = "critical"
            priority = 3
        elif cpu >= cpu_t['warning'] or mem >= mem_t['warning'] or disk >= disk_t['warning']:
            status = "warning"
            priority = 2
            
        return status, priority

    scored_servers = []
    for r in all_rows:
        status, priority = get_server_status(r)
        global_summary["total"] += 1
        if status == "offline":
            global_summary["down"] += 1
        else:
            global_summary["up"] += 1
            if status == "critical": global_summary["crit"] += 1
            elif status == "warning": global_summary["warn"] += 1
        
        scored_servers.append({"id": r.id, "priority": priority, "name": r.name or ""})

    scored_servers.sort(key=lambda x: (-x["priority"], x["name"].lower()))
    
    paged_ids = [s["id"] for s in scored_servers[offset:offset+size]]
    
    results = []
    if paged_ids:
        # Split paged_ids into server IDs and database IDs
        # Database IDs are offset by 20000 (matching hot store convention in prom_metrics_collector)
        # We track which IDs are database IDs from the all_rows query
        db_offset_ids = set(r.id for r in all_rows if hasattr(r, 'os_type') and r.os_type == 'Database')
        server_ids = [sid for sid in paged_ids if sid not in db_offset_ids]
        db_ids = [sid - 20000 for sid in paged_ids if sid in db_offset_ids]
        
        server_results = []
        if server_ids:
            query = text(f"""
                SELECT 
                    s.id, s.name, s.ip, s.status, s.environment, s.os_type, s.os_name, s.cpu,
                    s.memory, s.disk, s.uptime, s.last_seen, s.public_ip, s.detected_ips,
                    s.location_id, s.external_id
                FROM server_status s
                WHERE s.id = ANY(:server_ids)
            """)
            server_results = db.execute(query, {"server_ids": server_ids}).fetchall()
            
        db_results = []
        if db_ids:
            # Map database_status to same structure as server_status for the result set
            query = text(f"""
                SELECT 
                    20000 + d.id as id, d.name, '0.0.0.0' as ip, d.status, d.environment, 
                    'Database' as os_type, d.engine as os_name, d.cpu, d.memory, d.disk, 
                    0 as uptime, d.last_seen, NULL as public_ip, NULL as detected_ips,
                    d.location_id, d.external_id
                FROM database_status d
                WHERE d.id = ANY(:db_ids)
            """)
            db_results = db.execute(query, {"db_ids": db_ids}).fetchall()
            
        results = list(server_results) + list(db_results)
        
    results_map = {r.id: r for r in results}
    sorted_results = [results_map[sid] for sid in paged_ids if sid in results_map]
    
    servers = []
    metrics_map = {}
    hot_data_map = {}
    if paged_ids:
        try:
            hot_data_map = get_all_servers_hot_data(paged_ids)
            q_metrics = text("""
                SELECT DISTINCT ON (server_id, metric_name)
                    server_id, metric_name, value
                FROM server_metrics
                WHERE server_id = ANY(:server_ids)
                AND metric_name IN (
                    'network_bandwidth', 'network_bits_per_sec', 'packet_count', 'memory_total_bytes', 'memory_used_bytes',
                    'disk_total_bytes', 'disk_used_bytes', 'db_status', 'db_qsize', 'db_bandwidth', 'db_latency',
                    'app_throughput', 'app_latency', 'app_historical_throughput', 'app_historical_latency',
                    'app_failure_trade_api', 'app_failure_authentication'
                )
                ORDER BY server_id, metric_name, ts DESC
            """)
            metrics_result = db.execute(q_metrics, {"server_ids": paged_ids})
            for m_row in metrics_result:
                metrics_map[(m_row[0], m_row[1])] = float(m_row[2])
        except Exception as e:
            logger.error(f"Error fetching batch metrics: {e}")

    now = datetime.now()
    heartbeat_threshold = timedelta(minutes=SERVER_DOWN_THRESHOLD_MINUTES)
    
    for r in sorted_results:
        res_id = r.id
        res_last_seen = r.last_seen
        
        last_seen_dt = None
        if res_last_seen:
            if isinstance(res_last_seen, datetime):
                last_seen_dt = res_last_seen
            else:
                try: last_seen_dt = datetime.fromisoformat(str(res_last_seen).replace('Z', '+00:00'))
                except: pass
            if last_seen_dt and last_seen_dt.tzinfo:
                last_seen_dt = last_seen_dt.replace(tzinfo=None)

        server_status = "online" if last_seen_dt and (now - last_seen_dt) < heartbeat_threshold else "offline"
        
        inactive_threshold = timedelta(minutes=SERVER_DOWN_THRESHOLD_MINUTES * 2)
        is_inactive = not(last_seen_dt and (now - last_seen_dt) < inactive_threshold)

        hot_data = hot_data_map.get(res_id, {})
        res_cpu = float(hot_data.get('cpu', r.cpu or 0.0))
        res_memory = float(hot_data.get('memory', r.memory or 0.0))
        res_disk = float(hot_data.get('disk', r.disk or 0.0))
        
        if is_inactive:
            res_cpu = res_memory = res_disk = 0.0
        
        # Determine resource_id for AWS Console tracking
        resource_id = r.ip
        if r.location_id == 3 and r.external_id:
            # For AWS, prioritize the Instance ID or DB ID
            resource_id = r.external_id
        elif r.os_type == "Database" and r.external_id:
            resource_id = r.external_id

        servers.append(ServerResponse(
            id=res_id,
            name=r.name,
            ip=r.ip,
            resource_id=resource_id,
            public_ip=r.public_ip,
            status=server_status,
            environment=r.environment,
            os=r.os_type,
            os_name=r.os_name,
            cpu=res_cpu,
            memory=res_memory,
            memory_total_bytes=float(hot_data.get('memory_total_bytes', metrics_map.get((res_id, 'memory_total_bytes'), 0.0))),
            memory_used_bytes=float(hot_data.get('memory_used_bytes', metrics_map.get((res_id, 'memory_used_bytes'), 0.0))),
            disk=res_disk,
            disk_total_bytes=float(hot_data.get('disk_total_bytes', metrics_map.get((res_id, 'disk_total_bytes'), 0.0))),
            disk_used_bytes=float(hot_data.get('disk_used_bytes', metrics_map.get((res_id, 'disk_used_bytes'), 0.0))),
            uptime=float(r.uptime or 0.0),
            network_bandwidth=min(max(0.0, float(hot_data.get('network_bandwidth', metrics_map.get((res_id, 'network_bandwidth'), 0.0)))), 100.0),
            network_bits_per_sec=float(hot_data.get('network_bits_per_sec', metrics_map.get((res_id, 'network_bits_per_sec'), 0.0))),
            packet_count=float(hot_data.get('packet_count', metrics_map.get((res_id, 'packet_count'), 0.0))),
            last_seen=res_last_seen.isoformat() + 'Z' if res_last_seen else "",
            db_status=float(hot_data.get('db_status', metrics_map.get((res_id, 'db_status'), 0.0))),
            db_qsize=float(hot_data.get('db_qsize', metrics_map.get((res_id, 'db_qsize'), 0.0))),
            db_bandwidth=float(hot_data.get('db_bandwidth', metrics_map.get((res_id, 'db_bandwidth'), 0.0))),
            db_latency=float(hot_data.get('db_latency', metrics_map.get((res_id, 'db_latency'), 0.0))),
            location_id=r.location_id,
            external_id=r.external_id,
            app_throughput=float(hot_data.get('app_throughput', metrics_map.get((res_id, 'app_throughput'), 0.0))),
            app_latency=float(hot_data.get('app_latency', metrics_map.get((res_id, 'app_latency'), 0.0))),
            app_historical_throughput=float(hot_data.get('app_historical_throughput', metrics_map.get((res_id, 'app_historical_throughput'), 0.0))),
            app_historical_latency=float(hot_data.get('app_historical_latency', metrics_map.get((res_id, 'app_historical_latency'), 0.0))),
            app_failure_trade_api=float(hot_data.get('app_failure_trade_api', metrics_map.get((res_id, 'app_failure_trade_api'), 0.0))),
            app_failure_authentication=float(hot_data.get('app_failure_authentication', metrics_map.get((res_id, 'app_failure_authentication'), 0.0))),
            is_inactive=is_inactive
        ))
        
    import math
    total_pages = math.ceil(total_count / size) if size > 0 else 0
    
    return PaginatedServerResponse(
        items=servers,
        total_count=total_count,
        page=page,
        size=size,
        total_pages=total_pages,
        summary=global_summary
    )

@router.get("/{server_id}", response_model=ServerResponse)
def get_server(server_id: int, request: Request, db: Session = Depends(get_db)):
    """Get a single server by ID, based on collector data - requires authentication."""
    from app.utils.permissions import get_current_user
    get_current_user(request)
    
    query = text("""
        SELECT 
            s.id, s.name, s.ip, s.status, s.environment, s.os_type, s.os_name, s.cpu, 
            s.memory, s.disk, s.uptime, s.last_seen, s.public_ip,
            s.location_id, s.external_id
        FROM server_status s
        WHERE s.id = :server_id
    """)
    result = db.execute(query, {"server_id": server_id}).fetchone()
    if not result:
        raise HTTPException(status_code=404, detail="Server not found")
    
    now = datetime.now()
    heartbeat_threshold = timedelta(minutes=SERVER_DOWN_THRESHOLD_MINUTES)
    res_last_seen = result.last_seen
    
    last_seen_dt = None
    if res_last_seen:
        if isinstance(res_last_seen, datetime): last_seen_dt = res_last_seen
        else:
            try: last_seen_dt = datetime.fromisoformat(str(res_last_seen).replace('Z', '+00:00'))
            except: pass
        if last_seen_dt and last_seen_dt.tzinfo:
            last_seen_dt = last_seen_dt.replace(tzinfo=None)

    server_status = "online" if last_seen_dt and (now - last_seen_dt) < heartbeat_threshold else "offline"
    
    inactive_threshold = timedelta(minutes=SERVER_DOWN_THRESHOLD_MINUTES)
    is_inactive = not(last_seen_dt and (now - last_seen_dt) < inactive_threshold)
    
    # Determine resource_id for AWS Console tracking
    resource_id = result.ip
    if result.location_id == 3 and result.external_id:
        resource_id = result.external_id
    elif result.os_type == "Database" and result.external_id:
        resource_id = result.external_id

    # NEW: Fetch latest metrics from hot_store for full detail view
    hot_data = get_hot_store_server_data(server_id)
    
    return ServerResponse(
        id=result.id,
        name=result.name,
        ip=result.ip,
        resource_id=resource_id,
        public_ip=result.public_ip,
        status=server_status,
        environment=result.environment,
        os=result.os_type,
        os_name=result.os_name,
        cpu=float(hot_data.get('cpu', result.cpu or 0.0)),
        memory=float(hot_data.get('memory', result.memory or 0.0)),
        disk=float(hot_data.get('disk', result.disk or 0.0)),
        uptime=float(hot_data.get('uptime', result.uptime or 0.0)),
        network_bandwidth=float(hot_data.get('network_bandwidth', 0.0)),
        network_bits_per_sec=float(hot_data.get('network_bits_per_sec', 0.0)),
        packet_count=float(hot_data.get('packet_count', 0.0)),
        memory_total_bytes=float(hot_data.get('memory_total_bytes', 0.0)),
        memory_used_bytes=float(hot_data.get('memory_used_bytes', 0.0)),
        disk_total_bytes=float(hot_data.get('disk_total_bytes', 0.0)),
        disk_used_bytes=float(hot_data.get('disk_used_bytes', 0.0)),
        last_seen=res_last_seen.isoformat() + 'Z' if res_last_seen else "",
        is_inactive=is_inactive,
        location_id=result.location_id,
        external_id=result.external_id
    )

from app.utils.sanitizer import sanitize_string

@router.post("/", response_model=ServerResponse)
def create_server(server_data: ServerCreate, request: Request, db: Session = Depends(get_db)):
    """Create a new server - Admin only"""
    require_admin(request)
    
    # Sanitize inputs (VAPT Fix)
    server_data.name = sanitize_string(server_data.name)
    server_data.ip = sanitize_string(server_data.ip)
    
    query = select(server_status_table).where(server_status_table.c.ip == server_data.ip)
    if db.execute(query).fetchone():
        raise HTTPException(status_code=400, detail="Server with this IP already exists")
    
    public_ip = request.client.host if request.client else None
    
    insert_query = server_status_table.insert().values(
        name=server_data.name, ip=server_data.ip, public_ip=public_ip,
        status=server_data.status, environment=server_data.environment,
        os_type=server_data.os_type, location_id=server_data.location_id,
        last_seen=datetime.utcnow(),
        created_at=datetime.utcnow(), updated_at=datetime.utcnow()
    )
    result = db.execute(insert_query)
    server_id = result.inserted_primary_key[0]
    
    try:
        if server_data.environment in ['prod', 'uat']:
            selection_insert = insert(lama_exchange_server_selection_table).values(
                environment=server_data.environment, server_id=server_id, enabled=True)
            db.execute(selection_insert)
    except Exception as selection_error:
        logger.warning(f"Could not add server {server_id} to LAMA Exchange server selection: {selection_error}")
    
    db.commit()
    return get_server(server_id, request, db)

@router.put("/{server_id}", response_model=ServerResponse)
def update_server(server_id: int, server_data: ServerUpdate, request: Request, db: Session = Depends(get_db)):
    """Update server - Admin only"""
    require_admin(request)
    query = select(server_status_table).where(server_status_table.c.id == server_id)
    result = db.execute(query).fetchone()
    if not result:
        raise HTTPException(status_code=404, detail="Server not found")
    
    old_environment = result.environment
    
    update_values = server_data.dict(exclude_unset=True)
    update_values["updated_at"] = datetime.utcnow()
    
    if "environment" in update_values and update_values["environment"] != old_environment:
        with engine.begin() as conn:
            conn.execute(update(server_status_table).where(server_status_table.c.id == server_id).values(**update_values))
            sync_server_selection_on_environment_change(server_id, old_environment, update_values["environment"], conn=conn)
    else:
        db.execute(update(server_status_table).where(server_status_table.c.id == server_id).values(**update_values))
        db.commit()
    
    return get_server(server_id, request, db)

@router.delete("/{server_id}")
def delete_server(server_id: int, request: Request, db: Session = Depends(get_db)):
    """Delete server and associated data - Admin only"""
    from app.db.db import server_status_table, lama_exchange_server_selection_table, server_metrics_table, aws_ignore_list_table
    from sqlalchemy import delete
    
    require_admin(request)
    query = select(server_status_table).where(server_status_table.c.id == server_id)
    server = db.execute(query).fetchone()
    if not server:
        raise HTTPException(status_code=404, detail="Server not found")
    
    # 1. Add to ignore list if it's an AWS resource
    if server.external_id and (server.external_id.startswith('i-') or server.external_id.startswith('arn:aws:')):
        try:
            db.execute(text("""
                INSERT INTO aws_ignore_list (external_id, resource_type, environment)
                VALUES (:ext_id, 'ec2', :env)
                ON CONFLICT (external_id) DO NOTHING
            """), {"ext_id": server.external_id, "env": server.environment})
            logger.info(f"Added {server.external_id} to AWS ignore list")
        except Exception as e:
            logger.warning(f"Failed to add to ignore list: {e}")

    # 2. Cascading delete from linked tables
    db.execute(delete(lama_exchange_server_selection_table).where(lama_exchange_server_selection_table.c.server_id == server_id))
    db.execute(delete(server_metrics_table).where(server_metrics_table.c.server_id == server_id))
    
    # 3. Delete from status table
    db.execute(delete(server_status_table).where(server_status_table.c.id == server_id))
    db.commit()
    
    return {"message": "Server deleted successfully and added to ignore list"}

# The network-interfaces and disk-partitions endpoints remain useful for diagnostics
@router.get("/{server_id}/network-interfaces")
def get_network_interfaces(server_id: int, request: Request, db: Session = Depends(get_db)):
    """Get per-interface network metrics for a specific server - requires authentication."""
    from app.utils.permissions import get_current_user
    get_current_user(request)
    
    query = select(server_status_table).where(server_status_table.c.id == server_id)
    if not db.execute(query).fetchone():
        raise HTTPException(status_code=404, detail="Server not found")
    
    try:
        try:
            from app.routes.metrics import get_clickhouse_client
            client = get_clickhouse_client()
            if client:
                ch_query = f"""
                    SELECT 
                        interface_name, argMax(value, ts) as last_val,
                        max(ts) as last_updated, metric_name
                    FROM lama.server_metrics
                    WHERE server_id = {int(server_id)}
                    AND metric_name IN ('network_bandwidth', 'network_speed_bps', 'network_bytes_sent', 'network_bytes_recv', 'network_bits_per_sec')
                    AND interface_name IS NOT NULL
                    GROUP BY interface_name, metric_name
                """
                ch_result = client.query(ch_query)
                
                ifaces_map = {}
                for row in ch_result.result_rows:
                    iface_name, val, ts, m_name = row
                    if iface_name not in ifaces_map:
                        ifaces_map[iface_name] = {"name": iface_name, "last_updated": ts.isoformat() + 'Z'}
                    
                    if m_name == 'network_bandwidth': ifaces_map[iface_name]['utilization'] = float(val)
                    elif m_name == 'network_speed_bps': ifaces_map[iface_name]['speed_bps'] = float(val)
                    elif m_name == 'network_bytes_sent': ifaces_map[iface_name]['bytes_sent'] = float(val)
                    elif m_name == 'network_bytes_recv': ifaces_map[iface_name]['bytes_recv'] = float(val)
                    elif m_name == 'network_bits_per_sec': ifaces_map[iface_name]['bits_per_sec'] = float(val)
                
                interfaces = sorted(list(ifaces_map.values()), key=lambda x: x['name'])
                if interfaces:
                    return {"server_id": server_id, "interfaces": interfaces, "count": len(interfaces), "source": "clickhouse"}
        except Exception as e:
            logger.warning(f"ClickHouse network interface fetch failed: {e}")

        interfaces_query = text("""
            WITH distinct_interfaces AS (
                SELECT DISTINCT interface_name FROM server_metrics
                WHERE server_id = :server_id AND interface_name IS NOT NULL
                AND metric_name IN ('network_speed_bps', 'network_bandwidth', 'network_bits_per_sec')
            )
            SELECT 
                di.interface_name,
                (SELECT value FROM server_metrics WHERE server_id = :server_id AND metric_name = 'network_bandwidth' AND interface_name = di.interface_name ORDER BY ts DESC LIMIT 1) as utilization,
                (SELECT value FROM server_metrics WHERE server_id = :server_id AND metric_name = 'network_speed_bps' AND interface_name = di.interface_name ORDER BY ts DESC LIMIT 1) as speed_bps,
                (SELECT value FROM server_metrics WHERE server_id = :server_id AND metric_name = 'network_bytes_sent' AND interface_name = di.interface_name ORDER BY ts DESC LIMIT 1) as bytes_sent,
                (SELECT value FROM server_metrics WHERE server_id = :server_id AND metric_name = 'network_bytes_recv' AND interface_name = di.interface_name ORDER BY ts DESC LIMIT 1) as bytes_recv,
                (SELECT value FROM server_metrics WHERE server_id = :server_id AND metric_name = 'network_bits_per_sec' AND interface_name = di.interface_name ORDER BY ts DESC LIMIT 1) as bits_per_sec,
                (SELECT MAX(ts) FROM server_metrics WHERE server_id = :server_id AND interface_name = di.interface_name) as last_updated
            FROM distinct_interfaces di ORDER BY di.interface_name
        """)
        result = db.execute(interfaces_query, {"server_id": server_id}).fetchall()
        
        interfaces = [
            {"name": row[0], "utilization": float(row[1] or 0.0), "speed_bps": float(row[2] or 0.0),
             "bytes_sent": float(row[3] or 0.0), "bytes_recv": float(row[4] or 0.0),
             "bits_per_sec": float(row[5] or 0.0), "last_updated": row[6].isoformat() + 'Z' if row[6] else None}
            for row in result if row[0]
        ]
        return {"server_id": server_id, "interfaces": interfaces, "count": len(interfaces), "source": "postgresql"}
    except Exception as e:
        logger.error(f"Error fetching network interfaces for server {server_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{server_id}/disk-partitions")
def get_disk_partitions(server_id: int, request: Request, db: Session = Depends(get_db)):
    """Get latest disk partition metrics for a specific server - requires authentication."""
    from app.utils.permissions import get_current_user
    get_current_user(request)
    
    try:
        try:
            from app.routes.metrics import get_clickhouse_client
            client = get_clickhouse_client()
            if client:
                ch_query = f"""
                    SELECT 
                        interface_name as partition_name, argMax(value, ts) as last_val,
                        max(ts) as last_updated, metric_name
                    FROM lama.server_metrics
                    WHERE server_id = {int(server_id)}
                    AND metric_name IN ('disk', 'disk_total_gb', 'disk_used_gb', 'disk_free_gb')
                    AND interface_name IS NOT NULL
                    GROUP BY partition_name, metric_name
                """
                ch_result = client.query(ch_query)
                
                parts_map = {}
                for row in ch_result.result_rows:
                    p_name, val, ts, m_name = row
                    if p_name not in parts_map:
                        parts_map[p_name] = {"name": p_name, "last_updated": ts.isoformat() + 'Z'}
                    
                    if m_name == 'disk': parts_map[p_name]['utilization'] = float(val)
                    elif m_name == 'disk_total_gb': parts_map[p_name]['total_gb'] = float(val)
                    elif m_name == 'disk_used_gb': parts_map[p_name]['used_gb'] = float(val)
                    elif m_name == 'disk_free_gb': parts_map[p_name]['free_gb'] = float(val)
                
                partitions = list(parts_map.values())
                if partitions:
                    return {"server_id": server_id, "partitions": partitions, "count": len(partitions), "source": "clickhouse"}
        except Exception as e:
            logger.warning(f"ClickHouse partition fetch failed: {e}")

        partitions_query = text("""
            WITH distinct_partitions AS (
                SELECT DISTINCT interface_name FROM server_metrics
                WHERE server_id = :server_id AND interface_name IS NOT NULL
                AND metric_name IN ('disk', 'disk_total_gb', 'disk_used_gb', 'disk_free_gb')
            )
            SELECT 
                dp.interface_name as partition_name,
                (SELECT value FROM server_metrics WHERE server_id = :server_id AND metric_name = 'disk' AND interface_name = dp.interface_name ORDER BY ts DESC LIMIT 1) as utilization,
                (SELECT value FROM server_metrics WHERE server_id = :server_id AND metric_name = 'disk_total_gb' AND interface_name = dp.interface_name ORDER BY ts DESC LIMIT 1) as total_gb,
                (SELECT value FROM server_metrics WHERE server_id = :server_id AND metric_name = 'disk_used_gb' AND interface_name = dp.interface_name ORDER BY ts DESC LIMIT 1) as used_gb,
                (SELECT value FROM server_metrics WHERE server_id = :server_id AND metric_name = 'disk_free_gb' AND interface_name = dp.interface_name ORDER BY ts DESC LIMIT 1) as free_gb,
                (SELECT MAX(ts) FROM server_metrics WHERE server_id = :server_id AND interface_name = dp.interface_name) as last_updated
            FROM distinct_partitions dp ORDER BY dp.interface_name
        """)
        
        result = db.execute(partitions_query, {"server_id": server_id}).fetchall()
        
        partitions = [
            {"name": row[0], "utilization": float(row[1] or 0.0), "total_gb": float(row[2] or 0.0),
             "used_gb": float(row[3] or 0.0), "free_gb": float(row[4] or 0.0),
             "last_updated": row[5].isoformat() + 'Z' if row[5] else None}
            for row in result if row[0]
        ]
        return {"server_id": server_id, "partitions": partitions, "count": len(partitions)}
    except Exception as e:
        logger.error(f"Error fetching disk partitions for server {server_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

class MoveServerRequest(BaseModel):
    environment: str

@router.post("/{server_id}/move")
def move_server(server_id: int, move_data: MoveServerRequest, request: Request, db: Session = Depends(get_db)):
    """Move server to a different environment (prod/uat) - Admin only"""
    require_admin(request)
    target_environment = move_data.environment
    if target_environment not in ['prod', 'uat']:
        raise HTTPException(status_code=400, detail="Environment must be 'prod' or 'uat'")
    
    query = select(server_status_table).where(server_status_table.c.id == server_id)
    result = db.execute(query).fetchone()
    if not result:
        raise HTTPException(status_code=404, detail="Server not found")
    
    old_environment = result.environment
    
    if target_environment != old_environment:
        with engine.begin() as conn:
            update_query = update(server_status_table).where(server_status_table.c.id == server_id).values(
                environment=target_environment, updated_at=datetime.utcnow())
            conn.execute(update_query)
            sync_server_selection_on_environment_change(server_id, old_environment, target_environment, conn=conn)
    else:
        return {"message": f"Server is already in {target_environment} environment"}
    
    return {"message": f"Server moved to {target_environment} successfully"}
