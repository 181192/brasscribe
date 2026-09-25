#!/bin/sh
# Adapter contract: run.sh <input.wav> <output.mid>  (monophonic lines only)
set -eu
here=$(cd "$(dirname "$0")" && pwd)
uv run --project "$here" python "$here/transcribe.py" "$1" "$2" >/dev/null
