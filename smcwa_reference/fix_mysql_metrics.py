from sqlalchemy import text, create_engine
import os
import urllib.parse

# Database configuration
POSTGRES_HOST = os.getenv("POSTGRES_HOST", "postgres")
POSTGRES_USER = os.getenv("POSTGRES_USER", "lama")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "LAMA_prod_123")
POSTGRES_DB = os.getenv("POSTGRES_DB", "lama_prod")

safe_password = urllib.parse.quote(POSTGRES_PASSWORD)
DATABASE_URL = f"postgresql://{POSTGRES_USER}:{safe_password}@{POSTGRES_HOST}:5432/{POSTGRES_DB}"
engine = create_engine(DATABASE_URL)

def fix_mysql():
    with engine.begin() as conn:
        print("1. Creating database_config for DC Master (192.168.1.21)...")
        conn.execute(text("""
            INSERT INTO database_config (server_id, db_type, host, port, database, username, password, is_replication, enabled, unique_server_db)
            VALUES (23, 'mysql', '192.168.1.21', 3306, 'mysql', 'root', 'dummy', false, true, '23_mysql')
            ON CONFLICT (unique_server_db) DO UPDATE SET enabled = true
        """))

        print("2. Creating database_config for DR Replica (192.168.176.73)...")
        conn.execute(text("""
            INSERT INTO database_config (server_id, db_type, host, port, database, username, password, is_replication, master_host, enabled, unique_server_db)
            VALUES (9, 'mysql', '192.168.176.73', 3306, 'mysql', 'root', 'dummy', true, '192.168.1.21', true, '9_mysql')
            ON CONFLICT (unique_server_db) DO UPDATE SET enabled = true
        """))

        print("3. Updating Metric Source 37 (DC Master) config...")
        conn.execute(text("""
            UPDATE metric_sources 
            SET config = '{"url": "http://10.215.33.196:9090", "instance": "localhost:8001", "db_host": "192.168.1.21", "db_port": 3306, "db_type": "mysql", "is_replication": false}'::json
            WHERE id = 37
        """))

        print("4. Updating Metric Source 38 (DR Replica) config...")
        conn.execute(text("""
            UPDATE metric_sources 
            SET config = '{"url": "http://10.215.33.196:9090", "instance": "localhost:8021", "db_host": "192.168.176.73", "master_host": "192.168.1.21", "is_replication": true}'::json
            WHERE id = 38
        """))

        print("\n✅ Fix applied successfully!")

if __name__ == "__main__":
    fix_mysql()
