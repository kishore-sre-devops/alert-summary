# SMC-LAMA: Fresh System Setup & Restoration Guide

This guide explains how to get the entire SMC-LAMA stack running on a fresh system after a `git pull`. 

For security, sensitive files like passwords, API keys, and SSL certificates are **not** stored in Git. Follow these steps to restore them.

---

## 1. Environment Variables (.env)
You must create `.env` files from the provided templates.

### **Backend Configuration**
1. Navigate to `api/backend/`
2. Copy the template: `cp .env.example .env`
3. Edit `.env` with your production Database and Redis credentials.

### **Infrastructure Configuration**
1. Navigate to `smc-lama-config/`
2. Copy the template: `cp .env.example .env`
3. Edit `.env` with your specific server hostnames and ports.

---

## 2. SSL Certificates (Nginx)
The Nginx container requires SSL certificates to enable HTTPS.

1. Ensure your `.crt` and `.key` files are named correctly according to your `nginx/default-ssl.conf`.
2. Place them in: `smc-lama-config/certificates/`
   - `server.crt`
   - `server.key`

---

## 3. Secrets & Credentials
Certain services require JSON credential files.

1. **Firebase:** Ensure `api/backend/firebase-credentials.json` is present (this is currently tracked in Git).
2. **Backend Secrets:** If you have additional keys, place them in `api/backend/secrets/`.

---

## 4. One-Command Deployment
Once the `.env` and certificates are in place, you can start the entire stack using Docker Compose.

### **Build and Start**
Run this from the root directory:
```bash
docker-compose -f smc-lama-config/docker-compose.yml up --build -d
```

### **Verify Services**
Check if all containers are healthy:
```bash
docker ps
```

---

## 5. Troubleshooting
- **Database Connection Issues:** Verify the `POSTGRES_HOST` in `api/backend/.env` matches the service name in `docker-compose.yml`.
- **Nginx Failures:** Check the logs using `docker logs smc-lama-nginx`. Usually caused by missing SSL files in `smc-lama-config/certificates/`.
- **WebSocket Issues:** Ensure Redis is running and the `REDIS_HOST` is correctly configured in the backend `.env`.

---
*Last Updated: February 28, 2026*
