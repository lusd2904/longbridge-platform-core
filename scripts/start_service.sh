#!/bin/bash

set -euo pipefail

if [ "$#" -lt 3 ]; then
    echo "usage: $0 <service-name> <service-dir> <port>"
    exit 1
fi

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$ROOT_DIR/scripts/load_env.sh"
SERVICE_NAME="$1"
SERVICE_DIR="$2"
PORT="$3"
LOG_DIR="$ROOT_DIR/logs"
PID_DIR="$ROOT_DIR/.runtime"
PID_FILE="$PID_DIR/${SERVICE_NAME}.pid"
LOG_FILE="$LOG_DIR/${SERVICE_NAME}.log"

is_true() {
    case "${1:-}" in
        1|true|TRUE|yes|YES|on|ON) return 0 ;;
        *) return 1 ;;
    esac
}

mkdir -p "$LOG_DIR" "$PID_DIR"

if is_true "${REF_SERVICE_DRY_RUN:-false}"; then
    echo "[dry-run] service=$SERVICE_NAME dir=$SERVICE_DIR port=$PORT"
    exit 0
fi

if lsof -nP -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; then
    EXISTING_PID="$(lsof -nP -iTCP:"$PORT" -sTCP:LISTEN -t | head -n 1)"
    echo "${SERVICE_NAME} 已运行: http://127.0.0.1:$PORT (PID: $EXISTING_PID)"
    echo "$EXISTING_PID" > "$PID_FILE"
    exit 0
fi

if ! python3 - <<'PY' >/dev/null 2>&1
import fastapi
import uvicorn
import bcrypt
import jwt
import pymysql
import dotenv
PY
then
    python3 -m pip install --user -r "$ROOT_DIR/requirements.services.txt"
fi

python3 "$ROOT_DIR/scripts/detach_and_exec.py" \
    "$ROOT_DIR/$SERVICE_DIR/src" \
    "$LOG_FILE" \
    "$PID_FILE" \
    env PYTHONPATH="$ROOT_DIR${PYTHONPATH:+:$PYTHONPATH}" SERVICE_PORT="$PORT" python3 main.py

for _ in {1..20}; do
    if lsof -nP -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; then
        echo "${SERVICE_NAME} 启动成功: http://127.0.0.1:$PORT"
        exit 0
    fi
    sleep 1
done

echo "${SERVICE_NAME} 启动失败，请检查日志: $LOG_FILE"
tail -n 80 "$LOG_FILE" || true
exit 1
