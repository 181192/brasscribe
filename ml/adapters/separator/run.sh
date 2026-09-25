#!/bin/sh
# Separate <input.wav> into stems in <out_dir>. SEPARATOR_MODEL defaults to BS-Roformer-SW.ckpt
set -eu
here=$(cd "$(dirname "$0")" && pwd)
uv run --project "$here" audio-separator "$1" -m "${SEPARATOR_MODEL:-BS-Roformer-SW.ckpt}" --output_dir "$2" --output_format WAV --model_file_dir "$here/../../../models/separator" >/dev/null 2>&1
