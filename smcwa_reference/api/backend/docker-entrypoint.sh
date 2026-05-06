#!/bin/bash
# Docker entrypoint script for SMC-LAMA API
# The Go agents are now built via a multi-stage Docker build.
# This script is now simplified for just starting the application.

set -e

echo "=========================================="
echo "SMC-LAMA API Startup"
echo "=========================================="
echo "✅ Go agents are pre-built. Skipping build."
echo ""
echo "🚀 Starting API server..."
echo "=========================================="

# Execute the main command passed to the container
exec "$@"