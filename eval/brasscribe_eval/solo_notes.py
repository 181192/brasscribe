"""SwiftF0 and Basic Pitch transcriptions (and the SwiftF0 contour) of every single part, for confidence calibration.

For each part that solo_beats.py prepared (<root>/<set>/<song>/<part>.beats with the song's
reference.json), runs the light models on that part's own recording:
  <root>/<set>/<song>/<part>-sw.mid          SwiftF0 adapter
  <root>/<set>/<song>/<part>-bp.mid          Basic Pitch adapter
  <root>/<set>/<song>/<part>-sw.contour.npz  SwiftF0 contour

    uv run python -W ignore -m brasscribe_eval.solo_notes ../data/runs/music-core/solo-beats \\
        --urmp ../data/urmp/Dataset --choralebricks ../data/choralebricks/01_AudioAndAnnotations

Light models on single tracks: no GPU lock. BRASSCRIBE_ADAPTERS points at the adapters' environments.
"""

from __future__ import annotations

import argparse
import csv
import os
import subprocess
from pathlib import Path

ADAPTERS = Path(os.environ.get("BRASSCRIBE_ADAPTERS") or Path(__file__).resolve().parents[2] / "ml" / "adapters")
BRASS_QUARTET = {"S": "Trumpet", "A": "Flugelhorn", "T": "Baritone", "B": "Tuba"}  # as choralebricks.py


def _run(tool: list[str], wav: Path, dst: Path) -> None:
    if not dst.exists():
        subprocess.run([str(ADAPTERS / tool[0] / tool[1]), str(wav), str(dst)], check=True, capture_output=True)


def tracks(root: Path, urmp: Path | None, cb: Path | None):
    if urmp:
        for song in sorted((root / "urmp").iterdir()):
            for bf in sorted(song.glob("*.beats")):
                k = bf.stem.split("-")[0]
                yield song, bf.stem, next((urmp / song.name).glob(f"AuSep_{k}_*.wav"))
    if cb:
        with open(cb / "metadata_tracks.csv", newline="") as f:
            rows = list(csv.DictReader(f, delimiter=";"))
        for song in sorted((root / "choralebricks").iterdir()):
            for part, inst in BRASS_QUARTET.items():
                row = next(r for r in rows if r["song_id"] == song.name and r["part"] == part and r["instrument"] == inst)
                yield song, part, cb / song.name / "tracks_normalized" / row["path_audio"]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("root", type=Path)
    ap.add_argument("--urmp", type=Path)
    ap.add_argument("--choralebricks", type=Path)
    args = ap.parse_args()
    n = 0
    for song, part, wav in tracks(args.root, args.urmp, args.choralebricks):
        _run(["swift-f0", "run.sh"], wav, song / f"{part}-sw.mid")
        _run(["basic-pitch", "run.sh"], wav, song / f"{part}-bp.mid")
        _run(["swift-f0", "contour.sh"], wav, song / f"{part}-sw.contour.npz")
        n += 1
    print(n, "parts")


if __name__ == "__main__":
    main()
