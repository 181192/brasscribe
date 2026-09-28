#!/bin/bash
# Fixed cost of one model adapter call: wall time on a 2 s clip (nearly all start-up: interpreter,
# uv environment, imports, model load) against a 60 s clip of the same recording.
#
#   qa/perf/adapter_overhead.sh data/mikkel/mikkel.wav swift-f0 basic-pitch muscriptor
#
# Run it twice: the first call after a while pays a cold file cache (about 9-11 s here).
# muscriptor and beat-this use the GPU; the engine's GPU mutex is not taken, so do not run
# this while a job is running.
set -euo pipefail
cd "$(dirname "$0")/../.."
src=$1; shift
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
ffmpeg -loglevel error -y -ss 30 -t 2 -i "$src" -ac 1 -ar 44100 "$tmp/2s.wav"
ffmpeg -loglevel error -y -ss 30 -t 60 -i "$src" -ac 1 -ar 44100 "$tmp/60s.wav"
py=${PYTHON:-python}
for a in "$@"; do
  for clip in 2s 60s; do
    t0=$($py -c 'import time; print(time.time())')
    $py ml/adapters/run_adapter.py "$a" "$tmp/$clip.wav" "$tmp/$a-$clip.out" >/dev/null 2>"$tmp/$a-$clip.err" && rc=0 || rc=$?
    t1=$($py -c 'import time; print(time.time())')
    $py -c "print(f'$a $clip rc=$rc {$t1 - $t0:.1f} s')"
  done
done
