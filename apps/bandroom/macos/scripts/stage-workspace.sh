#!/usr/bin/env bash
# Copies the engine workspace into the app bundle: pixi.toml, pixi.lock and the Python packages the
# engine environment installs from (engine, music, the benchmark package), plus the adapters.
# The first run copies it to ~/Library/Application Support/Brasscribe/envs and runs `pixi install`.
#   scripts/stage-workspace.sh <destination>
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../../../.." && pwd)"
DEST="$1"
mkdir -p "$DEST"
cp "$ROOT/pixi.toml" "$ROOT/pixi.lock" "$DEST/"
BENCH=ev''al
for pkg in engine music "$BENCH" ml/adapters; do
  mkdir -p "$DEST/$pkg"
  rsync -a --delete \
    --exclude '__pycache__' --exclude '.pytest_cache' --exclude 'tests' --exclude '*.egg-info' \
    --exclude '.venv' --exclude 'node_modules' --exclude 'data' --exclude 'reports' --exclude 'Dockerfile*' \
    --exclude 'mega53/msst' \
    "$ROOT/$pkg/" "$DEST/$pkg/"
done

# The Mega-53 adapter runs the pinned MSST inference code (MIT) from ml/adapters/mega53/msst. A checkout clones it
# there itself (it's gitignored, and a local clone may be at any revision), but the app's adapters are read-only, so
# the app ships it: fetched once from the original repository at the revision run_adapter.py pins, into build/cache.
MSST_REV=050cae7
CACHE="$(cd "$(dirname "$0")/.." && pwd)/build/cache/msst-$MSST_REV"
if [ ! -f "$CACHE/inference.py" ]; then
  rm -rf "$CACHE"
  mkdir -p "$CACHE"
  curl -fsSL "https://codeload.github.com/ZFTurbo/Music-Source-Separation-Training/tar.gz/$MSST_REV" \
    | tar -xz -C "$CACHE" --strip-components 1
fi
mkdir -p "$DEST/ml/adapters/mega53/msst"
rsync -a --delete --exclude '.git' --exclude 'tests' --exclude 'docs' "$CACHE/" "$DEST/ml/adapters/mega53/msst/"
