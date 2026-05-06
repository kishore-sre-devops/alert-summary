#!/bin/bash
# Setup nginx configuration on startup
# This script should be run before starting docker-compose
# It auto-detects certificates and configures nginx accordingly

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=========================================="
echo "Nginx Auto-Configuration Setup"
echo "=========================================="
echo ""

# Check for certificates
CERT_DIR="./certificates"
CERT_FILE="$CERT_DIR/fullchain.crt"
KEY_FILE="$CERT_DIR/wildcard_smcindiaonline_com.key"

# Alternative certificate file names to check
CERT_FOUND=""
KEY_FOUND=""

# Check for certificate
if [ -f "$CERT_FILE" ]; then
    CERT_FOUND="$CERT_FILE"
elif [ -f "$CERT_DIR/smclama.smcindiaonline.com.crt" ]; then
    CERT_FOUND="$CERT_DIR/smclama.smcindiaonline.com.crt"
elif [ -f "$CERT_DIR/cert.crt" ]; then
    CERT_FOUND="$CERT_DIR/cert.crt"
fi

# Check for key
if [ -f "$KEY_FILE" ]; then
    KEY_FOUND="$KEY_FILE"
elif [ -f "$CERT_DIR/smclama.smcindiaonline.com.key" ]; then
    KEY_FOUND="$CERT_DIR/smclama.smcindiaonline.com.key"
elif [ -f "$CERT_DIR/key.key" ]; then
    KEY_FOUND="$CERT_DIR/key.key"
fi

# Determine configuration
if [ -n "$CERT_FOUND" ] && [ -n "$KEY_FOUND" ]; then
    echo "✅ Certificates found:"
    echo "   Certificate: $CERT_FOUND"
    echo "   Key: $KEY_FOUND"
    echo ""
    echo "📝 Using HTTPS configuration..."
    
    # Copy SSL config
    cp nginx/default-ssl.conf nginx/default.conf
    
    # Update certificate paths if using alternative names
    if [ "$CERT_FOUND" != "$CERT_FILE" ] || [ "$KEY_FOUND" != "$KEY_FILE" ]; then
        echo "   Updating certificate paths in config..."
        sed -i.bak "s|ssl_certificate /etc/nginx/ssl/fullchain.crt;|ssl_certificate /etc/nginx/ssl/$(basename $CERT_FOUND);|g" nginx/default.conf
        sed -i.bak "s|ssl_certificate_key /etc/nginx/ssl/wildcard_smcindiaonline_com.key;|ssl_certificate_key /etc/nginx/ssl/$(basename $KEY_FOUND);|g" nginx/default.conf
        rm -f nginx/default.conf.bak
    fi
    
    echo "✅ HTTPS configuration enabled"
    echo ""
    echo "   HTTP requests will redirect to HTTPS"
    echo "   HTTPS will be served on port 443"
else
    echo "⚠️  Certificates not found"
    echo ""
    echo "📝 Using HTTP-only configuration..."
    
    # Use HTTP config (already set as default)
    # Just ensure it has correct server_name
    echo "✅ HTTP-only configuration (already set)"
    echo ""
    echo "   HTTP will be served on port 80"
    echo "   To enable HTTPS, place certificates in $CERT_DIR/"
fi

echo ""
echo "=========================================="
echo "Configuration Complete"
echo "=========================================="
echo ""
echo "You can now start services with:"
echo "  docker-compose up -d"
echo ""

