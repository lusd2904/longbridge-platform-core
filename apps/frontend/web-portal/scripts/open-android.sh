#!/bin/sh
set -eu

if [ -n "${CAPACITOR_ANDROID_STUDIO_PATH:-}" ]; then
  exec env CAPACITOR_ANDROID_STUDIO_PATH="$CAPACITOR_ANDROID_STUDIO_PATH" npx cap open android
fi

if [ -d "/Applications/A.开发设计/Android Studio.app" ]; then
  exec env CAPACITOR_ANDROID_STUDIO_PATH="/Applications/A.开发设计/Android Studio.app" npx cap open android
fi

if [ -d "/Applications/Android Studio.app" ]; then
  exec env CAPACITOR_ANDROID_STUDIO_PATH="/Applications/Android Studio.app" npx cap open android
fi

exec npx cap open android
