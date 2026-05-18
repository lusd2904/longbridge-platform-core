#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PROJECT_DIR=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)

if [ -z "${DEVELOPER_DIR:-}" ]; then
  if [ -d "/Applications/A.开发设计/Xcode.app/Contents/Developer" ]; then
    DEVELOPER_DIR="/Applications/A.开发设计/Xcode.app/Contents/Developer"
    export DEVELOPER_DIR
  elif [ -d "/Applications/Xcode.app/Contents/Developer" ]; then
    DEVELOPER_DIR="/Applications/Xcode.app/Contents/Developer"
    export DEVELOPER_DIR
  fi
fi

if ! command -v xcodebuild >/dev/null 2>&1; then
  echo "xcodebuild 不可用，请先安装 Xcode Command Line Tools"
  exit 1
fi

if ! command -v xcrun >/dev/null 2>&1; then
  echo "xcrun 不可用，请先安装 Xcode"
  exit 1
fi

IOS_RUNTIME_VERSION="${IOS_SIM_RUNTIME_VERSION:-26.4}"

echo "Using DEVELOPER_DIR=${DEVELOPER_DIR:-$(xcode-select -p 2>/dev/null || echo '')}"
xcodebuild -version

if ! xcrun simctl list runtimes | grep -q "iOS ${IOS_RUNTIME_VERSION}"; then
  echo "缺少 iOS ${IOS_RUNTIME_VERSION} Simulator Runtime，尝试自动下载"
  xcodebuild -downloadPlatform iOS
fi

if ! xcrun simctl list runtimes | grep -q "iOS ${IOS_RUNTIME_VERSION}"; then
  echo "仍未检测到 iOS ${IOS_RUNTIME_VERSION} Simulator Runtime"
  exit 1
fi

cd "$PROJECT_DIR/ios/App"
xcodebuild \
  -workspace App.xcworkspace \
  -scheme App \
  -configuration Debug \
  -sdk iphonesimulator \
  -destination 'generic/platform=iOS Simulator' \
  CODE_SIGNING_ALLOWED=NO \
  build
