#!/usr/bin/env bash
# Copies the Rust core's command line (scribe-core) into the app bundle (Contents/Resources/bin).
# Bandroom points the engine it installs at it with SCRIBE_CORE_CLI: the bass-tab profile needs it.
# It comes from core/target/release, where `scripts/worktree-setup.sh` puts it (or
# `cargo build --release --locked -p scribe-cli` in core/). Without it the binary is left out
# and Bandroom logs that bass tabs cannot be made; a Release build stops instead.
#   scripts/stage-core-cli.sh <destination>
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../../../.." && pwd)"
DEST="$1"
SRC="$ROOT/core/target/release/scribe-core"
if [ ! -x "$SRC" ]; then
  msg="no core command line at $SRC (run: scripts/worktree-setup.sh, or cargo build --release --locked -p scribe-cli in core/)"
  if [ "${CONFIGURATION:-Debug}" = "Release" ]; then echo "error: $msg" >&2; exit 1; fi
  echo "warning: $msg; the engine will refuse bass-tab jobs" >&2
  rm -f "$DEST/scribe-core"
  exit 0
fi
mkdir -p "$DEST"
cp "$SRC" "$DEST/scribe-core"
chmod 755 "$DEST/scribe-core"
