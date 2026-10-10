#!/usr/bin/env python3
"""Record the bass tab fixture: what the engine answers for a `bass-tab` job on a short bass line.

The line is written here (eight bars, made up for this fixture) and synthesized as plucked strings: no
recording of anyone is involved. The engine then does what it does for a player's take of the bass
alone: Beat This!, Basic Pitch and SwiftF0 on the audio, the notes on the beat grid, and a string and
a fret for every note from the Rust core. The job runs through the engine's API in this process, in a
data directory that is thrown away, and the answers are saved as the API gave them.

    pixi run python apps/fixtures/make-bass-line.py

Needs the model adapters and their weights (`models/`), and the core's command line
(`cargo build --release -p scribe-cli` in core/, or SCRIBE_CORE_CLI).

Writes apps/fixtures/bass-line/:
    request.json      the body of POST /v1/jobs that the engine accepted
    job.json          GET /v1/jobs/{id}
    tab.json          GET /v1/jobs/{id}/tab
    tab.musicxml      GET /v1/jobs/{id}/musicxml
    composition.json  GET /v1/jobs/{id}/composition
    tab.txt, tab-instructions.en.txt, tab-instructions.nb.txt
                      GET /v1/jobs/{id}/artifacts/{name}: the tab as text and as playing instructions
The line is written in 4/4; the beat tracker hears this synthesized take in 2/4, and the fixture keeps
what the engine answered.
MuseScore is left out of the run, so there is no tab.pdf or tab.mid, as on a computer without it.
What differs from run to run is made fixed in job.json: the job's id, its times and each stage's seconds.
Only tests read this folder; no app build bundles it.
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
OUT = HERE / "bass-line"
TITLE = "Bass line"
BPM = 100.0
RATE = 22050
JOB_ID = "bass-line"
CREATED = 1767225600.0  # 2026-01-01T00:00:00Z

E1, G1, A1, B1, C2, D2, E2, G2 = 28, 31, 33, 35, 36, 38, 40, 43
R = None  # a rest
TEXTS = ("tab.txt", "tab-instructions.en.txt", "tab-instructions.nb.txt")  # the tab as text and as playing instructions
# (pitch, beats): eight bars of 4/4 in E minor.
LINE = [
    (E1, 1), (E1, 1), (G1, 1), (A1, 1),
    (B1, 1), (B1, 1), (A1, 1), (G1, 1),
    (E1, 2), (G1, 1), (B1, 1),
    (E2, 1), (D2, 1), (B1, 1), (A1, 1),
    (C2, 1), (C2, 1), (E2, 1), (G2, 1),
    (D2, 1), (D2, 1), (B1, 1), (A1, 1),
    (G1, 0.5), (A1, 0.5), (B1, 1), (D2, 1), (B1, 1),
    (E1, 2), (R, 2),
]
# The job as the Android client asks for it: every bass-tab option named, and the band options it always sends.
REQUEST = {"profile": "bass-tab", "render_audio": True, "allow_heavy": True, "title": TITLE,
           "lineup": "full", "difficulty": "faithful", "muscriptor": True,
           "instrument": "bass-4", "tuning": "standard", "capo": 0, "style": "as-played", "recording": "instrument",
           "octave": "auto", "layout": "tab"}


def take() -> bytes:
    """The line as 16-bit mono WAV: each note a plucked string, roughly (eight partials, decaying)."""
    beat = 60 / BPM
    total = sum(beats for _, beats in LINE)
    audio = np.zeros(int((total + 2) * beat * RATE))
    at = beat  # one beat of silence first
    played = 0.0
    for pitch, beats in LINE:
        level = 0.4 if played % 4 == 0 else 0.2  # the first beat of each bar is played harder
        played += beats
        if pitch is not None:
            t = np.arange(int(0.9 * beats * beat * RATE)) / RATE
            f = 440 * 2 ** ((pitch - 69) / 12)
            tone = sum(np.sin(2 * np.pi * f * k * t) / k for k in range(1, 9)) * np.exp(-3 * t)
            attack = int(0.005 * RATE)
            tone[:attack] *= np.linspace(0, 1, attack)
            start = int(at * RATE)
            audio[start:start + len(tone)] += level * tone
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


def fixed(job: dict) -> dict:
    """The job without what differs from run to run: its id, its times and each stage's seconds."""
    job = {**job, "id": JOB_ID, "created": CREATED, "started": CREATED, "finished": CREATED + len(job["stages"]),
           "previous_run_id": None, "device_name": None}
    for stage in job["stages"]:
        for key in ("seconds", "queue_wait_s", "run_s"):
            if stage.get(key) is not None:
                stage[key] = 1.0 if key != "queue_wait_s" else 0.0
    return job


def main() -> int:
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
            up = c.post("/v1/audio", files={"file": ("bass-line.wav", take(), "audio/wav")})
            if up.status_code != 201:
                print(f"the engine refused the upload: {up.status_code} {up.text}", file=sys.stderr)
                return 1
            audio_id = up.json()["audio_id"]
            request = {"audio_id": audio_id, **REQUEST}
            r = c.post("/v1/jobs", json=request)
            if r.status_code != 202:
                print(f"the engine refused the job: {r.status_code} {r.text}", file=sys.stderr)
                return 1
            job = r.json()
            while job["status"] not in ("succeeded", "failed", "cancelled"):
                time.sleep(0.5)
                job = c.get(f"/v1/jobs/{job['id']}").json()
            if job["status"] != "succeeded":
                print(f"the job {job['status']}: {job.get('error')}", file=sys.stderr)
                return 1
            answers = {"tab.json": c.get(f"/v1/jobs/{job['id']}/tab").text,
                       "tab.musicxml": c.get(f"/v1/jobs/{job['id']}/musicxml").text,
                       "composition.json": c.get(f"/v1/jobs/{job['id']}/composition").text,
                       **{name: c.get(f"/v1/jobs/{job['id']}/artifacts/{name}").text for name in TEXTS},
                       "job.json": json.dumps(fixed(job), indent=1) + "\n",
                       "request.json": json.dumps(request, indent=1) + "\n"}
    OUT.mkdir(exist_ok=True)
    for name, text in answers.items():
        if tmp in text:
            print(f"{name} names the temporary directory", file=sys.stderr)
            return 1
        (OUT / name).write_text(text, encoding="utf-8")
    tab = json.loads(answers["tab.json"])
    print(f"{OUT.name}: {len(tab['notes'])} notes on {tab['preset']}, {tab['key']['name']}, {tab['tempo_bpm']} BPM, "
          f"{sum(n['confidence'] < 0.4 for n in tab['notes'])} in doubt")
    return 0


if __name__ == "__main__":
    sys.exit(main())
