from fastapi import Request, HTTPException, Header, Query
from typing import Optional

def get_active_environment(
    request: Request,
    x_environment: Optional[str] = Header(None, alias="X-Environment"),
    environment: Optional[str] = Query(None)
) -> str:
    """
    FastAPI dependency to extract the active environment from headers or query parameters.
    Prioritizes X-Environment header, then 'environment' query parameter.
    Defaults to 'prod' if not provided.
    """
    active_env = x_environment or environment
    
    if not active_env:
        # Fallback to a default or raise an error if strictness is required
        # For now, default to 'prod' but log a warning if needed
        return 'prod'
    
    active_env = active_env.lower()
    if active_env not in ['prod', 'uat']:
        raise HTTPException(status_code=400, detail=f"Invalid environment: {active_env}. Must be 'prod' or 'uat'")
    
    return active_env
