# SMC-LAMA Fresh Installation & Setup Guide

This guide covers setting up the SMC-LAMA Monitoring and Mobile Alerting System on a fresh Ubuntu server.

## 1. Prerequisites
- **Ubuntu 22.04+**
- **Docker & Docker Compose (v2+)**
- **Python 3.10+** (for utility scripts)
- **Git**

## 2. Initial Setup
1. **Clone the Repository**:
   ```bash
   git clone https://github.com/dineshspathak/aws-lama.git smclama
   cd smclama
   ```

2. **Configuration (.env)**:
   The system requires a `.env` file in the `smc-lama-config/` directory. **This file is NOT in Git for security.**
   ```bash
   cp smc-lama-config/env.example smc-lama-config/.env
   # Edit .env with your production database passwords, Firebase keys, and SMTP settings
   nano smc-lama-config/.env
   ```

3. **SSL Certificates**:
   Place your SSL certificates in `smc-lama-config/certificates/`. Nginx expects these specific filenames:
   - `fullchain.crt`
   - `wildcard_smcindiaonline_com.key`
   
   If these are missing, Nginx will fail to start in HTTPS mode.

4. **Firebase Admin SDK**:
   Place your Firebase service account JSON file at the path defined in your `.env` (default: `api/backend/firebase-credentials.json`). This is required for mobile push notifications.

## 3. Automatic Database Initialization
The system is designed to be "self-healing" on a fresh install.
- **PostgreSQL**: When the `lama_api` or `lama_scheduler` starts, it automatically runs `init_db()`. This creates all tables, adds missing columns (like `last_processed_at`), and sets up unique constraints.
- **ClickHouse**: The build script automatically initializes the ClickHouse schema for high-performance metrics.

## 4. Building and Starting
Use the provided rebuild script to ensure all containers are built with the latest code:
```bash
cd smc-lama-config
chmod +x rebuild-containers.sh
./rebuild-containers.sh
```

## 5. Verification
1. **Check Container Status**:
   ```bash
   docker ps
   ```
   All `lama_*` containers should be "Up" or "Up (healthy)".

2. **Verify Scheduler**:
   Check logs to ensure the Mobile Escalation Worker is running:
   ```bash
   docker logs lama_scheduler | grep "Mobile Escalation Worker"
   ```

3. **Verify API**:
   ```bash
   curl https://your-domain.com/api/v1/health
   ```

## 6. Mobile App Integration
- **Backend URL**: Update the `BASE_URL` in the mobile app's API service to point to your new server's IP or Domain.
- **Firebase**: Ensure the `google-services.json` in the mobile app matches the Firebase project used in the backend.

## 7. Troubleshooting
- **Database Connection**: Ensure `POSTGRES_HOST=lama_postgres` in `.env` matches the service name in `docker-compose.yml`.
- **Nginx 502**: Usually means the `lama_api` container is still starting or has crashed. Check `docker logs lama_api`.
- **No Push Notifications**: Verify the Firebase credentials file exists and is correctly referenced in `.env`.
