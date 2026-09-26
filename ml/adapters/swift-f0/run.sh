#!/bin/sh
# Adapter contract: run.sh <input.wav> <output.mid>  (monophonic lines only)
# Runs ../run_adapter.py, the cross-platform runner (uv project by default, pixi with BRASSCRIBE_ADAPTER_RUNNER=pixi).
here=$(cd "$(dirname "$0")" && pwd)
exec "${BRASSCRIBE_PYTHON:-python3}" "$here/../run_adapter.py" swift-f0 "$@"
