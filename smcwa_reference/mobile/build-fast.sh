#!/bin/bash
set -e
echo "⚡ Starting FAST SMC LAMA Mobile Build..."
# Only rebuild what changed
cd android
chmod +x gradlew
echo "🔨 Running gradlew assembleRelease (with cache)..."
./gradlew assembleRelease --daemon
echo "✅ Fast Build completed successfully!"
