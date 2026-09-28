#!/usr/bin/env bash
# Copies the engine workspace into the app bundle: pixi.toml, pixi.lock and the Python packages the
# engine environment installs from (engine, music, the benchmark package), plus the adapters.
# The first run copies it to ~/Library/Application Support/Brasscribe/envs and runs `pixi install`; a launch after an
# app update replaces that copy when its stamp (.brasscribe-workspace.json, written last) differs from this one.
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

# The workspace stamp: a hash of every staged file's path and content (never dates), so Bandroom can tell at launch
# that the copy in the data folder comes from another build. pixi.lock gets its own hash: only a new lockfile needs
# `pixi install` again.
STAMP_FILE=.brasscribe-workspace.json
rm -f "$DEST/$STAMP_FILE"
STAMP="$(cd "$DEST" && find . -type f ! -name '.DS_Store' -print0 | LC_ALL=C sort -z | xargs -0 shasum -a 256 \
  | shasum -a 256 | cut -d' ' -f1)"
LOCK="$(shasum -a 256 "$DEST/pixi.lock" | cut -d' ' -f1)"
COMMIT="$(git -C "$ROOT" rev-parse --short HEAD 2>/dev/null || true)"
printf '{"stamp": "%s", "lock": "%s", "commit": "%s", "version": "%s", "build": "%s"}\n' \
  "$STAMP" "$LOCK" "$COMMIT" "${MARKETING_VERSION:-}" "${CURRENT_PROJECT_VERSION:-}" > "$DEST/$STAMP_FILE"
