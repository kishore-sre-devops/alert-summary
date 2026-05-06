"""
Role-based permission utilities
"""
from typing import Union, Optional
from fastapi import HTTPException, WebSocket, Request
from jose import JWTError, jwt
import os
import logging

logger = logging.getLogger(__name__)

JWT_SECRET = os.getenv("JWT_SECRET", os.getenv("JWT_SECRET_PROD", "your-secret-key-change-in-prod"))
JWT_ALGORITHM = "HS256"

def get_current_user(request: Request = None, websocket: WebSocket = None):
    """Extract current user from JWT token in Authorization header or HttpOnly cookie (VAPT Fix)"""
    # FastAPI dependency injection will provide either 'request' or 'websocket'
    conn = request or websocket
    if conn is None:
        raise HTTPException(status_code=500, detail="Internal Server Error: No request/websocket context.")
        
    token = None
    
    # 1. Try Authorization Header (only for Request)
    if isinstance(conn, Request):
        authorization = (
            conn.headers.get("Authorization") or 
            conn.headers.get("authorization") or
            conn.headers.get("AUTHORIZATION")
        )
        
        if authorization:
            # Handle "Bearer <token>" format
            parts = authorization.split()
            if len(parts) == 2 and parts[0].lower() == "bearer":
                token = parts[1]
                
    # 2. Try HttpOnly Cookie (VAPT Fix #5)
    if not token:
        token = conn.cookies.get("lama_session")
    
    # 3. Try query parameters (fallback for WebSockets)
    if not token and isinstance(conn, WebSocket):
        token = conn.query_params.get("token")
    
    if not token:
        if isinstance(conn, WebSocket):
             # Handled in the WebSocket route itself if needed, but raising for consistency
             pass
        
        raise HTTPException(status_code=401, detail="Not authenticated. Please provide a valid token or login.")
    
    # Verify token is valid
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return {
            "user_id": payload.get("user_id"),
            "email": payload.get("email", ""),
            "role": payload.get("role", "user")
        }
    except JWTError as e:
        logger.error(f"JWT decode error: {e}")
        raise HTTPException(status_code=401, detail=f"Invalid or expired token: {str(e)}")

def require_admin(request: Request):
    """Require admin role - raises exception if user is not admin"""
    user = get_current_user(request)
    if user["role"] != "admin":
        raise HTTPException(
            status_code=403, 
            detail="Access denied. Admin role required to perform this action."
        )
    return user

def require_role(request: Request, allowed_roles: list):
    """Require one of the specified roles"""
    user = get_current_user(request)
    if user["role"] not in allowed_roles:
        raise HTTPException(
            status_code=403,
            detail=f"Access denied. Required role: {', '.join(allowed_roles)}"
        )
    return user

