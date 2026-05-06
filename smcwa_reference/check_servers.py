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

services = [
    "smc-trade-midw-ace-publisher-portal-4",
    "smc-trade-midw-odin-ws-consumer-api-8",
    "smc-trade-midw-fund-api-4h0y",
    "smc-trading-edis-edis-api",
    "smc-trade-midw-order-websockt-api-q01",
    "smc-pre-trade-research-tool-api",
    "smc-pre-trade-sanjay-api",
    "smc-trade-midw-ace-trade-portal-q17r",
    "smc-pre-trade-munshi-api",
    "smc-trade-midw-omex-websocket-api-t11",
    "smc-pre-trade-algo-api",
    "smc-trade-midw-login-api-kv8z",
    "smc-pre-trade-khabri-daemon",
    "smc-trade-midw-login-grpc-87u1",
    "smc-pre-trade-dispatcher-api"
]

ec2_instances = [
    "i-0ca659d2fa5fc4021",
    "i-0f8c6ec6e729c3f50",
    "i-0bc43367ad04d9363"
]

def check_table(table_name, names):
    print(f"\n--- Checking table: {table_name} ---")
    with engine.connect() as conn:
        for name in names:
            query = text(f"SELECT id, name, environment, status FROM {table_name} WHERE name LIKE :name OR external_id = :name")
            result = conn.execute(query, {"name": f"%{name}%"}).fetchall()
            if result:
                for row in result:
                    print(f"FOUND: ID={row[0]}, Name={row[1]}, Env={row[2]}, Status={row[3]}")
            else:
                print(f"NOT FOUND: {name}")

print("Validating presence of ECS services and EC2 instances in the database...")
check_table("server_status", services + ec2_instances)
check_table("application_status", services)
