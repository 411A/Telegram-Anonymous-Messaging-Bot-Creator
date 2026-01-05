#!/bin/bash
set -e

# Change to src directory where the app is designed to run from
cd /app/src

# Debug: Show what port we're using
echo "Starting bot on port: ${FASTAPI_PORT:-13360}"

# Validate critical environment variables before starting
if [ -z "$MAIN_BOT_TOKEN" ]; then
    echo "❌ FATAL: MAIN_BOT_TOKEN is not set!"
    exit 1
fi

if [ -z "$WEBHOOK_BASE_URL" ]; then
    echo "❌ FATAL: WEBHOOK_BASE_URL is not set!"
    exit 1
fi

# Start the application - get_encryption_key() will handle password prompts
exec python -m uvicorn bot_creator:app --host 0.0.0.0 --port "${FASTAPI_PORT:-13360}"