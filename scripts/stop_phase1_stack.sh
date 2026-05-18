#!/bin/bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$ROOT_DIR/scripts/load_env.sh"

"$ROOT_DIR/scripts/stop_web_portal.sh"
"$ROOT_DIR/scripts/stop_service.sh" api-gateway "${REF_GATEWAY_PORT:-5101}"
"$ROOT_DIR/scripts/stop_service.sh" risk-service "${REF_RISK_SERVICE_PORT:-8108}"
"$ROOT_DIR/scripts/stop_service.sh" scheduler-service "${REF_SCHEDULER_SERVICE_PORT:-8107}"
"$ROOT_DIR/scripts/stop_service.sh" sentiment-service "${REF_SENTIMENT_SERVICE_PORT:-8106}"
"$ROOT_DIR/scripts/stop_service.sh" trade-service "${REF_TRADE_SERVICE_PORT:-8105}"
"$ROOT_DIR/scripts/stop_service.sh" strategy-service "${REF_STRATEGY_SERVICE_PORT:-8104}"
"$ROOT_DIR/scripts/stop_service.sh" analysis-service "${REF_ANALYSIS_SERVICE_PORT:-8103}"
"$ROOT_DIR/scripts/stop_service.sh" market-service "${REF_MARKET_SERVICE_PORT:-8102}"
"$ROOT_DIR/scripts/stop_service.sh" user-center "${REF_USER_CENTER_PORT:-8101}"
if [ -x "$ROOT_DIR/scripts/redis/stop_redis.sh" ]; then
    "$ROOT_DIR/scripts/redis/stop_redis.sh" || true
fi

echo "Refactor V2 phase-1 stack stopped."
