# api/backend/app/routes/database_config.py
"""
Database configuration endpoints: Manage database credentials for monitoring
"""

from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel
from typing import Optional
from sqlalchemy import select, insert, update, delete, text
from app.db.db import database_config_table, server_status_table, engine, database_status_table, lama_exchange_server_selection_table, metric_sources_table
from app.utils.permissions import require_admin, get_current_user, require_role
from datetime import datetime
import json
import logging
from cryptography.fernet import Fernet
import os
import base64

logger = logging.getLogger(__name__)

router = APIRouter()

def get_encryption_key():
    """Get encryption key for passwords"""
    key = os.getenv("ENCRYPTION_KEY", "default-key-change-in-production")
    key_bytes = key.encode()[:32].ljust(32, b'0')
    return base64.urlsafe_b64encode(key_bytes)

def encrypt_password(password: str) -> str:
    """Encrypt database password"""
    try:
        f = Fernet(get_encryption_key())
        encrypted = f.encrypt(password.encode())
        return encrypted.decode()
    except Exception as e:
        logger.error(f"Error encrypting password: {e}")
        raise HTTPException(status_code=500, detail=f"Error encrypting password: {str(e)}")

def decrypt_password(encrypted_password: str) -> str:
    """Decrypt database password"""
    try:
        f = Fernet(get_encryption_key())
        decrypted = f.decrypt(encrypted_password.encode())
        return decrypted.decode()
    except Exception as e:
        logger.error(f"Error decrypting password: {e}")
        raise HTTPException(status_code=500, detail=f"Error decrypting password: {str(e)}")

class DatabaseConfigCreate(BaseModel):
    server_id: int
    db_type: str  # 'postgresql', 'mysql', etc.
    host: str
    port: int
    database: str
    username: str
    password: str
    is_replication: bool = False
    master_host: str = None
    master_port: int = None
    enabled: bool = True
    location_id: Optional[int] = 1

class DatabaseConfigUpdate(BaseModel):
    db_type: str = None
    host: str = None
    port: int = None
    database: str = None
    username: str = None
    password: str = None
    is_replication: bool = None
    master_host: str = None
    master_port: int = None
    enabled: bool = None
    location_id: Optional[int] = None

class DatabaseConfigTest(BaseModel):
    db_type: str
    host: str
    port: int
    database: str
    username: str
    password: str

class DatabaseConfigResponse(BaseModel):
    id: int
    server_id: int
    db_type: str
    host: str
    port: int
    database: str
    username: str
    is_replication: Optional[bool] = False
    master_host: Optional[str] = None
    master_port: Optional[int] = None
    enabled: bool
    location_id: Optional[int] = 1
    created_at: str
    updated_at: str

class DiscoveredDatabaseResponse(BaseModel):
    id: int
    name: str
    engine: str
    environment: str
    status: str
    external_id: Optional[str] = None
    source_id: Optional[int] = None
    created_at: str

@router.get("/discovered", response_model=list[DiscoveredDatabaseResponse])
def list_discovered_databases(request: Request, environment: Optional[str] = None):
    """List automatically discovered databases (RDS) from database_status table"""
    require_role(request, ['admin', 'user'])
    try:
        with engine.connect() as conn:
            query = select(database_status_table)
            if environment:
                query = query.where(database_status_table.c.environment == environment)
            
            query = query.order_by(database_status_table.c.created_at.desc())
            results = conn.execute(query).fetchall()
            
            discovered = []
            for r in results:
                m = r._mapping
                discovered.append(DiscoveredDatabaseResponse(
                    id=m['id'],
                    name=m['name'],
                    engine=m['engine'],
                    environment=m['environment'],
                    status=m['status'],
                    external_id=m['external_id'],
                    source_id=m['source_id'],
                    created_at=m['created_at'].isoformat() if m['created_at'] else datetime.utcnow().isoformat()
                ))
            return discovered
    except Exception as e:
        logger.error(f"Error listing discovered databases: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/discovered/{db_id}")
def delete_discovered_database(db_id: int, request: Request):
    """
    Delete a discovered database from everywhere:
    1. database_status
    2. lama_exchange_server_selection
    3. Remove from AWS Metric Source selected_ids (to prevent re-sync)
    """
    require_admin(request)
    try:
        with engine.begin() as conn:
            # 1. Get info before deletion to clean up source config
            query = select(database_status_table).where(database_status_table.c.id == db_id)
            db_res = conn.execute(query).fetchone()
            if not db_res:
                raise HTTPException(status_code=404, detail="Discovered database not found")
            
            m = db_res._mapping
            external_id = m['external_id']
            source_id = m['source_id']

            # 2. Delete from monitoring and sync tables
            conn.execute(delete(database_status_table).where(database_status_table.c.id == db_id))
            
            # RDS instances are mapped to server_id + 20000 in the sync logic
            normalized_id = db_id + 20000
            conn.execute(delete(lama_exchange_server_selection_table).where(
                (lama_exchange_server_selection_table.c.server_id == normalized_id) |
                (lama_exchange_server_selection_table.c.server_id == db_id)
            ))

            # 3. CRITICAL: Update AWS Source Config to prevent re-discovery
            if source_id and external_id:
                src_query = select(metric_sources_table).where(metric_sources_table.c.id == source_id)
                src = conn.execute(src_query).fetchone()
                if src:
                    ms_mapping = src._mapping
                    config = ms_mapping['config']
                    if isinstance(config, str): config = json.loads(config)
                    
                    # Update selected_ids if they exist
                    selected_ids = config.get('selected_ids', {})
                    if 'rds' in selected_ids and external_id in selected_ids['rds']:
                        selected_ids['rds'].remove(external_id)
                        config['selected_ids'] = selected_ids
                        
                        conn.execute(update(metric_sources_table).where(
                            metric_sources_table.c.id == source_id
                        ).values(config=config))
                        logger.info(f"Removed RDS {external_id} from Source {source_id} configuration")

            logger.info(f"Discovered database {db_id} ({m['name']}) removed from system")
            return {"success": True, "message": "Discovered database removed from system"}
            
    except HTTPException: raise
    except Exception as e:
        logger.error(f"Error deleting discovered database: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/", response_model=DatabaseConfigResponse)
def create_database_config(config_data: DatabaseConfigCreate, request: Request):
    """Create database configuration for a server"""
    require_admin(request)
    
    try:
        with engine.begin() as conn:
            # Check if server exists
            from app.db.db import server_status_table
            server_query = select(server_status_table).where(server_status_table.c.id == config_data.server_id)
            server_result = conn.execute(server_query).fetchone()
            if not server_result:
                raise HTTPException(status_code=404, detail="Server not found")
            
            # Check if config already exists for this server
            existing_query = select(database_config_table).where(
                database_config_table.c.server_id == config_data.server_id
            )
            existing = conn.execute(existing_query).fetchone()
            if existing:
                raise HTTPException(status_code=400, detail="Database configuration already exists for this server")
            
            # Encrypt password
            encrypted_password = encrypt_password(config_data.password)
            
            # Create unique identifier
            unique_server_db = f"{config_data.server_id}_{config_data.host}_{config_data.port}_{config_data.database}"
            
            # Insert configuration
            insert_query = insert(database_config_table).values(
                server_id=config_data.server_id,
                db_type=config_data.db_type,
                host=config_data.host,
                port=config_data.port,
                database=config_data.database,
                username=config_data.username,
                password=encrypted_password,
                is_replication=config_data.is_replication,
                master_host=config_data.master_host,
                master_port=config_data.master_port,
                enabled=config_data.enabled,
                location_id=config_data.location_id,
                unique_server_db=unique_server_db,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )
            result = conn.execute(insert_query)
            config_id = result.inserted_primary_key[0]
            
            logger.info(f"Database configuration created for server {config_data.server_id}")
            
            # Return response (without password)
            return DatabaseConfigResponse(
                id=config_id,
                server_id=config_data.server_id,
                db_type=config_data.db_type,
                host=config_data.host,
                port=config_data.port,
                database=config_data.database,
                username=config_data.username,
                is_replication=config_data.is_replication,
                master_host=config_data.master_host,
                master_port=config_data.master_port,
                enabled=config_data.enabled,
                location_id=config_data.location_id,
                created_at=datetime.utcnow().isoformat(),
                updated_at=datetime.utcnow().isoformat()
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating database config: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error creating database config: {str(e)}")

@router.get("/", response_model=list[DatabaseConfigResponse])
def list_database_configs(server_id: int = None, environment: str = None, request: Request = None):
    """List database configurations, optionally filtered by server or environment
    
    Filters database configs by:
    - server_id: If provided, returns configs for that specific server
    - environment: If provided, returns configs for servers in that environment (prod/uat)
    - Both: If both are provided, returns configs matching both filters
    
    Admin/Manager/User - Read access for all authenticated users
    """
    require_role(request, ['admin', 'user'])  # Allow user role for read-only access
    # Validate environment parameter if provided
    if environment and environment not in ['prod', 'uat']:
        raise HTTPException(status_code=400, detail="Environment must be 'prod' or 'uat'")
    
    try:
        with engine.connect() as conn:
            # Use SQL JOIN to filter by server environment
            # Join database_config with server_status to access server.environment
            if environment:
                # Build query with JOIN when filtering by environment
                conditions = []
                params = {}
                
                if server_id:
                    conditions.append("dc.server_id = :server_id")
                    params["server_id"] = server_id
                
                if environment:
                    conditions.append("s.environment = :environment")
                    params["environment"] = environment
                
                where_clause = " AND " + " AND ".join(conditions) if conditions else ""
                
                sql_query = text(f"""
                    SELECT 
                        dc.id, dc.server_id, dc.db_type, dc.host, dc.port, dc.database, 
                        dc.username, dc.password, dc.is_replication, dc.master_host, 
                        dc.master_port, dc.enabled, dc.created_at, dc.updated_at, dc.location_id
                    FROM database_config dc
                    INNER JOIN server_status s ON dc.server_id = s.id
                    WHERE 1=1 {where_clause}
                    ORDER BY dc.created_at DESC
                """)
                
                results = conn.execute(sql_query, params).fetchall()
            elif server_id:
                # Filter by server_id only (no environment filter)
                query = select(database_config_table).where(
                    database_config_table.c.server_id == server_id
                ).order_by(database_config_table.c.created_at.desc())
                results = conn.execute(query).fetchall()
            else:
                # No filters - return all configs (for backward compatibility)
                query = select(database_config_table).order_by(database_config_table.c.created_at.desc())
                results = conn.execute(query).fetchall()
            
            configs = []
            for r in results:
                # Row access using mapping for safety
                m = r._mapping
                configs.append(DatabaseConfigResponse(
                    id=m['id'],
                    server_id=m['server_id'],
                    db_type=m['db_type'],
                    host=m['host'],
                    port=m['port'],
                    database=m['database'],
                    username=m['username'],
                    is_replication=m['is_replication'],
                    master_host=m['master_host'],
                    master_port=m['master_port'],
                    enabled=m['enabled'],
                    location_id=m.get('location_id', 1),
                    created_at=m['created_at'].isoformat() if m['created_at'] else datetime.utcnow().isoformat(),
                    updated_at=m['updated_at'].isoformat() if m['updated_at'] else datetime.utcnow().isoformat()
                ))

            return configs
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting database config: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error getting database config: {str(e)}")

@router.put("/{config_id}", response_model=DatabaseConfigResponse)
def update_database_config(config_id: int, config_data: DatabaseConfigUpdate, request: Request):
    """Update database configuration"""
    require_admin(request)
    
    try:
        with engine.begin() as conn:
            # Check if config exists
            query = select(database_config_table).where(database_config_table.c.id == config_id)
            result = conn.execute(query).fetchone()
            if not result:
                raise HTTPException(status_code=404, detail="Database configuration not found")
            
            # Build update values
            update_values = {"updated_at": datetime.utcnow()}
            if config_data.db_type is not None:
                update_values["db_type"] = config_data.db_type
            if config_data.host is not None:
                update_values["host"] = config_data.host
            if config_data.port is not None:
                update_values["port"] = config_data.port
            if config_data.database is not None:
                update_values["database"] = config_data.database
            if config_data.username is not None:
                update_values["username"] = config_data.username
            if config_data.password is not None:
                update_values["password"] = encrypt_password(config_data.password)
            if config_data.is_replication is not None:
                update_values["is_replication"] = config_data.is_replication
            if config_data.master_host is not None:
                update_values["master_host"] = config_data.master_host
            if config_data.master_port is not None:
                update_values["master_port"] = config_data.master_port
            if config_data.enabled is not None:
                update_values["enabled"] = config_data.enabled
            if config_data.location_id is not None:
                update_values["location_id"] = config_data.location_id
            
            # Update configuration
            update_query = update(database_config_table).where(
                database_config_table.c.id == config_id
            ).values(**update_values)
            conn.execute(update_query)
            
            # Fetch updated config
            updated_query = select(database_config_table).where(database_config_table.c.id == config_id)
            updated_result = conn.execute(updated_query).fetchone()
            m = updated_result._mapping
            
            return DatabaseConfigResponse(
                id=m['id'],
                server_id=m['server_id'],
                db_type=m['db_type'],
                host=m['host'],
                port=m['port'],
                database=m['database'],
                username=m['username'],
                is_replication=m['is_replication'],
                master_host=m['master_host'],
                master_port=m['master_port'],
                enabled=m['enabled'],
                location_id=m.get('location_id', 1),
                created_at=m['created_at'].isoformat() if m['created_at'] else datetime.utcnow().isoformat(),
                updated_at=m['updated_at'].isoformat() if m['updated_at'] else datetime.utcnow().isoformat()
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating database config: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error updating database config: {str(e)}")

@router.delete("/{config_id}")
def delete_database_config(config_id: int, request: Request):
    """Delete database configuration"""
    require_admin(request)
    
    try:
        with engine.begin() as conn:
            # Check if config exists
            query = select(database_config_table).where(database_config_table.c.id == config_id)
            result = conn.execute(query).fetchone()
            if not result:
                raise HTTPException(status_code=404, detail="Database configuration not found")
            
            # Clean up linked database_status entry (prevents ghost on dashboard)
            host = result._mapping.get("host")
            if host:
                conn.execute(text("DELETE FROM database_status WHERE external_id = :host OR name LIKE :pattern"),
                             {"host": host, "pattern": f"%{host}%"})
            
            # Delete configuration
            delete_query = delete(database_config_table).where(database_config_table.c.id == config_id)
            conn.execute(delete_query)
            
            logger.info(f"Database configuration {config_id} deleted")
            return {"message": "Database configuration deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting database config: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error deleting database config: {str(e)}")

@router.post("/test-connection")
def test_database_connection_unsaved(config_data: DatabaseConfigTest, request: Request):
    """Test database connection before saving and probe for role (Master/Slave)"""
    require_admin(request)
    try:
        from app.utils.database_monitor import check_database_metrics, probe_database_role
        
        # 1. Probe for role
        is_rep = probe_database_role(
            host=config_data.host,
            port=config_data.port,
            database=config_data.database,
            username=config_data.username,
            password=config_data.password,
            db_type=config_data.db_type
        )
        
        # 2. Test metrics
        metrics = check_database_metrics(
            host=config_data.host,
            port=config_data.port,
            database=config_data.database,
            username=config_data.username,
            password=config_data.password,
            db_type=config_data.db_type,
            is_replication=is_rep
        )
        
        if 'error' in metrics:
            return {
                "success": False,
                "message": metrics.get('error', 'Connection failed'),
                "is_replication": is_rep
            }
        
        return {
            "success": True,
            "message": f"Connection successful. Detected Role: {'Slave/Replica' if is_rep else 'Master/Primary'}",
            "is_replication": is_rep,
            "metrics": metrics
        }
    except Exception as e:
        logger.error(f"Error testing unsaved connection: {e}")
        return {"success": False, "message": str(e)}

@router.post("/{config_id}/test")
def test_database_connection(config_id: int, request: Request):
    """Test database connection and update role if changed - Admin only"""
    require_admin(request)
    try:
        with engine.begin() as conn:
            query = select(database_config_table).where(database_config_table.c.id == config_id)
            result = conn.execute(query).fetchone()
            if not result:
                raise HTTPException(status_code=404, detail="Database configuration not found")
            
            m = result._mapping
            password = decrypt_password(m['password'])
            
            from app.utils.database_monitor import check_database_metrics, probe_database_role
            
            # Probe current role
            is_rep = probe_database_role(m['host'], m['port'], m['database'], m['username'], password, m['db_type'])
            
            # If role changed, update it automatically
            if is_rep != m['is_replication']:
                conn.execute(update(database_config_table).where(
                    database_config_table.c.id == config_id
                ).values(is_replication=is_rep))
                logger.info(f"Auto-updated DB {config_id} role to {'Slave' if is_rep else 'Master'}")

            metrics = check_database_metrics(m['host'], m['port'], m['database'], m['username'], password, m['db_type'], is_rep)
            
            if 'error' in metrics:
                return {"success": False, "message": metrics.get('error', 'Connection failed')}
            
            return {
                "success": True,
                "message": f"Connection successful. Role: {'Slave' if is_rep else 'Master'}",
                "is_replication": is_rep,
                "metrics": metrics
            }
    except Exception as e:
        logger.error(f"Error testing database connection: {e}")
        return {"success": False, "message": str(e)}



@router.put("/prometheus-db/{source_id}/replication")
async def update_prometheus_db_replication(source_id: int, request: Request):
    """Update is_replication and master_host on database_status for a Prometheus DB source."""
    body = await request.json()
    is_replication = bool(body.get("is_replication", False))
    master_host = body.get("master_host") or None

    with engine.connect() as conn:
        result = conn.execute(
            text("UPDATE database_status SET is_replication = :is_rep, master_host = :master WHERE source_id = :sid"),
            {"is_rep": is_replication, "master": master_host, "sid": source_id}
        )
        conn.commit()
        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="No database_status entry found for this source")
    return {"success": True}
