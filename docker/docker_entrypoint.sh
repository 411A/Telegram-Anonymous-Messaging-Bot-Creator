#!/bin/bash
set -e

# Change to src directory where the app is designed to run from
cd /app/src

# Debug: Show what port we're using
echo "Starting bot on port: ${FASTAPI_PORT:-8000}"

# Start the application - get_encryption_key() will handle password prompts
exec python -m uvicorn bot_creator:app --host 0.0.0.0 --port "${FASTAPI_PORT:-8000}"