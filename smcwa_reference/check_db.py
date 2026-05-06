from app.db.db import engine
from sqlalchemy import text
with engine.connect() as conn:
    print("--- database_status (ds.ip) ---")
    dbs = conn.execute(text("SELECT id, name, ip, location_id FROM database_status LIMIT 10")).fetchall()
    for d in dbs: print(d)
    
    print("\n--- database_config (dc.host) ---")
    configs = conn.execute(text("SELECT id, server_id, host, is_replication FROM database_config LIMIT 10")).fetchall()
    for c in configs: print(c)

    print("\n--- JOIN Check ---")
    join_check = conn.execute(text("""
        SELECT ds.id, ds.name, ds.ip as host, dc.is_replication
        FROM database_status ds
        LEFT JOIN database_config dc ON ds.ip = dc.host
        WHERE ds.environment = 'uat'
    """)).fetchall()
    for j in join_check: print(j)
