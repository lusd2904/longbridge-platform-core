#!/bin/bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
source "$ROOT_DIR/scripts/load_env.sh"

PID_FILE="$ROOT_DIR/.runtime/redis.pid"
PORT="${REF_REDIS_PORT:-6379}"
HOST="${REF_REDIS_HOST:-127.0.0.1}"
PASSWORD="${REF_REDIS_PASSWORD:-}"

resolve_redis_cli() {
    if command -v redis-cli >/dev/null 2>&1; then
        command -v redis-cli
        return 0
    fi

    if command -v brew >/dev/null 2>&1; then
        local brew_prefix
        brew_prefix="$(brew --prefix redis 2>/dev/null || true)"
        if [ -n "$brew_prefix" ] && [ -x "$brew_prefix/bin/redis-cli" ]; then
            echo "$brew_prefix/bin/redis-cli"
            return 0
        fi
    fi

    for candidate in \
        /opt/homebrew/opt/redis/bin/redis-cli \
        /usr/local/opt/redis/bin/redis-cli
    do
        if [ -x "$candidate" ]; then
            echo "$candidate"
            return 0
        fi
    done

    return 1
}

redis_cli_bin="$(resolve_redis_cli || true)"

if lsof -nP -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; then
    if [ -n "$redis_cli_bin" ]; then
        if [ -n "$PASSWORD" ]; then
            "$redis_cli_bin" -h "$HOST" -p "$PORT" -a "$PASSWORD" shutdown save >/dev/null 2>&1 || true
        else
            "$redis_cli_bin" -h "$HOST" -p "$PORT" shutdown save >/dev/null 2>&1 || true
        fi
        sleep 1
    fi

    if lsof -nP -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; then
        existing_pid="$(lsof -nP -iTCP:"$PORT" -sTCP:LISTEN -t | head -n 1)"
        if [ -n "$existing_pid" ]; then
            kill "$existing_pid" >/dev/null 2>&1 || true
            sleep 1
        fi
    fi
fi

rm -f "$PID_FILE"

echo "redis 已停止"
