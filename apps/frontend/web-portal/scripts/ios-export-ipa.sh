#!/bin/sh
set -eu

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
IOS_ARCHIVE_PATH="${IOS_ARCHIVE_PATH:-$PROJECT_ROOT/ios/build/App.xcarchive}"
IOS_EXPORT_PATH="${IOS_EXPORT_PATH:-$PROJECT_ROOT/ios/build/export}"
IOS_EXPORT_OPTIONS_PLIST="${IOS_EXPORT_OPTIONS_PLIST:-$PROJECT_ROOT/ios/App/ExportOptions.plist}"

if [ ! -d "$IOS_ARCHIVE_PATH" ]; then
  echo "archive not found: $IOS_ARCHIVE_PATH" >&2
  exit 1
fi

if [ ! -f "$IOS_EXPORT_OPTIONS_PLIST" ]; then
  echo "export options not found: $IOS_EXPORT_OPTIONS_PLIST (use ios/App/ExportOptions.plist.example as template)" >&2
  exit 1
fi

mkdir -p "$IOS_EXPORT_PATH"

xcodebuild -exportArchive -archivePath "$IOS_ARCHIVE_PATH" -exportPath "$IOS_EXPORT_PATH" -exportOptionsPlist "$IOS_EXPORT_OPTIONS_PLIST"
