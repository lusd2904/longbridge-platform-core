#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PROJECT_DIR=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)
DEFAULT_ANDROID_SDK_ROOT="$HOME/Library/Android/sdk"
PORT="${REF_WEB_PORTAL_PORT:-3100}"
HOST="${CAPACITOR_LIVE_RELOAD_HOST:-127.0.0.1}"
TMP_BASE="${TMPDIR:-/tmp}"
DEV_SERVER_LOG="${TMP_BASE%/}/refactor-v2-web-portal-vite.log"
ANDROID_EMULATOR_LOG="${TMP_BASE%/}/refactor-v2-android-emulator.log"

ensure_android_sdk() {
  if [ -z "${ANDROID_SDK_ROOT:-}" ] && [ -d "$DEFAULT_ANDROID_SDK_ROOT" ]; then
    ANDROID_SDK_ROOT="$DEFAULT_ANDROID_SDK_ROOT"
    export ANDROID_SDK_ROOT
  fi

  if [ -z "${ANDROID_HOME:-}" ] && [ -n "${ANDROID_SDK_ROOT:-}" ]; then
    ANDROID_HOME="$ANDROID_SDK_ROOT"
    export ANDROID_HOME
  fi

  if [ -n "${ANDROID_SDK_ROOT:-}" ]; then
    PATH="$ANDROID_SDK_ROOT/platform-tools:$ANDROID_SDK_ROOT/emulator:$ANDROID_SDK_ROOT/cmdline-tools/latest/bin:$PATH"
    export PATH
  fi
}

wait_for_http() {
  url="$1"
  retries="${2:-30}"
  count=0

  while [ "$count" -lt "$retries" ]; do
    if curl -sf "$url" >/dev/null 2>&1; then
      return 0
    fi
    count=$((count + 1))
    sleep 1
  done

  return 1
}

ensure_dev_server() {
  if lsof -nP -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; then
    echo "Using existing Vite dev server on port $PORT"
    return 0
  fi

  echo "Starting Vite dev server on port $PORT"
  (
    cd "$PROJECT_DIR"
    nohup npm run dev -- --host 0.0.0.0 --port "$PORT" >"$DEV_SERVER_LOG" 2>&1 &
  )

  if wait_for_http "http://127.0.0.1:$PORT" 45; then
    return 0
  fi

  echo "Timed out waiting for the Vite dev server on port $PORT"
  echo "Recent dev server log:"
  tail -n 40 "$DEV_SERVER_LOG" || true
  exit 1
}

pick_android_serial() {
  adb devices | awk 'NR > 1 && $2 == "device" { print $1; exit }'
}

pick_android_avd() {
  emulator -list-avds | sed -n '1p'
}

ensure_android_emulator() {
  ensure_android_sdk

  if ! command -v adb >/dev/null 2>&1 || ! command -v emulator >/dev/null 2>&1; then
    echo "Android SDK tools are not available. Expected them under $DEFAULT_ANDROID_SDK_ROOT"
    exit 1
  fi

  adb start-server >/dev/null 2>&1 || true

  serial="$(pick_android_serial || true)"
  if [ -n "$serial" ]; then
    echo "$serial"
    return 0
  fi

  avd="${ANDROID_AVD_NAME:-$(pick_android_avd || true)}"
  if [ -z "$avd" ]; then
    echo "No Android AVD was found. Create one in Android Studio first."
    exit 1
  fi

  echo "Starting Android emulator: $avd"
  nohup emulator -avd "$avd" -netdelay none -netspeed full >"$ANDROID_EMULATOR_LOG" 2>&1 &

  adb wait-for-device >/dev/null 2>&1
  while [ "$(adb shell getprop sys.boot_completed 2>/dev/null | tr -d '\r')" != "1" ]; do
    sleep 2
  done

  serial="$(pick_android_serial || true)"
  if [ -z "$serial" ]; then
    echo "Android emulator booted, but no adb device is available."
    exit 1
  fi

  echo "$serial"
}

pick_booted_ios_udid() {
  xcrun simctl list devices available | awk -F '[()]' '/Booted/ && /iPhone|iPad/ { print $2; exit }'
}

pick_available_ios_udid() {
  xcrun simctl list devices available | awk -F '[()]' '/iPhone/ && /Shutdown|Booted/ { print $2; exit }'
}

ensure_ios_simulator() {
  udid="${IOS_SIMULATOR_UDID:-$(pick_booted_ios_udid || true)}"

  if [ -z "$udid" ]; then
    udid="$(pick_available_ios_udid || true)"
    if [ -z "$udid" ]; then
      echo "No available iOS simulator device was found."
      exit 1
    fi
    open -a Simulator >/dev/null 2>&1 || true
    xcrun simctl boot "$udid" >/dev/null 2>&1 || true
  fi

  xcrun simctl bootstatus "$udid" -b >/dev/null 2>&1
  echo "$udid"
}

run_android_live_reload() {
  ensure_dev_server
  serial="$(ensure_android_emulator)"
  echo "Running Android live reload on $serial"
  cd "$PROJECT_DIR"
  npx cap run android --target "$serial" -l --host "$HOST" --port "$PORT" --forwardPorts "$PORT:$PORT"
}

run_ios_live_reload() {
  ensure_dev_server
  udid="$(ensure_ios_simulator)"
  echo "Running iOS live reload on $udid"
  cd "$PROJECT_DIR"
  npx cap run ios --target "$udid" -l --host "$HOST" --port "$PORT"
}
