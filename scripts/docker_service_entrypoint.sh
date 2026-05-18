#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -lt 1 ]; then
    echo "usage: $0 <service-src-dir>"
    exit 1
fi

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SERVICE_SRC="$ROOT_DIR/$1"

if [ ! -d "$SERVICE_SRC" ]; then
    echo "service source directory not found: $SERVICE_SRC"
    exit 1
fi

export PYTHONPATH="$ROOT_DIR${PYTHONPATH:+:$PYTHONPATH}"
cd "$SERVICE_SRC"
exec python main.py
