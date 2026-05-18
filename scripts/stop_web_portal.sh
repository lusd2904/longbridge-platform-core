#!/bin/bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
"$ROOT_DIR/scripts/stop_service.sh" web-portal "${REF_WEB_PORTAL_PORT:-3100}"
