#!/bin/bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_DIR="$ROOT_DIR/apps/market/sentiment-service"
PORT="${REF_SENTIMENT_SERVICE_PORT:-8106}"

if lsof -nP -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; then
    echo "sentiment-service placeholder 已运行: http://127.0.0.1:$PORT"
    exit 0
fi

if ! python3 - <<'PY' >/dev/null 2>&1
import fastapi
import uvicorn
PY
then
    python3 -m pip install --user -r "$APP_DIR/requirements.txt"
fi

exec "$ROOT_DIR/scripts/start_service.sh" sentiment-service "apps/market/sentiment-service" "$PORT"
