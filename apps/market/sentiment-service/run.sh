#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
exec "$ROOT_DIR/scripts/start_service.sh" sentiment-service "apps/market/sentiment-service" "${REF_SENTIMENT_SERVICE_PORT:-8106}"
