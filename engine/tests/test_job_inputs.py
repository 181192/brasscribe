"""Jobs read audio from the engine's own audio folders only (uploads, captures, eval sets)."""

import json
import shutil

from fastapi.testclient import TestClient

from brasscribe_engine.api import create_app

from .test_api import wait
from .test_companion import bearer, lan, pair


def other_files(settings, audio):
    """A text file and an audio file in the data folder but outside the audio folders, plus a capture."""
    (settings.data_dir / "notes.txt").write_text("not audio")
    (settings.data_dir / "companion").mkdir(exist_ok=True)
    shutil.copy(audio, settings.data_dir / "companion" / "other.wav")
    cap = settings.data_dir / "captures"
    cap.mkdir()
    shutil.copy(audio, cap / "take.wav")
    (cap / "notes.txt").write_text("not audio")


def test_a_paired_device_cannot_start_a_job_from_a_path(settings, audio):
    other_files(settings, audio)
    with lan(settings) as c:
        auth = bearer(pair(c)["token"])
        for path in ("notes.txt", "captures/take.wav"):
            r = c.post("/v1/jobs", json={"path": path, "profile": "test"}, headers=auth)
            assert r.status_code == 403, path
        assert c.get("/v1/jobs", headers=auth).json() == []
        # what the apps use still works
        ref = c.post("/v1/audio", files={"file": ("song.wav", audio.read_bytes())}, headers=auth).json()
        r = c.post("/v1/jobs", json={"audio_id": ref["audio_id"], "profile": "test"}, headers=auth)
        assert r.status_code == 202
        assert c.post("/v1/jobs", json={"source_id": "capture:take.wav", "profile": "test"}, headers=auth).status_code == 202


def test_paths_must_be_audio_in_the_audio_folders(settings, audio):
    other_files(settings, audio)
    with TestClient(create_app(settings)) as c:
        for path in ("notes.txt", "companion/other.wav", "captures/notes.txt", "captures/../notes.txt",
                     str(settings.data_dir / "notes.txt"), str(settings.data_dir / "captures" / "take.wav"),
                     "captures\\take.wav", "captures/missing.wav"):
            assert c.post("/v1/jobs", json={"path": path, "profile": "test"}).status_code == 404, path
        r = c.post("/v1/jobs", json={"path": "captures/take.wav", "profile": "test"})
        assert r.status_code == 202
        job = wait(c, r.json()["id"])
        assert c.get(f"/v1/jobs/{job['id']}/input").content == audio.read_bytes()


def run_with_input(settings, audio, path) -> str:
    """A finished run from an earlier session whose manifest names `path` as its input."""
    with TestClient(create_app(settings)) as c:
        r = c.post("/v1/jobs/upload", files={"file": ("song.wav", audio.read_bytes())}, data={"profile": "test"})
        job = wait(c, r.json()["id"])
    manifest = settings.runs_dir / job["id"] / "manifest.json"
    m = json.loads(manifest.read_text())
    manifest.write_text(json.dumps({**m, "input": {**m["input"], "path": str(path)}}))
    return job["id"]


def test_a_paired_device_gets_input_only_from_the_audio_folders(settings, audio):
    other_files(settings, audio)
    for elsewhere in (settings.data_dir / "notes.txt", settings.data_dir / "companion" / "other.wav"):
        job_id = run_with_input(settings, audio, elsewhere)
        with lan(settings) as c:
            auth = bearer(pair(c)["token"])
            assert c.get(f"/v1/jobs/{job_id}/input", headers=auth).status_code == 404
            assert c.post(f"/v1/jobs/{job_id}/rerun", headers=auth).status_code == 409


def test_the_owner_gets_audio_input_from_elsewhere_but_nothing_else(settings, audio):
    """Runs started on the computer (`brasscribe run <file>`) keep A/B listening and re-runs in Studio."""
    other_files(settings, audio)
    job_id = run_with_input(settings, audio, settings.data_dir / "companion" / "other.wav")
    with TestClient(create_app(settings)) as c:
        assert c.get(f"/v1/jobs/{job_id}/input").content == audio.read_bytes()
        assert c.post(f"/v1/jobs/{job_id}/rerun").status_code == 202
    job_id = run_with_input(settings, audio, settings.data_dir / "notes.txt")
    with TestClient(create_app(settings)) as c:
        assert c.get(f"/v1/jobs/{job_id}/input").status_code == 404
        assert c.post(f"/v1/jobs/{job_id}/rerun").status_code == 409
