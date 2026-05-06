import os
import json
from sqlalchemy import create_engine, text

# Get DB URL from environment variables as configured in Docker
user = os.getenv("POSTGRES_USER", "lama")
password = os.getenv("POSTGRES_PASSWORD", "")
host = os.getenv("POSTGRES_HOST", "postgres")
db = os.getenv("POSTGRES_DB", "lama_prod")

db_url = f"postgresql://{user}:{password}@{host}:5432/{db}"

try:
    engine = create_engine(db_url)
    with engine.connect() as conn:
        print("--- Checking for ALB/NLB in metric_sources table ---")
        # Query for ecs type in metric_sources
        query = text("""
            SELECT id, name, environment, config
            FROM metric_sources
            WHERE type = 'ecs'
        """)
        res = conn.execute(query).fetchall()
        
        if not res:
            print("No 'ecs' type metric sources found.")
        else:
            for row in res:
                ms_id, name, env, config = row
                # config is often stored as JSON or a dict depending on the SQLAlchemy setup
                if isinstance(config, str):
                    try:
                        config_dict = json.loads(config)
                    except:
                        config_dict = {}
                else:
                    config_dict = config or {}
                
                alb_arn = config_dict.get('albArn')
                tg_arn = config_dict.get('targetGroupArn')
                nlb_arn = config_dict.get('nlbArn')
                
                print(f"ID: {ms_id} | Name: {name} | Env: {env}")
                print(f"  ALB ARN: {alb_arn}")
                print(f"  TG ARN:  {tg_arn}")
                if nlb_arn:
                    print(f"  NLB ARN: {nlb_arn}")
                print("-" * 30)
                
except Exception as e:
    print(f"Error: {e}")
