#!/bin/sh
# Adapter contract: run.sh <input.wav> <output.mid>  (monophonic lines only)
set -eu
here=$(cd "$(dirname "$0")" && pwd)
. "$here/../_env.sh"
adapter_exec swift-f0 python "$here/transcribe.py" "$1" "$2" >/dev/null
