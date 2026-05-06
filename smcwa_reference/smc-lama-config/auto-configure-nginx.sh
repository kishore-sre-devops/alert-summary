#!/bin/bash
# Auto-configure nginx based on certificate availability
# This script runs automatically on container startup

set -e

CERT_DIR="/etc/nginx/ssl"
CONFIG_DIR="/etc/nginx/conf.d"
CERT_FILE="$CERT_DIR/fullchain.crt"
KEY_FILE="$CERT_DIR/wildcard_smcindiaonline_com.key"

# Alternative certificate file names
ALT_CERT_NAMES=(
    "smclama.smcindiaonline.com.crt"
    "cert.crt"
    "certificate.crt"
    "*.crt"
)

ALT_KEY_NAMES=(
    "smclama.smcindiaonline.com.key"
    "key.key"
    "private.key"
    "*.key"
)

echo "=========================================="
echo "Nginx Auto-Configuration"
echo "=========================================="

# Check for certificates
CERT_FOUND=""
KEY_FOUND=""

# Check primary certificate file
if [ -f "$CERT_FILE" ]; then
    CERT_FOUND="$CERT_FILE"
    echo "✅ Found certificate: $CERT_FILE"
else
    # Check alternative names
    for alt_cert in "${ALT_CERT_NAMES[@]}"; do
        if [ -f "$CERT_DIR/$alt_cert" ]; then
            CERT_FOUND="$CERT_DIR/$alt_cert"
            echo "✅ Found certificate: $CERT_FOUND"
            break
        fi
    done
fi

# Check primary key file
if [ -f "$KEY_FILE" ]; then
    KEY_FOUND="$KEY_FILE"
    echo "✅ Found key: $KEY_FILE"
else
    # Check alternative names
    for alt_key in "${ALT_KEY_NAMES[@]}"; do
        if [ -f "$CERT_DIR/$alt_key" ]; then
            KEY_FOUND="$CERT_DIR/$alt_key"
            echo "✅ Found key: $KEY_FOUND"
            break
        fi
    done
fi

# Determine configuration
if [ -n "$CERT_FOUND" ] && [ -n "$KEY_FOUND" ]; then
    echo ""
    echo "✅ Certificates found - Using HTTPS configuration"
    
    # Create HTTPS config from template
    cat > "$CONFIG_DIR/default.conf" << 'NGINX_SSL_EOF'
# Production Configuration with SSL/HTTPS
# Auto-configured by startup script

# HTTP Server - Redirect to HTTPS
server {
    listen 80;
    server_name smclama.smcindiaonline.com _;
    
    # Redirect all HTTP traffic to HTTPS
    return 301 https://$host$request_uri;
}

# HTTPS Server
server {
    listen 443 ssl http2;
    server_name smclama.smcindiaonline.com _;
    client_max_body_size 100M;
    
    # SSL Certificate Configuration (auto-detected)
    ssl_certificate /etc/nginx/ssl/fullchain.crt;
    ssl_certificate_key /etc/nginx/ssl/wildcard_smcindiaonline_com.key;
    
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
    
    # Allow underscores in headers
    underscores_in_headers on;

    # Block source map files from being served (security)
    location ~* \.map$ {
        deny all;
        return 404;
    }

    # Root location - serve React app at root level
    location / {
        root /usr/share/nginx/html;
        try_files $uri $uri/ /index.html;
        index index.html;
    }

    # ======================
    # Single API Backend
    # ======================
    location /api/ {
        rewrite ^/api/(.*)$ /$1 break;
        proxy_pass http://lama_api:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-Host $host;
        proxy_set_header X-Forwarded-Port $server_port;
        proxy_set_header Authorization $http_authorization;
        proxy_pass_request_headers on;
        
        # WebSocket support
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
NGINX_SSL_EOF

    # Update certificate paths if using alternative names
    if [ "$CERT_FOUND" != "$CERT_FILE" ] || [ "$KEY_FOUND" != "$KEY_FILE" ]; then
        sed -i "s|ssl_certificate /etc/nginx/ssl/fullchain.crt;|ssl_certificate $CERT_FOUND;|g" "$CONFIG_DIR/default.conf"
        sed -i "s|ssl_certificate_key /etc/nginx/ssl/wildcard_smcindiaonline_com.key;|ssl_certificate_key $KEY_FOUND;|g" "$CONFIG_DIR/default.conf"
    fi
    
    echo "✅ HTTPS configuration created"
else
    echo ""
    echo "⚠️  Certificates not found - Using HTTP-only configuration"
    
    # Create HTTP-only config
    cat > "$CONFIG_DIR/default.conf" << 'NGINX_HTTP_EOF'
# HTTP Server Configuration (No SSL)
# Auto-configured by startup script

server {
    listen 80;
    server_name smclama.smcindiaonline.com _;
    client_max_body_size 100M;
    
    # Allow underscores in headers
    underscores_in_headers on;

    # Root location - serve React app at root level
    location / {
        root /usr/share/nginx/html;
        try_files $uri $uri/ /index.html;
        index index.html;
    }

    # ======================
    # Single API Backend
    # ======================
    location /api/ {
        rewrite ^/api/(.*)$ /$1 break;
        proxy_pass http://lama_api:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-Host $host;
        proxy_set_header X-Forwarded-Port $server_port;
        proxy_set_header Authorization $http_authorization;
        proxy_pass_request_headers on;
        
        # WebSocket support
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
NGINX_HTTP_EOF
    
    echo "✅ HTTP-only configuration created"
fi

echo ""
echo "=========================================="
echo "Configuration Complete"
echo "=========================================="

# Test nginx configuration
echo "Testing nginx configuration..."
nginx -t

if [ $? -eq 0 ]; then
    echo "✅ Nginx configuration is valid"
else
    echo "❌ Nginx configuration test failed"
    exit 1
fi

