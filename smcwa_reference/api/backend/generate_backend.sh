#!/usr/bin/env bash
set -euo pipefail

# generate_backend.sh
# Creates a FastAPI backend scaffold (auth + users + metrics + clickhouse + DB init)
# Intended to be run from the folder where you want the backend (e.g. /root/LAMA/SMC-LAMA/api/backend)

ROOT_DIR=$(pwd)
echo "Creating backend in: $ROOT_DIR"

# Create directories
mkdir -p app app/routes app/models app/db app/templates

# requirements.txt
cat > requirements.txt <<'PYREQ'
fastapi
uvicorn[standard]
clickhouse-connect
sqlalchemy
psycopg2-binary
bcrypt
python-jose[cryptography]
passlib[bcrypt]
python-multipart
PYREQ

# Dockerfile
cat > Dockerfile <<'DOCK'
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
ENV PYTHONUNBUFFERED=1
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
DOCK

# app/db/db.py - SQLAlchemy engine and initializer
cat > app/db/db.py <<'PY'
from sqlalchemy import create_engine, MetaData, Table, Column, Integer, String, DateTime, Text
from sqlalchemy.sql import func
import os

POSTGRES_HOST = os.getenv('POSTGRES_HOST', 'postgres_prod')
POSTGRES_PORT = os.getenv('POSTGRES_PORT', '5432')
POSTGRES_USER = os.getenv('POSTGRES_USER', 'lama')
POSTGRES_PASSWORD = os.getenv('POSTGRES_PASSWORD', '')
POSTGRES_DB = os.getenv('POSTGRES_DB', os.getenv('POSTGRES_DATABASE', 'lama_prod'))

DATABASE_URL = f"postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
metadata = MetaData()

users = Table(
    'users', metadata,
    Column('id', Integer, primary_key=True, autoincrement=True),
    Column('email', String(255), unique=True, nullable=False),
    Column('password', Text, nullable=False),
    Column('role', String(50), nullable=False, default='user'),
    Column('created_at', DateTime(timezone=True), server_default=func.now())
)

# create tables if not exists
def init_db():
    metadata.create_all(engine)

if __name__ == '__main__':
    init_db()
    print('DB initialized')
PY

# app/models/user.py
cat > app/models/user.py <<'PY'
from pydantic import BaseModel
from typing import Optional

class UserCreate(BaseModel):
    email: str
    password: str

class UserOut(BaseModel):
    id: int
    email: str
    role: str
    created_at: Optional[str]
PY

# app/routes/auth.py
cat > app/routes/auth.py <<'PY'
from fastapi import APIRouter, HTTPException
from starlette.status import HTTP_401_UNAUTHORIZED
from pydantic import BaseModel
from sqlalchemy import select
from app.db.db import engine, users
import bcrypt
import os
from jose import jwt

router = APIRouter(prefix='/api/auth')

JWT_SECRET = os.getenv('JWT_SECRET', 'change_this_secret')
JWT_ALGO = 'HS256'
JWT_EXP_SECONDS = int(os.getenv('JWT_EXP_SECONDS', '3600'))

class LoginPayload(BaseModel):
    email: str
    password: str

@router.post('/login')
def login(payload: LoginPayload):
    with engine.connect() as conn:
        q = select([users.c.id, users.c.email, users.c.password, users.c.role]).where(users.c.email == payload.email)
        r = conn.execute(q).fetchone()
        if not r:
            raise HTTPException(HTTP_401_UNAUTHORIZED, 'invalid credentials')
        stored = r['password']
        if isinstance(stored, str):
            stored_bytes = stored.encode('utf-8')
        else:
            stored_bytes = stored
        if not bcrypt.checkpw(payload.password.encode('utf-8'), stored_bytes):
            raise HTTPException(HTTP_401_UNAUTHORIZED, 'invalid credentials')

        token = jwt.encode({
            'sub': r['email']
        }, JWT_SECRET, algorithm=JWT_ALGO)

        return { 'token': token }
PY

# app/routes/metrics.py
cat > app/routes/metrics.py <<'PY'
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List
import clickhouse_connect
import os

router = APIRouter(prefix='/api/v1')

CLICKHOUSE_HOST = os.getenv('CLICKHOUSE_HOST', 'lama_clickhouse')
CLICKHOUSE_PORT = int(os.getenv('CLICKHOUSE_PORT', '8123'))
CLICKHOUSE_USER = os.getenv('CLICKHOUSE_USER', 'default')
CLICKHOUSE_PASS = os.getenv('CLICKHOUSE_PASSWORD', '')
CLICKHOUSE_DB = os.getenv('CLICKHOUSE_DB', 'lama_prod')

try:
    ch_client = clickhouse_connect.get_client(
        host=CLICKHOUSE_HOST,
        port=CLICKHOUSE_PORT,
        username=CLICKHOUSE_USER,
        password=CLICKHOUSE_PASS,
        database=CLICKHOUSE_DB
    )
except Exception as e:
    print('❌ Failed to connect to ClickHouse:', e)
    ch_client = None

class Metric(BaseModel):
    name: str
    min: float
    max: float
    avg: float
    med: float

class MetricsPayload(BaseModel):
    member_id: str
    instance_id: str
    timestamp: float
    metrics: List[Metric]

@router.post('/metrics')
def ingest_metrics(payload: MetricsPayload):
    if ch_client is None:
        raise HTTPException(500, 'ClickHouse not available')
    rows = []
    for m in payload.metrics:
        rows.append([
            payload.member_id,
            payload.instance_id,
            int(payload.timestamp),
            m.name,
            m.min,
            m.max,
            m.avg,
            m.med
        ])
    try:
        ch_client.insert(
            'metrics',
            rows,
            column_names=['member_id','instance_id','timestamp','metric_name','min','max','avg','med']
        )
    except Exception as e:
        raise HTTPException(500, f'ClickHouse insert error: {e}')
    return { 'status': 'OK', 'rows': len(rows) }

@router.get('/metrics/query')
def query_metrics(member_id: str, instance_id: str, metric: str):
    q = f"""
    SELECT timestamp, min, max, avg, med
    FROM metrics
    WHERE member_id = '{member_id}'
      AND instance_id = '{instance_id}'
      AND metric_name = '{metric}'
    ORDER BY timestamp DESC
    LIMIT 500
    """
    try:
        res = ch_client.query(q)
        return {'status':'OK', 'rows': res.result_rows}
    except Exception as e:
        raise HTTPException(500, f'ClickHouse query error: {e}')
PY

# app/main.py
cat > app/main.py <<'PY'
from fastapi import FastAPI
from app.routes import auth, metrics
from app.db import db
import os

app = FastAPI(title='SMC LAMA Backend (combined)')

# initialize postgres tables
try:
    db.init_db()
    print('Postgres DB initialized')
except Exception as e:
    print('DB init failed:', e)

# include routers
app.include_router(auth.router)
app.include_router(metrics.router)

@app.get('/')
def root():
    return {'msg': 'SMC LAMA Backend running'}
PY

# bootstrap script to create admin user if missing
cat > bootstrap_create_admin.py <<'PY'
from app.db.db import engine, users
import bcrypt

ADMIN_EMAIL = os.getenv('ADMIN_EMAIL', 'admin@smc.com')
ADMIN_PASSWORD = os.getenv('ADMIN_PASSWORD', 'Admin@123')
from sqlalchemy import select

with engine.connect() as conn:
    q = select([users.c.id]).where(users.c.email == ADMIN_EMAIL)
    r = conn.execute(q).fetchone()
    if not r:
        hashed = bcrypt.hashpw(ADMIN_PASSWORD.encode('utf-8'), bcrypt.gensalt()).decode()
        conn.execute(users.insert().values(email=ADMIN_EMAIL, password=hashed, role='admin'))
        print('Created admin user', ADMIN_EMAIL)
    else:
        print('Admin already exists')
PY

# .env.example
cat > .env.example <<'ENV'
# Postgres
POSTGRES_HOST=postgres_prod
POSTGRES_PORT=5432
POSTGRES_USER=lama
POSTGRES_PASSWORD=SmcPr0d_DB_yQH8j@Rz!53
POSTGRES_DB=lama_prod

# ClickHouse
CLICKHOUSE_HOST=lama_clickhouse
CLICKHOUSE_PORT=8123
CLICKHOUSE_USER=default
CLICKHOUSE_PASSWORD=
CLICKHOUSE_DB=lama_prod

# JWT
JWT_SECRET=change_this_secret
JWT_EXP_SECONDS=3600

# Admin credentials to auto-create
ADMIN_EMAIL=admin@smc.com
ADMIN_PASSWORD=Admin@123
ENV

# Make bootstrap runnable in container start (append to Dockerfile run)

# Make files executable and run db init locally so user can test before docker
python3 - <<'PY'
import sys, subprocess
print('Running local DB init (may fail if DB not reachable)')
try:
    subprocess.run(['python3','app/db/db.py'], check=True)
except Exception as e:
    print('Local DB init skipped or failed:', e)
PY

echo "\nDONE: generate_backend.sh created backend files in $ROOT_DIR"
echo "Next steps:\n 1) Review .env.example and create .env in this folder with correct credentials.\n 2) Build and run with your docker-compose (it should point to this folder as build context).\n 3) After containers are up run inside api container: python3 bootstrap_create_admin.py to create admin user (or set ADMIN_* envs and let container create on start)."
