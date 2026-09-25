"""Recording -> solo-with-band brass-band score, end to end.

  beats     Beat This! on the mix
  stems     Mega-53 on the mix
  layers    solo / bass / drums / orchestra residual, transcribed (layers.py)
  arrange   Composition + layered arrangement + MusicXML/PDF/MP3 (arrange_layers_song.py)

Each step is skipped when its output already exists, so a run can be resumed.

    uv run python -m brasscribe_eval.song_pipeline data/mikkel/mikkel.wav --out data/mikkel/run --title "Mikkel"
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from . import layers

ADAPTERS = Path(__file__).resolve().parents[2] / "ml" / "adapters"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("mix", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--title", default="Draft")
    args = ap.parse_args()
    out = args.out
    out.mkdir(parents=True, exist_ok=True)

    beats = out / "mix.beats"
    if not beats.exists():
        print("beats…", flush=True)
        subprocess.run([str(ADAPTERS / "beat-this" / "run.sh"), str(args.mix), str(beats)], check=True)

    stems = out / "stems"
    if not (stems / "trumpet.flac").exists():
        print("stems (Mega-53)…", flush=True)
        subprocess.run([str(ADAPTERS / "mega53" / "run.sh"), str(args.mix), str(stems)], check=True)

    print("layers + transcription…", flush=True)
    paths = layers.build(args.mix, stems, out / "layers")
    layers.transcribe(paths)

    print("arrangement…", flush=True)
    subprocess.run([sys.executable, "-W", "ignore", "-m", "brasscribe_eval.arrange_layers_song",
                    "--layers", str(out / "layers"), "--beats", str(beats),
                    "--out", str(out / "arranged-band"), "--title", args.title], check=True)


if __name__ == "__main__":
    main()
