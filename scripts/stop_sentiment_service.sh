#!/bin/bash

set -euo pipefail

PORT="${REF_SENTIMENT_SERVICE_PORT:-8106}"

if lsof -nP -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; then
    PID="$(lsof -nP -iTCP:"$PORT" -sTCP:LISTEN -t | head -n 1)"
    kill "$PID" >/dev/null 2>&1 || true
    sleep 1
    if kill -0 "$PID" >/dev/null 2>&1; then
        kill -9 "$PID" >/dev/null 2>&1 || true
    fi
    echo "sentiment-service placeholder 已停止: $PORT"
    exit 0
fi

echo "sentiment-service placeholder 未运行"
