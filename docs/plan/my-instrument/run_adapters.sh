#!/bin/sh
# Transcribe every brass stem of ChoraleBricks with SwiftF0 and Basic Pitch (cached).
CB=${CHORALEBRICKS:-/Users/k/private/brasscribe/data/choralebricks/01_AudioAndAnnotations}
HERE=$(cd "$(dirname "$0")" && pwd)
AD="$HERE/../../../ml/adapters"
OUT="$HERE/mid"
mkdir -p "$OUT"
for song in "$CB"/*/; do
  s=$(basename "$song")
  for w in "$song"tracks/*_tp.wav "$song"tracks/*_fh.wav "$song"tracks/*_fho.wav "$song"tracks/*_bar.wav "$song"tracks/*_tb.wav "$song"tracks/*_tba.wav; do
    [ -f "$w" ] || continue
    b=$(basename "$w" .wav)
    [ -f "$OUT/$s.$b.sw.mid" ] || "$AD/swift-f0/run.sh" "$w" "$OUT/$s.$b.sw.mid" >/dev/null 2>&1
    [ -f "$OUT/$s.$b.bp.mid" ] || "$AD/basic-pitch/run.sh" "$w" "$OUT/$s.$b.bp.mid" >/dev/null 2>&1
    echo "$s $b"
  done
done
echo DONE
