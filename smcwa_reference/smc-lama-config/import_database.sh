#!/bin/bash
# Import PostgreSQL database from export file
# This restores all credentials, configurations, and data

set -e

echo "=========================================="
echo "SMC-LAMA Database Import"
echo "=========================================="

# Configuration
DB_CONTAINER="lama_postgres"
DB_USER="${POSTGRES_USER:-lama}"
DB_NAME="${POSTGRES_DB:-lama}"
IMPORT_FILE="${1:-database_backups/database_export_latest.sql}"

if [ ! -f "$IMPORT_FILE" ]; then
    echo "❌ Error: Import file not found: $IMPORT_FILE"
    echo ""
    echo "Usage: $0 [path_to_export_file.sql]"
    echo ""
    echo "Available backup files:"
    ls -lh database_backups/*.sql 2>/dev/null || echo "  No backup files found in database_backups/"
    exit 1
fi

echo "Importing database to container: $DB_CONTAINER"
echo "Database: $DB_NAME"
echo "User: $DB_USER"
echo "Import file: $IMPORT_FILE"
echo ""

# Check if container is running
if ! docker ps | grep -q "$DB_CONTAINER"; then
    echo "❌ Error: Container $DB_CONTAINER is not running"
    echo "Please start the containers first: docker-compose up -d postgres"
    exit 1
fi

# Wait for PostgreSQL to be ready
echo "⏳ Waiting for PostgreSQL to be ready..."
sleep 5

# Import database
echo "📦 Importing database..."
echo "⚠️  WARNING: This will replace all existing data!"
read -p "Are you sure you want to continue? (yes/no): " confirm

if [ "$confirm" != "yes" ]; then
    echo "❌ Import cancelled"
    exit 1
fi

# Import the SQL file
docker exec -i -e PGPASSWORD="${POSTGRES_PASSWORD:-SmcLama_DB_2024!}" "$DB_CONTAINER" \
    psql -U "$DB_USER" -d postgres < "$IMPORT_FILE"

if [ $? -eq 0 ]; then
    echo "✅ Database imported successfully!"
    echo ""
    echo "Restored data includes:"
    echo "  - All user accounts and passwords"
    echo "  - LAMA Exchange credentials (UAT/PROD)"
    echo "  - Server configurations"
    echo "  - Alert configurations"
    echo "  - Threshold settings"
    echo "  - All historical data"
    echo ""
    echo "⚠️  You may need to restart the API container:"
    echo "   docker-compose restart api"
else
    echo "❌ Error: Database import failed"
    exit 1
fi

