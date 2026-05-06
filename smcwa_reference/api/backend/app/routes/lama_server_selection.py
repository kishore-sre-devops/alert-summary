# api/backend/app/routes/lama_server_selection.py
"""
LAMA Exchange Server Selection endpoints
Controls which servers send metrics to LAMA Exchange per environment
"""

from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel
from sqlalchemy import select, text
from sqlalchemy.orm import Session
from app.db.db import get_db, lama_exchange_server_selection_table, server_status_table, engine
from app.utils.permissions import get_current_user
from datetime import datetime
from typing import List, Optional
import logging

logger = logging.getLogger(__name__)

router = APIRouter()

class ServerSelectionItem(BaseModel):
    server_id: int
    server_name: str
    server_ip: str
    enabled: bool
    metric_source: Optional[str] = "auto"  # 'auto', 'onprem', 'aws'

class ServerSelectionRequest(BaseModel):
    environment: str  # 'prod' or 'uat'
    servers: List[ServerSelectionItem]  # List of servers with enabled status

class ServerSelectionResponse(BaseModel):
    environment: str
    servers: List[ServerSelectionItem]
    enabled_count: int
    total_count: int

@router.get("/{environment}", response_model=ServerSelectionResponse)
def get_server_selection(environment: str, request: Request):
    """Get server selection for an environment - requires authentication"""
    try:
        user = get_current_user(request)
        if not user:
            raise HTTPException(status_code=401, detail="Not authenticated")
    except Exception as e:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    if environment not in ['prod', 'uat']:
        raise HTTPException(status_code=400, detail="Environment must be 'prod' or 'uat'")
    
    try:
        with engine.connect() as conn:
            # Get all servers for this environment
            servers_query = text("""
                SELECT id, name, ip
                FROM server_status
                WHERE environment = :env
                ORDER BY name
            """)
            all_servers = conn.execute(servers_query, {"env": environment}).fetchall()
            
            # Get existing selections with explicit column names for safety
            selections_query = text("""
                SELECT server_id, enabled, metric_source
                FROM lama_exchange_server_selection
                WHERE environment = :env
            """)
            existing_selections = conn.execute(selections_query, {"env": environment}).fetchall()
            
            # Create a map of server_id -> selection data
            selection_map = {}
            for row in existing_selections:
                # Use mapping access for safety
                row_map = row._mapping if hasattr(row, '_mapping') else dict(row)
                
                server_id = row_map.get('server_id')
                enabled = row_map.get('enabled')
                # Force to string to prevent Pydantic validation errors
                raw_source = row_map.get('metric_source', 'auto')
                metric_source = str(raw_source) if raw_source is not None else "auto"
                if not metric_source or metric_source == "None":
                    metric_source = "auto"
                
                selection_map[server_id] = {
                    "enabled": enabled,
                    "metric_source": metric_source
                }
            
            # Build response with all servers and their enabled status
            servers_list = []
            enabled_count = 0
            
            for server in all_servers:
                server_id = server[0]
                server_name = server[1]
                server_ip = server[2]
                
                # If server has selection, use it; otherwise default to False (not enabled)
                selection_data = selection_map.get(server_id, {"enabled": False, "metric_source": "auto"})
                enabled = selection_data["enabled"]
                
                # CRITICAL: Ensure metric_source is a string and not a datetime object
                raw_metric_source = selection_data["metric_source"]
                if isinstance(raw_metric_source, datetime):
                    metric_source = "auto"
                else:
                    metric_source = str(raw_metric_source) if raw_metric_source else "auto"
                
                if metric_source == "None" or not metric_source:
                    metric_source = "auto"
                
                if enabled:
                    enabled_count += 1
                
                servers_list.append(ServerSelectionItem(
                    server_id=server_id,
                    server_name=server_name,
                    server_ip=server_ip,
                    enabled=enabled,
                    metric_source=metric_source
                ))
            
            return ServerSelectionResponse(
                environment=environment,
                servers=servers_list,
                enabled_count=enabled_count,
                total_count=len(servers_list)
            )
    except Exception as e:
        logger.error(f"Error getting server selection for {environment}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error getting server selection: {str(e)}")

@router.post("/{environment}", response_model=dict)
def save_server_selection(environment: str, selection: ServerSelectionRequest, request: Request):
    """Save server selection for an environment - Admin only"""
    from app.utils.permissions import require_admin
    require_admin(request)  # Only admin can save server selection
    
    if environment not in ['prod', 'uat']:
        raise HTTPException(status_code=400, detail="Environment must be 'prod' or 'uat'")
    
    if selection.environment != environment:
        raise HTTPException(status_code=400, detail="Environment in path and body must match")
    
    try:
        with engine.begin() as conn:  # Use begin() for transaction
            # Validate all server IDs exist and belong to the environment
            if selection.servers:
                server_ids = [s.server_id for s in selection.servers]
                validation_query = text("""
                    SELECT id
                    FROM server_status
                    WHERE id = ANY(:server_ids) AND environment = :env
                """)
                valid_servers = conn.execute(
                    validation_query,
                    {"server_ids": server_ids, "env": environment}
                ).fetchall()
                valid_server_ids = {row[0] for row in valid_servers}
                
                # Check for invalid server IDs
                invalid_ids = set(server_ids) - valid_server_ids
                if invalid_ids:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Invalid server IDs for {environment.upper()}: {', '.join(map(str, invalid_ids))}"
                    )
            
            # Count enabled servers
            enabled_count = sum(1 for s in selection.servers if s.enabled)
            
            # Validate: At least one server must be enabled (warn but allow)
            if enabled_count == 0:
                logger.warning(f"Warning: No servers enabled for LAMA Exchange in {environment.upper()}. Metrics will not be sent.")
                # Note: We allow this, but log a warning
            
            # Delete existing selections for this environment
            delete_query = text("""
                DELETE FROM lama_exchange_server_selection
                WHERE environment = :env
            """)
            conn.execute(delete_query, {"env": environment})
            
            # Insert new selections (only for servers with enabled=True)
            enabled_servers = [s for s in selection.servers if s.enabled]
            
            if enabled_servers:
                for server in enabled_servers:
                    insert_query = text("""
                        INSERT INTO lama_exchange_server_selection
                        (environment, server_id, enabled, metric_source, created_at, updated_at)
                        VALUES (:env, :server_id, true, :metric_source, NOW(), NOW())
                        ON CONFLICT ON CONSTRAINT unique_env_server DO UPDATE
                        SET enabled = true, metric_source = :metric_source, updated_at = NOW()
                    """)
                    conn.execute(
                        insert_query,
                        {
                            "env": environment,
                            "server_id": server.server_id,
                            "metric_source": server.metric_source or "auto"
                        }
                    )
            
            # Also insert entries for disabled servers (with enabled=False) for tracking preferences
            disabled_servers = [s for s in selection.servers if not s.enabled]
            for server in disabled_servers:
                insert_query = text("""
                    INSERT INTO lama_exchange_server_selection
                    (environment, server_id, enabled, metric_source, created_at, updated_at)
                    VALUES (:env, :server_id, false, :metric_source, NOW(), NOW())
                    ON CONFLICT ON CONSTRAINT unique_env_server DO UPDATE
                    SET enabled = false, metric_source = :metric_source, updated_at = NOW()
                """)
                conn.execute(
                    insert_query,
                    {
                        "env": environment,
                        "server_id": server.server_id,
                        "metric_source": server.metric_source or "auto"
                    }
                )
            
            logger.info(f"Server selection saved for {environment.upper()}: {enabled_count} server(s) enabled out of {len(selection.servers)}")
            
            return {
                "status": "success",
                "message": f"Server selection saved for {environment.upper()}",
                "environment": environment,
                "enabled_count": enabled_count,
                "total_count": len(selection.servers)
            }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error saving server selection for {environment}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error saving server selection: {str(e)}")

@router.get("/{environment}/count", response_model=dict)
def get_server_selection_count(environment: str, request: Request):
    """Get count of enabled servers for an environment - requires authentication"""
    try:
        user = get_current_user(request)
        if not user:
            raise HTTPException(status_code=401, detail="Not authenticated")
    except Exception as e:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    if environment not in ['prod', 'uat']:
        raise HTTPException(status_code=400, detail="Environment must be 'prod' or 'uat'")
    
    try:
        with engine.connect() as conn:
            # Count enabled servers
            enabled_count_query = text("""
                SELECT COUNT(*)
                FROM lama_exchange_server_selection
                WHERE environment = :env AND enabled = true
            """)
            enabled_result = conn.execute(enabled_count_query, {"env": environment}).fetchone()
            enabled_count = enabled_result[0] if enabled_result else 0
            
            # Count total servers in environment
            total_count_query = text("""
                SELECT COUNT(*)
                FROM server_status
                WHERE environment = :env
            """)
            total_result = conn.execute(total_count_query, {"env": environment}).fetchone()
            total_count = total_result[0] if total_result else 0
            
            return {
                "environment": environment,
                "enabled_count": enabled_count,
                "total_count": total_count,
                "has_selection": enabled_count > 0
            }
    except Exception as e:
        logger.error(f"Error getting server selection count for {environment}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error getting server selection count: {str(e)}")

