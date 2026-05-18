#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
exec "$ROOT_DIR/scripts/start_service.sh" trade-service "apps/trading/trade-service" "${REF_TRADE_SERVICE_PORT:-8105}"
