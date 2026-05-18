#!/bin/bash

REF_ENV_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

python3 "$REF_ENV_ROOT/scripts/ensure_refactor_env.py" >/dev/null

if [ -f "$REF_ENV_ROOT/.env" ]; then
    set -a
    . "$REF_ENV_ROOT/.env"
    set +a
fi
