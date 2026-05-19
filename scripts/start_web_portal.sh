#!/bin/bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$ROOT_DIR/scripts/load_env.sh"
REF_PYTHON="${REF_PYTHON:-$ROOT_DIR/.venv/bin/python}"
if [ ! -x "$REF_PYTHON" ]; then
    REF_PYTHON="${PYTHON:-python3}"
fi
APP_DIR="$ROOT_DIR/apps/frontend/web-portal"
LOG_DIR="$ROOT_DIR/logs"
PID_DIR="$ROOT_DIR/.runtime"
PORT="${REF_WEB_PORTAL_PORT:-3100}"
PID_FILE="$PID_DIR/web-portal.pid"
LOG_FILE="$LOG_DIR/web-portal.log"

is_true() {
    case "${1:-}" in
        1|true|TRUE|yes|YES|on|ON) return 0 ;;
        *) return 1 ;;
    esac
}

mkdir -p "$LOG_DIR" "$PID_DIR"

if is_true "${REF_SERVICE_DRY_RUN:-false}"; then
    echo "[dry-run] $ROOT_DIR/scripts/start_web_portal.sh"
    exit 0
fi

if lsof -nP -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; then
    EXISTING_PID="$(lsof -nP -iTCP:"$PORT" -sTCP:LISTEN -t | head -n 1)"
    echo "web-portal 已运行: http://127.0.0.1:$PORT (PID: $EXISTING_PID)"
    echo "$EXISTING_PID" > "$PID_FILE"
    exit 0
fi

if [ ! -d "$APP_DIR/node_modules" ]; then
    (cd "$APP_DIR" && npm install)
fi

"$REF_PYTHON" "$ROOT_DIR/scripts/detach_and_exec.py" \
    "$APP_DIR" \
    "$LOG_FILE" \
    "$PID_FILE" \
    env PORT="$PORT" npm run dev -- --host 0.0.0.0 --port "$PORT"

for _ in {1..30}; do
    if lsof -nP -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; then
        echo "web-portal 启动成功: http://127.0.0.1:$PORT"
        exit 0
    fi
    sleep 1
done

echo "web-portal 启动失败，请检查日志: $LOG_FILE"
tail -n 80 "$LOG_FILE" || true
exit 1
