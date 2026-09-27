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
    "$ROOT/$pkg/" "$DEST/$pkg/"
done
