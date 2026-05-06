import os
import urllib.parse
from sqlalchemy import create_engine, text

# These will be picked up from the container environment
POSTGRES_HOST = os.getenv("POSTGRES_HOST", "postgres")
POSTGRES_USER = os.getenv("POSTGRES_USER", "lama")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "")
POSTGRES_DB = os.getenv("POSTGRES_DB", "lama_prod")

safe_password = urllib.parse.quote(POSTGRES_PASSWORD)
DATABASE_URL = f"postgresql://{POSTGRES_USER}:{safe_password}@{POSTGRES_HOST}:5432/{POSTGRES_DB}"

engine = create_engine(DATABASE_URL)

def get_counts():
    counts = {}
    with engine.connect() as conn:
        # 1. Total Servers on Dashboard (excluding markers)
        # Location 1=DC, 2=DR, 3=Cloud
        res = conn.execute(text("""
            SELECT 
                COUNT(*) as total,
                COUNT(*) FILTER (WHERE location_id = 3 AND os_type != 'ECS') as ec2_dashboard,
                COUNT(*) FILTER (WHERE os_type = 'ECS' OR ip = 'aws-ecs') as ecs_dashboard,
                COUNT(*) FILTER (WHERE location_id IN (1, 2)) as physical_dashboard
            FROM server_status
            WHERE ip NOT IN ('aws')
        """)).fetchone()
        counts['dashboard'] = {
            'total': res[0],
            'ec2': res[1],
            'ecs': res[2],
            'physical': res[3]
        }

        # 2. Servers sending metrics to LAMA (Enabled in selection)
        res = conn.execute(text("""
            SELECT 
                COUNT(*) as total,
                COUNT(*) FILTER (WHERE s.location_id = 3 AND s.os_type != 'ECS') as ec2_sending,
                COUNT(*) FILTER (WHERE s.location_id IN (1, 2)) as physical_sending
            FROM server_status s
            INNER JOIN lama_exchange_server_selection less ON s.id = less.server_id
            WHERE less.enabled = TRUE
            AND s.ip NOT IN ('aws', 'aws-ecs')
        """)).fetchone()
        
        # Note: ECS services are collected from metric_sources
        res_ecs = conn.execute(text("""
            SELECT COUNT(*) 
            FROM metric_sources 
            WHERE type = 'ecs' AND enabled = TRUE
        """)).fetchone()
        
        counts['sending'] = {
            'total': res[0] + res_ecs[0],
            'ec2': res[1],
            'ecs': res_ecs[0],
            'physical': res[2]
        }

    return counts

if __name__ == "__main__":
    try:
        counts = get_counts()
        print("| Category | Server Dashboard | Sending to LAMA API |")
        print("|----------|------------------|---------------------|")
        print(f"| EC2 Instances | {counts['dashboard']['ec2']} | {counts['sending']['ec2']} |")
        print(f"| ECS Services | {counts['dashboard']['ecs']} | {counts['sending']['ecs']} |")
        print(f"| Physical (DC/DR) | {counts['dashboard']['physical']} | {counts['sending']['physical']} |")
        print(f"| **Total** | **{counts['dashboard']['total']}** | **{counts['sending']['total']}** |")
    except Exception as e:
        print(f"Error: {e}")
