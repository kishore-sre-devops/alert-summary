
import os
import sys
import asyncio
import aiomysql
from sqlalchemy import create_engine, text
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives import padding
from cryptography.hazmat.backends import default_backend
import base64

# Add the project root to sys.path
sys.path.append('/opt/smclama/api/backend')

from app.utils.aes_encryption import decrypt_password

# Postgres connection details (from environment or defaults)
POSTGRES_HOST = os.getenv("POSTGRES_HOST", "postgres_prod")
POSTGRES_USER = os.getenv("POSTGRES_USER", "lama")
POSTGRES_DB = os.getenv("POSTGRES_DB", "lama_prod")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "lama123") # Default from Dockerfile/setup

DATABASE_URL = f"postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}:5432/{POSTGRES_DB}"

async def check_vendor_db():
    try:
        engine = create_engine(DATABASE_URL)
        with engine.connect() as conn:
            query = text("SELECT host, port, database, username, password FROM database_config WHERE host = :host AND database = :db")
            result = conn.execute(query, {"host": "192.168.1.21", "db": "xts_broker_b1"}).fetchone()
            
            if not result:
                print("No configuration found for 192.168.1.21 and xts_broker_b1")
                return

            host, port, db_name, user, encrypted_password = result
            password = decrypt_password(encrypted_password)
            
            print(f"Connecting to MySQL at {host}:{port}/{db_name} as {user}...")
            
            mysql_conn = await aiomysql.connect(
                host=host,
                port=port,
                user=user,
                password=password,
                db=db_name,
                connect_timeout=10
            )
            
            async with mysql_conn.cursor(aiomysql.DictCursor) as cursor:
                # Describe table
                print("\nTable Structure for tbl_hardware_metrics_data:")
                await cursor.execute("DESCRIBE tbl_hardware_metrics_data")
                columns = await cursor.fetchall()
                for col in columns:
                    print(f"  {col['Field']}: {col['Type']}")
                
                # Fetch last 5 rows
                print("\nLast 5 rows from tbl_hardware_metrics_data:")
                await cursor.execute("SELECT * FROM tbl_hardware_metrics_data ORDER BY id DESC LIMIT 5")
                rows = await cursor.fetchall()
                for row in rows:
                    print(row)
            
            mysql_conn.close()

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(check_vendor_db())
