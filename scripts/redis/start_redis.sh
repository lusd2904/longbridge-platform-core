#!/bin/bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
source "$ROOT_DIR/scripts/load_env.sh"

LOG_DIR="$ROOT_DIR/logs"
RUNTIME_DIR="$ROOT_DIR/.runtime/redis"
DATA_DIR="$RUNTIME_DIR/data"
PID_FILE="$ROOT_DIR/.runtime/redis.pid"
LOG_FILE="$LOG_DIR/redis.log"
PORT="${REF_REDIS_PORT:-6379}"
HOST="${REF_REDIS_HOST:-127.0.0.1}"
PASSWORD="${REF_REDIS_PASSWORD:-}"

mkdir -p "$LOG_DIR" "$DATA_DIR" "$ROOT_DIR/.runtime"

resolve_redis_binary() {
    if command -v redis-server >/dev/null 2>&1; then
        command -v redis-server
        return 0
    fi

    if command -v brew >/dev/null 2>&1; then
        local brew_prefix
        brew_prefix="$(brew --prefix redis 2>/dev/null || true)"
        if [ -n "$brew_prefix" ] && [ -x "$brew_prefix/bin/redis-server" ]; then
            echo "$brew_prefix/bin/redis-server"
            return 0
        fi
    fi

    for candidate in \
        /opt/homebrew/opt/redis/bin/redis-server \
        /usr/local/opt/redis/bin/redis-server
    do
        if [ -x "$candidate" ]; then
            echo "$candidate"
            return 0
        fi
    done

    return 1
}

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

if lsof -nP -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; then
    existing_pid="$(lsof -nP -iTCP:"$PORT" -sTCP:LISTEN -t | head -n 1)"
    echo "redis 已在本地运行: $HOST:$PORT (PID: $existing_pid)"
    echo "$existing_pid" > "$PID_FILE"
    exit 0
fi

redis_server_bin="$(resolve_redis_binary || true)"
if [ -z "$redis_server_bin" ]; then
    echo "未找到 redis-server。请先安装 Redis，例如: brew install redis"
    exit 1
fi

redis_cli_bin="$(resolve_redis_cli || true)"

redis_args=(
    "--bind" "$HOST"
    "--port" "$PORT"
    "--daemonize" "yes"
    "--pidfile" "$PID_FILE"
    "--logfile" "$LOG_FILE"
    "--dir" "$DATA_DIR"
    "--appendonly" "yes"
    "--protected-mode" "yes"
)

if [ -n "$PASSWORD" ]; then
    redis_args+=("--requirepass" "$PASSWORD")
fi

"$redis_server_bin" "${redis_args[@]}"

for _ in {1..20}; do
    if [ -n "$redis_cli_bin" ]; then
        if [ -n "$PASSWORD" ]; then
            if "$redis_cli_bin" -h "$HOST" -p "$PORT" -a "$PASSWORD" ping >/dev/null 2>&1; then
                echo "redis 启动成功: $HOST:$PORT"
                exit 0
            fi
        elif "$redis_cli_bin" -h "$HOST" -p "$PORT" ping >/dev/null 2>&1; then
            echo "redis 启动成功: $HOST:$PORT"
            exit 0
        fi
    elif lsof -nP -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; then
        echo "redis 启动成功: $HOST:$PORT"
        exit 0
    fi
    sleep 1
done

echo "redis 启动失败，请检查日志: $LOG_FILE"
tail -n 80 "$LOG_FILE" || true
exit 1
