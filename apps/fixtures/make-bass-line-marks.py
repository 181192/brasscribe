#!/usr/bin/env python3
"""Write the second bass tab fixture: the bass line with notes to check.

The engine heard every note of the synthesized bass line well (apps/fixtures/bass-line), so that fixture
has no "?" and no note without a place. This one starts from what the engine heard there and changes
three notes by hand, then lets the engine place and write the line as its arrange stage does (the same
functions, with the Rust core): no audio and no models are involved.

    pixi run python apps/fixtures/make-bass-line-marks.py

Needs apps/fixtures/bass-line (make-bass-line.py) and the core's command line
(`cargo build --release -p scribe-cli` in core/, or SCRIBE_CORE_CLI).

The changes (CHANGES below), by the notes' places in tab.json:
    5   heard with little confidence: a doubtful note, marked "?"
    12  a D below the lowest string: a note with no place, marked "!"
    28  the last note starts an eighth late and is doubtful: it crosses the beat and the bar line, so it is
        written as tied pieces

Writes apps/fixtures/bass-line-marks/: tab.json, tab.musicxml, composition.json, and job.json and
request.json as the first fixture has them (the same job). The job asked for the tab staff alone; the
same notes in the other two layouts are written beside it as tab-and-notation.musicxml and
notation.musicxml (what tab.musicxml is for a job with that layout). Only tests read this folder.
"""
import json
import shutil
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
FIRST = HERE / "bass-line"
OUT = HERE / "bass-line-marks"
TITLE = "Bass line"
D1 = 26
CHANGES = {
    5: {"confidence": 0.31},
    12: {"pitch": D1},
    28: {"start": 684, "confidence": 0.22},
}
OTHER_LAYOUTS = ("tab-and-notation", "notation")
HEARD = ("pitch", "start", "dur", "confidence", "onset_s", "offset_s")


def main() -> int:
    from brasscribe_engine import bass_tab

    first = json.loads((FIRST / "tab.json").read_text())
    request = json.loads((FIRST / "request.json").read_text())
    notes = [{**{k: n[k] for k in HEARD}, **CHANGES.get(i, {})} for i, n in enumerate(first["notes"])]
    doc = {**{k: first[k] for k in ("octave_shift", "octave_source", "octave_notes_moved", "reference_pitch", "tempo_bpm", "key",
                                    "meter", "ticks_per_beat", "beat_times", "first_downbeat")}, "notes": notes}
    opts = bass_tab.options({k: request[k] for k in bass_tab.DEFAULTS if k in request})
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp)
        tab = bass_tab.fingered(doc, opts)
        tab["layout"] = request["layout"]
        tab["adjusted_notes"] = bass_tab.export_tab(tab, TITLE, request["layout"], out)
        bass_tab.composition(tab, TITLE).to_json(out / "composition.json")
        answers = {"tab.json": json.dumps(tab, indent=1), "tab.musicxml": (out / "tab.musicxml").read_text(),
                   "composition.json": (out / "composition.json").read_text()}
        for layout in OTHER_LAYOUTS:
            other = out / layout
            other.mkdir()
            bass_tab.export_tab(tab, TITLE, layout, other)
            answers[f"{layout}.musicxml"] = (other / "tab.musicxml").read_text()
        for name, text in answers.items():
            if tmp in text or str(HERE.parent.parent) in text:
                print(f"{name} names a directory of this computer", file=sys.stderr)
                return 1
    OUT.mkdir(exist_ok=True)
    for name, text in answers.items():
        (OUT / name).write_text(text)
    for name in ("job.json", "request.json"):
        shutil.copyfile(FIRST / name, OUT / name)
    print(f"{OUT.name}: {len(tab['notes'])} notes on {tab['preset']}, "
          f"{sum(n['confidence'] < bass_tab.DOUBT for n in tab['notes'])} in doubt, "
          f"{sum(n['out_of_range'] for n in tab['notes'])} with no place, {tab['adjusted_notes']} moved to the grid")
    return 0


if __name__ == "__main__":
    sys.exit(main())
