#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$ROOT_DIR/scripts/load_env.sh"

MODULE_NAME="${1:-}"
DRY_RUN="${REF_MODULE_DRY_RUN:-false}"

if [ -z "$MODULE_NAME" ]; then
    echo "usage: $0 <frontend|platform|market|intelligence|trading|governance|operations>"
    exit 1
fi

is_true() {
    case "${1:-}" in
        1|true|TRUE|yes|YES|on|ON) return 0 ;;
        *) return 1 ;;
    esac
}

run_cmd() {
    if is_true "$DRY_RUN"; then
        echo "[dry-run] $*"
    else
        "$@"
    fi
}

start_service() {
    local service_name="$1"
    local service_dir="$2"
    local port="$3"
    run_cmd "$ROOT_DIR/scripts/start_service.sh" "$service_name" "$service_dir" "$port"
}

start_web_portal() {
    run_cmd "$ROOT_DIR/scripts/start_web_portal.sh"
}

case "$MODULE_NAME" in
    frontend)
        start_web_portal
        ;;
    platform)
        start_service "user-center" "apps/platform/user-center" "${REF_USER_CENTER_PORT:-8101}"
        start_service "api-gateway" "apps/platform/api-gateway" "${REF_GATEWAY_PORT:-5101}"
        ;;
    market)
        start_service "market-service" "apps/market/market-service" "${REF_MARKET_SERVICE_PORT:-8102}"
        if [ -d "$ROOT_DIR/apps/market/sentiment-service/src" ] && is_true "${REF_SENTIMENT_ENABLED:-false}"; then
            start_service "sentiment-service" "apps/market/sentiment-service" "${REF_SENTIMENT_SERVICE_PORT:-8106}"
        else
            echo "sentiment-service 已跳过（未启用）"
        fi
        ;;
    intelligence)
        start_service "analysis-service" "apps/intelligence/analysis-service" "${REF_ANALYSIS_SERVICE_PORT:-8103}"
        start_service "strategy-service" "apps/intelligence/strategy-service" "${REF_STRATEGY_SERVICE_PORT:-8104}"
        start_service "agno-sidecar" "apps/intelligence/agno-sidecar" "${REF_AGNO_SIDECAR_PORT:-3200}"
        ;;
    trading)
        start_service "trade-service" "apps/trading/trade-service" "${REF_TRADE_SERVICE_PORT:-8105}"
        ;;
    governance)
        start_service "risk-service" "apps/governance/risk-service" "${REF_RISK_SERVICE_PORT:-8108}"
        ;;
    operations)
        start_service "scheduler-service" "apps/operations/scheduler-service" "${REF_SCHEDULER_SERVICE_PORT:-8107}"
        ;;
    *)
        echo "unknown module: $MODULE_NAME"
        exit 1
        ;;
esac
