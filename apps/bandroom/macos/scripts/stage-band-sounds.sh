#!/usr/bin/env bash
# Copies the band sounds Studio plays into the app bundle (Contents/Resources/band): the 16-bit band
# SoundFont as brasscribe-band.sf2, its part map and the licence notice. Bandroom points the engine at
# them with BRASSCRIBE_BAND_SOUNDS_DIR. The SoundFont is not in git: `pixi run fetch-sounds` gets it.
# Without it the folder is left out and Bandroom logs that the band sounds are missing; a Release
# build stops instead.
#   scripts/stage-band-sounds.sh <destination>
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../../../.." && pwd)"
DEST="$1"
SRC="$ROOT/data/sounds/band/brasscribe-band-16bit.sf2"
if [ ! -s "$SRC" ]; then
  msg="no band SoundFont at $SRC (run: pixi run fetch-sounds)"
  if [ "${CONFIGURATION:-Debug}" = "Release" ]; then echo "error: $msg" >&2; exit 1; fi
  echo "warning: $msg; Studio will play General MIDI sounds" >&2
  rm -rf "$DEST"
  exit 0
fi
mkdir -p "$DEST"
# APFS clone when possible (no extra disk space), plain copy otherwise
[ "$DEST/brasscribe-band.sf2" -nt "$SRC" ] || cp -c "$SRC" "$DEST/brasscribe-band.sf2" 2>/dev/null || cp "$SRC" "$DEST/brasscribe-band.sf2"
cp "$ROOT/sounds/mapping.json" "$DEST/mapping.json"
cp "$ROOT/sounds/band-notice.txt" "$DEST/NOTICE.txt"
