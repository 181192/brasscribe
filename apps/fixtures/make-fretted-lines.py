#!/usr/bin/env python3
"""Record the guitar and ukulele tab fixtures: what the engine answers for a `tab` job on a short take of each.

Both takes are written here (eight bars each, made up for these fixtures: strummed open chords with a line
between them) and synthesized as plucked strings: no recording of anyone is involved. The engine then does
what it does for a player's take of the instrument alone: Beat This!, Basic Pitch and SwiftF0 on the audio,
the notes on the beat grid, and a string and a fret for every note from the Rust core. Each job runs through
the engine's API in this process, in a data directory that is thrown away, and the answers are saved as the
API gave them.

    pixi run python apps/fixtures/make-fretted-lines.py

Needs the model adapters and their weights (`models/`), and the core's command line
(`cargo build --release -p brasscribe-cli` in core/, or BRASSCRIBE_CORE_CLI).

Writes apps/fixtures/guitar-line/ and apps/fixtures/ukulele-line/, each with:
    request.json      the body of POST /v1/jobs that the engine accepted
    job.json          GET /v1/jobs/{id}
    tab.json          GET /v1/jobs/{id}/tab
    tab.musicxml      GET /v1/jobs/{id}/musicxml
    composition.json  GET /v1/jobs/{id}/composition
    tab.txt, tab-instructions.en.txt, tab-instructions.nb.txt
                      GET /v1/jobs/{id}/artifacts/{name}: the tab as text and as playing instructions
The fixtures keep what the engine answered, also where it differs from what is written here.
MuseScore is left out of the run, so there is no tab.pdf or tab.mid, as on a computer without it.
What differs from run to run or from computer to computer is made fixed in job.json: the job's id, its
times, each stage's seconds and the device each stage ran on.
Only tests read these folders; no app build bundles them.
"""
import json
import os
import sys
import tempfile
import time
import wave
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
BPM = 100.0
RATE = 22050
CREATED = 1767225600.0  # 2026-01-01T00:00:00Z
STRUM = 0.012  # seconds between the strings of a strum

# Guitar, standard tuning: open chords, lowest string first, and single notes.
EM = (40, 47, 52, 55, 59, 64)
G = (43, 47, 50, 55, 59, 67)
D = (50, 57, 62, 66)
C = (48, 52, 55, 60, 64)
AM = (45, 52, 57, 60, 64)
E3, G3, A3, B3 = 52, 55, 57, 59
# (pitches, beats): eight bars of 4/4 in E minor.
GUITAR = [
    (EM, 2), (EM, 2),
    (G, 2), (G, 2),
    ((E3,), 1), ((G3,), 1), ((A3,), 1), ((B3,), 1),
    (D, 2), ((A3,), 1), ((B3,), 1),
    (C, 2), (C, 2),
    ((B3,), 1), ((A3,), 1), ((G3,), 1), ((E3,), 1),
    (AM, 2), (D, 2),
    (EM, 4),
]

# Ukulele, high G (G4 C4 E4 A4): open chords as they are fingered, and single notes.
UC = (67, 60, 64, 72)   # 0003
UF = (69, 60, 65, 69)   # 2010
UG = (67, 62, 67, 71)   # 0232: the G sounds on two strings
UAM = (69, 60, 64, 69)  # 2000
C4, D4, E4, G4, A4 = 60, 62, 64, 67, 69
# (pitches, beats): eight bars of 4/4 in C major.
UKULELE = [
    (UC, 2), (UC, 2),
    (UF, 2), (UF, 2),
    ((E4,), 1), ((G4,), 1), ((A4,), 1), ((G4,), 1),
    (UG, 2), (UG, 2),
    (UAM, 2), (UAM, 2),
    ((A4,), 1), ((G4,), 1), ((E4,), 1), ((D4,), 1),
    (UF, 2), (UG, 2),
    (UC, 4),
]


def request(title: str, instrument: str, tuning: str) -> dict:
    """The job as the Android client asks for it: the tab options it names, and the band options it always sends."""
    return {"profile": "tab", "render_audio": True, "allow_heavy": True, "title": title,
            "lineup": "full", "difficulty": "faithful", "muscriptor": True,
            "instrument": instrument, "tuning": tuning, "capo": 0, "recording": "instrument", "octave": "auto",
            "layout": "tab"}


TAKES = {
    "guitar-line": (GUITAR, request("Guitar line", "guitar-6", "standard")),
    "ukulele-line": (UKULELE, request("Ukulele line", "ukulele", "high-g")),
}


def take(line: list) -> bytes:
    """The take as 16-bit mono WAV: each note a plucked string, roughly (eight partials, decaying); the strings
    of a chord a little after one another, as a strum."""
    beat = 60 / BPM
    total = sum(beats for _, beats in line)
    audio = np.zeros(int((total + 2) * beat * RATE))
    at = beat  # one beat of silence first
    played = 0.0
    for pitches, beats in line:
        level = (0.4 if played % 4 == 0 else 0.25) / max(1, len(pitches)) ** 0.5  # the first beat of each bar is played harder
        played += beats
        for i, pitch in enumerate(pitches):
            t = np.arange(int(0.9 * beats * beat * RATE)) / RATE
            f = 440 * 2 ** ((pitch - 69) / 12)
            tone = sum(np.sin(2 * np.pi * f * k * t) / k for k in range(1, 9)) * np.exp(-3 * t)
            attack = int(0.005 * RATE)
            tone[:attack] *= np.linspace(0, 1, attack)
            start = int((at + i * STRUM) * RATE)
            audio[start:start + len(tone)] += level * tone[:len(audio) - start]
        at += beats * beat
    pcm = (np.clip(audio, -1, 1) * 32767).astype("<i2")
    path = Path(tempfile.mkstemp(suffix=".wav")[1])
    try:
        with wave.open(str(path), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(RATE)
            w.writeframes(pcm.tobytes())
        return path.read_bytes()
    finally:
        path.unlink()


def fixed(job: dict, job_id: str) -> dict:
    """The job without what differs from run to run and from computer to computer: its id, its times, each
    stage's seconds and the device each stage ran on."""
    job = {**job, "id": job_id, "created": CREATED, "started": CREATED, "finished": CREATED + len(job["stages"]),
           "previous_run_id": None, "device_name": None}
    for stage in job["stages"]:
        for key in ("seconds", "queue_wait_s", "run_s"):
            if stage.get(key) is not None:
                stage[key] = 1.0 if key != "queue_wait_s" else 0.0
        stage["device"] = None
    return job


def record(c, name: str, line: list, options: dict) -> dict[str, str] | None:
    up = c.post("/v1/audio", files={"file": (f"{name}.wav", take(line), "audio/wav")})
    if up.status_code != 201:
        print(f"the engine refused the upload: {up.status_code} {up.text}", file=sys.stderr)
        return None
    body = {"audio_id": up.json()["audio_id"], **options}
    r = c.post("/v1/jobs", json=body)
    if r.status_code != 202:
        print(f"the engine refused the job: {r.status_code} {r.text}", file=sys.stderr)
        return None
    job = r.json()
    while job["status"] not in ("succeeded", "failed", "cancelled"):
        time.sleep(0.5)
        job = c.get(f"/v1/jobs/{job['id']}").json()
    if job["status"] != "succeeded":
        print(f"the job {job['status']}: {job.get('error')}", file=sys.stderr)
        return None
    return {"tab.json": c.get(f"/v1/jobs/{job['id']}/tab").text,
            "tab.musicxml": c.get(f"/v1/jobs/{job['id']}/musicxml").text,
            "composition.json": c.get(f"/v1/jobs/{job['id']}/composition").text,
            **{text: c.get(f"/v1/jobs/{job['id']}/artifacts/{text}").text
               for text in ("tab.txt", "tab-instructions.en.txt", "tab-instructions.nb.txt")},
            "job.json": json.dumps(fixed(job, name), indent=1) + "\n",
            "request.json": json.dumps(body, indent=1) + "\n"}


def main() -> int:
    recorded = {}
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["BRASSCRIBE_DATA"] = str(Path(tmp) / "data")
        from fastapi.testclient import TestClient

        from brasscribe_engine.api import create_app
        from brasscribe_engine.config import Settings
        from brasscribe_music import musescore

        models = Settings(data_dir=HERE.parent.parent / "data").models_dir
        settings = Settings(models_override=models)
        settings.ensure()
        musescore.binary = lambda: None  # the same fixture with and without MuseScore installed
        with TestClient(create_app(settings), base_url="http://127.0.0.1") as c:
            for name, (line, options) in TAKES.items():
                answers = record(c, name, line, options)
                if answers is None:
                    return 1
                recorded[name] = answers
    for name, answers in recorded.items():
        for file, text in answers.items():
            if tmp in text or str(Path.home()) in text:
                print(f"{name}/{file} names a directory of this computer", file=sys.stderr)
                return 1
        out = HERE / name
        out.mkdir(exist_ok=True)
        for file, text in answers.items():
            (out / file).write_text(text, encoding="utf-8")
        tab = json.loads(answers["tab.json"])
        print(f"{name}: {len(tab['notes'])} notes on {tab['preset']}, {tab['key']['name']}, {tab['tempo_bpm']} BPM, "
              f"{sum(n['confidence'] < 0.4 for n in tab['notes'])} in doubt, {tab.get('unplayable_dropped', 0)} left out as "
              f"unplayable, {tab.get('doubled_notes', 0)} doubled")
    return 0


if __name__ == "__main__":
    sys.exit(main())
