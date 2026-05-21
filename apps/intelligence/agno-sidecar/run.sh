#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
"$ROOT_DIR/scripts/start_service.sh" agno-sidecar "apps/intelligence/agno-sidecar" "${REF_AGNO_SIDECAR_PORT:-3200}"
