#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
. "$SCRIPT_DIR/mobile-debug-common.sh"

run_ios_live_reload
run_android_live_reload
