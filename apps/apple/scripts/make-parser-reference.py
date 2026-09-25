"""Dump per-part concert pitches and onsets from a MusicXML file with music21.

The Swift MusicXML parser is tested against this output so the app hears and describes
the same notes as the Python reference. Tied notes are merged (stripTies).

Usage: python make-parser-reference.py score.musicxml out.json
Run with the music package environment, e.g. music/.venv/bin/python.
"""

import json
import sys

from music21 import converter, note, chord


def main(src: str, dst: str) -> None:
    s = converter.parse(src)
    out = {"parts": []}
    for p in s.parts:
        concert = p.toSoundingPitch(inPlace=False).stripTies()
        events = []
        for el in concert.flatten().notes:
            off = float(el.getOffsetInHierarchy(concert))
            if isinstance(el, note.Unpitched) or (isinstance(el, chord.Chord) and not hasattr(el, "pitches")):
                continue
            if isinstance(el, note.Note):
                events.append([round(off, 4), el.pitch.midi, round(float(el.quarterLength), 4)])
            elif isinstance(el, chord.Chord):
                for pt in el.pitches:
                    events.append([round(off, 4), pt.midi, round(float(el.quarterLength), 4)])
        events.sort()
        out["parts"].append({"name": p.partName, "count": len(events), "first": events[:40], "last": events[-10:]})
    with open(dst, "w") as f:
        json.dump(out, f, indent=1)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
