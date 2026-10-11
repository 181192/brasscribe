"""Build brass-quartet mixes and ground-truth note lists from ChoraleBricks.

Each song gets a mono mix of four isolated recordings (one per SATB part) and a
notes.json with the sounding-pitch ground truth for every part.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
import soundfile as sf

# Closest ChoraleBricks proxies for a brass-band quartet.
BRASS_QUARTET = {"S": "Trumpet", "A": "Flugelhorn", "T": "Baritone", "B": "Tuba"}


def track_row(tracks: pd.DataFrame, song_id: str, part: str, instrument: str):
    row = tracks[(tracks.song_id == song_id) & (tracks.part == part) & (tracks.instrument == instrument)]
    if row.empty:
        raise SystemExit(f"{song_id}: no {instrument} recording for part {part}")
    return row.iloc[0]


def alignment_path(song_id: str, path_audio: str) -> str:
    """Path of a track's alignment CSV, relative to 01_AudioAndAnnotations."""
    return f"{song_id}/alignments/{path_audio.replace('.wav', '.csv')}"


def reference_notes(alignments: dict[str, pd.DataFrame], instruments: dict[str, str]) -> list[dict]:
    """Ground truth from the alignments (part -> alignment table): performed note plus notated position."""
    notes = []
    for part, df in alignments.items():
        for n in df.itertuples():
            notes.append({"pitch": int(n.pitch), "onset": float(n.start_sec), "offset": float(n.end_sec),
                          "part": part, "instrument": instruments[part],
                          "quarter": float(n.start_quarter), "dur_quarter": float(n.dur_quarter),
                          "measure": float(n.start_meas), "time_sig": n.time_sig})
    return notes


def write_reference(dest: Path, notes: list[dict], parts: dict[str, str]) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    notes.sort(key=lambda n: (n["onset"], n["pitch"]))
    (dest / "reference.json").write_text(json.dumps({"parts": parts, "notes": notes}, indent=1))


def build_song(song_dir: Path, tracks: pd.DataFrame, out_dir: Path, parts: dict[str, str]) -> None:
    song_id = song_dir.name
    audio, alignments = [], {}
    for part, instrument in parts.items():
        row = track_row(tracks, song_id, part, instrument)
        y, sr = sf.read(song_dir / "tracks_normalized" / row.path_audio, dtype="float32")
        audio.append(y)
        # Alignments pair each performed note with its notated position.
        alignments[part] = pd.read_csv(song_dir.parent / alignment_path(song_id, row.path_audio), sep=";")
    notes = reference_notes(alignments, parts)

    length = max(len(y) for y in audio)
    mix = np.zeros(length, dtype=np.float32)
    for y in audio:
        mix[: len(y)] += y
    mix /= max(1e-9, np.abs(mix).max()) / 0.9

    dest = out_dir / song_id
    dest.mkdir(parents=True, exist_ok=True)
    sf.write(dest / "mix.wav", mix, sr, subtype="PCM_24")
    write_reference(dest, notes, parts)
    print(f"{song_id}: {len(notes)} notes, {length / sr:.1f} s")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", type=Path, required=True, help="ChoraleBricks 01_AudioAndAnnotations dir")
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    tracks = pd.read_csv(args.root / "metadata_tracks.csv", sep=";")
    for song_dir in sorted(p for p in args.root.iterdir() if p.is_dir()):
        build_song(song_dir, tracks, args.out, BRASS_QUARTET)


if __name__ == "__main__":
    main()
