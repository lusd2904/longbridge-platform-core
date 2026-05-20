#!/usr/bin/env bash
set -euo pipefail

for candidate in agy antigravity antigravity-cli ag; do
    if command -v "$candidate" >/dev/null 2>&1; then
        path="$(command -v "$candidate")"
        echo "[antigravity] using $candidate at $path"
        "$candidate" --help | sed -n '1,80p'
        exit 0
    fi
done

echo "[antigravity] CLI not found." >&2
echo "[antigravity] Install with: curl -fsSL https://antigravity.google/cli/install.sh | bash" >&2
echo "[antigravity] Expected binary name after install: agy" >&2
exit 1
