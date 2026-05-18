#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
exec "$ROOT_DIR/scripts/start_service.sh" strategy-service "apps/intelligence/strategy-service" "${REF_STRATEGY_SERVICE_PORT:-8104}"
