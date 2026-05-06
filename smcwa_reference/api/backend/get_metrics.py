import os
import sys
import json
from sqlalchemy import create_engine, text

db_url = os.environ.get("DATABASE_URL", "postgresql://lama:v3Yw9hi2jUdMQufY@lama_postgres:5432/lama_prod")

try:
    engine = create_engine(db_url)
    with engine.connect() as conn:
        print("Metric,Exchange,SentAt,MetricsJSON")
        res = conn.execute(text("SELECT metric_type, exchange_id, sent_at, metrics_sent FROM exchange_transactions WHERE status_code = 601 ORDER BY sent_at DESC LIMIT 10;")).fetchall()
        for row in res:
            # We use json.dumps for the JSON part to ensure it's easy to read
            print(f"{row[0]}|{row[1]}|{row[2]}|{json.dumps(row[3])}")
except Exception as e:
    print(f"Error: {e}")
