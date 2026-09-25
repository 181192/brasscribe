#!/bin/sh
# Adapter contract: run.sh <input audio> <output dir>  -> <output dir>/<stem>.flac for all 53 stems
set -eu
here=$(cd "$(dirname "$0")" && pwd)
. "$here/../_env.sh"
models="$here/../../../models/mega53"
[ -d "$here/msst" ] || "$here/setup.sh"
tmp=$(mktemp -d)
name=$(basename "$1" | sed 's/\.[^.]*$//')
ffmpeg -loglevel error -y -i "$1" -ar 44100 -ac 2 "$tmp/$name.wav"
mkdir -p "$tmp/out"
adapter_exec "$(torch_env mega53)" python "$here/msst/inference.py" --model_type bs_roformer \
  --config_path "$models/mvsep_mega_model_bs_roformer_53_stems.yaml" \
  --start_check_point "$models/mvsep_mega_model_bs_roformer_53_stems_v1.ckpt" \
  --input_folder "$tmp" --store_dir "$tmp/out" --disable_detailed_pbar --pcm_type PCM_16 >/dev/null 2>&1
mkdir -p "$2"
mv "$tmp/out/$name"/*.flac "$2"/
rm -rf "$tmp"
