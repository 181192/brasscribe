#!/usr/bin/env bash
# Downloads the baseline General MIDI sound font for Brasscribe Play:
# MuseScore_General.sf2 (MIT, S. Christian Collins), ~206 MB, uncompressed SF2 so
# AVAudioUnitSampler can load it (the SF3 builds are Ogg-compressed and cannot).
#
# Output (gitignored): data/soundfonts/MuseScore_General.sf2 (+ licence).
# The app finds it via BRASSCRIBE_SOUNDFONT, or copy it to
# ~/Library/Application Support/Brasscribe/SoundFonts/ (macOS) / the app's Documents.
set -euo pipefail

BASE=https://ftp.osuosl.org/pub/musescore/soundfont/MuseScore_General
ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
OUT="$ROOT/data/soundfonts"
mkdir -p "$OUT"
cd "$OUT"
if [ ! -s MuseScore_General.sf2 ]; then
  curl -fL --retry 3 -o MuseScore_General.sf2.part "$BASE/MuseScore_General.sf2"
  mv MuseScore_General.sf2.part MuseScore_General.sf2
fi
curl -fsSL -o MuseScore_General_License.md "$BASE/MuseScore_General_License.md"
head -c 4 MuseScore_General.sf2 | grep -q RIFF || { echo "not a RIFF sound font" >&2; exit 1; }
shasum -a 256 MuseScore_General.sf2 > MuseScore_General.sf2.sha256
echo "$OUT/MuseScore_General.sf2 ($(du -h MuseScore_General.sf2 | cut -f1)) $(cut -c1-16 MuseScore_General.sf2.sha256)"
