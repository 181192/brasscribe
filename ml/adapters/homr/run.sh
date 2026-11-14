#!/bin/sh
# Adapter contract: run.sh <page or folder of pages> <output.musicxml>  (PNG, JPEG, WebP or PDF; a folder's pages in name order)
# Runs ../run_adapter.py, the cross-platform runner (uv project on Apple silicon Macs, else pixi; SCRIBE_ADAPTER_RUNNER picks).
here=$(cd "$(dirname "$0")" && pwd)
exec "${SCRIBE_PYTHON:-python3}" "$here/../run_adapter.py" homr "$@"
