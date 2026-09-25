#!/bin/sh
# One-time setup: pinned MSST inference code + Mega-53 v1 weights (licence unstated; personal use).
set -eu
here=$(cd "$(dirname "$0")" && pwd)
models="$here/../../../models/mega53"
[ -d "$here/msst" ] || git clone -q https://github.com/ZFTurbo/Music-Source-Separation-Training "$here/msst"
git -C "$here/msst" checkout -q 050cae7
mkdir -p "$models"
base=https://github.com/ZFTurbo/Music-Source-Separation-Training/releases/download/v1.0.21
for f in mvsep_mega_model_bs_roformer_53_stems.yaml mvsep_mega_model_bs_roformer_53_stems_v1.ckpt; do
  [ -f "$models/$f" ] || curl -sL -o "$models/$f" "$base/$f"
done
