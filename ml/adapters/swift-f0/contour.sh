#!/bin/sh
# Contour contract: contour.sh <input.wav> <output.npz>  (frame-level SwiftF0 pitch, confidence, loudness)
set -eu
here=$(cd "$(dirname "$0")" && pwd)
. "$here/../_env.sh"
adapter_exec swift-f0 python "$here/contour.py" "$1" "$2" >/dev/null
