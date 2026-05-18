#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

cd "$ROOT_DIR"
export PYTHONPATH="$ROOT_DIR${PYTHONPATH:+:$PYTHONPATH}"

echo "[verify] python tests"
python3 -m pytest tests/python

echo "[verify] web unit tests"
npm --prefix apps/frontend/web-portal run test:unit

if curl -fsS "http://127.0.0.1:${REF_WEB_PORTAL_PORT:-3100}" >/dev/null 2>&1; then
  echo "[verify] live health contract"
  python3 scripts/check_platform_health.py
else
  echo "[verify] live stack not running, skipping health contract"
fi
