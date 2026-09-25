#!/usr/bin/env bash
# Run before generating the Xcode project: the Verovio framework is built locally.
set -euo pipefail
HERE="$(cd "$(dirname "$0")/.." && pwd)"
if [ ! -d "$HERE/Frameworks/Verovio.xcframework" ] || [ ! -d "$HERE/Frameworks/VerovioResources" ]; then
  echo "error: Verovio.xcframework missing. Run apps/apple/scripts/build-verovio.sh first." >&2
  exit 1
fi
