"""Make the data of the figures on Fretscribe's front page, in site/fretscribe/figures/.

tab-demo.json is the tab viewer's. The notes are the ones the engine wrote for apps/fixtures/guitar-line (a made-up
line, synthesized, then heard by the engine). For every tuning the viewer offers, the string and fret of each
note, its other places and the notes with no place are asked of the core's own solver (`scribe-core fret`), so the
page shows what the app would show and nothing is worked out in the browser. The run fails unless the solver gives
the fixture's own places back for the fixture's own tuning.

guitar-line-sound.json is the loudness of the take the engine heard, fifty times a second: the fixture's own
script synthesizes the take again, and the run fails unless it is, byte for byte, the audio the fixture's job
was given (the job's audio id is the start of its SHA-256).

    cargo build --release -p scribe-cli   (in core/, or set SCRIBE_CORE_CLI)
    uv run --with numpy python site/fretscribe/make_demo.py
"""

import hashlib
import importlib.util
import io
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "apps" / "fixtures" / "guitar-line"
OUT = ROOT / "site" / "fretscribe" / "figures" / "tab-demo.json"
PRESETS = ["guitar-standard", "guitar-drop-d", "guitar-open-g", "guitar-dadgad"]
CAPOS = [0]  # a capo takes the low notes off this line's neck in every tuning, so the viewer offers none


def module(path: Path):
    spec = importlib.util.spec_from_file_location(path.stem.replace("-", "_"), path)
    made = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(made)
    return made


def sound() -> dict | None:
    """The take's loudness, from the audio the fixture's own script makes: its peak in every fiftieth of a second."""
    import wave

    import numpy as np

    lines = module(ROOT / "apps" / "fixtures" / "make-fretted-lines.py")
    audio = lines.take(lines.GUITAR)
    heard = json.loads((FIXTURE / "request.json").read_text())["audio_id"]
    if hashlib.sha256(audio).hexdigest()[:len(heard)] != heard:
        print("the take made here is not the audio the fixture's job was given", file=sys.stderr)
        return None
    with wave.open(io.BytesIO(audio)) as w:
        rate = w.getframerate()
        samples = np.abs(np.frombuffer(w.readframes(w.getnframes()), dtype="<i2").astype(float)) / 32768
    step = rate // 50
    peaks = [round(float(samples[i:i + step].max()), 3) for i in range(0, len(samples), step)]
    top = max(peaks)
    return {"source": "apps/fixtures/make-fretted-lines.py take(GUITAR), the audio of apps/fixtures/guitar-line's job",
            "audio_id": heard, "per_second": 50, "peak": [round(p / top, 3) for p in peaks]}


def main() -> int:
    cli = Path(os.environ.get("SCRIBE_CORE_CLI", ROOT / "core" / "target" / "release" / "scribe-core"))
    if not cli.is_file():
        print("scribe-core is missing: cargo build --release -p scribe-cli in core/", file=sys.stderr)
        return 1
    tab = json.loads((FIXTURE / "tab.json").read_text())
    marks = module(ROOT / "site" / "shared" / "figures.py").doubtful((FIXTURE / "tab.musicxml").read_text())
    heard = sound()
    if heard is None:
        return 1
    (OUT.parent / "guitar-line-sound.json").write_text(json.dumps(heard, separators=(",", ":")) + "\n")
    notes = [{k: n[k] for k in ("pitch", "start", "dur")} for n in tab["notes"]]
    variants = {}
    with tempfile.TemporaryDirectory() as tmp:
        for preset in PRESETS:
            for capo in CAPOS:
                request = {"instrument": {"preset": preset, "capo": capo}, "notes": notes,
                           "options": {"style": tab["style"], "tempo_bpm": tab["tempo_bpm"]}}
                (Path(tmp) / "request.json").write_text(json.dumps(request))
                subprocess.run([str(cli), "fret", "--request", f"{tmp}/request.json", "--out", f"{tmp}/out.json"], check=True)
                answer = json.loads((Path(tmp) / "out.json").read_text())
                places = answer["fingering"]["notes"]
                if preset == tab["preset"] and capo == tab["instrument"]["capo"]:
                    same = all((p["string"], p["fret"], p["out_of_range"]) == (n["string"], n["fret"], n["out_of_range"])
                               for p, n in zip(places, tab["notes"]))
                    if not same:
                        print("the solver no longer gives the fixture's places: make the fixture again first", file=sys.stderr)
                        return 1
                variants[f"{preset}/{capo}"] = {
                    "tuning": answer["instrument"]["tuning"]["name"],
                    "open": [s["open_pitch"] for s in answer["instrument"]["tuning"]["strings"]],
                    # per note: string, fret, 1 when it has no place, then its other places as string, fret pairs
                    "places": [[p["string"], p["fret"], int(p["out_of_range"]), *[v for a in p["alternatives"] for v in (a["string"], a["fret"])]]
                               for p in places],
                }
    demo = {
        "source": "apps/fixtures/guitar-line, places from scribe-core fret (site/fretscribe/make_demo.py)",
        "title": json.loads((FIXTURE / "job.json").read_text())["title"],
        "ticks_per_beat": tab["ticks_per_beat"], "meter": tab["meter"], "tempo_bpm": tab["tempo_bpm"],
        "presets": PRESETS, "capos": CAPOS, "default": f'{tab["preset"]}/{tab["instrument"]["capo"]}',
        "notes": [[n["pitch"], n["start"], n["dur"], int(i in marks)] for i, n in enumerate(tab["notes"])],
        "variants": variants,
    }
    OUT.write_text(json.dumps(demo, separators=(",", ":"), ensure_ascii=False) + "\n")
    for key, v in variants.items():
        print(f"{key:22} {v['tuning']:9} notes with no place: {sum(p[2] for p in v['places'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
