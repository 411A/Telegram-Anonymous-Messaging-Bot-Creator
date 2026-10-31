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

# Start the application - get_encryption_key() will handle password prompts.
# UVICORN_EXTRA_ARGS is an opt-in hook (e.g. set by docker-compose.lean.yml):
# extra flags are appended only when the operator/lean mode provides them,
# so default behavior is exactly the plain command below.
# shellcheck disable=SC2086
exec python -m uvicorn bot_creator:app --host 0.0.0.0 --port "${FASTAPI_PORT:-13360}" ${UVICORN_EXTRA_ARGS:-}
