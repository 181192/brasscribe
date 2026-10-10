#!/bin/bash
# Fetches sfizz (BSD-2-Clause) into apps/android/third_party/sfizz (git-ignored). The audio module
# links it into Brasscribe's library when the directory exists, which turns on the realistic playback
# tier; without it, and always for Fretscribe, the module builds a stub. Tag 1.2.3 is the version the Android build was tested with.
set -euo pipefail
here="$(cd "$(dirname "$0")/.." && pwd)"
dest="$here/third_party/sfizz"
if [ -f "$dest/CMakeLists.txt" ]; then echo "sfizz already at $dest"; exit 0; fi
mkdir -p "$here/third_party"
git clone --recursive --depth 1 --shallow-submodules -b 1.2.3 https://github.com/sfztools/sfizz.git "$dest"
echo "sfizz at $dest"
