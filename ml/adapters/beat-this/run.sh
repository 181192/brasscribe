#!/bin/sh
# Adapter contract: run.sh <input.wav> <output.beats>
set -eu
here=$(cd "$(dirname "$0")" && pwd)
. "$here/../_env.sh"
adapter_exec "$(torch_env beat-this)" beat_this "$1" -o "$2" >/dev/null 2>&1
