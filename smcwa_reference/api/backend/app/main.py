from fastapi import FastAPI, Request, status, Depends, Response
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from app.routes.auth import router as auth_router
from app.routes.dashboard import router as dashboard_router
from app.routes.metrics import router as metrics_router
from app.routes.scheduler_status import router as scheduler_status_router
from app.routes.users import router as users_router
from app.routes.servers import router as servers_router
from app.routes.logs import router as logs_router
from app.routes.config import router as config_router
from app.routes.retention import router as retention_router
from app.routes.historical_data import router as historical_data_router
from app.routes.thresholds import router as thresholds_router
from app.routes.alert_config import router as alert_config_router
from app.routes.database_config import router as database_config_router
from app.routes.alerts import router as alerts_router
from app.routes.lama_diagnostics import router as lama_diagnostics_router
from app.routes.lama_server_selection import router as lama_server_selection_router
from app.routes.exchange_connectivity_errors import router as exchange_connectivity_errors_router
from app.routes.exchange_status import router as exchange_status_router
from app.routes.certificate_status import router as certificate_status_router
from app.routes.metric_sources import router as metric_sources_router
from app.routes.raw_metrics_validation import router as raw_metrics_validation_router
from app.routes.scheduler_config import router as scheduler_config_router
from app.routes.websockets import router as websockets_router, redis_listener
from app.db.db import init_db
import os
import sys
import asyncio
import bcrypt
from sqlalchemy import select, text
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
import logging
import threading
from app.utils.data_retention import run_data_retention_cleanup

logger = logging.getLogger(__name__)

ENVIRONMENT = os.getenv("ENVIRONMENT", "prod")

# VAPT FIX: Security Headers Middleware
class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        # Hide server version and type
        response.headers["Server"] = ""
        # Prevent MIME type sniffing
        response.headers["X-Content-Type-Options"] = "nosniff"
        # Prevent clickjacking
        response.headers["X-Frame-Options"] = "DENY"
        # Enable XSS protection in older browsers
        response.headers["X-XSS-Protection"] = "1; mode=block"
        # HSTS (1 year)
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        # Referrer Policy
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        # Content Security Policy (Basic)
        response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self' 'unsafe-inline' 'unsafe-eval'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self' ws: wss:;"
        return response

# Configure Swagger and OpenAPI (VAPT Fix #7)
# Use a custom root_path to handle proxy correctly
# Disable documentation in production for security
app_configs = {
    "title": "SMC LAMA Backend",
    "root_path": "/api"
}

if ENVIRONMENT == "prod":
    app_configs["docs_url"] = None
    app_configs["redoc_url"] = None
    app_configs["openapi_url"] = None
else:
    app_configs["docs_url"] = "/docs"
    app_configs["redoc_url"] = "/redoc"
    app_configs["openapi_url"] = "/openapi.json"

app = FastAPI(**app_configs)

# Add Security Headers Middleware
app.add_middleware(SecurityHeadersMiddleware)

# Fix OpenAPI version for better compatibility (VAPT Fix #7 part 2)
def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    from fastapi.openapi.utils import get_openapi
    openapi_schema = get_openapi(
        title=app.title,
        version="0.1.0",
        description="SMC LAMA API Documentation",
        routes=app.routes,
    )
    # Force OpenAPI 3.0.3 for maximum compatibility with older rendering tools
    openapi_schema["openapi"] = "3.0.3"
    app.openapi_schema = openapi_schema
    return app.openapi_schema

if ENVIRONMENT != "prod":
    app.openapi = custom_openapi

# Global exception handler for Pydantic validation errors
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Handle Pydantic validation errors and return user-friendly messages"""
    errors = exc.errors()
    error_messages = []
    
    for error in errors:
        field = " -> ".join(str(loc) for loc in error.get("loc", []))
        message = error.get("msg", "Validation error")
        error_type = error.get("type", "unknown")
        
        # Create user-friendly error messages
        if error_type == "value_error.missing":
            error_messages.append(f"Missing required field: {field}")
        elif error_type == "type_error.str":
            error_messages.append(f"Field '{field}' must be a string")
        elif error_type == "type_error.bool":
            error_messages.append(f"Field '{field}' must be a boolean")
        else:
            error_messages.append(f"Field '{field}': {message}")
    
    logger.error(f"Validation error on {request.url.path}: {error_messages}")
    
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={
            "detail": "; ".join(error_messages) if error_messages else "Validation error",
            "errors": errors
        }
    )

# Initialize scheduler for background tasks
scheduler = BackgroundScheduler()

# Initialize database on startup
@app.on_event("startup")
def startup_event():
    init_db()
    print("Application started - database initialized")
    
    # TOKEN PERSISTENCE: Load valid tokens from database on startup
    try:
        from app.utils.token_storage import load_all_tokens_from_db
        from app.utils.lama_token_cache import _token_cache, _get_cache_key
        import time
        
        all_tokens = load_all_tokens_from_db()
        valid_tokens = 0
        expired_tokens = 0
        
        current_time = time.time()
        for token_data in all_tokens:
            environment = token_data['environment']
            exchange_id = token_data['exchange_id']
            expires_at = token_data['expires_at']
            
            # Convert datetime to timestamp
            if isinstance(expires_at, datetime):
                expires_at_timestamp = expires_at.timestamp()
            else:
                expires_at_timestamp = time.mktime(expires_at.timetuple()) if hasattr(expires_at, 'timetuple') else 0
            
            if expires_at_timestamp > current_time:
                # Valid token - load into memory cache
                cache_key = _get_cache_key(environment, exchange_id)
                _token_cache[cache_key] = {
                    "token": token_data['token'],
                    "expires_at": expires_at_timestamp
                }
                valid_tokens += 1
                exchange_name = {1: "NSE", 2: "BSE", 4: "MCX", 5: "NCDEX"}.get(exchange_id, f"Exchange {exchange_id}")
                logger.info(f"[TOKEN_PERSISTENCE] ✅ Loaded valid token for {environment.upper()} {exchange_name} from database")
            else:
                # Expired token - delete from database
                from app.utils.token_storage import delete_token_from_db
                try:
                    delete_token_from_db(environment, exchange_id)
                    expired_tokens += 1
                except Exception as e:
                    logger.debug(f"[TOKEN_PERSISTENCE] Failed to delete expired token (non-critical): {e}")
        
        if valid_tokens > 0 or expired_tokens > 0:
            print(f"✓ Token persistence: Loaded {valid_tokens} valid token(s), deleted {expired_tokens} expired token(s) on startup")
            logger.info(f"[TOKEN_PERSISTENCE] Loaded {valid_tokens} valid token(s), deleted {expired_tokens} expired token(s) on startup")
    except Exception as e:
        print(f"⚠️  Token persistence loading failed (non-critical): {e}")
        logger.warning(f"[TOKEN_PERSISTENCE] Failed to load tokens on startup (non-critical): {e}", exc_info=True)
    
    # Initialize scheduler logger background worker (non-blocking async logging)
    try:
        from app.utils.scheduler_logger import _start_log_worker
        _start_log_worker()
        print("Scheduler logger background worker initialized (non-blocking async logging)")
    except Exception as e:
        print(f"Note: Scheduler logger worker initialization failed (non-critical): {e}")
        logger.warning(f"Scheduler logger worker initialization failed (non-critical): {e}")
    
    # PHASE 1 ERROR-PROOF IMPLEMENTATION: Setup graceful shutdown handlers
    try:
        from app.utils.graceful_shutdown import setup_signal_handlers
        setup_signal_handlers()
        print("✓ Graceful shutdown handlers registered (SIGTERM, SIGINT)")
        logger.info("[PHASE1] Graceful shutdown handlers registered")
    except Exception as e:
        print(f"⚠️  Graceful shutdown setup failed: {e}")
        logger.error(f"[PHASE1] Graceful shutdown setup failed: {e}", exc_info=True)

    # PHASE 4: WebSockets - Start Redis listener background task
    try:
        asyncio.create_task(redis_listener())
        print("✓ WebSocket Redis listener task started")
        logger.info("[PHASE4] WebSocket Redis listener task started")
    except Exception as e:
        print(f"⚠️  WebSocket listener failed to start: {e}")
        logger.error(f"[PHASE4] WebSocket listener failed to start: {e}")
    
    # PHASE 1 ERROR-PROOF IMPLEMENTATION: Run initial health checks
    try:
        from app.utils.health_monitor import run_all_health_checks
        health_results = run_all_health_checks()
        all_healthy = all(result.status for result in health_results.values())
        if all_healthy:
            print("✓ Health checks passed (disk space, memory, database)")
            logger.info("[PHASE1] All health checks passed")
        else:
            failed = [name for name, result in health_results.items() if not result.status]
            print(f"⚠️  Health check warnings: {', '.join(failed)}")
            logger.warning(f"[PHASE1] Health check warnings: {', '.join(failed)}")
    except Exception as e:
        print(f"⚠️  Health check failed: {e}")
        logger.error(f"[PHASE1] Health check failed: {e}", exc_info=True)
    
    # PROCESS ISOLATION: Schedulers are now run in a dedicated 'scheduler' process.
    # We only run them here if ENABLE_IN_PROCESS_SCHEDULER is explicitly set to 'true'.
    if os.getenv("ENABLE_IN_PROCESS_SCHEDULER", "false").lower() == "true":
        logger.info("Starting in-process scheduler (ENABLE_IN_PROCESS_SCHEDULER=true)")
        
        # Schedule data retention cleanup to run daily at 2 AM IST (Indian Standard Time)
        from pytz import timezone
        ist = timezone('Asia/Kolkata')
        scheduler.add_job(
            run_data_retention_cleanup,
            trigger=CronTrigger(hour=2, minute=0, timezone=ist),
            id='data_retention_cleanup',
            name='Data Retention Cleanup',
            replace_existing=True
        )
        
        # Schedule database metrics collection
        from app.utils.database_metrics_collector import collect_database_metrics
        scheduler.add_job(
            collect_database_metrics,
            trigger='interval',
            seconds=6,
            id='database_metrics_collection',
            name='Database Metrics Collection',
            replace_existing=True
        )

        # Schedule Prometheus metrics collection
        from app.utils.prom_metrics_collector import collect_prom_metrics
        scheduler.add_job(
            collect_prom_metrics,
            trigger='interval',
            seconds=10,
            id='prom_metrics_collection',
            name='Prometheus Metrics Collection',
            replace_existing=True,
            max_instances=2,
            coalesce=True
        )
        
        # Schedule server down monitoring
        from app.utils.server_down_monitor import server_down_monitor_scheduler
        scheduler.add_job(
            server_down_monitor_scheduler,
            trigger='interval',
            minutes=2,
            id='server_down_monitor',
            name='Server Down Monitor',
            replace_existing=True,
            max_instances=1,
            coalesce=True
        )

        # NEW: ECS Application Metrics Collector (1m resolution for compliance)
        from app.utils.ecs_app_collector import collect_ecs_app_metrics
        scheduler.add_job(
            collect_ecs_app_metrics,
            trigger='interval',
            minutes=1,
            id='ecs_app_metrics_collection',
            name='ECS Application Metrics Collection',
            replace_existing=True,
            max_instances=1,
            coalesce=True
        )
        logger.info("Scheduled: ECS Application Metrics Collection (Every 1m)")
        
        # All 4 exchange schedulers
        from app.schedulers import hardware_scheduler, network_scheduler, db_scheduler
        
        scheduler.add_job(
            hardware_scheduler,
            trigger=CronTrigger(minute='*/5', timezone=ist),
            id='hardware_scheduler',
            name='Hardware-Scheduler',
            replace_existing=True,
            max_instances=1,
            coalesce=True,
            misfire_grace_time=300
        )
        
        scheduler.add_job(
            network_scheduler,
            trigger=CronTrigger(minute='*/5', timezone=ist),
            id='network_scheduler',
            name='Network-Scheduler',
            replace_existing=True,
            max_instances=1,
            coalesce=True,
            misfire_grace_time=300
        )
        
        scheduler.add_job(
            db_scheduler,
            trigger=CronTrigger(minute='*/5', timezone=ist),
            id='db_scheduler',
            name='DB-Scheduler',
            replace_existing=True,
            max_instances=1,
            coalesce=True,
            misfire_grace_time=300
        )
        
        from app.utils.application_metrics_scheduler_v2 import run_application_metrics_scheduler
        scheduler.add_job(
            run_application_metrics_scheduler,
            trigger=CronTrigger(minute='*/5', timezone=ist),
            id='application_metrics_scheduler',
            name='Application-Scheduler',
            replace_existing=True,
            max_instances=1,
            coalesce=True,
            misfire_grace_time=300
        )
        
        # SSL certificate expiry check
        def check_certificate_expiry_wrapper():
            try:
                from app.routes.certificate_status import check_certificate_expiry as cert_check
                result = cert_check()
                if result.get('needs_alert'):
                    logger.info(f"[CERT] {result.get('message')}")
            except Exception as e:
                logger.error(f"[CERT] Error: {e}")
        
        scheduler.add_job(
            check_certificate_expiry_wrapper,
            trigger=CronTrigger(hour=9, minute=0, timezone=ist),
            id='certificate_expiry_check',
            name='SSL Certificate Expiry Check',
            replace_existing=True,
            misfire_grace_time=3600,
            coalesce=True
        )

        # PHASE 1 ERROR-PROOF IMPLEMENTATION: Start queue worker for processing failed metrics
        try:
            from app.utils.queue_worker import start_worker
            start_worker()
            print("✓ Queue worker started (In-Process Scheduler Mode)")
            logger.info("[PHASE1] Queue worker started (In-Process Scheduler Mode)")
        except Exception as e:
            print(f"⚠️  Queue worker initialization failed: {e}")
            logger.error(f"[PHASE1] Queue worker initialization failed: {e}", exc_info=True)

        scheduler.start()

        # Start self-healing watchdog (monitors all schedulers, auto-recovers)
        try:
            from app.utils.scheduler_watchdog import start_watchdog
            start_watchdog()
            print("✓ Self-healing scheduler watchdog started")
            logger.info("[WATCHDOG] Self-healing scheduler watchdog started")
        except Exception as e:
            print(f"⚠️  Watchdog initialization failed: {e}")
            logger.error(f"[WATCHDOG] Watchdog initialization failed: {e}", exc_info=True)
    else:
        logger.info("In-process scheduler is DISABLED (Process Isolation).")



    # Create/verify admin user from environment variables
    from app.db.db import engine, users_table
    from sqlalchemy import delete
    
    # CRITICAL FIX BUG-013: Require admin password from environment variable
    # Security: No hardcoded default password
    USER_EMAIL = os.getenv("ADMIN_EMAIL", "admin@lama.local")
    USER_PASS = os.getenv("ADMIN_PASSWORD")
    
    if not USER_PASS:
        error_msg = "ADMIN_PASSWORD environment variable is required. Please set it before starting the application."
        print(f"✗ CRITICAL ERROR: {error_msg}")
        logger.error(f"CRITICAL: {error_msg}")
        raise ValueError(error_msg)
    
    # Delete admin@smc.local if it exists (inactive user)
    ADMIN_EMAIL_TO_DELETE = "admin@smc.local"
    
    try:
        with engine.begin() as conn:  # Use begin() for automatic transaction management
            # Delete admin@smc.local if it exists
            query_delete = select(users_table).where(users_table.c.email == ADMIN_EMAIL_TO_DELETE)
            admin_to_delete = conn.execute(query_delete).fetchone()
            if admin_to_delete:
                delete_query = delete(users_table).where(users_table.c.email == ADMIN_EMAIL_TO_DELETE)
                conn.execute(delete_query)
                print(f"✓ Deleted inactive admin user: {ADMIN_EMAIL_TO_DELETE}")
            else:
                print(f"Admin user {ADMIN_EMAIL_TO_DELETE} not found (already deleted or never existed)")
            
            # Create/update admin user - Only set default password if user doesn't exist
            # Use SELECT ... FOR UPDATE to prevent race conditions during fresh build
            query2 = select(users_table).where(users_table.c.email == USER_EMAIL).with_for_update()
            result2 = conn.execute(query2).fetchone()
            
            if not result2:
                # User doesn't exist - create with default password
                hashed2 = bcrypt.hashpw(USER_PASS.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
                
                # Verify the hash works before saving
                test_verify = bcrypt.checkpw(USER_PASS.encode('utf-8'), hashed2.encode('utf-8'))
                if not test_verify:
                    print(f"✗ ERROR: Generated password hash verification failed for {USER_EMAIL}")
                else:
                    # Only insert if verification passed
                    try:
                        insert_query2 = users_table.insert().values(
                            email=USER_EMAIL,
                            password=hashed2,
                            role="admin",
                            is_active=True,
                            created_at=datetime.utcnow(),
                            updated_at=datetime.utcnow()
                        )
                        conn.execute(insert_query2)
                        print(f"✓ Admin user created: {USER_EMAIL} (role: admin)")
                    except Exception as ins_err:
                        # Handle race condition where another worker inserted between SELECT and INSERT
                        print(f"ℹ️  Admin user {USER_EMAIL} already created by another worker.")
            else:
                # User exists - only ensure admin role, DO NOT overwrite password
                stored_role = result2[5]  # role is at index 5
                if stored_role != "admin":
                    from sqlalchemy import update
                    update_query = update(users_table).where(
                        users_table.c.email == USER_EMAIL
                    ).values(role="admin", updated_at=datetime.utcnow())
                    conn.execute(update_query)
                    print(f"✓ Admin user role updated: {USER_EMAIL} (role: admin)")
                else:
                    print(f"✓ Admin user verified: {USER_EMAIL} (role: {stored_role}) - password preserved")
    except Exception as e:
        print(f"✗ ERROR creating/updating users: {e}")
        import traceback
        traceback.print_exc()
        # Don't fail startup if user creation fails, but log it

@app.on_event("shutdown")
def shutdown_event():
    """Cleanup on application shutdown"""
    try:
        from app.routes.metrics import cleanup_clients
        cleanup_clients()
        scheduler.shutdown()
        logger.info("Application shutdown complete (Scheduler and DB connections closed)")
    except Exception as e:
        logger.error(f"Error during shutdown: {e}")


# CORS Configuration - Security Fix (BUG-002)
# Restrict to specific domains instead of allowing all origins
# Production allowed origins
ALLOWED_ORIGINS_PROD = [
    "https://smcalert.smcindiaonline.com",
    "https://www.smcindiaonline.com",
]

# Development allowed origins
ALLOWED_ORIGINS_DEV = [
    "http://localhost:3000",
    "http://localhost:8000",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:8000",
]

# Determine allowed origins based on environment
if ENVIRONMENT == "prod":
    allowed_origins = ALLOWED_ORIGINS_PROD
elif ENVIRONMENT == "dev" or ENVIRONMENT == "development":
    allowed_origins = ALLOWED_ORIGINS_DEV + ALLOWED_ORIGINS_PROD
else:
    # Default to production for safety
    allowed_origins = ALLOWED_ORIGINS_PROD

# Allow additional origins from environment variable (comma-separated)
additional_origins = os.getenv("ALLOWED_ORIGINS", "")
if additional_origins:
    allowed_origins.extend([origin.strip() for origin in additional_origins.split(",")])

logger.info(f"[CORS] Environment: {ENVIRONMENT}, Allowed origins: {allowed_origins}")

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,  # Specific domains only (security fix)
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-Requested-With", "X-Environment", "Cookie"],
)

from app.utils.permissions import get_current_user
protected_dependency = [Depends(get_current_user)]

app.include_router(auth_router, prefix="/auth")
app.include_router(auth_router, prefix="/v1/auth") # Support both /auth and /v1/auth for mobile app
app.include_router(dashboard_router, prefix="/v1/dashboard", tags=["dashboard"], dependencies=protected_dependency)
app.include_router(users_router, prefix="/v1/users", dependencies=protected_dependency)
app.include_router(servers_router, prefix="/v1/servers", dependencies=protected_dependency)
app.include_router(metrics_router, prefix="/v1", dependencies=protected_dependency)
app.include_router(scheduler_status_router, prefix="/v1/schedulers", tags=["schedulers"], dependencies=protected_dependency)
app.include_router(logs_router, prefix="/v1", dependencies=protected_dependency)
app.include_router(config_router, prefix="/v1/lama-config", dependencies=protected_dependency)
app.include_router(retention_router, prefix="/v1/retention", dependencies=protected_dependency)
app.include_router(historical_data_router, prefix="/v1/historical", dependencies=protected_dependency)
app.include_router(thresholds_router, prefix="/v1/thresholds", dependencies=protected_dependency)
app.include_router(alert_config_router, prefix="/v1/alert-config", dependencies=protected_dependency)
app.include_router(database_config_router, prefix="/v1/database-config", tags=["database-config"], dependencies=protected_dependency)
app.include_router(alerts_router, prefix="/v1/alerts", tags=["alerts"], dependencies=protected_dependency)
app.include_router(lama_diagnostics_router, prefix="/v1/lama-diagnostics", tags=["lama-diagnostics"], dependencies=protected_dependency)
app.include_router(lama_server_selection_router, prefix="/v1/lama-config/server-selection", tags=["lama-server-selection"], dependencies=protected_dependency)
app.include_router(exchange_connectivity_errors_router, prefix="/v1", tags=["exchange-connectivity-errors"], dependencies=protected_dependency)
app.include_router(exchange_status_router, prefix="/v1/exchange", tags=["exchange-status"], dependencies=protected_dependency)
app.include_router(certificate_status_router, prefix="/v1", tags=["certificate-status"], dependencies=protected_dependency)
app.include_router(metric_sources_router, prefix="/v1", tags=["metric-sources"], dependencies=protected_dependency)
app.include_router(scheduler_config_router, prefix="/v1/scheduler-config", tags=["scheduler-config"], dependencies=protected_dependency)
app.include_router(raw_metrics_validation_router, prefix="/v1", tags=["raw-validation"], dependencies=protected_dependency)
app.include_router(websockets_router, tags=["websockets"])

# Mobile App Router
from app.routes.mobile import router as mobile_router
app.include_router(mobile_router, prefix="/v1/mobile", tags=["mobile"])
app.include_router(mobile_router, prefix="/mobile", tags=["mobile"]) # Alias for legacy mobile app support

# Import and register scheduler logs router
from app.routes.scheduler_logs import router as scheduler_logs_router
app.include_router(scheduler_logs_router, prefix="/v1", tags=["scheduler-logs"], dependencies=protected_dependency)

@app.get("/")
async def home():
    return {"msg": "Backend running"}

@app.get("/health")
async def health_check():
    """Health check endpoint for monitoring - only checks core services"""
    from app.db.db import engine
    
    health_status = {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "services": {}
    }
    
    # Check database connectivity (CRITICAL - must be working)
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        health_status["services"]["database"] = "connected"
    except Exception as e:
        health_status["services"]["database"] = f"error: {str(e)}"
        health_status["status"] = "unhealthy"  # Database failure = unhealthy
        return health_status
    
    # External service checks are non-blocking - don't mark as unhealthy if they fail
    # These are checked asynchronously and failures don't affect core functionality
    health_status["services"]["external_services"] = "checked separately (non-blocking)"
    
    # Always return healthy if database is connected
    # External service failures (LAMA Exchange) are logged but don't affect health status
    return health_status

@app.get("/api/diagnostics")
async def diagnostics(request: Request):
    """Diagnostics endpoint for troubleshooting LAMA Exchange connectivity"""
    import httpx
    import socket
    from datetime import datetime
    
    diagnostics = {
        "timestamp": datetime.utcnow().isoformat(),
        "server_info": {
            "hostname": socket.gethostname(),
            "ip_address": request.client.host if request.client else "unknown"
        },
        "lama_exchange": {
            "uat": {},
            "prod": {}
        },
        "network": {}
    }
    
    # Test UAT endpoint
    uat_url = "https://lama.uat.nseindia.com/api/V1/auth/login"
    try:
        # DNS resolution
        import socket
        hostname = "lama.uat.nseindia.com"
        ip = socket.gethostbyname(hostname)
        diagnostics["lama_exchange"]["uat"]["dns_resolution"] = f"OK - {ip}"
    except Exception as e:
        diagnostics["lama_exchange"]["uat"]["dns_resolution"] = f"FAILED - {str(e)}"
    
    try:
        # HTTPS connectivity
        timeout = httpx.Timeout(connect=5.0, read=10.0)
        with httpx.Client(timeout=timeout, verify=True, http2=False) as client:
            start_time = datetime.utcnow()
            response = client.get(uat_url, timeout=5.0)
            end_time = datetime.utcnow()
            duration = (end_time - start_time).total_seconds()
            diagnostics["lama_exchange"]["uat"]["connectivity"] = {
                "status": "OK",
                "status_code": response.status_code,
                "response_time_ms": round(duration * 1000, 2)
            }
    except Exception as e:
        diagnostics["lama_exchange"]["uat"]["connectivity"] = {
            "status": "FAILED",
            "error": str(e)[:200]
        }
    
    # Test PROD endpoint
    prod_url = "https://lama.nseindia.com/api/V1/auth/login"
    try:
        hostname = "lama.nseindia.com"
        ip = socket.gethostbyname(hostname)
        diagnostics["lama_exchange"]["prod"]["dns_resolution"] = f"OK - {ip}"
    except Exception as e:
        diagnostics["lama_exchange"]["prod"]["dns_resolution"] = f"FAILED - {str(e)}"
    
    try:
        timeout = httpx.Timeout(connect=5.0, read=10.0)
        with httpx.Client(timeout=timeout, verify=True, http2=False) as client:
            start_time = datetime.utcnow()
            response = client.get(prod_url, timeout=5.0)
            end_time = datetime.utcnow()
            duration = (end_time - start_time).total_seconds()
            diagnostics["lama_exchange"]["prod"]["connectivity"] = {
                "status": "OK",
                "status_code": response.status_code,
                "response_time_ms": round(duration * 1000, 2)
            }
    except Exception as e:
        diagnostics["lama_exchange"]["prod"]["connectivity"] = {
            "status": "FAILED",
            "error": str(e)[:200]
        }
    
    return diagnostics
