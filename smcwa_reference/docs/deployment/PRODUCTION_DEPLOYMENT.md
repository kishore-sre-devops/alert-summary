# SMC-LAMA Production Deployment Guide

## Overview
This guide provides step-by-step instructions for deploying SMC-LAMA to a production server for testing with LAMA Exchange.

## Prerequisites

### Server Requirements
- **OS**: Linux (Ubuntu 20.04+ or CentOS 7+ recommended)
- **RAM**: Minimum 4GB (8GB recommended)
- **CPU**: 2+ cores
- **Disk**: 20GB+ free space
- **Network**: Outbound HTTPS access to LAMA Exchange APIs
  - UAT: `https://lama.uat.nseindia.com`
  - PROD: `https://lama.nseindia.com`

### Software Requirements
- Docker 20.10+
- Docker Compose 2.0+
- Git (for cloning repository)

## Pre-Deployment Checklist

- [ ] Server has outbound internet access
- [ ] Server can reach LAMA Exchange API endpoints (UAT/PROD)
- [ ] Firewall allows inbound connections on ports 80, 443 (if exposing UI)
- [ ] Docker and Docker Compose installed
- [ ] SSH access to server configured
- [ ] LAMA Exchange credentials obtained (Member ID, Login ID, Password, Secret Key)

## Deployment Steps

### 1. Clone Repository
```bash
cd /opt
git clone <repository-url> smc-lama
cd smc-lama
```

### 2. Configure Environment Variables

Edit `smc-lama-config/docker-compose.yml` and update:
- Database passwords
- JWT secret (generate a strong random secret)
- SSL verification setting (if needed)

Or create `.env` file:
```bash
cd smc-lama-config
cat > .env << EOF
POSTGRES_PASSWORD=YourSecurePassword123!
JWT_SECRET=$(openssl rand -hex 32)
LAMA_EXCHANGE_SSL_VERIFY=true
EOF
```

### 3. Build and Start Services

```bash
cd smc-lama-config
docker-compose build
docker-compose up -d
```

### 4. Verify Deployment

Check all containers are running:
```bash
docker-compose ps
```

Check API health:
```bash
curl http://localhost/api/health
```

Check logs:
```bash
docker-compose logs api --tail 50
```

### 5. Access the Application

- **Web UI**: `http://<server-ip>` or `https://<server-ip>` (if SSL configured)
- **Default Admin**: `dineshpathak@smcindiaonline.com` / `Admin@123`

### 6. Configure LAMA Exchange

1. Login to the web UI
2. Navigate to **Configuration** page
3. Select **UAT** or **PROD** tab
4. Enter credentials:
   - Member ID
   - Login ID
   - Password
   - Secret Key
5. Click **Save**
6. Check the API test result in the message

### 7. Monitor LAMA Exchange Requests

All login and metrics requests are logged to the database. Check transaction logs:

```bash
# Connect to PostgreSQL
docker exec -it lama_postgres psql -U lama -d lama

# View recent login transactions
SELECT 
    id, 
    environment, 
    metric_type, 
    status, 
    status_code, 
    error_message,
    sent_at,
    response_received_at
FROM exchange_transactions 
WHERE metric_type = 'login'
ORDER BY sent_at DESC 
LIMIT 10;
```

## Network Diagnostics

### Test LAMA Exchange Connectivity

From the server, test connectivity:

```bash
# Test UAT endpoint
curl -v https://lama.uat.nseindia.com/api/V1/auth/login

# Test PROD endpoint
curl -v https://lama.nseindia.com/api/V1/auth/login
```

### Check API Logs

```bash
# View all LAMA Exchange API calls
docker logs lama_api 2>&1 | grep -i "LAMA Exchange"

# View recent login attempts
docker logs lama_api 2>&1 | grep -i "\[REQUEST SENT\]\|\[RESPONSE RECEIVED\]\|\[REQUEST FAILED\]"
```

## Troubleshooting

### Issue: LAMA Exchange not receiving requests

**Check 1: Network Connectivity**
```bash
# From server, test DNS resolution
nslookup lama.uat.nseindia.com
nslookup lama.nseindia.com

# Test HTTPS connectivity
curl -v https://lama.uat.nseindia.com/api/V1/auth/login
```

**Check 2: Firewall/Proxy**
- Ensure outbound HTTPS (443) is allowed
- Check if corporate proxy is blocking requests
- Verify IP whitelisting (if LAMA Exchange requires it)

**Check 3: API Logs**
```bash
# Check if requests are being sent
docker logs lama_api 2>&1 | grep "\[REQUEST SENT\]"

# Check for errors
docker logs lama_api 2>&1 | grep -i "error\|failed\|timeout"
```

**Check 4: Database Transactions**
```bash
# Check if transactions are being logged
docker exec -it lama_postgres psql -U lama -d lama -c \
  "SELECT COUNT(*) FROM exchange_transactions WHERE metric_type = 'login';"
```

### Issue: SSL Certificate Errors

If you get SSL errors, you can temporarily disable SSL verification (NOT recommended for production):

```bash
# Add to docker-compose.yml environment:
LAMA_EXCHANGE_SSL_VERIFY=false
```

**Note**: For production, use proper SSL certificates or configure certificate bundle.

### Issue: Timeout Errors

If requests timeout:
1. Check network latency: `ping lama.uat.nseindia.com`
2. Increase timeout in code (currently 60s)
3. Check if requests are reaching the server (check LAMA Exchange logs with tech team)

### Issue: Bad Request (400) Errors

1. Verify payload format matches LAMA Exchange API specification
2. Check password encryption (AES-ECB with Base64)
3. Verify all required fields are present:
   - memberId
   - loginId
   - password (encrypted)
   - secretKey

## Production Configuration

### Security Settings

1. **Change Default Passwords**
   - Update `POSTGRES_PASSWORD` in docker-compose.yml
   - Update `JWT_SECRET` (use strong random value)

2. **Enable SSL Verification**
   ```yaml
   environment:
     LAMA_EXCHANGE_SSL_VERIFY: "true"
   ```

3. **Restrict Network Access**
   - Use firewall rules to restrict access
   - Consider VPN for admin access

### Monitoring

1. **Log Rotation**
   - Configure Docker log rotation
   - Monitor log sizes

2. **Database Backup**
   - Set up regular PostgreSQL backups
   - Store backups securely

3. **Health Checks**
   - Monitor container health
   - Set up alerts for failures

## API Endpoints for Monitoring

### Health Check
```
GET /api/health
```

### LAMA Exchange Transaction Logs
```
GET /api/v1/exchange-transactions?environment=uat&limit=10
```

### System Status
```
GET /api/v1/dashboard/summary
```

## Support and Troubleshooting

### Log Locations
- **API Logs**: `docker logs lama_api`
- **Nginx Logs**: `docker logs lama_nginx`
- **Database Logs**: `docker logs lama_postgres`

### Common Commands

```bash
# Restart all services
docker-compose restart

# View all logs
docker-compose logs -f

# Rebuild after code changes
docker-compose build api
docker-compose up -d api

# Check container status
docker-compose ps

# Access API container shell
docker exec -it lama_api bash
```

## Next Steps After Deployment

1. ✅ Configure LAMA Exchange credentials (UAT first)
2. ✅ Test login API from Configuration page
3. ✅ Verify requests are reaching LAMA Exchange (check with tech team)
4. ✅ Configure servers and agents
5. ✅ Test metrics submission
6. ✅ Monitor transaction logs
7. ✅ Set up alerts and monitoring

## Contact

For issues or questions:
- Check logs: `docker logs lama_api`
- Review transaction database: `exchange_transactions` table
- Contact LAMA Exchange tech team with transaction IDs

