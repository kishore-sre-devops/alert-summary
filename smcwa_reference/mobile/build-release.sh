#!/bin/bash
set -e

echo "🚀 Starting SMC LAMA Mobile Release Build..."

# 1. Environment

export NODE_OPTIONS="--max-old-space-size=4096"
export CI=true
export METRO_DISABLE_WATCHER=true

# 2. Install dependencies

if [ ! -d "node_modules" ]; then
echo "📦 Installing dependencies..."
npm install --legacy-peer-deps
else
echo "📦 Using existing node_modules..."
fi

# 3. Apply minimal patches

echo "🩹 Applying patches..."
node nuke_exports.js || true

# 🚫 IMPORTANT: Removed manual Metro bundling (causing crash)

# Expo + Gradle will handle bundling automatically

# 4. Build APK

echo "🏗️ Building Android Release APK..."
cd android

chmod +x gradlew

./gradlew clean

./gradlew assembleRelease \
    --build-cache \
    --daemon \
    -x lint \
    -x lintVitalRelease

echo "✅ Build completed!"
echo "📦 APK: android/app/build/outputs/apk/release/app-release.apk"

