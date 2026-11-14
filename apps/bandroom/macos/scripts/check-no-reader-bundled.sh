#!/usr/bin/env bash
# Stops when a folder that is about to become a build of Bandroom (the staged engine workspace, the app, the folder
# the Windows download is zipped from) holds an adapter's Python environment. The reader of printed music, homr, is
# AGPL-3.0: Bandroom fetches it on the user's own computer when they ask for it, and it must never be in a build,
# an installer or a release of Brasscribe (licences/README.md). Bandroom keeps the adapters' environments in the
# data folder, never in the app; a developer checkout keeps one beside each adapter (ml/adapters/<name>/.venv), so a
# build staged from a checkout that ran them is where one could come from.
#
#   check-no-reader-bundled.sh <folder>
#
# Fails (1) on any folder named .venv or .pixi (pixi's environments, which Bandroom makes in the data folder), and on
# any site-packages/homr, wherever it is in <folder>; 2 when <folder>
# is not there, since a check of nothing would pass.
set -euo pipefail
dir="${1:?usage: check-no-reader-bundled.sh <folder>}"
[ -d "$dir" ] || { echo "check-no-reader-bundled: no folder $dir to check" >&2; exit 2; }

found=$(find "$dir" -type d \( -name .venv -o -name .pixi -o -path '*/site-packages/homr' \) -prune -print)
if [ -n "$found" ]; then
  echo "check-no-reader-bundled: $dir holds a Python environment that must not be in a build of Bandroom:" >&2
  printf '%s\n' "$found" | sed 's/^/  /' >&2
  echo "homr, the reader of printed music, is AGPL-3.0 and is only ever fetched on the user's own computer;" >&2
  echo "a build that carried it would have to take the AGPL. Build from a clean checkout, or delete these folders." >&2
  exit 1
fi
echo "no adapter environment in $dir"
