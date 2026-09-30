#!/bin/sh
# Adapter contract: run.sh <input audio> <output dir>  -> <output dir>/<stem>.flac for all 53 stems
# Runs ../run_adapter.py, the cross-platform runner (uv project on Apple silicon Macs, else pixi; BRASSCRIBE_ADAPTER_RUNNER picks).
here=$(cd "$(dirname "$0")" && pwd)
exec "${BRASSCRIBE_PYTHON:-python3}" "$here/../run_adapter.py" mega53 "$@"
