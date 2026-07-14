#!/usr/bin/env bash
# Run full pytest suite inside the Docker image.
# Usage:  bash scripts/docker_run_tests.sh
#
# This script:
#   1. Builds the refactor-v2-platform image (if not already built)
#   2. Runs pytest inside a container with all runtime deps + test deps installed
#   3. Exits 0 only if all tests pass
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

IMAGE="refactor-v2-platform:local"

echo "=== Building Docker image ==="
docker build -t "$IMAGE" "$ROOT_DIR"

echo "=== Running full test suite inside container ==="
docker run --rm \
  -v "$ROOT_DIR/tests/python:/app/tests/python:ro" \
  -v "$ROOT_DIR/backend-server/src:/app/backend-server/src:ro" \
  -v "$ROOT_DIR/apps:/app/apps:ro" \
  -v "$ROOT_DIR/shared:/app/shared:ro" \
  -v "$ROOT_DIR/legacy_trade_service:/app/legacy_trade_service:ro" \
  -e PYTHONPATH="/app:/app/backend-server/src" \
  "$IMAGE" \
  python -m pytest tests/python/ -v --tb=short 2>&1
