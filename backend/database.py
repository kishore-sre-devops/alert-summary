import os
import time
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv
from sqlalchemy.exc import OperationalError

load_dotenv()

# MySQL Connection String format: mysql+pymysql://user:password@host:port/database
MYSQL_USER = os.getenv("MYSQL_USER", "root")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "")
MYSQL_HOST = os.getenv("MYSQL_HOST", "localhost")
MYSQL_PORT = os.getenv("MYSQL_PORT", "3306")
MYSQL_DB = os.getenv("MYSQL_DB", "alert_summary")

SQLALCHEMY_DATABASE_URL = f"mysql+pymysql://{MYSQL_USER}:{MYSQL_PASSWORD}@{MYSQL_HOST}:{MYSQL_PORT}/{MYSQL_DB}"

# Retry logic for database connection
def get_engine():
    retries = 5
    while retries > 0:
        try:
            engine = create_engine(SQLALCHEMY_DATABASE_URL)
            # Try to connect to verify
            engine.connect()
            return engine
        except Exception:
            retries -= 1
            print(f"Database not ready, retrying in 5s... ({retries} retries left)")
            time.sleep(5)
    return create_engine(SQLALCHEMY_DATABASE_URL)

engine = get_engine()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
