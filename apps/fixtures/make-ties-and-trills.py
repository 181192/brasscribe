#!/usr/bin/env python3
"""Build the ties and trills playback fixture: apps/fixtures/ties-and-trills.musicxml.

Three parts at 60 bpm in 4/4, one bar a second of quarter notes:
- Solo Cornet (B♭, written a tone up) and Flugelhorn (B♭, key of one flat written): transposing parts.
- Bass Trombone: concert pitch.

Bars 1-3 hold ties as files written before the ties were numbered: no `number` on `<tied>`. A tie in a bar, a
chain over a barline with a stop+start note, and (Flugelhorn, bar 1) a middle note with start before stop.
Bars 4-9 hold trills: a semitone auxiliary from the key, a whole tone, an accidental-mark sharp, an
accidental-mark flat, and a trill tied over a barline with a wavy line. The Flugelhorn's bar-4 trill takes its
semitone auxiliary (B♭) from its key of one flat.

    python3 apps/fixtures/make-ties-and-trills.py

The players' tests (Windows, Android, Apple) read the file and expect the notes in EXPECTED below.
"""
from pathlib import Path

OUT = Path(__file__).resolve().parent / "ties-and-trills.musicxml"

# (bar, step, octave, quarters, ties, trill) per note; trill = accidental-mark name, "" (from the key) or None
CHAIN = [
    (1, "D", 5, 2, ["start"], None), (1, "D", 5, 1, ["stop"], None), (1, "E", 5, 1, [], None),
    (2, "C", 5, 1, [], None), (2, "G", 4, 1, [], None), (2, "A", 4, 2, ["start"], None),
    (3, "A", 4, 2, ["stop", "start"], None), (3, "A", 4, 1, ["stop"], None), (3, None, 0, 1, [], None),
    (4, "E", 5, 4, [], ""), (5, "D", 5, 4, [], ""), (6, "E", 5, 4, [], "sharp"), (7, "A", 4, 4, [], "flat"),
    (8, "G", 4, 4, ["start"], "wavy"), (9, "G", 4, 2, ["stop"], None), (9, None, 0, 2, [], None),
]


def octave_down(notes, by):
    return [(b, s, o - by if s else o, q, t, tr) for b, s, o, q, t, tr in notes]


FLUGEL = [
    (1, "C", 5, 2, ["start"], None), (1, "C", 5, 1, ["start", "stop"], None), (1, "C", 5, 1, ["stop"], None),
    (2, None, 0, 4, [], None), (3, None, 0, 4, [], None),
    (4, "A", 4, 4, [], ""), (5, None, 0, 4, [], None), (6, None, 0, 4, [], None), (7, None, 0, 4, [], None),
    (8, None, 0, 4, [], None), (9, None, 0, 4, [], None),
]

PARTS = [
    ("P1", "Solo Cornet", 57, (-1, -2, 0), 0, "G", CHAIN),
    ("P2", "Flugelhorn", 57, (-1, -2, 0), -1, "G", FLUGEL),
    ("P3", "Bass Trombone", 58, None, 0, "F", octave_down(CHAIN, 2)),
]


def note_xml(step, octave, quarters, ties, trill):
    types = {1: "quarter", 2: "half", 4: "whole"}
    if step is None:
        return f"      <note>\n        <rest />\n        <duration>{quarters}</duration>\n        <type>{types[quarters]}</type>\n      </note>\n"
    x = f"      <note>\n        <pitch>\n          <step>{step}</step>\n          <octave>{octave}</octave>\n        </pitch>\n"
    x += f"        <duration>{quarters}</duration>\n"
    for t in ties:
        x += f'        <tie type="{t}" />\n'
    x += f"        <type>{types[quarters]}</type>\n"
    nots = [f'<tied type="{t}" />' for t in ties]
    if trill is not None:
        orn = '<ornaments><trill-mark placement="above" />'
        if trill not in ("", "wavy"):
            orn += f'<accidental-mark placement="above">{trill}</accidental-mark>'
        if trill == "wavy":
            orn += '<wavy-line type="start" number="1" />'
        nots.append(orn + "</ornaments>")
    if ties == ["stop"] and step == "G":
        nots.append('<ornaments><wavy-line type="stop" number="1" /></ornaments>')
    if nots:
        x += "        <notations>\n" + "".join(f"          {n}\n" for n in nots) + "        </notations>\n"
    return x + "      </note>\n"


def main():
    x = ['<?xml version="1.0" encoding="utf-8"?>\n<score-partwise version="4.0">\n',
         "  <work>\n    <work-title>Ties and trills</work-title>\n  </work>\n  <part-list>\n"]
    for pid, name, prog, _, _, _, _ in PARTS:
        x.append(f'    <score-part id="{pid}">\n      <part-name>{name}</part-name>\n'
                 f'      <midi-instrument id="{pid}-I1">\n        <midi-program>{prog}</midi-program>\n'
                 "      </midi-instrument>\n    </score-part>\n")
    x.append("  </part-list>\n")
    for pid, _, _, tr, fifths, clef, notes in PARTS:
        x.append(f'  <part id="{pid}">\n')
        for bar in range(1, 10):
            x.append(f'    <measure number="{bar}">\n')
            if bar == 1:
                x.append(f"      <attributes>\n        <divisions>1</divisions>\n        <key>\n          <fifths>{fifths}</fifths>\n"
                         "        </key>\n        <time>\n          <beats>4</beats>\n          <beat-type>4</beat-type>\n        </time>\n"
                         f"        <clef>\n          <sign>{clef}</sign>\n          <line>{2 if clef == 'G' else 4}</line>\n        </clef>\n")
                if tr:
                    x.append(f"        <transpose>\n          <diatonic>{tr[0]}</diatonic>\n          <chromatic>{tr[1]}</chromatic>\n"
                             "        </transpose>\n")
                x.append("      </attributes>\n")
                if pid == "P1":
                    x.append('      <direction>\n        <direction-type>\n          <metronome>\n            <beat-unit>quarter</beat-unit>\n'
                             "            <per-minute>60</per-minute>\n          </metronome>\n        </direction-type>\n"
                             '        <sound tempo="60" />\n      </direction>\n')
            for b, s, o, q, t, trill in notes:
                if b == bar:
                    x.append(note_xml(s, o, q, t, trill))
            x.append("    </measure>\n")
        x.append("  </part>\n")
    x.append("</score-partwise>\n")
    OUT.write_text("".join(x), encoding="utf-8")
    print(OUT)


# What every player should sound, concert MIDI keys: (part, start s, end s, key) for the plain notes; trills
# alternate main and auxiliary over (start, end).
EXPECTED_TRILLS = {  # part: [(start s, end s, main, auxiliary)]
    "Solo Cornet": [(12, 16, 74, 75), (16, 20, 72, 74), (20, 24, 74, 76), (24, 28, 67, 68), (28, 34, 65, 67)],
    "Flugelhorn": [(12, 16, 67, 68)],
    "Bass Trombone": [(12, 16, 52, 53), (16, 20, 50, 52), (20, 24, 52, 54), (24, 28, 45, 46), (28, 34, 43, 45)],
}

if __name__ == "__main__":
    main()
