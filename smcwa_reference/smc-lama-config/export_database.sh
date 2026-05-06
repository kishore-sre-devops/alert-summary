#!/bin/bash
# Export PostgreSQL database for deployment
# This preserves all credentials, configurations, and data

set -e

echo "=========================================="
echo "SMC-LAMA Database Export"
echo "=========================================="

# Configuration
DB_CONTAINER="lama_postgres"
DB_USER="${POSTGRES_USER:-lama}"
DB_NAME="${POSTGRES_DB:-lama}"
EXPORT_FILE="database_export_$(date +%Y%m%d_%H%M%S).sql"
EXPORT_DIR="./database_backups"

# Create export directory
mkdir -p "$EXPORT_DIR"

echo "Exporting database from container: $DB_CONTAINER"
echo "Database: $DB_NAME"
echo "User: $DB_USER"
echo ""

# Check if container is running
if ! docker ps | grep -q "$DB_CONTAINER"; then
    echo "❌ Error: Container $DB_CONTAINER is not running"
    echo "Please start the containers first: docker-compose up -d"
    exit 1
fi

# Export database
echo "📦 Exporting database..."
docker exec -e PGPASSWORD="${POSTGRES_PASSWORD:-SmcLama_DB_2024!}" "$DB_CONTAINER" \
    pg_dump -U "$DB_USER" -d "$DB_NAME" --clean --if-exists --create > "$EXPORT_DIR/$EXPORT_FILE"

if [ $? -eq 0 ]; then
    echo "✅ Database exported successfully: $EXPORT_DIR/$EXPORT_FILE"
    echo ""
    echo "This file contains:"
    echo "  - All user accounts and passwords"
    echo "  - LAMA Exchange credentials (UAT/PROD)"
    echo "  - Server configurations"
    echo "  - Alert configurations"
    echo "  - Threshold settings"
    echo "  - All historical data"
    echo ""
    echo "⚠️  IMPORTANT: This file contains sensitive credentials!"
    echo "   Keep it secure and do not commit to version control."
    echo ""
    echo "File size: $(du -h "$EXPORT_DIR/$EXPORT_FILE" | cut -f1)"
else
    echo "❌ Error: Database export failed"
    exit 1
fi

