#!/bin/bash
# SMC LAMA V2.0 - 100% Automated Fresh Build Bootstrap
# This script generates all required secrets and starts the stack.

set -e

ENV_FILE="smc-lama-config/.env"

echo "🚀 Starting 100% Automated LAMA V2.0 Bootstrap..."

# 1. Generate .env if it doesn't exist
if [ ! -f "$ENV_FILE" ]; then
    echo "📄 Generating fresh .env with secure random secrets..."
    
    # Generate secure random strings (Alphanumeric only to prevent shell escaping issues)
    PG_PASS=$(LC_ALL=C tr -dc 'A-Za-z0-9' < /dev/urandom | head -c 16)
    ADMIN_PASS=$(LC_ALL=C tr -dc 'A-Za-z0-9' < /dev/urandom | head -c 12)
    JWT_SEC=$(openssl rand -hex 32)
    
    cat <<EOF > "$ENV_FILE"
# --- Automated Fresh Build Secrets ---
POSTGRES_USER=lama
POSTGRES_PASSWORD=$PG_PASS
POSTGRES_DB=lama_prod

ADMIN_EMAIL=admin@lama.local
ADMIN_PASSWORD=$ADMIN_PASS
JWT_SECRET=$JWT_SEC

# --- Data Source Defaults ---
CLICKHOUSE_HOST=lama_clickhouse
CLICKHOUSE_PORT=8123
CLICKHOUSE_PASSWORD=
POSTGRES_HOST=postgres

# --- LAMA Exchange Config ---
LAMA_EXCHANGE_SSL_VERIFY=true
AWS_DEFAULT_REGION=ap-south-1
# AWS_ROLE_ARN= (Set this manually for AWS metrics)
EOF
    # VAPT FIX: Secure file permissions
    chmod 600 "$ENV_FILE"
    echo "✅ .env created with strict 600 permissions."
else
    echo "ℹ️  Existing .env found. Using existing secrets."
fi

# 2. VAPT: Ensure SSL Certificates exist (Auto-generate self-signed if missing)
CERT_DIR="smc-lama-config/certificates"
mkdir -p "$CERT_DIR"
if [ ! -f "$CERT_DIR/server.crt" ]; then
    echo "🔐 VAPT: SSL Certificates missing. Generating self-signed for security..."
    openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
        -keyout "$CERT_DIR/server.key" -out "$CERT_DIR/server.crt" \
        -subj "/C=IN/ST=Delhi/L=Delhi/O=SMC/CN=smclama.local"
    echo "✅ SSL Certificates generated."
fi

# 3. VAPT: Hardening Nginx Configuration (Banner Grabbing & CSP)
echo "🛡️  VAPT: Hardening Nginx security headers..."
NGINX_CONF="smc-lama-config/nginx/lama.conf"
if [ -f "$NGINX_CONF" ]; then
    # Disable server tokens (Banner Grabbing)
    sed -i 's/server_tokens on;/server_tokens off;/g' "$NGINX_CONF"
    # Ensure Security Headers are present
    if ! grep -q "X-Frame-Options" "$NGINX_CONF"; then
        sed -i '/server {/a \    add_header X-Frame-Options "SAMEORIGIN";\n    add_header X-Content-Type-Options "nosniff";\n    add_header X-XSS-Protection "1; mode=block";\n    add_header Content-Security-Policy "default-src '\''self'\''; script-src '\''self'\'' '\''unsafe-inline'\''; style-src '\''self'\'' '\''unsafe-inline'\'';";' "$NGINX_CONF"
    fi
    echo "✅ Nginx security headers applied."
fi

# 4. VAPT: Enforce Production Mode (Security Misconfiguration)
echo "🔒 VAPT: Enforcing strict production security (Disabling Swagger/Debug)..."
sed -i 's/ENVIRONMENT=dev/ENVIRONMENT=prod/g' "$ENV_FILE"
sed -i 's/DEBUG=true/DEBUG=false/g' "$ENV_FILE"

# 5. 🤖 AI SCHEDULER: Verify AI module is present
echo "🤖 AI: Verifying AI Scheduler Intelligence Layer..."
AI_MODULE="api/backend/app/utils/scheduler_ai.py"
if [ -f "$AI_MODULE" ]; then
    echo "✅ AI Scheduler module found"
    # Validate syntax
    if python3 -m py_compile "$AI_MODULE" 2>/dev/null; then
        echo "✅ AI module syntax validated"
    else
        echo "⚠️  AI module has syntax errors - will be skipped"
    fi
else
    echo "⚠️  AI Scheduler module not found - schedulers will run without AI enhancements"
    echo "   AI features: Predictive validation, auto-healing, drift detection"
    echo "   To add AI: Ensure scheduler_ai.py exists in api/backend/app/utils/"
fi

# 2. Run Docker Compose Build & Up
echo "🐳 Building and starting LAMA V2.0 containers..."
cd smc-lama-config
docker compose up -d --build

echo "✨ LAMA V2.0 is now 100% Automated and Running!"
echo "🤖 AI-Enhanced Schedulers: Active (if module present)"
echo "Check logs: docker compose logs -f api"
