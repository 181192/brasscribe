#!/bin/sh
# Pipeline B: separate <input.wav> into stems, transcribe each pitched stem, merge to <output.mid>.
# Env: TRANSCRIBER=muscriptor|basic-pitch (default muscriptor)
set -eu
here=$(cd "$(dirname "$0")" && pwd)
adapters="$here/../adapters"
in=$1 out=$2
work="${out%.mid}.work"
mkdir -p "$work/stems" "$work/midi"
[ -n "$(ls "$work/stems" 2>/dev/null)" ] || "$adapters/separator/run.sh" "$in" "$work/stems"
for stem in "$work"/stems/*.wav; do
  name=$(basename "$stem" .wav)
  case "$name" in *drums*) continue ;; esac
  "$adapters/${TRANSCRIBER:-muscriptor}/run.sh" "$stem" "$work/midi/$name.mid"
done
uv run --project "$here/../../eval" python -W ignore -m brasscribe_eval.merge_midi "$out" "$work"/midi/*.mid
