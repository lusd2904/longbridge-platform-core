#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
exec "$ROOT_DIR/scripts/start_service.sh" scheduler-service "apps/operations/scheduler-service" "${REF_SCHEDULER_SERVICE_PORT:-8107}"
