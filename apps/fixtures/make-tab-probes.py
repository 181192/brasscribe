#!/usr/bin/env python3
"""Write the tab probes: short hand-written bass lines that each put the tab view's marks in a hard place.

Each probe is a list of notes written here (nothing is recorded or transcribed), placed and written by
the engine as its arrange stage does it, with the Rust core. A probe has notes in doubt (a confidence
under 0.4) and, where it says so, a note below the lowest string.

    pixi run python apps/fixtures/make-tab-probes.py

Needs apps/fixtures/bass-line (the rest of a tab's facts are taken from it) and the core's command line
(`cargo build --release -p scribe-cli` in core/, or SCRIBE_CORE_CLI).

Writes apps/fixtures/tab-probes/<name>/: tab.json, and the page in the three layouts as tab.musicxml,
tab-and-notation.musicxml and notation.musicxml. Only tests read this folder.
"""
import json
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
FIRST = HERE / "bass-line"
OUT = HERE / "tab-probes"
LAYOUTS = {"tab": "tab", "tab-and-notation": "tab-and-notation", "notation": "notation"}
SURE, DOUBT = 0.9, 0.2
E1, G1, A1, B1, C2, D2, E2, G2, A2, D1 = 28, 31, 33, 35, 36, 38, 40, 43, 45, 26
Q = 24  # ticks to a quarter note


def n(pitch, start, dur, confidence=SURE):
    return {"pitch": pitch, "start": start, "dur": dur, "confidence": confidence}


# name: (what it probes, meter, capo, notes)
PROBES = {
    "chords": ("chords with a doubtful inner note, and one with two doubtful notes", (4, 4), 0, [
        n(A1, 0, Q), n(E2, 0, Q, DOUBT), n(A2, 0, Q),
        n(E1, Q, Q), n(G1, 2 * Q, Q), n(A1, 3 * Q, Q),
        n(A1, 4 * Q, 2 * Q, DOUBT), n(E2, 4 * Q, 2 * Q), n(A2, 4 * Q, 2 * Q, DOUBT),
        n(E1, 6 * Q, 2 * Q),
    ]),
    "tie-over-the-bar": ("a doubtful note tied over the bar line", (4, 4), 0, [
        n(E1, 0, Q), n(G1, Q, Q), n(A1, 2 * Q, Q), n(B1, 3 * Q, 2 * Q, DOUBT),
        n(A1, 5 * Q, Q), n(G1, 6 * Q, 2 * Q),
    ]),
    "moved-to-the-grid": ("notes that start between the starts that can be written", (4, 4), 0, [
        n(E1, 0, 19), n(G1, 19, 24, DOUBT), n(A1, 43, 29), n(B1, 3 * Q, Q, DOUBT),
        n(E1, 4 * Q + 1, 2 * Q - 1, DOUBT), n(G1, 6 * Q, 2 * Q),
    ]),
    "pickup": ("a pickup whose first note is in doubt, and a doubtful first note of a bar in mid-line", (4, 4), 0, [
        n(B1, -Q, Q, DOUBT),
        n(E1, 0, Q, DOUBT), n(G1, Q, Q), n(A1, 2 * Q, Q), n(B1, 3 * Q, Q),
        n(E2, 4 * Q, Q, DOUBT), n(D2, 5 * Q, Q), n(B1, 6 * Q, 2 * Q),
    ]),
    "triplets": ("triplets with a doubtful note inside one", (4, 4), 0, [
        n(E1, 0, 8), n(G1, 8, 8, DOUBT), n(A1, 16, 8), n(B1, Q, Q),
        n(A1, 2 * Q, 8), n(G1, 2 * Q + 8, 8), n(E1, 2 * Q + 16, 8, DOUBT), n(E1, 3 * Q, Q),
    ]),
    "no-place-in-a-chord": ("a note below the lowest string in a chord, and one alone that is also in doubt", (4, 4), 0, [
        n(D1, 0, Q), n(A1, 0, Q), n(E2, Q, Q, DOUBT), n(G1, 2 * Q, Q), n(D1, 3 * Q, Q, DOUBT),
    ]),
    "capo": ("a capo at the second fret", (4, 4), 2, [
        n(A1, 0, Q), n(B1, Q, Q, DOUBT), n(D2, 2 * Q, Q), n(E2, 3 * Q, Q),
        n(G2, 4 * Q, 2 * Q, DOUBT), n(D2, 6 * Q, 2 * Q),
    ]),
    "six-eight": ("six-eight time, a doubtful note on the fourth eighth", (6, 8), 0, [
        n(E1, 0, 12), n(G1, 12, 12), n(A1, 24, 12), n(B1, 36, 12, DOUBT), n(A1, 48, 12), n(G1, 60, 12),
        n(E1, 72, 36), n(B1, 108, 36, DOUBT),
    ]),
}


def main() -> int:
    from brasscribe_engine import bass_tab

    first = json.loads((FIRST / "tab.json").read_text())
    request = json.loads((FIRST / "request.json").read_text())
    facts = {k: first[k] for k in ("octave_shift", "octave_source", "octave_notes_moved", "reference_pitch", "tempo_bpm", "key",
                                   "ticks_per_beat", "beat_times", "first_downbeat")}
    answers = {}
    with tempfile.TemporaryDirectory() as tmp:
        for name, (_, (beats, unit), capo, notes) in PROBES.items():
            heard = [{**note, "onset_s": round(note["start"] / Q * 0.6, 3), "offset_s": round((note["start"] + note["dur"]) / Q * 0.6, 3)}
                     for note in sorted(notes, key=lambda x: (x["start"], x["pitch"]))]
            doc = {**facts, "meter": {"beats": beats, "beat_unit": unit}, "notes": heard}
            opts = bass_tab.options({**{k: request[k] for k in bass_tab.DEFAULTS if k in request}, "capo": capo})
            tab = bass_tab.fingered(doc, opts)
            tab["layout"] = "tab"
            for layout, stem in LAYOUTS.items():
                out = Path(tmp) / name / layout
                out.mkdir(parents=True)
                adjusted = bass_tab.export_tab(tab, name, layout, out)
                if layout == "tab":
                    tab["adjusted_notes"] = adjusted
                answers[f"{name}/{stem}.musicxml" if layout != "tab" else f"{name}/tab.musicxml"] = (out / "tab.musicxml").read_text()
            answers[f"{name}/tab.json"] = json.dumps(tab, indent=1)
            print(f"{name}: {len(tab['notes'])} notes, {sum(x['confidence'] < bass_tab.DOUBT for x in tab['notes'])} in doubt, "
                  f"{sum(x['out_of_range'] for x in tab['notes'])} with no place, {tab['adjusted_notes']} moved to the grid")
        for path, text in answers.items():
            if tmp in text or str(HERE.parent.parent) in text:
                print(f"{path} names a directory of this computer", file=sys.stderr)
                return 1
    for path, text in answers.items():
        (OUT / path).parent.mkdir(parents=True, exist_ok=True)
        (OUT / path).write_text(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
