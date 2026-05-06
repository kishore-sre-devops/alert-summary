import sys
import os
from sqlalchemy import text, create_engine
import urllib.parse
from datetime import datetime, timedelta

# Database configuration
POSTGRES_HOST = os.getenv("POSTGRES_HOST", "postgres")
POSTGRES_USER = os.getenv("POSTGRES_USER", "lama")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "LAMA_prod_123")
POSTGRES_DB = os.getenv("POSTGRES_DB", "lama_prod")

safe_password = urllib.parse.quote(POSTGRES_PASSWORD)
DATABASE_URL = f"postgresql://{POSTGRES_USER}:{safe_password}@{POSTGRES_HOST}:5432/{POSTGRES_DB}"
engine = create_engine(DATABASE_URL)

def format_last_seen(dt):
    if not dt:
        return "Never"
    now = datetime.utcnow()
    diff = now - dt
    if diff < timedelta(minutes=10):
        return f"Recent ({int(diff.total_seconds())}s ago)"
    elif diff < timedelta(hours=1):
        return f"{int(diff.total_seconds() // 60)}m ago"
    else:
        return dt.strftime("%Y-%m-%d %H:%M")

def get_status_emoji(last_seen, status):
    if not last_seen:
        return "❌ (No Data)"
    now = datetime.utcnow()
    # Allow 30 minutes for cloud resources as they might have slower refresh rates
    if now - last_seen < timedelta(minutes=30) and status != 'offline':
        return "✅ (Active)"
    return f"⚠️ ({status})"

def fmt_val(val, format_str=".2f"):
    if val is None:
        return "N/A"
    try:
        return f"{val:{format_str}}"
    except:
        return str(val)

def show_resources():
    with engine.connect() as conn:
        # 1. EC2 Instances
        ec2_query = text("""
            SELECT name, ip, external_id, status, cpu, memory, last_seen 
            FROM server_status 
            WHERE location_id = 3 OR external_id LIKE 'i-%%'
            ORDER BY name
        """)
        ec2s = conn.execute(ec2_query).fetchall()

        # 2. ECS Services
        ecs_query = text("""
            SELECT name, external_id, status, cpu, memory, last_seen 
            FROM application_status 
            ORDER BY name
        """)
        ecss = conn.execute(ecs_query).fetchall()

        # 3. RDS Instances
        rds_query = text("""
            SELECT name, engine, external_id, status, cpu, memory, last_seen 
            FROM database_status 
            ORDER BY name
        """)
        rdss = conn.execute(rds_query).fetchall()

    print(f"{'Type':<10} | {'Name':<45} | {'External ID':<25} | {'Metrics Status':<15} | {'CPU %':<8} | {'MEM %':<8} | {'Last Seen'}")
    print("-" * 150)

    for row in ec2s:
        status = get_status_emoji(row.last_seen, row.status)
        last_seen = format_last_seen(row.last_seen)
        cpu = fmt_val(row.cpu)
        mem = fmt_val(row.memory)
        print(f"{'EC2':<10} | {row.name[:43]:<45} | {str(row.external_id):<25} | {status:<15} | {cpu:<8} | {mem:<8} | {last_seen}")

    for row in ecss:
        status = get_status_emoji(row.last_seen, row.status)
        last_seen = format_last_seen(row.last_seen)
        cpu = fmt_val(row.cpu)
        mem = fmt_val(row.memory)
        print(f"{'ECS':<10} | {row.name[:43]:<45} | {str(row.external_id):<25} | {status:<15} | {cpu:<8} | {mem:<8} | {last_seen}")

    for row in rdss:
        status = get_status_emoji(row.last_seen, row.status)
        last_seen = format_last_seen(row.last_seen)
        cpu = fmt_val(row.cpu)
        mem = fmt_val(row.memory)
        print(f"{'RDS':<10} | {row.name[:43]:<45} | {str(row.external_id):<25} | {status:<15} | {cpu:<8} | {mem:<8} | {last_seen}")

if __name__ == "__main__":
    show_resources()
