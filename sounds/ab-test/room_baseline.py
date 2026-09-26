"""Room-matched baseline: put the baseline mix in the same hall as the realistic tier.

    uv run --project sounds python sounds/ab-test/room_baseline.py \
        --baseline data/golden/mikkel-arranged-band/brass-band.mp3 \
        --realistic-info data/runs/sound/realistic/mikkel.realistic.json \
        -o data/runs/sound/baseline-room/brass-band.room.mp3

The control for the room confound in the A/B test: the baseline audio (dry of any placement)
is summed to mono, convolved with the same stereo IR the realistic render used (same room,
same direct sound removal), and the wet signal is scaled so its energy relative to the
baseline equals the realistic render's measured wet-to-direct ratio (`wet_to_direct_db` in
its info JSON). The result is encoded to 128 kb/s MP3 like the original baseline.
"""

from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
import soundfile as sf
from scipy import signal

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from dsp import SR  # noqa: E402
from render import room_ir  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--baseline", required=True)
    ap.add_argument("--realistic-info", required=True)
    ap.add_argument("-o", "--out", required=True)
    args = ap.parse_args()
    info = json.loads(Path(args.realistic_info).read_text())
    wtd = info["wet_to_direct_db"]
    work = Path(tempfile.mkdtemp(prefix="brasscribe-roombase-"))
    dec = work / "baseline.wav"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", args.baseline, "-ar", str(SR), "-ac", "2", str(dec)], check=True)
    x, _ = sf.read(str(dec), dtype="float64", always_2d=True)
    ir = room_ir(info["room"])
    mono = x.mean(axis=1)
    wet = np.stack([signal.oaconvolve(mono, ir[:, c]) for c in range(2)], axis=1)
    wet *= math.sqrt(float(np.sum(x ** 2)) * 10 ** (wtd / 10) / float(np.sum(wet ** 2)))
    y = np.zeros((max(len(x), len(wet)), 2))
    y[: len(x)] += x
    y[: len(wet)] += wet
    y *= 10 ** (-1 / 20) / np.abs(y).max()  # peak -1 dBFS; the A/B generator re-matches loudness
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    wav = work / "room.wav"
    sf.write(str(wav), y.astype(np.float32), SR, subtype="PCM_24")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(wav), "-codec:a", "libmp3lame", "-b:a", "128k",
                    str(out)], check=True)
    meta = {"baseline": args.baseline, "room": info["room"], "wet_to_direct_db": wtd, "out": str(out)}
    out.with_suffix(".json").write_text(json.dumps(meta, indent=1))
    print(json.dumps(meta))


if __name__ == "__main__":
    main()
