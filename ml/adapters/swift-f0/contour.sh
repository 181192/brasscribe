#!/bin/sh
# Adapter contract: contour.sh <input.wav> <output.npz>  (frame-level SwiftF0 pitch, confidence, loudness)
# Runs ../run_adapter.py, the cross-platform runner (uv project on Apple silicon Macs, else pixi; SCRIBE_ADAPTER_RUNNER picks).
here=$(cd "$(dirname "$0")" && pwd)
exec "${SCRIBE_PYTHON:-python3}" "$here/../run_adapter.py" swift-f0-contour "$@"
