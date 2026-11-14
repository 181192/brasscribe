#!/bin/bash
# Runs a command against a new iPhone SE (3rd generation) simulator, the shortest screen the app supports, on the
# newest available iOS runtime, and deletes the simulator again when the command ends:
#   scripts/small-iphone.sh xcodebuild … test-without-building
# The simulator's destination is added to the command as -destination. It is started and waited for first, as
# xcodebuild otherwise begins the tests while the simulator's own services are still starting.
set -euo pipefail
runtime=$(xcrun simctl list -j runtimes | jq -er '[.runtimes[] | select(.platform == "iOS" and .isAvailable)]
  | sort_by(.version | split(".") | map(tonumber)) | last | .identifier') || {
  echo "no available iOS runtime" >&2
  exit 1
}
udid=$(xcrun simctl create "Large text SE" com.apple.CoreSimulator.SimDeviceType.iPhone-SE-3rd-generation "$runtime")
trap 'xcrun simctl shutdown "$udid" >/dev/null 2>&1 || true; xcrun simctl delete "$udid"' EXIT
echo "iPhone simulator: iPhone SE (3rd generation) ($runtime)" >&2
xcrun simctl bootstatus "$udid" -b >/dev/null
"$@" -destination "platform=iOS Simulator,id=$udid"
