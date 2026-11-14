#!/bin/bash
# Prints an xcodebuild destination for a phone the iPhone screen catalogue is taken on, on the newest iOS runtime, made
# there if there is none: the smallest phone of that iOS (the highest-numbered "iPhone NNe"), or with `shortest` the
# iPhone SE, the shortest screen (375 × 667).
set -euo pipefail
rt=$(xcrun simctl list -j runtimes | jq -er '[.runtimes[] | select(.platform == "iOS" and .isAvailable)]
  | sort_by(.version | split(".") | map(tonumber)) | last | "\(.identifier)\t\(.version)"')
id=${rt%%$'\t'*}
if [ "${1:-}" = shortest ]; then pattern='^iPhone SE'; else pattern='^iPhone [0-9]+e$'; fi
type=$(xcrun simctl list -j devicetypes | jq -er --arg p "$pattern" '[.devicetypes[] | select(.name | test($p))]
  | sort_by(.name | [scan("[0-9]+")] | map(tonumber)) | last | "\(.identifier)\t\(.name)"')
name=${type#*$'\t'}
udid=$(xcrun simctl list -j devices | jq -r --arg rt "$id" --arg name "$name" \
  '[.devices[$rt][]? | select(.isAvailable and .name == $name)] | first | .udid // empty')
[ -n "$udid" ] || udid=$(xcrun simctl create "$name" "${type%%$'\t'*}" "$id")
echo "iPhone simulator: $name (iOS ${rt#*$'\t'})" >&2
echo "platform=iOS Simulator,id=$udid"
