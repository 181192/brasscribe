#!/bin/sh
# Transcribe the URMP brass stems (horn, trombone, tuba, trumpet) with SwiftF0 and Basic Pitch (cached).
U=/Users/k/private/brasscribe/data/urmp/Dataset
HERE=$(cd "$(dirname "$0")" && pwd)
AD="$HERE/../../../ml/adapters"
OUT="$HERE/urmp"
mkdir -p "$OUT"
for w in "$U"/*/AuSep_*_tpt_*.wav "$U"/*/AuSep_*_hn_*.wav "$U"/*/AuSep_*_tbn_*.wav "$U"/*/AuSep_*_tba_*.wav; do
  [ -f "$w" ] || continue
  b=$(basename "$w" .wav)
  [ -f "$OUT/$b.sw.mid" ] || "$AD/swift-f0/run.sh" "$w" "$OUT/$b.sw.mid" >/dev/null 2>&1
  [ -f "$OUT/$b.bp.mid" ] || "$AD/basic-pitch/run.sh" "$w" "$OUT/$b.bp.mid" >/dev/null 2>&1
  echo "$b"
done
echo DONE
