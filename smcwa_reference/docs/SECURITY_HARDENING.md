# SMC-LAMA Security Hardening - VAPT Compliance

## ✅ Security Features Implemented

### 1. Secure Installation Process
- **Interactive password generation during installation**
- Strong random passwords (16+ characters)
- Option for manual password entry
- Credentials saved to secure file (root-only readable)
- No hardcoded passwords exposed in Git

### 2. Authentication Security
- **Bcrypt password hashing** (industry standard)
- **JWT tokens** with 24-hour expiration
- **Rate limiting**: Max 5 failed attempts per IP in 15 minutes
- **Account lockout**: 30-minute block after 5 failed attempts
- **IP tracking**: Failed attempts tracked per IP address
- Dual authentication: Email or mobile login

### 3. Network Security
- **HTTPS enforced**: HTTP automatically redirects to HTTPS
- **TLS 1.2/1.3 only**: Older protocols disabled
- **Strong cipher suites**: Modern encryption algorithms
- **HSTS enabled**: Strict-Transport-Security header
- **CORS restricted**: Specific domains only (no wildcard *)

### 4. HTTP Security Headers
```
X-Frame-Options: SAMEORIGIN          (Clickjacking protection)
X-Content-Type-Options: nosniff      (MIME sniffing protection)
X-XSS-Protection: 1; mode=block      (XSS protection)
Strict-Transport-Security            (Force HTTPS)
```

### 5. Database Security
- **Parameterized queries**: All SQL uses SQLAlchemy ORM
- **No SQL injection**: No string concatenation in queries
- **Connection pooling**: Proper resource management
- **Password encryption**: Bcrypt with salt

### 6. Application Security
- **No XSS vulnerabilities**: No dangerouslySetInnerHTML
- **Input validation**: All user inputs validated
- **Error handling**: No stack traces exposed
- **Activity logging**: Login attempts logged
- **Environment separation**: UAT vs PROD isolated

### 7. Docker Security
- **Internal network**: Services on bridge network
- **Volume isolation**: Sensitive data in volumes only
- **Health checks**: Monitor container status
- **Auto-restart**: Service resilience

## 📋 How to Use Secure Installation

### For Fresh Installation (New Server):

```bash
cd /opt/smc-lama/smc-lama-config

# Run secure installation wizard
./SECURE_INSTALL.sh

# Choose:
# 1. Environment (Production/UAT)
# 2. Admin email (or use default)
# 3. Password method:
#    - Option 1: Enter your own password
#    - Option 2: Generate random strong password (recommended)
```

**What happens:**
1. Script creates `.env` file with your passwords
2. Generates strong JWT secret and database password
3. Shows you the admin credentials on screen
4. Saves credentials to `/root/.lama_credentials_TIMESTAMP.txt`
5. Starts application containers

### For Existing Installation (Upgrade):

```bash
cd /opt/smc-lama/smc-lama-config

# Pull latest code
git pull

# Rebuild containers with security updates
docker compose build api nginx
docker compose up -d

# Your existing .env file is preserved
# Your existing passwords continue to work
# Rate limiting automatically enabled
```

**No action needed** - all security features work automatically!

## 🔒 Rate Limiting Behavior

### Normal Usage:
- Users can login normally
- Failed attempts tracked per IP address
- Successful login clears failed attempt count

### After 5 Failed Attempts:
```
❌ Login failed: Invalid email/mobile or password
   (4 attempts remaining before temporary lock)

❌ Login failed: Invalid email/mobile or password
   (3 attempts remaining before temporary lock)

❌ Login failed: Invalid email/mobile or password
   (2 attempts remaining before temporary lock)

❌ Login failed: Invalid email/mobile or password
   (1 attempt remaining before temporary lock)

❌ Login failed: Invalid email/mobile or password
   (0 attempts remaining)

🔒 Too many failed login attempts. Account temporarily locked.
   Please try again in 30 minutes.
```

### Automatic Unblock:
- After 30 minutes, IP is automatically unblocked
- No admin intervention needed
- Failed attempt counter resets

### Successful Login:
- Clears all failed attempts for that IP
- No lockout even if had previous failures

## 📊 Security Logs

### View Rate Limiting Activity:
```bash
# See blocked IPs and failed attempts
docker compose logs api | grep "\[SECURITY\]"

# Example output:
# [SECURITY] Failed login from 192.168.1.100. 4 attempts remaining before block
# [SECURITY] IP 192.168.1.100 blocked for 30 minutes after 5 failed login attempts
# [SECURITY] IP 192.168.1.100 unblocked after timeout
```

### View All Login Attempts:
```bash
# See all authentication activity
docker compose logs api | grep "Login attempt"
docker compose logs api | grep "Login successful"
```

## 🎯 VAPT Compliance Checklist

| Security Control | Status | Standard |
|-----------------|--------|----------|
| Password Hashing | ✅ Bcrypt | OWASP |
| Password Strength | ✅ 8+ chars | NIST |
| Rate Limiting | ✅ 5/15min | OWASP |
| Account Lockout | ✅ 30min | OWASP |
| HTTPS/TLS | ✅ 1.2/1.3 | PCI-DSS |
| Security Headers | ✅ All | OWASP |
| SQL Injection | ✅ Protected | OWASP |
| XSS Protection | ✅ Protected | OWASP |
| CSRF Protection | ✅ JWT | OWASP |
| Secrets Management | ✅ .env | OWASP |
| Activity Logging | ✅ Enabled | ISO 27001 |
| Error Handling | ✅ Secure | OWASP |

## 🔐 Password Policy

**Minimum Requirements:**
- Length: 8+ characters (recommendation: 12+)
- Complexity: Mix of letters, numbers, symbols recommended
- No common passwords (admin, password123, etc.)
- Unique per user

**Automatic Generation:**
- 16 characters
- Random mix of alphanumeric characters
- Cryptographically secure (OpenSSL)

## 📞 Security Contact

**If you discover a security issue:**
1. Do NOT post publicly
2. Contact: dineshpathak@smcindiaonline.com
3. Include: Description, steps to reproduce, impact

## 🔄 Regular Security Maintenance

### Monthly:
- Review login attempt logs
- Check for blocked IPs
- Verify SSL certificate expiry

### Quarterly:
- Update passwords (recommended)
- Review user accounts
- Update Docker images

### Annually:
- Security audit
- Penetration testing
- Update SSL certificates

## ✅ Verification Steps After Installation

### 1. Test Rate Limiting:
```bash
# Try to login 6 times with wrong password
# Should see: "Too many failed login attempts"
```

### 2. Test HTTPS Redirect:
```bash
curl -I http://smclama.smcindiaonline.com
# Should see: 301 Moved Permanently
# Location: https://...
```

### 3. Test Security Headers:
```bash
curl -I https://smclama.smcindiaonline.com
# Should see:
# X-Frame-Options: SAMEORIGIN
# X-Content-Type-Options: nosniff
# Strict-Transport-Security: max-age=31536000
```

### 4. Test Login:
```bash
# Login with your admin credentials
# Should work normally
```

## 🎉 Benefits

✅ **No downtime** - Existing installations keep working
✅ **No breaking changes** - All features work as before
✅ **Automatic security** - Rate limiting works automatically
✅ **Easy fresh install** - Interactive password setup
✅ **VAPT compliant** - Passes security audits
✅ **Production ready** - Battle-tested security controls

---

**Last Updated**: December 17, 2025
**Version**: 1.0
**Status**: Production Ready ✅
