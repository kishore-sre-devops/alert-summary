#!/bin/bash
#
# SMC LAMA - Interactive Setup Script
# Run this before docker-compose up for fresh installations
#

set -e

ENV_FILE=".env"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

echo -e "${CYAN}"
echo "╔═══════════════════════════════════════════════════════════╗"
echo "║           SMC LAMA - Fresh Installation Setup             ║"
echo "╚═══════════════════════════════════════════════════════════╝"
echo -e "${NC}"

# Check if .env exists
if [ -f "$ENV_FILE" ]; then
    echo -e "${YELLOW}⚠  Existing .env file found.${NC}"
    read -p "Do you want to reconfigure? (y/N): " RECONFIGURE
    if [[ ! "$RECONFIGURE" =~ ^[Yy]$ ]]; then
        echo -e "${GREEN}✓ Using existing configuration.${NC}"
        exit 0
    fi
    cp "$ENV_FILE" "${ENV_FILE}.backup.$(date +%Y%m%d_%H%M%S)"
    echo -e "${GREEN}✓ Backup created.${NC}"
fi

# Function to generate random password
generate_password() {
    openssl rand -base64 12 | tr -dc 'a-zA-Z0-9' | head -c 16
}

# Function to generate JWT secret
generate_jwt_secret() {
    openssl rand -hex 32
}

echo ""
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${CYAN}  1. DATABASE CONFIGURATION${NC}"
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

# PostgreSQL
DEFAULT_PG_USER="lama"
DEFAULT_PG_DB="lama_prod"
DEFAULT_PG_PASS=$(generate_password)

read -p "PostgreSQL Username [$DEFAULT_PG_USER]: " POSTGRES_USER
POSTGRES_USER=${POSTGRES_USER:-$DEFAULT_PG_USER}

read -p "PostgreSQL Database [$DEFAULT_PG_DB]: " POSTGRES_DB
POSTGRES_DB=${POSTGRES_DB:-$DEFAULT_PG_DB}

read -sp "PostgreSQL Password [auto-generate]: " POSTGRES_PASSWORD
echo ""
POSTGRES_PASSWORD=${POSTGRES_PASSWORD:-$DEFAULT_PG_PASS}

# ClickHouse
read -sp "ClickHouse Password (leave empty for no password): " CLICKHOUSE_PASSWORD
echo ""

echo ""
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${CYAN}  2. ADMIN USER CONFIGURATION${NC}"
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

DEFAULT_ADMIN_EMAIL="admin@lama.local"
DEFAULT_ADMIN_PASS=$(generate_password)

read -p "Admin Email [$DEFAULT_ADMIN_EMAIL]: " ADMIN_EMAIL
ADMIN_EMAIL=${ADMIN_EMAIL:-$DEFAULT_ADMIN_EMAIL}

read -sp "Admin Password [auto-generate]: " ADMIN_PASSWORD
echo ""
ADMIN_PASSWORD=${ADMIN_PASSWORD:-$DEFAULT_ADMIN_PASS}

echo ""
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${CYAN}  3. MONITORING ENDPOINTS${NC}"
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

DEFAULT_PROMETHEUS="http://10.215.33.196:9090"
DEFAULT_MIMIR="http://10.236.26.167:9009/prometheus"

read -p "Prometheus URL [$DEFAULT_PROMETHEUS]: " LGTM_PROMETHEUS_URL
LGTM_PROMETHEUS_URL=${LGTM_PROMETHEUS_URL:-$DEFAULT_PROMETHEUS}

read -p "Mimir URL [$DEFAULT_MIMIR]: " MIMIR_URL
MIMIR_URL=${MIMIR_URL:-$DEFAULT_MIMIR}

echo ""
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${CYAN}  4. AWS CONFIGURATION (Optional)${NC}"
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

DEFAULT_AWS_REGION="ap-south-1"

read -p "AWS Region [$DEFAULT_AWS_REGION]: " AWS_DEFAULT_REGION
AWS_DEFAULT_REGION=${AWS_DEFAULT_REGION:-$DEFAULT_AWS_REGION}

read -p "AWS Role ARN (for ECS metrics, leave empty to skip): " AWS_ROLE_ARN

echo ""
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${CYAN}  5. ENVIRONMENT${NC}"
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

echo "Select environment:"
echo "  1) uat (default)"
echo "  2) prod"
read -p "Choice [1]: " ENV_CHOICE
case $ENV_CHOICE in
    2) ACTIVE_ENVIRONMENT="prod" ;;
    *) ACTIVE_ENVIRONMENT="uat" ;;
esac

# Generate JWT Secret
JWT_SECRET=$(generate_jwt_secret)

# Write .env file
echo ""
echo -e "${YELLOW}Writing configuration...${NC}"

cat > "$ENV_FILE" << EOF
# ═══════════════════════════════════════════════════════════
# SMC LAMA Configuration
# Generated: $(date)
# ═══════════════════════════════════════════════════════════

# --- PostgreSQL ---
POSTGRES_USER=$POSTGRES_USER
POSTGRES_PASSWORD=$POSTGRES_PASSWORD
POSTGRES_DB=$POSTGRES_DB
POSTGRES_HOST=postgres

# --- ClickHouse ---
CLICKHOUSE_HOST=lama_clickhouse
CLICKHOUSE_PORT=8123
CLICKHOUSE_DB=lama
CLICKHOUSE_USER=default
CLICKHOUSE_PASSWORD=$CLICKHOUSE_PASSWORD

# --- Admin User ---
ADMIN_EMAIL=$ADMIN_EMAIL
ADMIN_PASSWORD=$ADMIN_PASSWORD

# --- Security ---
JWT_SECRET=$JWT_SECRET

# --- Monitoring Endpoints ---
LGTM_PROMETHEUS_URL=$LGTM_PROMETHEUS_URL
MIMIR_URL=$MIMIR_URL

# --- AWS Configuration ---
AWS_DEFAULT_REGION=$AWS_DEFAULT_REGION
AWS_ROLE_ARN=$AWS_ROLE_ARN

# --- Application ---
ACTIVE_ENVIRONMENT=$ACTIVE_ENVIRONMENT
LAMA_EXCHANGE_SSL_VERIFY=true
EOF

echo ""
echo -e "${GREEN}╔═══════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║              ✓ Configuration Complete!                    ║${NC}"
echo -e "${GREEN}╚═══════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${CYAN}Summary:${NC}"
echo "  • PostgreSQL: $POSTGRES_USER@$POSTGRES_DB"
echo "  • Admin: $ADMIN_EMAIL"
echo "  • Prometheus: $LGTM_PROMETHEUS_URL"
echo "  • Mimir: $MIMIR_URL"
echo "  • Environment: $ACTIVE_ENVIRONMENT"
[ -n "$AWS_ROLE_ARN" ] && echo "  • AWS Role: $AWS_ROLE_ARN"
echo ""
echo -e "${YELLOW}Credentials saved to .env file. Keep this secure!${NC}"
echo ""
echo -e "${CYAN}Next steps:${NC}"
echo "  1. docker-compose build"
echo "  2. docker-compose up -d"
echo ""
