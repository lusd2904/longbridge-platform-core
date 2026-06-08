#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-}"
NODE_BIN="${NODE_BIN:-node}"
NPM_BIN="${NPM_BIN:-npm}"

if [ -z "$PYTHON_BIN" ]; then
  if [ -x "$ROOT_DIR/.venv/bin/python" ]; then
    PYTHON_BIN="$ROOT_DIR/.venv/bin/python"
  else
    PYTHON_BIN="python3"
  fi
fi

cd "$ROOT_DIR"
export PYTHONPATH="$ROOT_DIR${PYTHONPATH:+:$PYTHONPATH}"

echo "[verify] python tests"
"$PYTHON_BIN" -m pytest tests/python

echo "[verify] node smoke tests"
"$NODE_BIN" --test tests/node/*.test.cjs

echo "[verify] web unit tests"
"$NPM_BIN" --prefix apps/frontend/web-portal run test:unit

if curl -fsS "http://127.0.0.1:${REF_WEB_PORTAL_PORT:-3100}" >/dev/null 2>&1; then
  echo "[verify] live health contract"
  "$PYTHON_BIN" scripts/check_platform_health.py
else
  echo "[verify] live stack not running, skipping health contract"
fi
