#!/usr/bin/env bash
# Starts a simulator by its id and waits until it has finished starting, for at most SECONDS (default 600).
# A fresh simulator on a hosted runner can hang in its first start ("Waiting on Data Migration"); when the wait runs
# out it is shut down, erased and started once more. Fails when the second start runs out too.
#
#   scripts/boot-simulator.sh <udid> [seconds]
set -euo pipefail
udid=${1:?usage: boot-simulator.sh <udid> [seconds]}
limit=${2:-600}

# bootstatus -b boots the device if it is shut down and returns when it has finished starting.
wait_for_boot() { perl -e 'alarm shift; exec @ARGV' "$limit" xcrun simctl bootstatus "$udid" -b >/dev/null; }

start=$SECONDS
if wait_for_boot; then
  echo "simulator $udid started in $((SECONDS - start)) s"
  exit 0
fi
echo "simulator $udid did not start within $limit s: erasing it and starting it again" >&2
xcrun simctl shutdown "$udid" 2>/dev/null || true
xcrun simctl erase "$udid"
start=$SECONDS
wait_for_boot
echo "simulator $udid started in $((SECONDS - start)) s (second try)"
