"""Meter benchmark for the tab profiles: one instrument alone, in bars that are not four beats.

The recordings the tab benchmarks use are all in 4/4, so they cannot show what the bar rule of the tab
profiles (bass_tab.bar_beats: a bar of one, two or eight tracked beats is written as four) does to music
in another meter. The passages here are written in this file and rendered with FluidSynth and the
MuseScore General SoundFont, the instrument alone: a polka bass and a march in 2/4, a chord waltz and a
melody over a bass in 3/4, an arpeggio and a jig in 6/8, a shuffle in 12/8 and a pattern in 5/4.

For each passage the benchmark reports the beats in a bar the beat tracker found (what was written before
the rule) and the beats in the bar that is written, against the meter it was written in. A compound
meter is right counted either way: 6/8 as two beats or six, 12/8 as four or twelve.

    python -m brasscribe_eval.meter_tab_bench synthesize [--data DIR]    the passages (FluidSynth)
    python -m brasscribe_eval.meter_tab_bench prepare [--data DIR]       run the models
    python -m brasscribe_eval.meter_tab_bench report [--data DIR]        per-passage meters

Rendered, one take each: weak evidence. It runs on a computer that has the SoundFont and the models.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

SET = "meter-tab"
BARS = 16
FILES = {"beats": "alone.beats", "bp": "alone-bp.mid", "sw": "alone-sw.mid"}
ROOTS = (0, 5, 7, 0)  # semitones over the first root, one per bar


def _bar(kind: str, root: int) -> list[tuple[int, float, float]]:
    """One bar of `kind` on `root`: (pitch, start, length) in the passage's counted beats."""
    third, fifth, octave = root + 4, root + 7, root + 12
    chord = (octave, octave + 4, octave + 7)
    if kind == "polka-bass":  # 2/4: root, fifth
        return [(root, 0, 0.9), (fifth - 12 if fifth - 12 >= 28 else fifth, 1, 0.9)]
    if kind == "march":  # 2/4: bass, chord
        return [(root, 0, 0.9)] + [(p, 1, 0.9) for p in chord]
    if kind == "waltz":  # 3/4: bass, chord, chord
        return [(root, 0, 0.9)] + [(p, b, 0.9) for b in (1, 2) for p in chord]
    if kind == "melody-over-bass":  # 3/4: a held bass note and three melody notes
        return [(root, 0, 2.9)] + [(p, b, 0.9) for b, p in enumerate((octave + 7, octave + 4, octave + 5))]
    if kind == "six-eight":  # two dotted beats, each an arpeggio of three eighths
        return [(p, k / 3, 0.3) for k, p in enumerate((root, fifth, octave, third + 12, octave, fifth))]
    if kind == "jig":  # 6/8 melody: long-short twice, then three eighths
        return [(octave, 0, 0.6), (octave + 2, 2 / 3, 0.3), (octave + 4, 1, 0.3), (octave + 5, 4 / 3, 0.3), (octave + 7, 5 / 3, 0.3)]
    if kind == "shuffle":  # 12/8: four dotted beats, bass long and chord short on each
        return [x for b in range(4) for x in ([(root, b, 0.6)] + [(p, b + 2 / 3, 0.3) for p in chord[:2]])]
    if kind == "five-four":  # 3 + 2: bass, chord, chord, bass, chord
        return [(root, 0, 0.9), (fifth, 3, 0.9)] + [(p, b, 0.9) for b in (1, 2, 4) for p in chord]
    raise KeyError(kind)


# name -> (the job's instrument, SoundFont bank and program, the bar's kind, beats in a bar as counted,
#          what counts as right, tempo of the counted beat, the first root)
PASSAGES = {
    "polka-bass-2-4": ("bass-4", (0, 33), "polka-bass", 2, (2,), 120.0, 40),
    "march-guitar-2-4": ("guitar-6", (0, 25), "march", 2, (2,), 112.0, 45),
    "waltz-chords-3-4": ("guitar-6", (0, 24), "waltz", 3, (3,), 132.0, 45),
    "melody-over-bass-3-4": ("guitar-6", (0, 24), "melody-over-bass", 3, (3,), 100.0, 43),
    "arpeggio-6-8": ("guitar-6", (0, 24), "six-eight", 2, (2, 6), 72.0, 45),
    "jig-6-8": ("guitar-6", (0, 25), "jig", 2, (2, 6), 112.0, 50),
    "shuffle-12-8": ("guitar-6", (0, 25), "shuffle", 4, (4, 12), 96.0, 40),
    "five-four": ("guitar-6", (0, 24), "five-four", 5, (5,), 120.0, 45),
}


def passage(name: str) -> list[dict]:
    """The notes of a passage, {pitch, onset, offset} in seconds, after one bar's rest."""
    _, _, kind, beats, _, bpm, root = PASSAGES[name]
    beat = 60 / bpm
    notes = []
    for bar in range(BARS):
        for pitch, start, length in _bar(kind, root + ROOTS[bar % len(ROOTS)]):
            at = (beats * (bar + 1) + start) * beat
            notes.append({"pitch": int(pitch), "onset": round(at, 6), "offset": round(at + length * beat, 6)})
    return sorted(notes, key=lambda n: (n["onset"], n["pitch"]))


def synthesize(data: Path) -> list[Path]:
    from .small_tab_bench import SOUNDFONT, _render

    made = []
    for name, (instrument, (bank, program), _, beats, right, bpm, _) in PASSAGES.items():
        dest = Path(data) / "eval" / SET / name
        dest.mkdir(parents=True, exist_ok=True)
        notes = passage(name)
        _render([(bank, program, False, [(n["pitch"], n["onset"], n["offset"], 92) for n in notes])], bpm, Path(data) / SOUNDFONT, dest / "alone.wav")
        (dest / "reference.json").write_text(json.dumps({"instrument": instrument, "beats_per_bar": beats, "right": list(right),
                                                         "tempo_bpm": bpm, "notes": notes}))
        made.append(dest)
    return made


def entries(data: Path) -> list[Path]:
    root = Path(data) / "eval" / SET
    return sorted(p for p in root.iterdir() if (p / "reference.json").exists()) if root.is_dir() else []


def prepare(entry: Path) -> None:
    """Beat This!, and Basic Pitch and SwiftF0 on the recording retuned as a whole recording is."""
    from .suites import _run_adapter, _run_retuned

    if not (entry / FILES["beats"]).exists():
        _run_adapter("beat-this", entry / "alone.wav", entry / FILES["beats"])
    for key, tool in (("bp", "basic-pitch"), ("sw", "swift-f0")):
        if not (entry / FILES[key]).exists():
            _run_retuned(tool, entry / "alone.wav", entry / FILES[key])


def meters(entry: Path) -> dict:
    """The beats in a bar the tracker found for the passage (what the tab had before the bar rule) and the
    beats in the bar the tab profile writes, with the tempo it writes."""
    from brasscribe_engine import bass_tab, tab

    ref = json.loads((entry / "reference.json").read_text())
    heard, second = bass_tab.load_transcription(entry / FILES["bp"]), bass_tab.load_transcription(entry / FILES["sw"])
    beats = np.loadtxt(entry / FILES["beats"], ndmin=2)

    def written() -> dict:
        if ref["instrument"] in bass_tab.INSTRUMENTS:
            return bass_tab.transcribed_line(heard, beats, "auto", second)
        return tab.played_notes(heard, beats, ref["instrument"], "auto", second)

    doc = written()
    rule = bass_tab.bar_beats
    bass_tab.bar_beats = lambda tracked, *evidence: tracked  # the bar as tracked
    try:
        before = written()
    finally:
        bass_tab.bar_beats = rule
    return {"passage": entry.name, "right": ref["right"], "tracked": before["meter"]["beats"], "written": doc["meter"]["beats"],
            "tempo": doc["tempo_bpm"], "true_tempo": ref["tempo_bpm"]}


def evaluate(data: Path) -> tuple[dict[str, float], list[dict]]:
    rows = [meters(e) for e in entries(data) if all((e / f).exists() for f in FILES.values())]
    before = [r["tracked"] in r["right"] for r in rows]
    after = [r["written"] in r["right"] for r in rows]
    return {"tracked_ok": float(np.mean(before)), "meter_ok": float(np.mean(after)),
            "right_became_wrong": float(sum(b and not a for b, a in zip(before, after))),
            "wrong_became_right": float(sum(a and not b for b, a in zip(before, after))), "excerpts": float(len(rows))}, rows


def main() -> None:
    from .paths import DATA

    ap = argparse.ArgumentParser()
    ap.add_argument("command", choices=["synthesize", "prepare", "report"])
    ap.add_argument("--data", type=Path, default=DATA)
    args = ap.parse_args()
    if args.command == "synthesize":
        for d in synthesize(args.data):
            print(d.name, len(json.loads((d / "reference.json").read_text())["notes"]), "notes")
    elif args.command == "prepare":
        for d in entries(args.data):
            prepare(d)
            print(d.name, "ready", flush=True)
    else:
        summary, rows = evaluate(args.data)
        for r in rows:
            print(f"{r['passage']:22s} right {r['right']}  tracked {r['tracked']}  written {r['written']}  tempo {r['tempo']} (true {r['true_tempo']})")
        print(" ".join(f"{k}={v:.3f}" for k, v in summary.items()))


if __name__ == "__main__":
    main()
