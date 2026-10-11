#!/bin/sh
# Adapter contract: run.sh <input.wav> <output.mid>  (monophonic lines only)
# Runs ../run_adapter.py, the cross-platform runner (uv project on Apple silicon Macs, else pixi; SCRIBE_ADAPTER_RUNNER picks).
here=$(cd "$(dirname "$0")" && pwd)
exec "${SCRIBE_PYTHON:-python3}" "$here/../run_adapter.py" swift-f0 "$@"
