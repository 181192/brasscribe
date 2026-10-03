"""SwiftF0 contour of every part's own track, for duration_bench --offsets swiftf0.

URMP ships each player's separate recording (AuSep_<k>_<inst>_*.wav) and
ChoraleBricks each part's track (tracks_normalized/, chosen as in
choralebricks.BRASS_QUARTET). Runs inside the SwiftF0 adapter's environment:

    uv run --project ml/adapters/swift-f0 python eval/brasscribe_eval/track_contours.py \
        urmp data/urmp/Dataset data/eval/urmp-brass data/runs/contours/urmp-brass
    uv run --project ml/adapters/swift-f0 python eval/brasscribe_eval/track_contours.py \
        choralebricks data/choralebricks/01_AudioAndAnnotations data/eval/choralebricks-brass4 data/runs/contours/choralebricks-brass4

Writes <out>/<song>/<part>.npz (t, pitch_hz, confidence, loudness_db).
"""

from __future__ import annotations

import os

# ONNX Runtime reports to Microsoft unless this is set before it starts.
os.environ.setdefault("ORT_DISABLE_TELEMETRY", "1")

import csv
import json
import sys
from pathlib import Path

import numpy as np
from swift_f0 import SwiftF0

BRASS_QUARTET = {"S": "Trumpet", "A": "Flugelhorn", "T": "Baritone", "B": "Tuba"}


def tracks_urmp(root: Path, song: str, parts: list[str]) -> dict[str, Path]:
    out = {}
    for part in parts:
        k = part.split("-")[0]
        out[part] = next((root / song).glob(f"AuSep_{k}_*.wav"))
    return out


def tracks_choralebricks(root: Path, song: str, parts: list[str]) -> dict[str, Path]:
    with open(root / "metadata_tracks.csv", newline="") as f:
        rows = [r for r in csv.DictReader(f, delimiter=";") if r["song_id"] == song]
    out = {}
    for part in parts:
        row = next(r for r in rows if r["part"] == part and r["instrument"] == BRASS_QUARTET[part])
        out[part] = root / song / "tracks_normalized" / row["path_audio"]
    return out


def main() -> None:
    kind, root, eval_dir, out = sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3]), Path(sys.argv[4])
    find = {"urmp": tracks_urmp, "choralebricks": tracks_choralebricks}[kind]
    det = SwiftF0()
    for song in sorted(p for p in eval_dir.iterdir() if (p / "reference.json").exists()):
        parts = sorted(json.loads((song / "reference.json").read_text())["parts"])
        for part, wav in find(root, song.name, parts).items():
            dst = out / song.name / f"{part}.npz"
            if dst.exists():
                continue
            dst.parent.mkdir(parents=True, exist_ok=True)
            r = det.detect_file(wav)
            np.savez_compressed(dst, t=r.timestamps, pitch_hz=r.pitch_hz, confidence=r.confidence, loudness_db=r.loudness_db)
            print(song.name, part, wav.name, len(r.timestamps))


if __name__ == "__main__":
    main()
