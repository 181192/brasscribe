#!/bin/bash
# Fetches sfizz (BSD-2-Clause) into apps/android/third_party/sfizz (git-ignored). The audio module
# links it into Brasscribe's library when the directory exists, which turns on the realistic playback
# tier; without it, and always for Fretscribe, the module builds a stub. Tag 1.2.3 is the version the Android build was tested with.
set -euo pipefail
here="$(cd "$(dirname "$0")/.." && pwd)"
dest="$here/third_party/sfizz"
if [ -f "$dest/CMakeLists.txt" ]; then
  echo "sfizz already at $dest"
else
  mkdir -p "$here/third_party"
  git clone --recursive --depth 1 --shallow-submodules -b 1.2.3 https://github.com/sfztools/sfizz.git "$dest"
  echo "sfizz at $dest"
fi
# sfizz writes a Doxyfile into its own source directory every time it is configured. Gradle
# configures the ABIs at the same time from this one checkout, and the second one to write fails
# with "No such file or directory". The app needs no Doxyfile, so the line is taken out.
if grep -q 'scripts/doxygen/Doxyfile.in' "$dest/src/CMakeLists.txt"; then
  sed -i.orig '/scripts\/doxygen\/Doxyfile.in/d' "$dest/src/CMakeLists.txt"
  rm -f "$dest/src/CMakeLists.txt.orig"
fi
