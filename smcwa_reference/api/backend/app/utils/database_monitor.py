"""
Database monitoring utility - checks replication and sync status
Connects directly to databases from the backend (not from agents)
"""

import logging
import time
from typing import Dict, Optional, Tuple
from datetime import datetime

logger = logging.getLogger(__name__)

def check_postgresql_replication(host: str, port: int, database: str, username: str, password: str, is_replication: bool = False) -> Dict:
    """
    Check PostgreSQL replication status
    """
    try:
        import psycopg2
        from psycopg2.extras import RealDictCursor
        
        conn = psycopg2.connect(
            host=host,
            port=port,
            database=database,
            user=username,
            password=password,
            connect_timeout=5
        )
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        # If user explicitly marked this as NOT a replication target (Master), 
        # we just confirm connection and return Up.
        if not is_replication:
            cursor.close()
            conn.close()
            return {
                'status': 1.0,
                'qsize': 0.0,
                'bandwidth': 0.0,
                'latency': 0.0
            }

        # Check if this is a replica
        cursor.execute("SELECT pg_is_in_recovery() as is_replica")
        db_is_replica = cursor.fetchone()['is_replica']
        
        if not db_is_replica:
            # Service says it's a master
            return {
                'status': 1.0,
                'qsize': 0.0,
                'bandwidth': 0.0,
                'latency': 0.0
            }
        
        # This is a replica - check replication lag
        cursor.execute("""
            SELECT 
                pg_wal_lsn_diff(pg_current_wal_lsn(), replay_lsn) as lag_bytes,
                EXTRACT(EPOCH FROM (now() - pg_last_xact_replay_timestamp())) * 1000 as lag_milliseconds
            FROM pg_stat_replication
            LIMIT 1
        """)
        
        result = cursor.fetchone()
        if result:
            lag_bytes = result.get('lag_bytes', 0) or 0
            lag_ms = result.get('lag_milliseconds', 0) or 0
            
            return {
                'status': 1.0 if lag_bytes < (1024 * 1024 * 1024) else 0.0,
                'qsize': lag_bytes / (1024 * 1024),
                'bandwidth': 0.0,
                'latency': lag_ms
            }
        else:
            cursor.close()
            conn.close()
            return {'status': 0.0, 'qsize': 0.0, 'bandwidth': 0.0, 'latency': 0.0}
            
    except Exception as e:
        logger.error(f"Error checking PostgreSQL replication: {e}")
        return {'status': 0.0, 'qsize': 0.0, 'bandwidth': 0.0, 'latency': 0.0, 'error': str(e)}

def check_mysql_replication(host: str, port: int, database: str, username: str, password: str, is_replication: bool = False) -> Dict:
    """
    Check MySQL replication status
    """
    try:
        import pymysql
        
        conn = pymysql.connect(
            host=host,
            port=port,
            database=database,
            user=username,
            password=password,
            connect_timeout=5
        )
        
        # If user explicitly marked this as NOT a replication target (Master), 
        # we just confirm connection and return Up.
        if not is_replication:
            conn.close()
            return {
                'status': 1.0,
                'qsize': 0.0,
                'bandwidth': 0.0,
                'latency': 0.0
            }

        cursor = conn.cursor(pymysql.cursors.DictCursor)
        
        # Check if this is a replica
        slave_status = None
        try:
            cursor.execute("SHOW REPLICA STATUS")
            slave_status = cursor.fetchone()
        except: pass
            
        if not slave_status:
            try:
                cursor.execute("SHOW SLAVE STATUS")
                slave_status = cursor.fetchone()
            except: pass
        
        if not slave_status:
            # No replication configured on this server, but it's alive
            cursor.close()
            conn.close()
            return {'status': 1.0, 'qsize': 0.0, 'bandwidth': 0.0, 'latency': 0.0}
        
        # This is a replica - check status and lag
        io_running = slave_status.get('Slave_IO_Running', slave_status.get('Replica_IO_Running', 'No'))
        sql_running = slave_status.get('Slave_SQL_Running', slave_status.get('Replica_SQL_Running', 'No'))
        seconds_behind = slave_status.get('Seconds_Behind_Master', 0)
        if seconds_behind is None: seconds_behind = 0
        
        relay_log_pos = slave_status.get('Relay_Log_Pos', 0) or 0
        exec_master_log_pos = slave_status.get('Exec_Master_Log_Pos', 0) or 0
        
        # Calculate stats
        qsize = abs(relay_log_pos - exec_master_log_pos) / (1024 * 1024)
        latency = seconds_behind * 1000.0 # Convert to Microseconds
        
        status = 1.0 if (io_running == 'Yes' and sql_running == 'Yes') else 0.0
        
        cursor.close()
        conn.close()
        return {'status': status, 'qsize': qsize, 'bandwidth': 0.0, 'latency': latency}
        
    except Exception as e:
        logger.error(f"Error checking MySQL replication: {e}")
        return {'status': 0.0, 'qsize': 0.0, 'bandwidth': 0.0, 'latency': 0.0, 'error': str(e)}

def check_mssql_replication(host: str, port: int, database: str, username: str, password: str) -> Dict:
    """
    Check Microsoft SQL Server (MSSQL) replication status
    Returns: {
        'status': 1.0 (Up) or 0.0 (Down),
        'qsize': queue_size,
        'bandwidth': bandwidth_utilization_percent,
        'latency': latency_microseconds
    }
    """
    try:
        import pyodbc
        
        # Build connection string for MSSQL
        # Default port is 1433 if not specified
        if port is None:
            port = 1433
        
        # Connection string for SQL Server
        conn_str = f"DRIVER={{ODBC Driver 17 for SQL Server}};SERVER={host},{port};DATABASE={database};UID={username};PWD={password};TrustServerCertificate=yes;Connection Timeout=5"
        
        # Try alternative drivers if ODBC Driver 17 is not available
        try:
            conn = pyodbc.connect(conn_str)
        except pyodbc.Error:
            # Try with SQL Server driver
            conn_str = f"DRIVER={{SQL Server}};SERVER={host},{port};DATABASE={database};UID={username};PWD={password};Connection Timeout=5"
            conn = pyodbc.connect(conn_str)
        
        cursor = conn.cursor()
        
        # Check if this is a replica (subscriber) or publisher
        # Query replication status
        cursor.execute("""
            SELECT 
                CASE 
                    WHEN EXISTS (
                        SELECT 1 FROM sys.dm_repl_articles 
                        WHERE publisher_db = DB_NAME()
                    ) THEN 1  -- Publisher
                    WHEN EXISTS (
                        SELECT 1 FROM sys.dm_repl_schemas 
                        WHERE schema_id = SCHEMA_ID()
                    ) THEN 2  -- Subscriber
                    ELSE 0  -- Not in replication
                END as replication_role
        """)
        
        role_result = cursor.fetchone()
        replication_role = role_result[0] if role_result else 0
        
        if replication_role == 0:
            # Not in replication - return default values
            cursor.close()
            conn.close()
            return {
                'status': 1.0,
                'qsize': 0.0,
                'bandwidth': 0.0,
                'latency': 0.0
            }
        
        if replication_role == 1:
            # This is a publisher - check distribution latency
            cursor.execute("""
                SELECT 
                    MAX(CAST(ls.time AS FLOAT)) as max_latency_seconds
                FROM distribution.dbo.MSdistribution_history dh
                INNER JOIN distribution.dbo.MSlogreader_history lh ON dh.agent_id = lh.agent_id
                INNER JOIN distribution.dbo.MSlogreader_status ls ON lh.agent_id = ls.agent_id
                WHERE dh.time > DATEADD(minute, -1, GETDATE())
            """)
            
            latency_result = cursor.fetchone()
            latency_seconds = latency_result[0] if latency_result and latency_result[0] else 0.0
            latency = latency_seconds * 1000  # Convert to milliseconds
            
            cursor.close()
            conn.close()
            
            return {
                'status': 1.0 if latency_seconds < 60 else 0.0,
                'qsize': 0.0,
                'bandwidth': 0.0,
                'latency': latency
            }
        
        # This is a subscriber - check replication lag
        cursor.execute("""
            SELECT 
                CASE 
                    WHEN EXISTS (
                        SELECT 1 FROM sys.dm_repl_articles 
                        WHERE publisher_db = DB_NAME()
                    ) THEN 1
                    ELSE 0
                END as is_subscriber,
                MAX(CAST(ls.time AS FLOAT)) as max_latency_seconds
            FROM distribution.dbo.MSdistribution_history dh
            INNER JOIN distribution.dbo.MSdistribution_status ds ON dh.agent_id = ds.agent_id
            LEFT JOIN distribution.dbo.MSdistribution_status ls ON ds.agent_id = ls.agent_id
            WHERE dh.time > DATEADD(minute, -1, GETDATE())
        """)
        
        lag_result = cursor.fetchone()
        if lag_result:
            latency_seconds = lag_result[1] if lag_result[1] else 0.0
            latency = latency_seconds * 1000  # Convert to milliseconds
            
            # Get queue size (undistributed commands)
            cursor.execute("""
                SELECT COUNT(*) as queue_size
                FROM distribution.dbo.MSrepl_commands
                WHERE xact_seqno > (
                    SELECT MAX(xact_seqno) 
                    FROM distribution.dbo.MSdistribution_status
                )
            """)
            
            queue_result = cursor.fetchone()
            queue_size = queue_result[0] if queue_result else 0.0
            
            cursor.close()
            conn.close()
            
            return {
                'status': 1.0 if latency_seconds < 60 else 0.0,
                'qsize': queue_size / (1024 * 1024) if queue_size else 0.0,  # Convert to MB
                'bandwidth': 0.0,  # Placeholder
                'latency': latency
            }
        else:
            # Simplified check for subscriber lag
            cursor.execute("""
                SELECT 
                    DATEDIFF(second, MAX(time), GETDATE()) as lag_seconds
                FROM distribution.dbo.MSdistribution_history
                WHERE time > DATEADD(minute, -1, GETDATE())
            """)
            
            lag_result = cursor.fetchone()
            lag_seconds = lag_result[0] if lag_result else 0.0
            latency = lag_seconds * 1000  # Convert to milliseconds
            
            cursor.close()
            conn.close()
            
            return {
                'status': 1.0 if lag_seconds < 60 else 0.0,
                'qsize': 0.0,
                'bandwidth': 0.0,
                'latency': latency
            }
            
    except ImportError:
        logger.error("pyodbc not installed. Install it with: pip install pyodbc")
        return {
            'status': 0.0,
            'qsize': 0.0,
            'bandwidth': 0.0,
            'latency': 0.0,
            'error': 'pyodbc not installed. Install with: pip install pyodbc'
        }
    except Exception as e:
        logger.error(f"Error checking MSSQL replication: {e}")
        # Try simplified connection test
        try:
            import pyodbc
            conn_str = f"DRIVER={{ODBC Driver 17 for SQL Server}};SERVER={host},{port};DATABASE={database};UID={username};PWD={password};TrustServerCertificate=yes;Connection Timeout=5"
            conn = pyodbc.connect(conn_str)
            conn.close()
            # Connection successful but replication check failed
            return {
                'status': 1.0,
                'qsize': 0.0,
                'bandwidth': 0.0,
                'latency': 0.0,
                'warning': 'Connection successful but replication status unavailable'
            }
        except (ImportError, Exception) as e:
            logger.error(f"Simplified MSSQL connection test failed: {e}")
            return {
                'status': 0.0,
                'qsize': 0.0,
                'bandwidth': 0.0,
                'latency': 0.0,
                'error': str(e)
            }

def probe_database_role(host: str, port: int, database: str, username: str, password: str, db_type: str) -> bool:
    """
    Connect to database and detect if it is a Replica/Slave (True) or Master (False)
    """
    db_type = db_type.lower()
    try:
        if db_type in ['postgresql', 'postgres']:
            import psycopg2
            conn = psycopg2.connect(host=host, port=port, database=database, user=username, password=password, connect_timeout=5)
            cursor = conn.cursor()
            cursor.execute("SELECT pg_is_in_recovery()")
            is_rep = cursor.fetchone()[0]
            conn.close()
            return is_rep
        elif db_type in ['mysql', 'mariadb']:
            import pymysql
            conn = pymysql.connect(host=host, port=port, database=database, user=username, password=password, connect_timeout=5)
            cursor = conn.cursor(pymysql.cursors.DictCursor)
            # Try newer REPLICA syntax, fallback to SLAVE
            slave_status = None
            try:
                cursor.execute("SHOW REPLICA STATUS")
                slave_status = cursor.fetchone()
            except: pass
            if not slave_status:
                try:
                    cursor.execute("SHOW SLAVE STATUS")
                    slave_status = cursor.fetchone()
                except: pass
            conn.close()
            return slave_status is not None
        return False
    except Exception as e:
        logger.error(f"Error probing database role for {host}: {e}")
        return False

def check_database_metrics(host: str, port: int, database: str, username: str, password: str, db_type: str, is_replication: bool = False) -> Dict:
    """
    Check database replication/sync metrics based on database type
    """
    # FOR AWS MANAGED RDS: We don't connect directly for replication stats usually
    if username == 'aws_cloudwatch_managed':
        return {
            'status': 1.0,
            'qsize': 0.0,
            'bandwidth': 0.0,
            'latency': 0.0,
            'info': 'AWS Managed RDS - metrics collected via CloudWatch'
        }

    db_type_lower = db_type.lower()
    
    if db_type_lower in ['postgresql', 'postgres']:
        return check_postgresql_replication(host, port, database, username, password, is_replication)
    elif db_type_lower in ['mysql', 'mariadb']:
        return check_mysql_replication(host, port, database, username, password, is_replication)
    elif db_type_lower in ['mssql', 'sqlserver', 'sql-server', 'microsoft sql server']:
        return check_mssql_replication(host, port, database, username, password, is_replication)
    else:
        logger.warning(f"Unsupported database type: {db_type}")
        return {
            'status': 0.0,
            'qsize': 0.0,
            'bandwidth': 0.0,
            'latency': 0.0,
            'error': f'Unsupported database type: {db_type}'
        }

def decrypt_password(encrypted_password: str) -> str:
    """
    Decrypt database password (using same encryption as LAMA config)
    """
    try:
        from cryptography.fernet import Fernet
        import os
        import base64
        
        # Use the same key as LAMA config encryption
        key = os.getenv("ENCRYPTION_KEY", "default-key-change-in-production")
        # Convert to 32-byte key for Fernet
        key_bytes = key.encode()[:32].ljust(32, b'0')
        key_b64 = base64.urlsafe_b64encode(key_bytes)
        
        f = Fernet(key_b64)
        decrypted = f.decrypt(encrypted_password.encode())
        return decrypted.decode()
    except Exception as e:
        logger.error(f"Error decrypting password: {e}")
        return encrypted_password  # Return as-is if decryption fails

