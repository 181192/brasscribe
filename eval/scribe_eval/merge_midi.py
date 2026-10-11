"""Merge per-stem MIDI files into one, one instrument track per stem."""

import sys
from pathlib import Path

import pretty_midi


def main() -> None:
    out, inputs = sys.argv[1], sys.argv[2:]
    merged = pretty_midi.PrettyMIDI()
    for path in inputs:
        pm = pretty_midi.PrettyMIDI(path)
        track = pretty_midi.Instrument(program=0, name=Path(path).stem)
        track.notes = [n for inst in pm.instruments if not inst.is_drum for n in inst.notes]
        merged.instruments.append(track)
    merged.write(out)


if __name__ == "__main__":
    main()
