#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
exec "$ROOT_DIR/scripts/start_service.sh" risk-service "apps/governance/risk-service" "${REF_RISK_SERVICE_PORT:-8108}"
