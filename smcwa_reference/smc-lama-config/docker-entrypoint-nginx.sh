#!/bin/sh
# Nginx entrypoint with auto-configuration
# Automatically detects certificates and configures nginx accordingly
# Runs inside nginx container on startup - NO MANUAL STEPS REQUIRED

set -e

CERT_DIR="/etc/nginx/ssl"
CONFIG_DIR="/etc/nginx/conf.d"
CONFIG_FILE="$CONFIG_DIR/default.conf"

echo "=========================================="
echo "Checking for Mobile Source Code..."
echo "=========================================="

DOWNLOADS_DIR="/usr/share/nginx/html/mobile_apps"
mkdir -p "$DOWNLOADS_DIR"

if [ -d "/mobile_source" ]; then
    echo "📱 Mobile source found mounted at /mobile_source"
    echo "📦 Creating source code archive in background..."
    # Create tarball excluding node_modules to keep it small (backgrounded)
    tar -czf "$DOWNLOADS_DIR/mobile_source.tar.gz" -C /mobile_source --exclude='node_modules' . &
    echo "✅ Tarball process started"
    
    # Copy latest APK if it exists
    if [ -f "/mobile_source/smclama-v1.0.53-fixed.apk" ]; then
        cp "/mobile_source/smclama-v1.0.53-fixed.apk" "$DOWNLOADS_DIR/smclama-v1.0.53-fixed.apk"
        # Create a generic link for the current version
        cp "/mobile_source/smclama-v1.0.53-fixed.apk" "$DOWNLOADS_DIR/smc-lama.apk"
    fi
else
    echo "⚠️  Mobile source not found at /mobile_source"
fi

echo ""
echo "=========================================="
echo "Nginx Auto-Configuration"
echo "=========================================="

# Check for certificates (in order of preference)
CERT_FOUND=""
KEY_FOUND=""

# Check for certificate files
if [ -f "$CERT_DIR/fullchain.crt" ]; then
    CERT_FOUND="fullchain.crt"
elif [ -f "$CERT_DIR/smclama.smcindiaonline.com.crt" ]; then
    CERT_FOUND="smclama.smcindiaonline.com.crt"
elif [ -f "$CERT_DIR/cert.crt" ]; then
    CERT_FOUND="cert.crt"
fi

# Check for key files
if [ -f "$CERT_DIR/wildcard_smcindiaonline_com.key" ]; then
    KEY_FOUND="wildcard_smcindiaonline_com.key"
elif [ -f "$CERT_DIR/smclama.smcindiaonline.com.key" ]; then
    KEY_FOUND="smclama.smcindiaonline.com.key"
elif [ -f "$CERT_DIR/key.key" ]; then
    KEY_FOUND="key.key"
fi

# Determine configuration
if [ -n "$CERT_FOUND" ] && [ -n "$KEY_FOUND" ]; then
    echo "✅ Certificates found:"
    echo "   Certificate: $CERT_FOUND"
    echo "   Key: $KEY_FOUND"
    echo ""
    echo "📝 Using HTTPS configuration..."
    
    # Create HTTPS configuration (Dual Mode: Supports ALB HTTP & Direct HTTPS)
    cat > "$CONFIG_FILE" << NGINX_SSL_EOF
# Production Configuration with SSL/HTTPS
# Auto-configured on container startup

server {
    listen 80;
    listen 443 ssl;
    http2 on;
    server_name smclama.smcindiaonline.com _;
    client_max_body_size 100M;
    
    # SSL Certificate Configuration (auto-detected)
    ssl_certificate /etc/nginx/ssl/$CERT_FOUND;
    ssl_certificate_key /etc/nginx/ssl/$KEY_FOUND;
    
    # SSL Security Settings
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers 'ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384:ECDHE-ECDSA-CHACHA20-POLY1305:ECDHE-RSA-CHACHA20-POLY1305:DHE-RSA-AES128-GCM-SHA256:DHE-RSA-AES256-GCM-SHA384';
    ssl_prefer_server_ciphers off;
    ssl_session_cache shared:SSL:10m;
    ssl_session_timeout 10m;
    ssl_session_tickets off;
    
    # Security Headers
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Content-Security-Policy "default-src 'self' http: https: data: blob: 'unsafe-inline' 'unsafe-eval'; frame-ancestors 'self';" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;
    
    # Hide server version
    server_tokens off;
    
    # Allow underscores in headers
    underscores_in_headers on;

    # Dynamic DNS resolution for Docker containers
    resolver 127.0.0.11 valid=30s;
    set \$upstream_api lama_api;

    # Mobile App Download
    location /download/smclama-v1.0.53-fixed.apk {
        alias /usr/share/nginx/html/mobile_apps/smclama-v1.0.53-fixed.apk;
        add_header Content-Disposition 'attachment; filename="smclama-v1.0.53-fixed.apk"';
        default_type application/vnd.android.package-archive;
    }

    location /download/smclama-v1.0.52.apk {
        alias /usr/share/nginx/html/mobile_apps/smclama-v1.0.52.apk;
        add_header Content-Disposition 'attachment; filename="smclama-v1.0.52.apk"';
        default_type application/vnd.android.package-archive;
    }

    location /download/smc-lama-v1.0.51.apk {
        alias /usr/share/nginx/html/mobile_apps/smc-lama-v1.0.51.apk;
        add_header Content-Disposition 'attachment; filename="smc-lama-v1.0.51.apk"';
        default_type application/vnd.android.package-archive;
    }

    location /download/smc-lama-v1.0.50.apk {
        alias /usr/share/nginx/html/mobile_apps/smc-lama-v1.0.50.apk;
        add_header Content-Disposition 'attachment; filename="smc-lama-v1.0.50.apk"';
        default_type application/vnd.android.package-archive;
    }

    location /download/smc-lama-v1.0.48.apk {
        alias /usr/share/nginx/html/mobile_apps/smc-lama-v1.0.48.apk;
        add_header Content-Disposition 'attachment; filename="smc-lama-v1.0.48.apk"';
        default_type application/vnd.android.package-archive;
    }

    # Technical Runbook Download
    location /download/SMC_LAMA_RUNBOOK.md {
        alias /usr/share/nginx/html/docs/SMC_LAMA_RUNBOOK.md;
        add_header Content-Disposition 'attachment; filename="SMC_LAMA_RUNBOOK.md"';
        default_type text/markdown;
    }






    # Root location - serve React app at root level
    location / {
        root /usr/share/nginx/html;
        try_files \$uri \$uri/ /index.html;
        index index.html;
        
        # Prevent caching of index.html so updates are seen immediately
        location = /index.html {
            add_header Cache-Control "no-store, no-cache, must-revalidate";
            add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
            add_header X-Frame-Options "SAMEORIGIN" always;
            add_header X-Content-Type-Options "nosniff" always;
            add_header X-XSS-Protection "1; mode=block" always;
        }
    }

    # Block source map files from being served (security) - must come after location /
    location ~* \.map\$ {
        deny all;
        return 404;
    }

    # ======================
    # WebSockets (Real-time)
    # ======================
    location /ws/ {
        rewrite ^/ws/(.*)$ /ws/\$1 break;
        proxy_pass http://\$upstream_api:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_read_timeout 86400;
    }

    # ======================
    # Single API Backend
    # ======================
    location /api/ {
        rewrite ^/api/(.*)$ /\$1 break;
        proxy_pass http://\$upstream_api:8000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_set_header X-Forwarded-Host \$host;
        proxy_set_header X-Forwarded-Port \$server_port;
        proxy_set_header Authorization \$http_authorization;
        proxy_pass_request_headers on;
    }

    # ======================
    # V1 API Backend
    # ======================
    location /v1/ {
        rewrite ^/v1/(.*)$ /v1/\$1 break;
        proxy_pass http://\$upstream_api:8000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_set_header X-Forwarded-Host \$host;
        proxy_set_header X-Forwarded-Port \$server_port;
        proxy_set_header Authorization \$http_authorization;
        proxy_pass_request_headers on;
    }
}
NGINX_SSL_EOF
    
    echo "✅ HTTPS configuration created"
else
    echo "⚠️  Certificates not found"
    echo ""
    echo "📝 Using HTTP-only configuration..."
    
    # Create HTTP-only config
    cat > "$CONFIG_FILE" << NGINX_HTTP_EOF
# HTTP Server Configuration (No SSL)
# Auto-configured on container startup

server {
    listen 80;
    server_name smclama.smcindiaonline.com _;
    client_max_body_size 100M;
    
    # Hide server version
    server_tokens off;
    
    # Security Headers
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Content-Security-Policy "default-src 'self' http: https: data: blob: 'unsafe-inline' 'unsafe-eval'; frame-ancestors 'self';" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;
    
    # Allow underscores in headers
    underscores_in_headers on;

    # Mobile App Download
    location /download/smclama-v1.0.53-fixed.apk {
        alias /usr/share/nginx/html/mobile_apps/smclama-v1.0.53-fixed.apk;
        add_header Content-Disposition 'attachment; filename="smclama-v1.0.53-fixed.apk"';
        default_type application/vnd.android.package-archive;
    }

    location /download/smclama-v1.0.52.apk {
        alias /usr/share/nginx/html/mobile_apps/smclama-v1.0.52.apk;
        add_header Content-Disposition 'attachment; filename="smclama-v1.0.52.apk"';
        default_type application/vnd.android.package-archive;
    }

    location /download/smc-lama-v1.0.51.apk {
        alias /usr/share/nginx/html/mobile_apps/smc-lama-v1.0.51.apk;
        add_header Content-Disposition 'attachment; filename="smc-lama-v1.0.51.apk"';
        default_type application/vnd.android.package-archive;
    }

    location /download/smc-lama-v1.0.50.apk {
        alias /usr/share/nginx/html/mobile_apps/smc-lama-v1.0.50.apk;
        add_header Content-Disposition 'attachment; filename="smc-lama-v1.0.50.apk"';
        default_type application/vnd.android.package-archive;
    }

    location /download/smc-lama-v1.0.48.apk {
        alias /usr/share/nginx/html/mobile_apps/smc-lama-v1.0.48.apk;
        add_header Content-Disposition 'attachment; filename="smc-lama-v1.0.48.apk"';
        default_type application/vnd.android.package-archive;
    }

    # Technical Runbook Download
    location /download/SMC_LAMA_RUNBOOK.md {
        alias /usr/share/nginx/html/docs/SMC_LAMA_RUNBOOK.md;
        add_header Content-Disposition 'attachment; filename="SMC_LAMA_RUNBOOK.md"';
        default_type text/markdown;
    }






    # Root location - serve React app at root level
    location / {
        root /usr/share/nginx/html;
        try_files \$uri \$uri/ /index.html;
        index index.html;

        # Prevent caching of index.html so updates are seen immediately
        location = /index.html {
            add_header Cache-Control "no-store, no-cache, must-revalidate";
            add_header X-Frame-Options "SAMEORIGIN" always;
            add_header X-Content-Type-Options "nosniff" always;
            add_header X-XSS-Protection "1; mode=block" always;
        }
    }

    # ======================
    # WebSockets (Real-time)
    # ======================
    location /ws/ {
        rewrite ^/ws/(.*)$ /ws/\$1 break;
        proxy_pass http://\$upstream_api:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_read_timeout 86400;
    }

    # ======================
    # Single API Backend
    # ======================
    location /api/ {
        rewrite ^/api/(.*)$ /\$1 break;
        proxy_pass http://\$upstream_api:8000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_set_header X-Forwarded-Host \$host;
        proxy_set_header X-Forwarded-Port \$server_port;
        proxy_set_header Authorization \$http_authorization;
        proxy_pass_request_headers on;
    }

    # ======================
    # V1 API Backend
    # ======================
    location /v1/ {
        rewrite ^/v1/(.*)$ /v1/\$1 break;
        proxy_pass http://\$upstream_api:8000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_set_header X-Forwarded-Host \$host;
        proxy_set_header X-Forwarded-Port \$server_port;
        proxy_set_header Authorization \$http_authorization;
        proxy_pass_request_headers on;
    }
}
NGINX_HTTP_EOF
    
    echo "✅ HTTP-only configuration created"
fi

echo ""
echo "=========================================="
echo "Fixing file permissions..."
echo "=========================================="

# Fix permissions for nginx to read files (only if running as root)
if [ "$(id -u)" = "0" ]; then
    # Ensure parent directory is traversable
    chmod 755 /usr/share/nginx 2>/dev/null || true
    chmod -R 755 /usr/share/nginx/html 2>/dev/null || true
    chown -R nginx:nginx /usr/share/nginx/html 2>/dev/null || true
    # Ensure nginx can access the directory
    chmod +x /usr/share/nginx/html 2>/dev/null || true
else
    echo "Skipping permission fix (running as non-root)"
fi

echo ""
echo "=========================================="
echo "Testing nginx configuration..."
echo "=========================================="

# Test nginx configuration
nginx -t

if [ $? -eq 0 ]; then
    echo "✅ Nginx configuration is valid"
    echo ""
    echo "Starting nginx..."
else
    echo "❌ Nginx configuration test failed"
    exit 1
fi

# Start nginx directly
exec nginx -g "daemon off;"