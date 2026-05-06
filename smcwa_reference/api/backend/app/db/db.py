"""
Database initialization module - creates all tables and indexes
Run this on application startup if tables don't exist
"""

import urllib.parse
import os
import logging
import clickhouse_connect
from sqlalchemy import create_engine, MetaData, Table, Column, Integer, String, DateTime, Text, Float, Boolean, JSON, BigInteger, ForeignKey, text, UniqueConstraint

# Initialize logger
logger = logging.getLogger(__name__)

# ClickHouse Client for high-performance metric queries
CLICKHOUSE_HOST = os.getenv("CLICKHOUSE_HOST", "lama_clickhouse")
CLICKHOUSE_PORT = int(os.getenv("CLICKHOUSE_PORT", 8123))
CLICKHOUSE_USER = os.getenv("CLICKHOUSE_USER", "default")
CLICKHOUSE_PASSWORD = os.getenv("CLICKHOUSE_PASSWORD", "")

try:
    clickhouse_client = clickhouse_connect.get_client(
        host=CLICKHOUSE_HOST,
        port=CLICKHOUSE_PORT,
        username=CLICKHOUSE_USER,
        password=CLICKHOUSE_PASSWORD,
        connect_timeout=10
    )
    logger.info("✅ ClickHouse client initialized successfully")
except Exception as e:
    logger.error(f"❌ Failed to initialize ClickHouse client: {e}")
    clickhouse_client = None

from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import sessionmaker
from datetime import datetime

POSTGRES_HOST = os.getenv("POSTGRES_HOST", "postgres_prod")
POSTGRES_USER = os.getenv("POSTGRES_USER", "lama")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "")
POSTGRES_DB = os.getenv("POSTGRES_DB", "lama_prod")

safe_password = urllib.parse.quote(POSTGRES_PASSWORD)
DATABASE_URL = f"postgresql://{POSTGRES_USER}:{safe_password}@{POSTGRES_HOST}:5432/{POSTGRES_DB}"

# Optimize connection pool for better performance
# pool_size: Number of connections to maintain in pool
# max_overflow: Maximum number of connections beyond pool_size
# pool_pre_ping: Test connections before using (prevents stale connections)
# pool_recycle: Recycle connections frequently to prevent stale connections
engine = create_engine(
    DATABASE_URL,
    echo=False,
    pool_size=50,  # Increased to 50 to handle 200+ concurrent server heartbeats
    max_overflow=20,  # Increased overflow
    pool_pre_ping=True,  # Test connections before using
    pool_recycle=3600,  # Recycle connections after 1 hour (increased from 300s to avoid aggressive recycling)
    connect_args={
        "connect_timeout": 10,  # 10 second connection timeout
        "application_name": "smc_lama_backend"
    }
)

# Dispose of any existing connections on module import (fresh start)
try:
    engine.dispose()
    logger.info("Database connection pool disposed - starting fresh")
except Exception as e:
    logger.warning(f"Could not dispose connection pool: {e}")
metadata = MetaData()

# ============= TABLE DEFINITIONS =============

users_table = Table(
    "users",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("email", String(255), unique=True, nullable=True),  # Nullable to allow mobile-only users
    Column("mobile", String(20), unique=True, nullable=True),  # Mobile number for login
    Column("password", Text, nullable=False),
    Column("full_name", String(255), nullable=True),  # Full name field
    Column("role", String(50), default="user"),
    Column("is_active", Boolean, default=True),
    Column("created_at", DateTime, default=datetime.utcnow),
    Column("updated_at", DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
)

application_status_table = Table(
    "application_status",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("name", String(255), nullable=False),
    Column("ip", String(255), nullable=True),
    Column("environment", String(50), default="prod"),
    Column("status", String(50), default="offline"),
    Column("location_id", Integer, default=1),
    Column("external_id", String(255), nullable=True),
    Column("source_id", Integer, ForeignKey("metric_sources.id", ondelete="SET NULL"), nullable=True), # Link to discovery source
    Column("cpu", Float, default=0),
    Column("memory", Float, default=0),
    Column("uptime_seconds", Float, nullable=True),
    Column("latency_ms", Float, nullable=True),
    Column("throughput", Float, default=0),
    Column("throughput_req_sec", Float, nullable=True),
    Column("failure_trade_api", Float, default=0),
    Column("failure_authentication", Float, default=0),
    Column("last_seen", DateTime, nullable=True),
    Column("created_at", DateTime, default=datetime.utcnow),
    Column("updated_at", DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
)

database_status_table = Table(
    "database_status",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("name", String(255), nullable=False),
    Column("engine", String(50), nullable=False),
    Column("environment", String(50), default="prod"),
    Column("status", String(50), default="offline"),
    Column("location_id", Integer, default=1),
    Column("external_id", String(255), nullable=True),
    Column("source_id", Integer, ForeignKey("metric_sources.id", ondelete="SET NULL"), nullable=True), # Link to discovery source
    Column("cpu", Float, default=0),
    Column("memory", Float, default=0),
    Column("disk", Float, default=0),
    Column("connections", Integer, nullable=True),
    Column("query_latency_ms", Float, nullable=True),
    Column("cache_hit_ratio", Float, nullable=True),
    Column("last_seen", DateTime, nullable=True),
    Column("created_at", DateTime, default=datetime.utcnow),
    Column("updated_at", DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
)

server_status_table = Table(
    "server_status",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("name", String(255), nullable=False),
    Column("ip", String(255), nullable=False),
    Column("public_ip", String(45), nullable=True), # Added to store remote source IP
    Column("detected_ips", JSON, nullable=True), # Store all IPs detected by agent
    Column("status", String(50), default="offline"),
    Column("environment", String(50), default="prod"),  # 'prod' or 'uat'
    Column("os_type", String(50), default="Linux"),  # 'Windows', 'Linux', 'macOS', etc.
    Column("os_name", String(255), nullable=True),   # Descriptive OS name (e.g. 'Windows Server 2019', 'Ubuntu 22.04')
    Column("external_id", String(255), nullable=True), # AWS InstanceID, RDS ID, etc.
    Column("cpu", Float, default=0),
    Column("memory", Float, default=0),
    Column("disk", Float, default=0),
    Column("uptime", Float, default=0),
    Column("network_bandwidth", Float, default=0),      # Aggregated utilization %
    Column("packet_count", Float, default=0),      # Network packet errors
    Column("network_speed", BigInteger, default=0), # Link capacity in bits/sec
    Column("location_id", Integer, default=1),      # LAMA V1.3: 1=DC, 2=DR, 3=Cloud
    Column("source_id", Integer, ForeignKey("metric_sources.id", ondelete="SET NULL"), nullable=True), # Link to discovery source
    Column("last_seen", DateTime, default=datetime.utcnow),
    Column("created_at", DateTime, default=datetime.utcnow),
    Column("updated_at", DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
)

# New: AWS Ignore List to prevent re-discovery of manually deleted items
aws_ignore_list_table = Table(
    "aws_ignore_list",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("external_id", String(255), unique=True, nullable=False), # ARN or InstanceID
    Column("resource_type", String(50), nullable=False), # 'ec2', 'rds', 'ecs'
    Column("environment", String(50), nullable=True),
    Column("created_at", DateTime, default=datetime.utcnow)
)

server_metrics_table = Table(
    "server_metrics",
    metadata,
    Column("id", BigInteger, primary_key=True, autoincrement=True),
    Column("server_id", Integer, ForeignKey("server_status.id", ondelete="CASCADE"), nullable=False),
    Column("metric_name", String(100), nullable=False),
    Column("value", Float, nullable=False),
    Column("interface_name", String(100), nullable=True),  # For per-interface metrics (e.g., "eth0", "Ethernet")
    Column("ts", DateTime, default=datetime.utcnow)
)

application_metrics_storage_table = Table(
    "application_metrics_storage",
    metadata,
    Column("id", BigInteger, primary_key=True, autoincrement=True),
    Column("metric_name", String(100), nullable=False),
    Column("min_value", Float, nullable=True),
    Column("max_value", Float, nullable=True),
    Column("avg_value", Float, nullable=True),
    Column("med_value", Float, nullable=True),
    Column("value", Float, nullable=True),
    Column("ts", DateTime, default=datetime.utcnow)
)

audit_logs_table = Table(
    "audit_logs",
    metadata,
    Column("id", BigInteger, primary_key=True, autoincrement=True),
    Column("user_id", Integer, ForeignKey("users.id", ondelete="SET NULL")),
    Column("action", String(255), nullable=False),
    Column("resource_type", String(100)),
    Column("resource_id", Integer),
    Column("details", JSON),
    Column("created_at", DateTime, default=datetime.utcnow)
)

alerts_table = Table(
    "alerts",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("server_id", Integer, ForeignKey("server_status.id", ondelete="CASCADE")),
    Column("site_name", String(255), nullable=True),
    Column("alert_type", String(100), nullable=False),
    Column("severity", String(50), nullable=False),
    Column("message", Text),
    Column("is_resolved", Boolean, default=False),
    Column("metric_value", Float, nullable=True),
    Column("threshold_value", Float, nullable=True),
    Column("created_at", DateTime, default=datetime.utcnow),
    Column("resolved_at", DateTime)
)

lama_config_table = Table(
    "lama_config",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("environment", String(50), nullable=False),  # 'prod' or 'uat'
    Column("enabled", Boolean, default=False),
    Column("lama_api_url", String(255)), # New: Source of truth for API URL
    Column("member_id", String(255)),
    Column("login_id", String(255)),
    Column("password", Text),  # Encrypted password
    Column("secret_key", Text),  # Encrypted secret key
    Column("created_at", DateTime, default=datetime.utcnow),
    Column("updated_at", DateTime, default=datetime.utcnow, onupdate=datetime.utcnow),
    # Ensure one config per environment
    Column("unique_environment", String(50), unique=True)
)

# LAMA Exchange metric configuration table - controls which metric types are sent
lama_exchange_metric_config_table = Table(
    "lama_exchange_metric_config",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("environment", String(50), nullable=False),  # 'prod' or 'uat'
    Column("metric_type", String(20), nullable=False),  # 'hardware', 'network', 'database', 'application'
    Column("enabled", Boolean, default=True),
    Column("created_at", DateTime, default=datetime.utcnow),
    Column("updated_at", DateTime, default=datetime.utcnow, onupdate=datetime.utcnow),
    # Ensure one config per environment and metric type
    Column("unique_env_metric", String(70), unique=True)
)

# LAMA Exchange configuration table - controls which exchanges are enabled per environment
lama_exchange_config_table = Table(
    "lama_exchange_config",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("environment", String(50), nullable=False),  # 'prod' or 'uat'
    Column("exchange_id", Integer, nullable=False),  # NSE=1, BSE=2, MCX=4, NCDEX=5
    Column("enabled", Boolean, default=False),
    Column("created_at", DateTime, default=datetime.utcnow),
    Column("updated_at", DateTime, default=datetime.utcnow, onupdate=datetime.utcnow),
    UniqueConstraint("environment", "exchange_id", name="unique_env_exchange")
)

# Login lock status table - tracks soft block and manual lock status per environment/exchange
login_lock_status_table = Table(
    "login_lock_status",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("environment", String(50), nullable=False),  # 'prod' or 'uat'
    Column("exchange_id", Integer),  # NULL = all exchanges, or 1, 2, 4, 5
    Column("soft_block", Boolean, default=False),  # Automatic soft block after 3 failed attempts
    Column("soft_block_at", DateTime),  # When soft block was set
    Column("soft_block_cleared_at", DateTime),  # When soft block was cleared
    Column("manual_lock", Boolean, default=False),  # Manual permanent lock
    Column("locked_by", Integer, ForeignKey("users.id", ondelete="SET NULL")),  # User who locked
    Column("locked_at", DateTime),  # When manual lock was set
    Column("unlocked_at", DateTime),  # When manual lock was cleared
    Column("reason", Text),  # Reason for lock
    Column("last_error_message", Text),  # Last error message for context
    # Error 907 (LAMA account locked) persistence - survives container restarts
    Column("error_907_locked", Boolean, default=False),  # True when LAMA returns Error 907
    Column("error_907_locked_at", DateTime),  # When Error 907 was received
    Column("error_907_cleared_at", DateTime),  # When Error 907 was cleared (admin action or successful login)
    # Failed login attempts persistence - survives container restarts
    Column("failed_attempts", Integer, default=0),  # Count of consecutive failed login attempts
    Column("last_failed_at", DateTime),  # When the last failed attempt occurred
    Column("created_at", DateTime, default=datetime.utcnow),
    Column("updated_at", DateTime, default=datetime.utcnow, onupdate=datetime.utcnow),
    UniqueConstraint("environment", "exchange_id", name="unique_env_exchange_lock")
)

# LAMA Exchange server selection table - controls which servers send metrics per environment
lama_exchange_server_selection_table = Table(
    "lama_exchange_server_selection",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("environment", String(50), nullable=False),  # 'prod' or 'uat'
    Column("server_id", Integer, ForeignKey("server_status.id", ondelete="CASCADE"), nullable=False),
    Column("enabled", Boolean, default=True),
    Column("metric_source", String(20), default="auto"),  # 'auto', 'onprem', 'aws'
    Column("created_at", DateTime, default=datetime.utcnow),
    Column("updated_at", DateTime, default=datetime.utcnow, onupdate=datetime.utcnow),
    UniqueConstraint("environment", "server_id", name="unique_env_server")
)

# Exchange transactions table - tracks all data sent to LAMA Exchange
exchange_transactions_table = Table(
    "exchange_transactions",
    metadata,
    Column("id", BigInteger, primary_key=True, autoincrement=True),
    Column("environment", String(50), nullable=False),  # 'prod' or 'uat'
    Column("server_id", String(100)),  # Changed from Integer to String to support scheduler names
    Column("server_name", Text),
    Column("server_ip", Text),  # Changed from String(45) to Text to support comma-separated lists
    Column("member_id", String(255)),
    Column("instance_id", String(255)),  # Server IP or instance identifier
    Column("metric_type", String(50), nullable=False),  # 'hardware', 'network', 'database', 'application'
    Column("metrics_sent", JSON, nullable=False),  # Full metrics payload sent
    Column("sequence_id", String(255)),  # Sequence ID received from exchange (if any)
    Column("exchange_response", JSON),  # Full response from exchange
    Column("status", String(50), nullable=False),  # 'success', 'failed', 'error'
    Column("status_code", Integer),  # HTTP status code
    Column("error_message", Text),  # Error message if failed
    Column("sent_at", DateTime, default=datetime.utcnow),
    Column("response_received_at", DateTime),  # When response was received
    Column("exchange_id", Integer),  # 1=NSE, 2=BSE, 4=MCX, 5=NCDEX
    Column("location_id", Integer, default=1),  # 1=DC, 2=DR, 3=Cloud
    Column("record_type", String(50), server_default="sent"), # 'sent', 'hint'
    Column("original_metrics", JSON) # Store breakdown data for individual server display
)

# Sequence ID reservation table - LONG-TERM FIX: Atomic reservation to prevent race conditions
# Reserves sequence IDs before sending to guarantee uniqueness
sequence_id_reservations_table = Table(
    "sequence_id_reservations",
    metadata,
    Column("id", BigInteger, primary_key=True, autoincrement=True),
    Column("environment", String(50), nullable=False),  # 'prod' or 'uat'
    Column("member_id", String(255), nullable=False),
    Column("exchange_id", Integer, nullable=False),  # 1=NSE, 2=BSE, 4=MCX, 5=NCDEX
    Column("metric_type", String(50), nullable=False),  # 'hardware', 'network', 'database', 'application'
    Column("sequence_id", Integer, nullable=False),  # Reserved sequence ID
    Column("reservation_status", String(50), nullable=False, default="reserved"),  # 'reserved', 'used', 'expired', 'cancelled'
    Column("scheduler_name", String(100)),  # Which scheduler reserved this ID
    Column("reserved_at", DateTime, nullable=False, default=datetime.utcnow),  # When reserved
    Column("used_at", DateTime),  # When actually used (status='used')
    Column("expires_at", DateTime, nullable=False),  # Reservation expiry (5 minutes from reserved_at)
    Column("transaction_id", BigInteger, ForeignKey("exchange_transactions.id", ondelete="SET NULL")),  # Link to actual transaction
    Column("location_id", Integer, default=1),      # 1=DC, 2=DR, 3=Cloud
    UniqueConstraint("environment", "member_id", "exchange_id", "metric_type", "location_id", "sequence_id", name="unique_seq_reservation")
)

# Alert thresholds table - stores threshold configurations for metrics
alert_thresholds_table = Table(
    "alert_thresholds",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("metric_type", String(50), nullable=False),  # 'hardware', 'network', 'database', 'application'
    Column("metric_key", String(100), nullable=False),  # e.g., 'cpu', 'memory', 'throughput', etc.
    Column("warning_threshold", Float, nullable=False),
    Column("error_threshold", Float, nullable=False),
    Column("enabled", Boolean, default=True),
    Column("created_at", DateTime, default=datetime.utcnow),
    Column("updated_at", DateTime, default=datetime.utcnow, onupdate=datetime.utcnow),
    # Ensure unique metric_type + metric_key combination
    Column("unique_metric", String(150), unique=True)
)

# Alert configuration table - stores email, Slack, and mobile alert settings
alert_config_table = Table(
    "alert_config",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("alert_channel", String(50), nullable=False),  # 'email', 'slack', 'mobile'
    Column("enabled", Boolean, default=False),
    # Email configuration
    Column("smtp_host", String(255)),
    Column("smtp_port", Integer),
    Column("smtp_username", String(255)),
    Column("smtp_password", Text),  # Encrypted
    Column("smtp_from_email", String(255)),
    Column("smtp_to_emails", JSON),  # Array of email addresses
    Column("smtp_to_user_ids", JSON),  # Array of user IDs to send alerts to
    Column("smtp_use_tls", Boolean, default=True),
    # Slack configuration
    Column("slack_webhook_url", Text),  # Encrypted
    Column("slack_channel", String(255)),
    Column("slack_to_user_ids", JSON),  # Array of user IDs (for future use)
    # Mobile/SMS configuration
    Column("sms_provider", String(50)),  # 'twilio', 'aws_sns', etc.
    Column("sms_api_key", Text),  # Encrypted
    Column("sms_api_secret", Text),  # Encrypted
    Column("sms_from_number", String(50)),
    Column("sms_to_numbers", JSON),  # Array of phone numbers
    Column("sms_to_user_ids", JSON),  # Array of user IDs to send alerts to
    # Voice Call configuration (C-Zentrix)
    Column("voice_provider", String(50), default="c-zentrix"),
    Column("voice_api_url", String(255)),

    Column("voice_to_numbers", JSON),  # Array of phone numbers
    Column("voice_to_user_ids", JSON),  # Array of user IDs
    Column("voice_campaign_name", String(100)),  # C-Zentrix Department/Campaign
    Column("voice_client_id", String(100)),  # C-Zentrix Client ID
    Column("created_at", DateTime, default=datetime.utcnow),
    Column("updated_at", DateTime, default=datetime.utcnow, onupdate=datetime.utcnow),
    # Ensure one config per channel
    Column("unique_channel", String(50), unique=True)
)

# Database configuration table - stores database credentials for monitoring replication/sync
database_config_table = Table(
    "database_config",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("server_id", Integer, ForeignKey("server_status.id", ondelete="SET NULL"), nullable=True),
    Column("db_type", String(50), nullable=False),  # 'postgresql', 'mysql', 'mongodb', etc.
    Column("host", String(255), nullable=False),
    Column("port", Integer, nullable=False),
    Column("database", String(255), nullable=False),
    Column("username", String(255), nullable=False),
    Column("password", Text, nullable=False),  # Encrypted
    Column("is_replication", Boolean, default=False),  # Whether this is a replication database
    Column("master_host", String(255)),  # Master database host
    Column("master_port", Integer),  # Master database port
    Column("enabled", Boolean, default=True),
    Column("location_id", Integer, default=1),      # 1=DC, 2=DR, 3=Cloud
    Column("created_at", DateTime, default=datetime.utcnow),

    Column("updated_at", DateTime, default=datetime.utcnow, onupdate=datetime.utcnow),
    # Ensure one config per server
    Column("unique_server_db", String(100), unique=True)
)

# Elasticsearch configuration table - stores Elasticsearch connection details for application metrics
# Supports dual configuration (Primary DC + Standby DR) with automatic failover
elasticsearch_config_table = Table(
    "elasticsearch_config",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("environment", String(50), nullable=False),  # 'prod' or 'uat'
    
    # Legacy columns (kept for backwards compatibility)
    Column("ip", String(255)),
    Column("type", String(100), default="63 Moons - ElasticSearch"),
    Column("host", String(255)),
    Column("port", Integer, default=9200),
    Column("username", String(255)),
    Column("password", Text),
    
    # Dual Elasticsearch configuration (DC/DR)
    Column("active_server", String(20), default="primary"),  # 'primary' or 'standby'
    Column("auto_failover", Boolean, default=True),
    
    # Primary (DC) server configuration
    Column("primary_ip", String(255)),
    Column("primary_type", String(100), default="DC - ElasticSearch"),
    Column("primary_host", String(255)),
    Column("primary_port", Integer, default=9200),
    Column("primary_username", String(255)),
    Column("primary_password", Text),
    
    # Standby (DR) server configuration
    Column("standby_ip", String(255)),
    Column("standby_type", String(100), default="DR - ElasticSearch"),
    Column("standby_host", String(255)),
    Column("standby_port", Integer, default=9200),
    Column("standby_username", String(255)),
    Column("standby_password", Text),
    
    # Health monitoring
    Column("primary_status", String(50), default="unknown"),  # 'connected', 'disconnected', 'unknown'
    Column("standby_status", String(50), default="unknown"),
    Column("primary_enabled", Boolean, default=True),  # Enable/disable primary (DC) server
    Column("standby_enabled", Boolean, default=False),  # Enable/disable standby (DR) server
    Column("last_health_check", DateTime),
    Column("last_failover_at", DateTime),
    Column("failover_count", Integer, default=0),
    
    Column("enabled", Boolean, default=False),
    Column("created_at", DateTime, default=datetime.utcnow),
    Column("updated_at", DateTime, default=datetime.utcnow, onupdate=datetime.utcnow),
    
    # Ensure one config per environment
    Column("unique_environment", String(50), unique=True)
)

# Application metrics configuration table - stores metric-specific settings
app_metrics_config_table = Table(
    "app_metrics_config",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("environment", String(50), nullable=False),  # 'prod' or 'uat'
    Column("metric_name", String(100), nullable=False),  # 'throughput', 'latency', 'failureTradeApi', etc.
    Column("warning_threshold", Float),
    Column("critical_threshold", Float),
    Column("index_name", String(255), nullable=False),  # Elasticsearch index name
    Column("db_query", Text, nullable=False),  # Database query to fetch data
    Column("enabled", Boolean, default=True),
    Column("server_type", String(20), default="dc"),  # 'dc' or 'dr' - which server this metric applies to
    Column("created_at", DateTime, default=datetime.utcnow),
    Column("updated_at", DateTime, default=datetime.utcnow, onupdate=datetime.utcnow),
    # Ensure unique metric per environment
    Column("unique_metric_env", String(150), unique=True)
)

# Scheduler logs table - stores structured scheduler logs for visibility and debugging
# Retention: 10 days (logs older than 10 days are automatically deleted)
scheduler_logs_table = Table(
    "scheduler_logs",
    metadata,
    Column("id", BigInteger, primary_key=True, autoincrement=True),
    Column("timestamp", DateTime, nullable=False, default=datetime.utcnow, index=True),  # Indexed for fast queries
    Column("scheduler_name", String(100), nullable=False, index=True),  # 'Hardware-Scheduler', 'Network-Scheduler', etc.
    Column("environment", String(50), nullable=False, index=True),  # 'uat' or 'prod'
    Column("exchange_id", Integer, nullable=True, index=True),  # NSE=1, BSE=2, MCX=4, NCDEX=5
    Column("exchange_name", String(50)),  # 'NSE', 'BSE', 'MCX', 'NCDEX'
    Column("metric_type", String(50), nullable=True, index=True),  # 'hardware', 'network', 'database', 'application'
    Column("log_type", String(50), nullable=False, index=True),  # 'token', 'sequence_id', 'scheduler', 'error', 'success'
    Column("action", String(100), nullable=False),  # 'login', 'token_cached', 'token_used', 'sequence_calculated', 'metrics_sent', etc.
    Column("message", Text, nullable=False),  # Human-readable log message
    Column("details", JSON, nullable=True),  # Structured details: {token_preview, sequence_id, response_code, etc.}
    Column("status", String(50), nullable=True),  # 'success', 'failed', 'warning', 'info'
    Column("duration_ms", Integer, nullable=True),  # Duration in milliseconds for operations
    Column("created_at", DateTime, default=datetime.utcnow, index=True)
)

# Persistent queue table - stores metrics before sending to guarantee zero data loss
# PHASE 1 ERROR-PROOF IMPLEMENTATION: Store-first approach
# Retention: 7 days for failed/expired metrics, 1 day for successful metrics
metric_queue_table = Table(
    "metric_queue",
    metadata,
    Column("id", BigInteger, primary_key=True, autoincrement=True),
    Column("environment", String(50), nullable=False, index=True),  # 'uat' or 'prod'
    Column("exchange_id", Integer, nullable=False, index=True),  # NSE=1, BSE=2, MCX=4, NCDEX=5
    Column("exchange_name", String(50), nullable=False),  # 'NSE', 'BSE', 'MCX', 'NCDEX'
    Column("scheduler_name", String(100), nullable=False, index=True),  # 'Hardware-Scheduler', 'Network-Scheduler', etc.
    Column("metric_type", String(50), nullable=False, index=True),  # 'hardware', 'network', 'database', 'application'
    Column("sequence_id", Integer, nullable=False),  # Sequence ID for this metric
    Column("payload", JSON, nullable=False),  # Complete metric payload to send
    Column("status", String(50), nullable=False, default="pending", index=True),  # 'pending', 'sent', 'failed', 'expired'
    Column("retry_count", Integer, nullable=False, default=0),  # Number of retry attempts
    Column("max_retries", Integer, nullable=False, default=7),  # Maximum retry attempts (7 days total)
    Column("next_retry_at", DateTime, nullable=True, index=True),  # When to retry next (exponential backoff)
    Column("error_message", Text, nullable=True),  # Error message if failed
    Column("error_code", String(50), nullable=True),  # LAMA API error code (704, 801, etc.)
    Column("expected_sequence_id", Integer, nullable=True),  # Expected sequence ID from Error 704 response
    Column("sent_at", DateTime, nullable=True),  # When successfully sent
    Column("created_at", DateTime, nullable=False, default=datetime.utcnow, index=True),  # When queued
    Column("updated_at", DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow),
    # Indexes for efficient queue processing
    # Note: Additional indexes will be created in create_indexes.py
)

# LAMA tokens table - stores authentication tokens for persistence across restarts
# TOKEN PERSISTENCE IMPLEMENTATION: Database storage for token recovery
# Tokens are stored with expiry timestamp and loaded on startup
lama_tokens_table = Table(
    "lama_tokens",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("environment", String(10), nullable=False),  # 'uat' or 'prod'
    Column("exchange_id", Integer, nullable=False),  # 1=NSE, 2=BSE, 4=MCX, 5=NCDEX
    Column("token", Text, nullable=False),  # Encrypted token from LAMA API
    Column("expires_at", DateTime, nullable=False),  # Token expiry time (24 hours from generation)
    Column("created_at", DateTime, default=datetime.utcnow),
    Column("updated_at", DateTime, default=datetime.utcnow, onupdate=datetime.utcnow),
    Column("last_used_at", DateTime, nullable=True),  # Last time token was used
    Column("login_count", Integer, default=0),  # Number of times logged in (for this token)
    Column("status", String(20), default="active"),  # 'active', 'expired', 'invalid'
    Column("credential_hash", String(64), nullable=True),  # Hash of credentials used to generate token (for proactive invalidation)
    UniqueConstraint("environment", "exchange_id", name="unique_env_exchange_token")
)

# Scheduler state table - persists states like last successful run, historical metrics index, etc.
scheduler_config_table = Table(
    "scheduler_config",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("job_id", String(100), unique=True, nullable=False),
    Column("name", String(200), nullable=False),
    Column("cron_expression", String(100)),
    Column("interval_minutes", Integer),
    Column("enabled", Boolean, default=True),
    Column("description", Text),
    Column("created_at", DateTime, default=datetime.utcnow),
    Column("updated_at", DateTime, default=datetime.utcnow, onupdate=datetime.utcnow),
)

scheduler_state_table = Table(
    "scheduler_state",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("environment", String(50), nullable=False),
    Column("key", String(100), nullable=False),
    Column("value", Text),
    Column("updated_at", DateTime, default=datetime.utcnow, onupdate=datetime.utcnow),
    UniqueConstraint("environment", "key", name="unique_env_key")
)

component_health_table = Table(
    "component_health",
    metadata,
    Column("id", BigInteger, primary_key=True, autoincrement=True),
    Column("component_name", String(100), nullable=False),
    Column("environment", String(50), nullable=True),
    Column("status", String(20), nullable=False),
    Column("severity", String(20), nullable=False, default="info"),
    Column("summary", String(255)),
    Column("details", JSON),
    Column("last_error", Text),
    Column("updated_at", DateTime, default=datetime.utcnow, onupdate=datetime.utcnow),
    UniqueConstraint("component_name", "environment", name="unique_component_health")
)

# Generic Metric Sources - Support for N application servers (Elasticsearch, SQL, etc.)
metric_sources_table = Table(
    "metric_sources",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("name", String(100), nullable=False),  # e.g., "Trading App 1", "Logs DB"
    Column("type", String(50), nullable=False),   # 'elasticsearch', 'mysql', 'postgresql', 'mssql'
    Column("config", JSON, nullable=False),       # Connection details {host, port, auth...}
    Column("environment", String(50), nullable=False),  # 'prod', 'uat'
    Column("enabled", Boolean, default=True),
    Column("location_id", Integer, default=1),      # 1=DC, 2=DR, 3=Cloud
    Column("created_at", DateTime, default=datetime.utcnow),
    Column("updated_at", DateTime, default=datetime.utcnow, onupdate=datetime.utcnow),
    Column("historical_precalculated", Boolean, default=False),  # True = skip 21-day calc, historicals from Prometheus
)

# Configured Queries for each source
metric_queries_table = Table(
    "metric_queries",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("source_id", Integer, ForeignKey("metric_sources.id", ondelete="CASCADE"), nullable=False),
    Column("location_id", Integer, default=1),      # 1=DC, 2=DR, 3=Cloud
    Column("metric_name", String(100), nullable=False),  # 'throughput', 'latency', 'failureTradeApi'
    Column("index_name", String(255)),                   # Elasticsearch index pattern or specific table context
    Column("query_payload", Text, nullable=False),       # The actual query (JSON for ES, SQL for DB)
    Column("value_field", String(100)),                  # Which field to extract from result (e.g. 'avg_val')
    Column("warning_threshold", Float),
    Column("critical_threshold", Float),
    Column("enabled", Boolean, default=True),
    Column("created_at", DateTime, default=datetime.utcnow),
    Column("updated_at", DateTime, default=datetime.utcnow, onupdate=datetime.utcnow),
    UniqueConstraint("source_id", "metric_name", name="unique_source_metric")
)

# Sequence tracking per exchange (V2.0 Architecture)
lama_sequence_table = Table(
    "lama_sequence",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("exchange_id", Integer, nullable=False),
    Column("environment", String(10), nullable=False),
    Column("metric_type", String(50), nullable=True),  # Added for Bug 2
    Column("current_seq", BigInteger, nullable=False, default=0),
    Column("last_updated", DateTime, default=datetime.utcnow, onupdate=datetime.utcnow),
    UniqueConstraint("exchange_id", "environment", "metric_type", name="unique_exchange_env_metric_seq")
)

lama_prepared_metrics_table = Table(
    "lama_prepared_metrics",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("environment", String(10), nullable=False),  
    Column("metric_type", String(50)), # NEW: hardware, network, app, database
    Column("member_id", String(50), nullable=False),  
    Column("tokens", JSON, nullable=True), # Made nullable for early raw capture
    Column("enabled_exchanges", ARRAY(Integer), nullable=True),  
    Column("metric_config", JSON, nullable=True),  
    Column("raw_data_snapshot", JSON), # NEW: Immutable raw points from source
    Column("source_metadata", JSON), # NEW: Exact API params used for fetch
    Column("calculated_stats", JSON), # NEW: Local math results
    Column("individual_details", JSON), # NEW: Per-server breakdown
    Column("location_id", Integer, default=1), # LAMA V1.3: 1=DC, 2=DR, 3=Cloud
    Column("prepared_at", DateTime, nullable=False),  
    Column("send_time", DateTime, nullable=False),  
    Column("status", String(20), default="prepared"),  # prepared, calculating, sending, success, failed
    Column("sent_at", DateTime, nullable=True),  
    Column("error_message", Text, nullable=True),  
    Column("created_at", DateTime, default=datetime.utcnow),
    Column("updated_at", DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def init_db():
    """Create all tables if they don't exist"""
    # Import mobile models here to avoid circular imports during MetaData registration
    try:
        from app.models.mobile import (
            mobile_devices_table, 
            escalation_policies_table, 
            active_escalations_table, 
            mobile_alerts_table
        )
        logger.info("Mobile tables registered with metadata for creation")
    except ImportError:
        logger.warning("Could not import mobile models in init_db")

    metadata.create_all(bind=engine)
    
    # Add environment column if it doesn't exist (migration)
    try:
        with engine.connect() as conn:
            # Check if lama_api_url column exists in lama_config
            result = conn.execute(
                text("SELECT column_name FROM information_schema.columns WHERE table_name='lama_config' AND column_name='lama_api_url'")
            ).fetchone()
            if not result:
                conn.execute(text("ALTER TABLE lama_config ADD COLUMN lama_api_url VARCHAR(255)"))
                # Set defaults based on environment
                conn.execute(text("UPDATE lama_config SET lama_api_url = 'https://lama.uat.nseindia.com/api/V1' WHERE environment = 'uat'"))
                conn.execute(text("UPDATE lama_config SET lama_api_url = 'https://lama.nseindia.com/api/V1' WHERE environment = 'prod'"))
                conn.commit()
                print("Added lama_api_url column to lama_config table")

            # Check if environment column exists
            result = conn.execute(
                text("SELECT column_name FROM information_schema.columns WHERE table_name='server_status' AND column_name='environment'")
            ).fetchone()
            if not result:
                # Add environment column with default value
                conn.execute(text("ALTER TABLE server_status ADD COLUMN environment VARCHAR(50) DEFAULT 'prod'"))
                conn.commit()
                print("Added environment column to server_status table")
            
            # Check if source_id column exists (migration)
            result = conn.execute(
                text("SELECT column_name FROM information_schema.columns WHERE table_name='server_status' AND column_name='source_id'")
            ).fetchone()
            if not result:
                conn.execute(text("ALTER TABLE server_status ADD COLUMN source_id INTEGER REFERENCES metric_sources(id) ON DELETE SET NULL"))
                conn.commit()
                print("Added source_id column to server_status table")

            # Check for application_status source_id
            result = conn.execute(
                text("SELECT column_name FROM information_schema.columns WHERE table_name='application_status' AND column_name='source_id'")
            ).fetchone()
            if not result:
                conn.execute(text("ALTER TABLE application_status ADD COLUMN source_id INTEGER REFERENCES metric_sources(id) ON DELETE SET NULL"))
                conn.commit()
                print("Added source_id column to application_status table")

            # Check for database_status source_id
            result = conn.execute(
                text("SELECT column_name FROM information_schema.columns WHERE table_name='database_status' AND column_name='source_id'")
            ).fetchone()
            if not result:
                conn.execute(text("ALTER TABLE database_status ADD COLUMN source_id INTEGER REFERENCES metric_sources(id) ON DELETE SET NULL"))
                conn.commit()
                print("Added source_id column to database_status table")

            # Check if public_ip column exists (migration)
            result = conn.execute(
                text("SELECT column_name FROM information_schema.columns WHERE table_name='server_status' AND column_name='public_ip'")
            ).fetchone()
            if not result:
                conn.execute(text("ALTER TABLE server_status ADD COLUMN public_ip VARCHAR(45)"))
                conn.commit()
                print("Added public_ip column to server_status table")

            # Check if detected_ips column exists (migration)
            result = conn.execute(
                text("SELECT column_name FROM information_schema.columns WHERE table_name='server_status' AND column_name='detected_ips'")
            ).fetchone()
            if not result:
                conn.execute(text("ALTER TABLE server_status ADD COLUMN detected_ips JSON"))
                conn.commit()
                print("Added detected_ips column to server_status table")
    except Exception as e:
        print(f"Note: Could not add environment/public_ip/detected_ips columns (may already exist): {e}")
    
    # Add interface_name column to server_metrics if it doesn't exist (migration)
    try:
        with engine.connect() as conn:
            # Alerts table: site_name
            result = conn.execute(
                text("SELECT column_name FROM information_schema.columns WHERE table_name='alerts' AND column_name='site_name'")
            ).fetchone()
            if not result:
                conn.execute(text("ALTER TABLE alerts ADD COLUMN site_name VARCHAR(255)"))
                conn.commit()
                print("Added site_name column to alerts table")

            # Migration: Add metric_value and threshold_value to alerts table
            result = conn.execute(
                text("SELECT column_name FROM information_schema.columns WHERE table_name='alerts' AND column_name='metric_value'")
            ).fetchone()
            if not result:
                conn.execute(text("ALTER TABLE alerts ADD COLUMN metric_value FLOAT"))
                conn.execute(text("ALTER TABLE alerts ADD COLUMN threshold_value FLOAT"))
                conn.commit()
                print("Added metric_value and threshold_value columns to alerts table")

            # Mobile alerts table: user_id
            result = conn.execute(
                text("SELECT column_name FROM information_schema.columns WHERE table_name='mobile_alerts' AND column_name='user_id'")
            ).fetchone()
            if not result:
                # Check if table exists
                table_exists = conn.execute(
                    text("SELECT table_name FROM information_schema.tables WHERE table_name='mobile_alerts'")
                ).fetchone()
                if table_exists:
                    conn.execute(text("ALTER TABLE mobile_alerts ADD COLUMN user_id INTEGER"))
                    conn.commit()
                    print("Added user_id column to mobile_alerts table")

            # Mobile devices table: is_logged_in
            result = conn.execute(
                text("SELECT column_name FROM information_schema.columns WHERE table_name='mobile_devices' AND column_name='is_logged_in'")
            ).fetchone()
            if not result:
                # Check if table exists
                table_exists = conn.execute(
                    text("SELECT table_name FROM information_schema.tables WHERE table_name='mobile_devices'")
                ).fetchone()
                if table_exists:
                    conn.execute(text("ALTER TABLE mobile_devices ADD COLUMN is_logged_in BOOLEAN DEFAULT TRUE"))
                    conn.commit()
                    print("Added is_logged_in column to mobile_devices table")

            result = conn.execute(
                text("SELECT column_name FROM information_schema.columns WHERE table_name='server_metrics' AND column_name='interface_name'")
            ).fetchone()
            if not result:
                conn.execute(text("ALTER TABLE server_metrics ADD COLUMN interface_name VARCHAR(100)"))
                conn.commit()
                print("Added interface_name column to server_metrics table")
    except Exception as e:
        print(f"Note: Could not add interface_name column (may already exist): {e}")
    
    # Add unique_server_db column to database_config if it doesn't exist
    try:
        with engine.connect() as conn:
            result = conn.execute(
                text("SELECT column_name FROM information_schema.columns WHERE table_name='database_config' AND column_name='unique_server_db'")
            ).fetchone()
            if not result:
                table_exists = conn.execute(
                    text("SELECT table_name FROM information_schema.tables WHERE table_name='database_config'")
                ).fetchone()
                if table_exists:
                    conn.execute(text("ALTER TABLE database_config ADD COLUMN unique_server_db VARCHAR(100)"))
                    conn.commit()
                    # Create unique constraint
                    try:
                        conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS idx_database_config_server_db ON database_config(unique_server_db)"))
                        conn.commit()
                    except Exception as e:
                        # Index may already exist or creation failed
                        logger.warning(f"Could not create unique index on database_config.unique_server_db: {e}")
                    print("Added unique_server_db column to database_config table")
            
            # Migration: Add master_host column to database_config
            result = conn.execute(
                text("SELECT column_name FROM information_schema.columns WHERE table_name='database_config' AND column_name='master_host'")
            ).fetchone()
            if not result:
                table_exists = conn.execute(
                    text("SELECT table_name FROM information_schema.tables WHERE table_name='database_config'")
                ).fetchone()
                if table_exists:
                    conn.execute(text("ALTER TABLE database_config ADD COLUMN master_host VARCHAR(255)"))
                    conn.commit()
                    print("Added master_host column to database_config table")
    except Exception as e:
        print(f"Note: Could not add unique_server_db column (may already exist): {e}")
    
    # Add unique_environment column to lama_config if it doesn't exist
    try:
        with engine.connect() as conn:
            result = conn.execute(
                text("SELECT column_name FROM information_schema.columns WHERE table_name='lama_config' AND column_name='unique_environment'")
            ).fetchone()
            if not result:
                # First check if table exists
                table_exists = conn.execute(
                    text("SELECT table_name FROM information_schema.tables WHERE table_name='lama_config'")
                ).fetchone()
                if table_exists:
                    conn.execute(text("ALTER TABLE lama_config ADD COLUMN unique_environment VARCHAR(50)"))
                    conn.commit()
                    # Create unique constraint
                    try:
                        conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS idx_lama_config_env ON lama_config(environment)"))
                        conn.commit()
                    except Exception as e:
                        # Index may already exist
                        logger.warning(f"Could not create unique index on lama_config: {e}")
                    print("Added unique_environment column to lama_config table")
    except Exception as e:
        print(f"Note: Could not add unique_environment column (may already exist): {e}")
    
    # Add mobile and full_name columns to users table if they don't exist
    try:
        with engine.connect() as conn:
            # Check for mobile column
            result = conn.execute(
                text("SELECT column_name FROM information_schema.columns WHERE table_name='users' AND column_name='mobile'")
            ).fetchone()
            if not result:
                conn.execute(text("ALTER TABLE users ADD COLUMN mobile VARCHAR(20)"))
                # Make email nullable if it's not already
                try:
                    conn.execute(text("ALTER TABLE users ALTER COLUMN email DROP NOT NULL"))
                except Exception as e:
                    # Column may already be nullable
                    logger.warning(f"Could not alter users.email column: {e}")
                # Add unique constraint on mobile
                try:
                    conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_mobile ON users(mobile) WHERE mobile IS NOT NULL"))
                except Exception as e:
                    # Index may already exist
                    logger.warning(f"Could not create unique index on users.mobile: {e}")
                conn.commit()
                print("Added mobile column to users table")
            
            # Check for full_name column
            result = conn.execute(
                text("SELECT column_name FROM information_schema.columns WHERE table_name='users' AND column_name='full_name'")
            ).fetchone()
            if not result:
                conn.execute(text("ALTER TABLE users ADD COLUMN full_name VARCHAR(255)"))
                conn.commit()
                print("Added full_name column to users table")

            # Check for is_active column
            result = conn.execute(
                text("SELECT column_name FROM information_schema.columns WHERE table_name='users' AND column_name='is_active'")
            ).fetchone()
            if not result:
                conn.execute(text("ALTER TABLE users ADD COLUMN is_active BOOLEAN DEFAULT TRUE"))
                conn.commit()
                print("Added is_active column to users table")
    except Exception as e:
        print(f"Note: Could not add mobile/full_name/is_active columns (may already exist): {e}")
    
    # Add unique_metric column to alert_thresholds if it doesn't exist
    try:
        with engine.connect() as conn:
            result = conn.execute(
                text("SELECT column_name FROM information_schema.columns WHERE table_name='alert_thresholds' AND column_name='unique_metric'")
            ).fetchone()
            if not result:
                table_exists = conn.execute(
                    text("SELECT table_name FROM information_schema.tables WHERE table_name='alert_thresholds'")
                ).fetchone()
                if table_exists:
                    conn.execute(text("ALTER TABLE alert_thresholds ADD COLUMN unique_metric VARCHAR(150)"))
                    conn.commit()
                    # Create unique constraint on metric_type + metric_key
                    try:
                        conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS idx_alert_thresholds_metric ON alert_thresholds(metric_type, metric_key)"))
                        conn.commit()
                    except Exception as e:
                        # Index may already exist
                        logger.warning(f"Could not create unique index on alert_thresholds: {e}")
                    print("Added unique_metric column to alert_thresholds table")
    except Exception as e:
        print(f"Note: Could not add unique_metric column (may already exist): {e}")
    
    # Add unique_channel column to alert_config if it doesn't exist
    try:
        with engine.connect() as conn:
            result = conn.execute(
                text("SELECT column_name FROM information_schema.columns WHERE table_name='alert_config' AND column_name='unique_channel'")
            ).fetchone()
            if not result:
                table_exists = conn.execute(
                    text("SELECT table_name FROM information_schema.tables WHERE table_name='alert_config'")
                ).fetchone()
                if table_exists:
                    conn.execute(text("ALTER TABLE alert_config ADD COLUMN unique_channel VARCHAR(50)"))
                    conn.commit()
                    # Create unique constraint on alert_channel
                    try:
                        conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS idx_alert_config_channel ON alert_config(alert_channel)"))
                        conn.commit()
                    except Exception as e:
                        # Index may already exist
                        logger.warning(f"Could not create unique index on alert_config: {e}")
                    print("Added unique_channel column to alert_config table")
    except Exception as e:
        print(f"Note: Could not add unique_channel column (may already exist): {e}")
    
    # Add user_id columns to alert_config if they don't exist
    try:
        with engine.connect() as conn:
            table_exists = conn.execute(
                text("SELECT table_name FROM information_schema.tables WHERE table_name='alert_config'")
            ).fetchone()
            if table_exists:
                # Check and add smtp_to_user_ids
                result = conn.execute(
                    text("SELECT column_name FROM information_schema.columns WHERE table_name='alert_config' AND column_name='smtp_to_user_ids'")
                ).fetchone()
                if not result:
                    conn.execute(text("ALTER TABLE alert_config ADD COLUMN smtp_to_user_ids JSON"))
                    conn.commit()
                    print("Added smtp_to_user_ids column to alert_config table")
                
                # Check and add slack_to_user_ids
                result = conn.execute(
                    text("SELECT column_name FROM information_schema.columns WHERE table_name='alert_config' AND column_name='slack_to_user_ids'")
                ).fetchone()
                if not result:
                    conn.execute(text("ALTER TABLE alert_config ADD COLUMN slack_to_user_ids JSON"))
                    conn.commit()
                    print("Added slack_to_user_ids column to alert_config table")
                
                # Check and add sms_to_user_ids
                result = conn.execute(
                    text("SELECT column_name FROM information_schema.columns WHERE table_name='alert_config' AND column_name='sms_to_user_ids'")
                ).fetchone()
                if not result:
                    conn.execute(text("ALTER TABLE alert_config ADD COLUMN sms_to_user_ids JSON"))
                    conn.commit()
                    print("Added sms_to_user_ids column to alert_config table")

                # Check and add voice columns (C-Zentrix)
                voice_columns = [
                    ("voice_provider", "VARCHAR(50) DEFAULT 'c-zentrix'"),
                    ("voice_api_url", "VARCHAR(255)"),

                    ("voice_to_numbers", "JSON"),
                    ("voice_to_user_ids", "JSON"),
                    ("voice_campaign_name", "VARCHAR(100)"),
                    ("voice_client_id", "VARCHAR(100)")
                ]
                
                for col_name, col_type in voice_columns:
                    result = conn.execute(
                        text(f"SELECT column_name FROM information_schema.columns WHERE table_name='alert_config' AND column_name='{col_name}'")
                    ).fetchone()
                    if not result:
                        conn.execute(text(f"ALTER TABLE alert_config ADD COLUMN {col_name} {col_type}"))
                        conn.commit()
                        print(f"Added {col_name} column to alert_config table")

    except Exception as e:
        print(f"Note: Could not add user_id/voice columns (may already exist): {e}")
    
    # Add os_type column to server_status table if it doesn't exist
    try:
        with engine.connect() as conn:
            result = conn.execute(
                text("SELECT column_name FROM information_schema.columns WHERE table_name='server_status' AND column_name='os_type'")
            ).fetchone()
            if not result:
                conn.execute(text("ALTER TABLE server_status ADD COLUMN os_type VARCHAR(50) DEFAULT 'Linux'"))
                conn.commit()
                print("Added os_type column to server_status table")
            
            # Add os_name column to server_status table
            result = conn.execute(
                text("SELECT column_name FROM information_schema.columns WHERE table_name='server_status' AND column_name='os_name'")
            ).fetchone()
            if not result:
                conn.execute(text("ALTER TABLE server_status ADD COLUMN os_name VARCHAR(255)"))
                conn.commit()
                print("Added os_name column to server_status table")

        # Add external_id column if not exists
        with engine.connect() as conn:
            result = conn.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name='server_status' AND column_name='external_id'")).fetchone()
            if not result:
                conn.execute(text("ALTER TABLE server_status ADD COLUMN external_id VARCHAR(255)"))
                conn.commit()
                print("Added external_id column to server_status table")

            # Migration: Add last_processed_at to active_escalations
            result = conn.execute(
                text("SELECT column_name FROM information_schema.columns WHERE table_name='active_escalations' AND column_name='last_processed_at'")
            ).fetchone()
            if not result:
                table_exists = conn.execute(
                    text("SELECT table_name FROM information_schema.tables WHERE table_name='active_escalations'")
                ).fetchone()
                if table_exists:
                    conn.execute(text("ALTER TABLE active_escalations ADD COLUMN last_processed_at TIMESTAMP WITHOUT TIME ZONE"))
                    conn.commit()
                    print("Added last_processed_at column to active_escalations table")

            # Migration: Add unique constraint to mobile_alerts
            result = conn.execute(
                text("SELECT constraint_name FROM information_schema.table_constraints WHERE table_name='mobile_alerts' AND constraint_name='unique_alert_user'")
            ).fetchone()
            if not result:
                table_exists = conn.execute(
                    text("SELECT table_name FROM information_schema.tables WHERE table_name='mobile_alerts'")
                ).fetchone()
                if table_exists:
                    try:
                        conn.execute(text("ALTER TABLE mobile_alerts ADD CONSTRAINT unique_alert_user UNIQUE (alert_id, user_id)"))
                        conn.commit()
                        print("Added unique_alert_user constraint to mobile_alerts table")
                    except Exception as e:
                        logger.warning(f"Could not add unique constraint to mobile_alerts: {e}")
    except Exception as e:
        print(f"Note: Could not add os_type/last_processed_at/unique_alert_user columns: {e}")

    # Add uptime column to server_status table if it doesn't exist
    try:
        with engine.connect() as conn:
            result = conn.execute(
                text("SELECT column_name FROM information_schema.columns WHERE table_name='server_status' AND column_name='uptime'")
            ).fetchone()
            if not result:
                conn.execute(text("ALTER TABLE server_status ADD COLUMN uptime FLOAT DEFAULT 0"))
                conn.commit()
                print("Added uptime column to server_status table")

            # Check if network_bandwidth column exists
            result = conn.execute(
                text("SELECT column_name FROM information_schema.columns WHERE table_name='server_status' AND column_name='network_bandwidth'")
            ).fetchone()
            if not result:
                conn.execute(text("ALTER TABLE server_status ADD COLUMN network_bandwidth FLOAT DEFAULT 0"))
                conn.commit()
                print("Added network_bandwidth column to server_status table")

            # Check if packet_count column exists
            result = conn.execute(
                text("SELECT column_name FROM information_schema.columns WHERE table_name='server_status' AND column_name='packet_count'")
            ).fetchone()
            if not result:
                conn.execute(text("ALTER TABLE server_status ADD COLUMN packet_count FLOAT DEFAULT 0"))
                conn.commit()
                print("Added packet_count column to server_status table")
    except Exception as e:
        print(f"Note: Could not add uptime column (may already exist): {e}")
    
    # Add metric_type column to lama_sequence table if it doesn't exist
    try:
        with engine.connect() as conn:
            result = conn.execute(
                text("SELECT column_name FROM information_schema.columns WHERE table_name='lama_sequence' AND column_name='metric_type'")
            ).fetchone()
            if not result:
                conn.execute(text("ALTER TABLE lama_sequence ADD COLUMN metric_type VARCHAR(50) DEFAULT 'hardware'"))
                conn.commit()
                print("Added metric_type column to lama_sequence table")
            
            # ALWAYS ensure the unique constraint is updated to include metric_type
            # Drop all possible old constraint names
            try:
                conn.execute(text("ALTER TABLE lama_sequence DROP CONSTRAINT IF EXISTS unique_exchange_env"))
                conn.execute(text("ALTER TABLE lama_sequence DROP CONSTRAINT IF EXISTS unique_exchange_env_seq"))
                conn.execute(text("ALTER TABLE lama_sequence DROP CONSTRAINT IF EXISTS unique_exchange_env_type"))
                # Add the final 3-way unique constraint
                conn.execute(text("ALTER TABLE lama_sequence ADD CONSTRAINT unique_exchange_env_metric_seq UNIQUE (exchange_id, environment, metric_type)"))
                conn.commit()
                print("Updated unique constraint on lama_sequence table")
            except Exception as const_e:
                # If it already exists, this might fail, which is fine
                logger.debug(f"Note: unique constraint on lama_sequence already correct or error: {const_e}")
    except Exception as e:
        print(f"Note: Could not add metric_type column to lama_sequence: {e}")
    
    # Migration for exchange_transactions columns (Bug 3 logging fix)
    try:
        with engine.connect() as conn:
            # Check if server_id is still integer
            result = conn.execute(text("SELECT data_type FROM information_schema.columns WHERE table_name='exchange_transactions' AND column_name='server_id'")).fetchone()
            if result and result[0] == 'integer':
                # Rename old column and add new one
                conn.execute(text("ALTER TABLE exchange_transactions RENAME COLUMN server_id TO server_id_int"))
                conn.execute(text("ALTER TABLE exchange_transactions ADD COLUMN server_id VARCHAR(100)"))
                # Copy data back
                conn.execute(text("UPDATE exchange_transactions SET server_id = CAST(server_id_int AS VARCHAR)"))
                conn.commit()
                print("Migrated server_id to VARCHAR(100)")
            
            # Change server_ip to TEXT
            conn.execute(text("ALTER TABLE exchange_transactions ALTER COLUMN server_ip TYPE TEXT"))
            
            # Add original_metrics column if missing
            result = conn.execute(text("SELECT 1 FROM information_schema.columns WHERE table_name='exchange_transactions' AND column_name='original_metrics'")).fetchone()
            if not result:
                conn.execute(text("ALTER TABLE exchange_transactions ADD COLUMN original_metrics JSON"))
                conn.commit()
                print("Migrated exchange_transactions: added original_metrics column")
            else:
                conn.commit()
            print("Migrated exchange_transactions column server_ip to TEXT")
    except Exception as e:
        print(f"Note: Could not migrate exchange_transactions columns: {e}")

    # Initialize LAMA Exchange metric configuration with default values (all enabled)
    try:
        with engine.connect() as conn:
            # Check if table exists
            table_exists = conn.execute(
                text("SELECT table_name FROM information_schema.tables WHERE table_name='lama_exchange_metric_config'")
            ).fetchone()
            
            if table_exists:
                # Check if we have any configs
                existing_configs = conn.execute(
                    text("SELECT COUNT(*) FROM lama_exchange_metric_config")
                ).scalar()
                
                if existing_configs == 0:
                    # Insert default configs (all enabled) for both environments
                    metric_types = ['hardware', 'network', 'database', 'application']
                    for env in ['uat', 'prod']:
                        for metric_type in metric_types:
                            try:
                                conn.execute(
                                    text("""
                                        INSERT INTO lama_exchange_metric_config 
                                        (environment, metric_type, enabled, unique_env_metric)
                                        VALUES (:env, :metric_type, true, :unique_key)
                                        ON CONFLICT (unique_env_metric) DO NOTHING
                                    """),
                                    {
                                        "env": env,
                                        "metric_type": metric_type,
                                        "unique_key": f"{env}_{metric_type}"
                                    }
                                )
                            except Exception as e:
                                print(f"Note: Could not insert default config for {env}/{metric_type}: {e}")
                    conn.commit()
                    print("Initialized LAMA Exchange metric configuration with default values (all enabled)")
    except Exception as e:
        print(f"Note: Could not initialize metric configuration (may already exist): {e}")
    
    # Initialize LAMA Exchange server selection with all existing servers (Option A: auto-select all)
    try:
        # First check if table exists (read-only, no transaction needed)
        with engine.connect() as check_conn:
            table_exists = check_conn.execute(
                text("SELECT table_name FROM information_schema.tables WHERE table_name='lama_exchange_server_selection'")
            ).fetchone()
            
            if table_exists:
                # Check if we have any selections (read-only, no transaction needed)
                existing_selections = check_conn.execute(
                    text("SELECT COUNT(*) FROM lama_exchange_server_selection")
                ).fetchone()
                
                if existing_selections and existing_selections[0] == 0:
                    # Table exists but is empty - auto-select all servers (Option A migration)
                    print("Initializing LAMA Exchange server selection: auto-selecting all existing servers...")
                    
                    # Get all servers for prod and uat environments (read-only, no transaction needed)
                    servers = check_conn.execute(
                        text("SELECT id, environment FROM server_status WHERE environment IN ('prod', 'uat')")
                    ).fetchall()
                    
                    if servers:
                        # Use engine.begin() for automatic transaction management
                        # Auto-commits on success or auto-rollbacks on exception
                        with engine.begin() as init_conn:
                            # Insert entries for all servers with enabled=TRUE
                            for server_id, env in servers:
                                try:
                                    init_conn.execute(
                                        text("""
                                            INSERT INTO lama_exchange_server_selection 
                                            (environment, server_id, enabled)
                                            VALUES (:env, :server_id, true)
                                            ON CONFLICT ON CONSTRAINT unique_env_server DO NOTHING
                                        """),
                                        {
                                            "env": env,
                                            "server_id": server_id
                                        }
                                    )
                                except Exception as e:
                                    print(f"Warning: Could not add server {server_id} to selection: {e}")
                                    # Continue with other servers even if one fails
                            # Transaction auto-commits here on successful exit
                        
                        print(f"Initialized LAMA Exchange server selection: {len(servers)} server(s) auto-selected (enabled=TRUE)")
                    else:
                        print("No servers found for LAMA Exchange server selection initialization")
                else:
                    print(f"LAMA Exchange server selection already initialized ({existing_selections[0] if existing_selections else 0} entries)")
    except Exception as e:
        print(f"Note: Could not initialize server selection (may already exist or no servers): {e}")
    
    # Add index_name column to metric_queries if it doesn't exist
    try:
        with engine.connect() as conn:
            # Check and create scheduler_state table
            table_exists = conn.execute(
                text("SELECT table_name FROM information_schema.tables WHERE table_name='scheduler_state'")
            ).fetchone()
            if not table_exists:
                conn.execute(text("""
                    CREATE TABLE scheduler_state (
                        id SERIAL PRIMARY KEY,
                        environment VARCHAR(50) NOT NULL,
                        key VARCHAR(100) NOT NULL,
                        value TEXT,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE(environment, key)
                    )
                """))
                conn.commit()
                print("Created scheduler_state table")

            result = conn.execute(
                text("SELECT column_name FROM information_schema.columns WHERE table_name='metric_queries' AND column_name='index_name'")
            ).fetchone()
            if not result:
                # Check if table exists first
                table_exists = conn.execute(
                    text("SELECT table_name FROM information_schema.tables WHERE table_name='metric_queries'")
                ).fetchone()
                if table_exists:
                    conn.execute(text("ALTER TABLE metric_queries ADD COLUMN index_name VARCHAR(255)"))
                    conn.commit()
                    print("Added index_name column to metric_queries table")
            
            # Add metric_source column to lama_exchange_server_selection if it doesn't exist
            result = conn.execute(
                text("SELECT column_name FROM information_schema.columns WHERE table_name='lama_exchange_server_selection' AND column_name='metric_source'")
            ).fetchone()
            if not result:
                # Check if table exists first
                table_exists = conn.execute(
                    text("SELECT table_name FROM information_schema.tables WHERE table_name='lama_exchange_server_selection'")
                ).fetchone()
                if table_exists:
                    conn.execute(text("ALTER TABLE lama_exchange_server_selection ADD COLUMN metric_source VARCHAR(20) DEFAULT 'auto'"))
                    conn.commit()
                    print("Added metric_source column to lama_exchange_server_selection table")

    except Exception as e:
        print(f"Note: Could not add columns (index_name/metric_source) (may already exist): {e}")

    print("Database tables created/verified successfully")
    
    # Create performance indexes after tables are created
    # Create login_lock_status table if it doesn't exist (migration)
    # This table tracks soft block (after 3 failed attempts) and manual lock status
    try:
        with engine.connect() as conn:
            result = conn.execute(
                text("SELECT table_name FROM information_schema.tables WHERE table_name='login_lock_status'")
            ).fetchone()
            if not result:
                # Table doesn't exist - create it
                conn.execute(text("""
                    CREATE TABLE login_lock_status (
                        id SERIAL PRIMARY KEY,
                        environment VARCHAR(50) NOT NULL,
                        exchange_id INTEGER,
                        soft_block BOOLEAN DEFAULT FALSE,
                        soft_block_at TIMESTAMP,
                        soft_block_cleared_at TIMESTAMP,
                        manual_lock BOOLEAN DEFAULT FALSE,
                        locked_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
                        locked_at TIMESTAMP,
                        unlocked_at TIMESTAMP,
                        reason TEXT,
                        last_error_message TEXT,
                        error_907_locked BOOLEAN DEFAULT FALSE,
                        error_907_locked_at TIMESTAMP,
                        error_907_cleared_at TIMESTAMP,
                        failed_attempts INTEGER DEFAULT 0,
                        last_failed_at TIMESTAMP,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE(environment, exchange_id)
                    )
                """))
                # Create index for fast lookups
                conn.execute(text("""
                    CREATE INDEX idx_login_lock_status_env_exchange 
                    ON login_lock_status(environment, exchange_id)
                """))
                conn.commit()
                print("✅ Created login_lock_status table for soft block and manual lock tracking")
            else:
                # Table exists - check if columns exist and add them (migration)
                columns_to_add = [
                    ("last_error_message", "TEXT"),
                    ("error_907_locked", "BOOLEAN DEFAULT FALSE"),
                    ("error_907_locked_at", "TIMESTAMP"),
                    ("error_907_cleared_at", "TIMESTAMP"),
                    ("failed_attempts", "INTEGER DEFAULT 0"),
                    ("last_failed_at", "TIMESTAMP")
                ]
                for col_name, col_type in columns_to_add:
                    try:
                        col_result = conn.execute(
                            text(f"SELECT column_name FROM information_schema.columns WHERE table_name='login_lock_status' AND column_name='{col_name}'")
                        ).fetchone()
                        if not col_result:
                            conn.execute(text(f"ALTER TABLE login_lock_status ADD COLUMN {col_name} {col_type}"))
                            conn.commit()
                            print(f"✅ Added {col_name} column to login_lock_status table")
                    except Exception as col_e:
                        # Column may already exist or other error - non-critical
                        pass
    except Exception as e:
        print(f"Note: Could not create login_lock_status table (may already exist): {e}")
        logger.warning(f"Note: Could not create login_lock_status table (may already exist): {e}")
        # Don't fail startup if table creation fails
    
    # Add credential_hash column to lama_tokens if it doesn't exist (migration)
    # This column stores hash of credentials used to generate token for proactive invalidation
    try:
        with engine.connect() as conn:
            result = conn.execute(
                text("SELECT column_name FROM information_schema.columns WHERE table_name='lama_tokens' AND column_name='credential_hash'")
            ).fetchone()
            if not result:
                # Check if table exists first
                table_exists = conn.execute(
                    text("SELECT table_name FROM information_schema.tables WHERE table_name='lama_tokens'")
                ).fetchone()
                if table_exists:
                    conn.execute(text("ALTER TABLE lama_tokens ADD COLUMN credential_hash VARCHAR(64)"))
                    conn.commit()
                    print("✅ Added credential_hash column to lama_tokens table for proactive credential change detection")
    except Exception as e:
        print(f"Note: Could not add credential_hash column (may already exist): {e}")
    
    try:
        from app.db.create_indexes import create_performance_indexes
        logger.info("Creating performance indexes...")
        index_result = create_performance_indexes(engine)
        logger.info(f"Index creation result: {index_result}")
        if index_result["created"] > 0:
            print(f"✅ Created {index_result['created']} performance index(es)")
    except Exception as e:
        logger.warning(f"Note: Could not create performance indexes (may already exist): {e}")
        # Don't fail startup if index creation fails

def get_db():
    """Dependency for FastAPI to get database session"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def get_connection():
    """Get a raw database connection for Core API usage"""
    return engine.connect()
