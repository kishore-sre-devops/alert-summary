
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
    print("Checking for duplicate IPs in server_status:")
    res = conn.execute(text("SELECT ip, COUNT(*) FROM server_status GROUP BY ip HAVING COUNT(*) > 1"))
    for row in res:
        print(f"IP: {row[0]}, Count: {row[1]}")
        # Find details
        details = conn.execute(text("SELECT id, name FROM server_status WHERE ip = :ip"), {"ip": row[0]})
        for d in details:
            print(f"  ID: {d[0]}, Name: {d[1]}")

    print("\nChecking for duplicate External IDs in database_status:")
    res = conn.execute(text("SELECT external_id, COUNT(*) FROM database_status WHERE external_id IS NOT NULL GROUP BY external_id HAVING COUNT(*) > 1"))
    for row in res:
        print(f"External ID: {row[0]}, Count: {row[1]}")

    print("\nChecking if any server_status IP matches database_status external_id:")
    res = conn.execute(text("""
        SELECT s.ip, s.name, ds.external_id, ds.name
        FROM server_status s
        JOIN database_status ds ON s.ip = ds.external_id
    """))
    for row in res:
        print(f"Match found! IP/ExtID: {row[0]}, Server Name: {row[1]}, DB Name: {row[3]}")
