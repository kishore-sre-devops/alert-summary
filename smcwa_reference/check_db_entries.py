
import os
import urllib.parse
from sqlalchemy import create_engine, text

POSTGRES_HOST = os.getenv("POSTGRES_HOST", "postgres_prod")
POSTGRES_USER = os.getenv("POSTGRES_USER", "lama")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "")
POSTGRES_DB = os.getenv("POSTGRES_DB", "lama_prod")

safe_password = urllib.parse.quote(POSTGRES_PASSWORD)
DATABASE_URL = f"postgresql://{POSTGRES_USER}:{safe_password}@{POSTGRES_HOST}:5432/{POSTGRES_DB}"

engine = create_engine(DATABASE_URL)

with engine.connect() as conn:
    print("--- server_status ---")
    res = conn.execute(text("SELECT id, name, ip FROM server_status LIMIT 10"))
    for row in res:
        print(row)
    
    print("\n--- database_config ---")
    res = conn.execute(text("SELECT id, server_id, host, is_replication, master_host FROM database_config"))
    for row in res:
        print(row)

    print("\n--- database_status (RDS) ---")
    res = conn.execute(text("SELECT id, name, external_id, status FROM database_status"))
    for row in res:
        print(row)
