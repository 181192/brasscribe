#!/usr/bin/env bash
# Stage the band sounds for the app bundle: apps/apple/Sounds/ (not committed) becomes the
# bundle's Sounds/ folder, where PlaybackKit looks for them first (BandSounds.locateBand).
#   brasscribe-band-16bit.sf2  from data/sounds/band (sounds/band.py --bits 16), else the 24-bit file
#   mapping.json, seating.json from sounds/
# Run by `make bandsound` and by check-prereqs.sh before the project is generated. Without the
# SoundFont the folder stays empty and the app reports the missing band sounds (basic tier).
set -euo pipefail
HERE="$(cd "$(dirname "$0")/.." && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
OUT="$HERE/Sounds"
mkdir -p "$OUT"
SRC=""
for f in brasscribe-band-16bit.sf2 brasscribe-band.sf2; do
  if [ -s "$ROOT/data/sounds/band/$f" ]; then SRC="$ROOT/data/sounds/band/$f"; break; fi
done
if [ -z "$SRC" ]; then
  echo "warning: no band SoundFont in data/sounds/band (build it with sounds/band.py --bits 16);" \
       "the app will play the basic tier and say the band sounds are missing." >&2
  exit 0
fi
rm -f "$OUT"/brasscribe-band*.sf2
# APFS clone when possible (no extra disk space), plain copy otherwise
cp -c "$SRC" "$OUT/$(basename "$SRC")" 2>/dev/null || cp "$SRC" "$OUT/$(basename "$SRC")"
cp "$ROOT/sounds/mapping.json" "$ROOT/sounds/seating.json" "$OUT/"
echo "band sounds staged: $OUT/$(basename "$SRC") ($(du -h "$SRC" | cut -f1))"
