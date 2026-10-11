#!/bin/sh
# Adapter contract: run.sh <input.wav> <output.mid>
# Env: MUSCRIPTOR_MODEL=small|medium|large, MUSCRIPTOR_INSTRUMENTS=trumpet,trombone,... (optional)
# Runs ../run_adapter.py, the cross-platform runner (uv project on Apple silicon Macs, else pixi; SCRIBE_ADAPTER_RUNNER picks).
here=$(cd "$(dirname "$0")" && pwd)
exec "${SCRIBE_PYTHON:-python3}" "$here/../run_adapter.py" muscriptor "$@"
