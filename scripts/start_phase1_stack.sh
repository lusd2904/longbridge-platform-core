#!/bin/bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$ROOT_DIR/scripts/load_env.sh"
if [ -x "$ROOT_DIR/scripts/redis/start_redis.sh" ]; then
    "$ROOT_DIR/scripts/redis/start_redis.sh"
fi
python3 "$ROOT_DIR/scripts/bootstrap_refactor_db.py"

"$ROOT_DIR/scripts/start_service.sh" user-center "apps/platform/user-center" "${REF_USER_CENTER_PORT:-8101}"
"$ROOT_DIR/scripts/start_service.sh" market-service "apps/market/market-service" "${REF_MARKET_SERVICE_PORT:-8102}"
"$ROOT_DIR/scripts/start_service.sh" analysis-service "apps/intelligence/analysis-service" "${REF_ANALYSIS_SERVICE_PORT:-8103}"
"$ROOT_DIR/scripts/start_service.sh" strategy-service "apps/intelligence/strategy-service" "${REF_STRATEGY_SERVICE_PORT:-8104}"
"$ROOT_DIR/scripts/start_service.sh" agno-sidecar "apps/intelligence/agno-sidecar" "${REF_AGNO_SIDECAR_PORT:-3200}"
"$ROOT_DIR/scripts/start_service.sh" trade-service "apps/trading/trade-service" "${REF_TRADE_SERVICE_PORT:-8105}"
if [ "${REF_SENTIMENT_ENABLED:-false}" = "true" ] && [ -d "$ROOT_DIR/apps/market/sentiment-service/src" ]; then
    "$ROOT_DIR/scripts/start_service.sh" sentiment-service "apps/market/sentiment-service" "${REF_SENTIMENT_SERVICE_PORT:-8106}"
else
    echo "sentiment-service 已跳过（目录未落地或未启用）"
fi

if [ -d "$ROOT_DIR/apps/operations/scheduler-service/src" ]; then
    "$ROOT_DIR/scripts/start_service.sh" scheduler-service "apps/operations/scheduler-service" "${REF_SCHEDULER_SERVICE_PORT:-8107}"
elif [ -d "$ROOT_DIR/apps/risk-service/scheduler/src" ]; then
    "$ROOT_DIR/scripts/start_service.sh" scheduler-service "apps/risk-service/scheduler" "${REF_SCHEDULER_SERVICE_PORT:-8107}"
else
    echo "scheduler-service 已跳过（未找到服务目录）"
fi
"$ROOT_DIR/scripts/start_service.sh" risk-service "apps/governance/risk-service" "${REF_RISK_SERVICE_PORT:-8108}"
"$ROOT_DIR/scripts/start_service.sh" api-gateway "apps/platform/api-gateway" "${REF_GATEWAY_PORT:-5101}"
"$ROOT_DIR/scripts/start_web_portal.sh"

echo "Refactor V2 phase-1 stack is ready."
echo "Web Portal:     http://127.0.0.1:${REF_WEB_PORTAL_PORT:-3100}"
echo "Gateway:        http://127.0.0.1:${REF_GATEWAY_PORT:-5101}"
echo "User Center:    http://127.0.0.1:${REF_USER_CENTER_PORT:-8101}"
echo "Market Service: http://127.0.0.1:${REF_MARKET_SERVICE_PORT:-8102}"
echo "Analysis:       http://127.0.0.1:${REF_ANALYSIS_SERVICE_PORT:-8103}"
echo "Strategy:       http://127.0.0.1:${REF_STRATEGY_SERVICE_PORT:-8104}"
echo "Agno Sidecar:   http://127.0.0.1:${REF_AGNO_SIDECAR_PORT:-3200}"
echo "Trade:          http://127.0.0.1:${REF_TRADE_SERVICE_PORT:-8105}"
echo "Sentiment:      http://127.0.0.1:${REF_SENTIMENT_SERVICE_PORT:-8106}"
echo "Scheduler:      http://127.0.0.1:${REF_SCHEDULER_SERVICE_PORT:-8107}"
echo "Risk:           http://127.0.0.1:${REF_RISK_SERVICE_PORT:-8108}"
