#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
exec "$ROOT_DIR/scripts/start_service.sh" market-service "apps/market/market-service" "${REF_MARKET_SERVICE_PORT:-8102}"
