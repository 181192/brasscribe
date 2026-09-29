#!/usr/bin/env bash
# Stage the band sounds for the app bundles: apps/apple/Sounds/<platform>/Sounds/ (not committed)
# becomes each bundle's Sounds/ folder, where PlaybackKit looks for them first (BandSounds.locateBand).
#   macOS  brasscribe-band-16bit.sf2  (200 MB; else the 24-bit brasscribe-band.sf2)
#   iOS    brasscribe-band-mobile.sf2 (71 MB: smaller, for phone memory and download size)
#   both   mapping.json, seating.json from sounds/
# The SoundFonts come from data/sounds/band (`pixi run fetch-sounds`, sounds/tools/band_sounds.py).
# Run by `make bandsound` and by check-prereqs.sh before the project is generated. Without a
# SoundFont that platform's folder stays empty and the app reports the missing band sounds (basic tier).
set -euo pipefail
HERE="$(cd "$(dirname "$0")/.." && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
BAND="$ROOT/data/sounds/band"
# Earlier layouts put one SoundFont for every platform straight into Sounds/.
rm -f "$HERE"/Sounds/*.sf2 "$HERE"/Sounds/*.json

stage() {  # <platform> <SoundFont file name...>, the first that exists wins
  local platform="$1"; shift
  local out="$HERE/Sounds/$platform/Sounds" src=""
  for f in "$@"; do
    if [ -s "$BAND/$f" ]; then src="$BAND/$f"; break; fi
  done
  mkdir -p "$out"
  rm -f "$out"/brasscribe-band*.sf2
  if [ -z "$src" ]; then
    echo "warning: no $1 in $BAND (run: pixi run fetch-sounds); the $platform app will play the basic tier" \
         "and say the band sounds are missing." >&2
    return
  fi
  # APFS clone when possible (no extra disk space), plain copy otherwise
  cp -c "$src" "$out/$(basename "$src")" 2>/dev/null || cp "$src" "$out/$(basename "$src")"
  cp "$ROOT/sounds/mapping.json" "$ROOT/sounds/seating.json" "$out/"
  echo "band sounds staged for $platform: $(basename "$src") ($(du -h "$src" | cut -f1))"
}

stage macOS brasscribe-band-16bit.sf2 brasscribe-band.sf2
stage iOS brasscribe-band-mobile.sf2
