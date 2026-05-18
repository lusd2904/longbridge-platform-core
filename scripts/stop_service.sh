#!/bin/bash

set -euo pipefail

if [ "$#" -lt 2 ]; then
    echo "usage: $0 <service-name> <port>"
    exit 1
fi

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SERVICE_NAME="$1"
PORT="$2"
PID_FILE="$ROOT_DIR/.runtime/${SERVICE_NAME}.pid"

if [ -f "$PID_FILE" ]; then
    PID="$(cat "$PID_FILE" 2>/dev/null || true)"
    if [ -n "${PID:-}" ] && kill -0 "$PID" >/dev/null 2>&1; then
        kill "$PID" >/dev/null 2>&1 || true
        sleep 1
        if kill -0 "$PID" >/dev/null 2>&1; then
            kill -9 "$PID" >/dev/null 2>&1 || true
        fi
    fi
    rm -f "$PID_FILE"
fi

if lsof -nP -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; then
    PID="$(lsof -nP -iTCP:"$PORT" -sTCP:LISTEN -t | head -n 1)"
    kill "$PID" >/dev/null 2>&1 || true
    sleep 1
    if kill -0 "$PID" >/dev/null 2>&1; then
        kill -9 "$PID" >/dev/null 2>&1 || true
    fi
fi

echo "${SERVICE_NAME} 已停止"
