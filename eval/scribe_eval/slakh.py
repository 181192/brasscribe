"""Build an eval entry from a Slakh2100 track: mix.wav, reference.json and score.musicxml.

Each rendered stem becomes a reference "part" named after its MIDI program, so
score.py reports per-instrument recall (e.g. the trumpet melody vs the bass).
Drums are excluded from the note reference.

Slakh renders bass patches an octave below the MIDI (bass is written an octave
above sounding), so Bass-class stems are shifted down 12 to sounding pitch.
Verified with pYIN on the rendered stems.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from pathlib import Path

import pretty_midi
import yaml


def build(track: Path, out: Path) -> None:
    meta = yaml.safe_load((track / "metadata.yaml").read_text())
    notes, parts = [], {}
    for sid, stem in meta["stems"].items():
        if stem["is_drum"] or not (track / "stems" / f"{sid}.wav").exists():
            continue
        name = f"{sid}-{stem['midi_program_name']}"
        parts[name] = stem["inst_class"]
        shift = -12 if stem["inst_class"] == "Bass" else 0
        pm = pretty_midi.PrettyMIDI(str(track / "MIDI" / f"{sid}.mid"))
        for inst in pm.instruments:
            for n in inst.notes:
                notes.append({"pitch": n.pitch + shift, "onset": n.start, "offset": n.end,
                              "part": name, "instrument": stem["midi_program_name"]})
    notes.sort(key=lambda n: (n["onset"], n["pitch"]))

    dest = out / track.name
    dest.mkdir(parents=True, exist_ok=True)
    shutil.copy(track / "mix.wav", dest / "mix.wav")
    shutil.copy(track / "all_src.mid", dest / "score.mid")
    (dest / "reference.json").write_text(json.dumps({"parts": parts, "notes": notes}, indent=1))
    subprocess.run(["mscore", "-o", str(dest / "score.musicxml"), str(dest / "score.mid")],
                   check=True, capture_output=True)
    print(f"{track.name}: {len(notes)} notes in {len(parts)} parts -> {dest}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("tracks", type=Path, nargs="+")
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    for t in args.tracks:
        build(t, args.out)


if __name__ == "__main__":
    main()
