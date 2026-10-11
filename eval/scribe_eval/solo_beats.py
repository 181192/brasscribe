"""Beat This! beats (and reference notes) for every single part of URMP and ChoraleBricks.

For the solo path (one instrument, no band) the apps run Beat This! small0.
This builds, per part:
  <out>/<set>/<song>/<part>.beats   Beat This! on that part's own recording (BEAT_THIS_MODEL, default small0)
  <out>/<set>/<song>/reference.json the song's reference notes with notated positions, plus the score meter

    uv run python -W ignore -m brasscribe_eval.solo_beats --urmp ../data/urmp/Dataset \\
        --choralebricks ../data/choralebricks/01_AudioAndAnnotations --out ../data/runs/music-core/solo-beats

Beat This! runs through ml/adapters/beat-this/run.sh inside the machine-wide heavy-model lock.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import subprocess
from pathlib import Path

import pretty_midi

from . import urmp
from .gpulock import gpu_lock
BRASS_QUARTET = {"S": "Trumpet", "A": "Flugelhorn", "T": "Baritone", "B": "Tuba"}  # as choralebricks.py

# The adapters' environments live in the main checkout; BRASSCRIBE_ADAPTERS points there from a worktree.
ADAPTERS = Path(os.environ.get("BRASSCRIBE_ADAPTERS") or Path(__file__).resolve().parents[2] / "ml" / "adapters")


def _beats(wav: Path, dst: Path, model: str) -> None:
    if dst.exists():
        return
    with gpu_lock(poll=5):
        env = dict(os.environ, BEAT_THIS_MODEL=model)
        subprocess.run([str(ADAPTERS / "beat-this" / "run.sh"), str(wav), str(dst)], check=True, env=env,
                       capture_output=True)


def urmp_songs(root: Path, out: Path, model: str) -> None:
    for piece in sorted(p for p in root.iterdir() if p.is_dir() and re.match(r"\d+_", p.name)):
        dest = out / "urmp" / piece.name
        if not (dest / "reference.json").exists():
            urmp.build(piece, out / "urmp")
            (dest / "mix.wav").unlink(missing_ok=True)
            pm = pretty_midi.PrettyMIDI(str(dest / "score.mid"))
            ts = pm.time_signature_changes[0] if pm.time_signature_changes else None
            ref = json.loads((dest / "reference.json").read_text())
            ref["time_sig"] = f"{ts.numerator}/{ts.denominator}" if ts else "4/4"
            (dest / "reference.json").write_text(json.dumps(ref))
        parts = json.loads((dest / "reference.json").read_text())["parts"]
        for part in parts:
            k = part.split("-")[0]
            wav = next(piece.glob(f"AuSep_{k}_*.wav"))
            _beats(wav, dest / f"{part}.beats", model)
        print(piece.name, len(parts), "parts")


def choralebricks_songs(root: Path, eval_dir: Path, out: Path, model: str) -> None:
    with open(root / "metadata_tracks.csv", newline="") as f:
        rows = list(csv.DictReader(f, delimiter=";"))
    for song in sorted(p for p in eval_dir.iterdir() if (p / "reference.json").exists()):
        dest = out / "choralebricks" / song.name
        dest.mkdir(parents=True, exist_ok=True)
        if not (dest / "reference.json").exists():
            ref = json.loads((song / "reference.json").read_text())
            ref["time_sig"] = next((n["time_sig"] for n in ref["notes"] if n.get("time_sig")), "4/4")
            (dest / "reference.json").write_text(json.dumps(ref))
        for part, inst in BRASS_QUARTET.items():
            row = next(r for r in rows if r["song_id"] == song.name and r["part"] == part and r["instrument"] == inst)
            _beats(root / song.name / "tracks_normalized" / row["path_audio"], dest / f"{part}.beats", model)
        print(song.name)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--urmp", type=Path)
    ap.add_argument("--choralebricks", type=Path)
    ap.add_argument("--choralebricks-eval", type=Path, default=Path("../data/eval/choralebricks-brass4"))
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--model", default="small0")
    args = ap.parse_args()
    if args.urmp:
        urmp_songs(args.urmp, args.out, args.model)
    if args.choralebricks:
        choralebricks_songs(args.choralebricks, args.choralebricks_eval, args.out, args.model)


if __name__ == "__main__":
    main()
