# SMC-LAMA Production Deployment Checklist

Use this checklist to ensure a successful production deployment.

## Pre-Deployment

- [ ] **Server Requirements Met**
  - [ ] Linux server (Ubuntu 20.04+ or CentOS 7+)
  - [ ] 4GB+ RAM (8GB recommended)
  - [ ] 2+ CPU cores
  - [ ] 20GB+ free disk space
  - [ ] Outbound HTTPS access to internet

- [ ] **Software Installed**
  - [ ] Docker 20.10+ installed
  - [ ] Docker Compose 2.0+ installed
  - [ ] Git installed

- [ ] **Network Configuration**
  - [ ] Server can reach `https://lama.uat.nseindia.com`
  - [ ] Server can reach `https://lama.nseindia.com`
  - [ ] DNS resolution working
  - [ ] Firewall allows outbound HTTPS (443)
  - [ ] Firewall allows inbound HTTP/HTTPS (80/443) if exposing UI

- [ ] **LAMA Exchange Credentials**
  - [ ] UAT credentials obtained (Member ID, Login ID, Password, Secret Key)
  - [ ] PROD credentials obtained (if needed)
  - [ ] Credentials verified with LAMA Exchange team

## Deployment

- [ ] **Repository Setup**
  - [ ] Repository cloned to server
  - [ ] Code is up to date
  - [ ] All files present

- [ ] **Configuration**
  - [ ] `.env` file created from `.env.example`
  - [ ] Database password changed (strong password)
  - [ ] JWT secret changed (generate with `openssl rand -hex 32`)
  - [ ] SSL verification setting configured
  - [ ] Admin credentials configured

- [ ] **Build and Start**
  - [ ] Docker images built: `docker-compose build`
  - [ ] Containers started: `docker-compose up -d`
  - [ ] All containers running: `docker-compose ps`
  - [ ] No container errors in logs

## Verification

- [ ] **Health Checks**
  - [ ] API health check: `curl http://localhost/api/health`
  - [ ] API diagnostics: `curl http://localhost/api/diagnostics`
  - [ ] Database connectivity verified
  - [ ] LAMA Exchange connectivity verified (UAT and PROD)

- [ ] **Application Access**
  - [ ] Web UI accessible: `http://<server-ip>`
  - [ ] Can login with admin credentials
  - [ ] Dashboard loads correctly
  - [ ] All pages accessible

- [ ] **LAMA Exchange Configuration**
  - [ ] Navigate to Configuration page
  - [ ] UAT tab visible
  - [ ] PROD tab visible
  - [ ] Can enter credentials
  - [ ] Save button works
  - [ ] API test result displayed

## Testing

- [ ] **LAMA Exchange Login Test**
  - [ ] Save UAT credentials
  - [ ] Check API test result (should show success or detailed error)
  - [ ] Check API logs: `docker logs lama_api | grep "LAMA Exchange"`
  - [ ] Verify request sent: `docker logs lama_api | grep "\[REQUEST SENT\]"`
  - [ ] Check transaction log in database

- [ ] **Transaction Logging**
  - [ ] Login transactions logged to `exchange_transactions` table
  - [ ] Can query transactions: `SELECT * FROM exchange_transactions WHERE metric_type = 'login'`
  - [ ] Transaction details include request/response data

- [ ] **Network Diagnostics**
  - [ ] DNS resolution working: `nslookup lama.uat.nseindia.com`
  - [ ] HTTPS connectivity: `curl -v https://lama.uat.nseindia.com/api/V1/auth/login`
  - [ ] No firewall blocking requests
  - [ ] No proxy interfering

## Monitoring

- [ ] **Log Monitoring**
  - [ ] API logs accessible: `docker logs lama_api`
  - [ ] Log rotation configured
  - [ ] Error logs monitored

- [ ] **Database Monitoring**
  - [ ] Database backups configured
  - [ ] Transaction logs reviewed regularly
  - [ ] Database health monitored

- [ ] **LAMA Exchange Monitoring**
  - [ ] Regular check of transaction logs
  - [ ] Monitor for failed requests
  - [ ] Track success rate
  - [ ] Alert on persistent failures

## Troubleshooting

If LAMA Exchange not receiving requests:

- [ ] **Check Network**
  - [ ] Test DNS: `nslookup lama.uat.nseindia.com`
  - [ ] Test connectivity: `curl -v https://lama.uat.nseindia.com/api/V1/auth/login`
  - [ ] Check firewall rules
  - [ ] Verify proxy settings (if applicable)

- [ ] **Check Logs**
  - [ ] API logs: `docker logs lama_api | grep "LAMA Exchange"`
  - [ ] Look for `[REQUEST SENT]` entries
  - [ ] Check for errors: `docker logs lama_api | grep -i "error\|failed"`
  - [ ] Review transaction database

- [ ] **Check Configuration**
  - [ ] Credentials correct in Configuration page
  - [ ] Environment (UAT/PROD) selected correctly
  - [ ] Configuration enabled
  - [ ] SSL verification setting appropriate

- [ ] **Database Check**
  - [ ] Transactions being logged: `SELECT COUNT(*) FROM exchange_transactions`
  - [ ] Review recent transactions
  - [ ] Check error messages in transactions

## Post-Deployment

- [ ] **Documentation**
  - [ ] Server IP/domain documented
  - [ ] Admin credentials secured
  - [ ] Access methods documented
  - [ ] Troubleshooting steps documented

- [ ] **Security**
  - [ ] Default passwords changed
  - [ ] JWT secret changed
  - [ ] SSL configured (if exposing externally)
  - [ ] Firewall rules configured
  - [ ] Access restricted appropriately

- [ ] **Backup**
  - [ ] Database backup configured
  - [ ] Backup schedule set
  - [ ] Backup restoration tested

## Support Information

- **Log Locations**:
  - API: `docker logs lama_api`
  - Database: `docker logs lama_postgres`
  - Nginx: `docker logs lama_nginx`

- **Useful Commands**:
  ```bash
  # View all logs
  docker-compose logs -f
  
  # Restart services
  docker-compose restart
  
  # Check status
  docker-compose ps
  
  # Health check
  curl http://localhost/api/health
  
  # Diagnostics
  curl http://localhost/api/diagnostics
  ```

- **Transaction Query**:
  ```sql
  SELECT * FROM exchange_transactions 
  WHERE metric_type = 'login' 
  ORDER BY sent_at DESC 
  LIMIT 10;
  ```

## Contact

For issues:
1. Check logs: `docker logs lama_api`
2. Check transaction database
3. Review diagnostics: `curl http://localhost/api/diagnostics`
4. Contact LAMA Exchange tech team with transaction IDs

