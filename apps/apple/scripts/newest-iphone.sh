#!/bin/bash
# Prints an xcodebuild destination for the newest flagship iPhone simulator: the highest-numbered
# "iPhone NN Pro" on the newest available iOS runtime. Selected by id, so xcodebuild cannot
# resolve the name against a different runtime.
set -euo pipefail
pick=$(xcrun simctl list -j | jq -er '. as $all
  | [.runtimes[] | select(.platform == "iOS" and .isAvailable)]
  | sort_by(.version | split(".") | map(tonumber)) | last as $rt
  | [$all.devices[$rt.identifier][]? | select(.isAvailable and (.name | test("^iPhone [0-9]+ Pro$")))]
  | sort_by(.name | capture("(?<n>[0-9]+)").n | tonumber) | last
  | "platform=iOS Simulator,id=\(.udid)\t\(.name) (iOS \($rt.version))"') || {
  echo "no iPhone NN Pro simulator on the newest iOS runtime" >&2
  exit 1
}
echo "iPhone simulator: ${pick#*$'\t'}" >&2
echo "${pick%%$'\t'*}"
