#!/bin/sh
# Adapter contract: run.sh <input.wav> <out_dir>  (stems; SEPARATOR_MODEL defaults to BS-Roformer-SW.ckpt)
# Runs ../run_adapter.py, the cross-platform runner (uv project by default, pixi with BRASSCRIBE_ADAPTER_RUNNER=pixi).
here=$(cd "$(dirname "$0")" && pwd)
exec "${BRASSCRIBE_PYTHON:-python3}" "$here/../run_adapter.py" separator "$@"
