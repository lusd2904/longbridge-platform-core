#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
exec "$ROOT_DIR/scripts/start_service.sh" analysis-service "apps/intelligence/analysis-service" "${REF_ANALYSIS_SERVICE_PORT:-8103}"
