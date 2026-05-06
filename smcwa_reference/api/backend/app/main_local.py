from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routes.auth import router as auth_router
from app.routes.users import router as users_router
from app.local_storage import init_users

app = FastAPI(title="SMC LAMA Backend - Local Mode")

# Initialize local storage on startup
@app.on_event("startup")
def startup_event():
    init_users()
    print("Application started - local mode (JSON storage)")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router, prefix="/auth")
app.include_router(users_router, prefix="/v1/users")

@app.get("/")
async def home():
    return {"msg": "Backend running in local mode", "storage": "JSON files"}

@app.get("/v1/dashboard")
async def dashboard():
    """Mock dashboard endpoint with sample data"""
    return {
        "summary": {
            "total": 27,
            "up": 22,
            "down": 5,
            "warn": 0
        },
        "instances": [
            {
                "id": 1,
                "name": "SMCXTS",
                "system": "FOREX",
                "private_ip": "192.168.1.10",
                "public_ip": "203.168.1.50",
                "status": "UP",
                "cpu": 45.2,
                "memory": 62.5,
                "hdd": 48.3,
                "last_seen": "2025-11-18T05:00:00Z"
            },
            {
                "id": 2,
                "name": "odlnlama",
                "system": "EQUITY",
                "private_ip": "192.168.1.11",
                "public_ip": "203.168.1.51",
                "status": "UP",
                "cpu": 38.7,
                "memory": 55.2,
                "hdd": 72.1,
                "last_seen": "2025-11-18T05:00:00Z"
            },
            {
                "id": 3,
                "name": "mcx-server",
                "system": "MCX",
                "private_ip": "192.168.1.12",
                "public_ip": "203.168.1.52",
                "status": "DOWN",
                "cpu": 0,
                "memory": 0,
                "hdd": 0,
                "last_seen": "2025-11-18T04:45:00Z"
            }
        ]
    }
