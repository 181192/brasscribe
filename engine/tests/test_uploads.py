"""Uploads: a size cap, audio suffixes only, and metadata that an upload's own name cannot replace."""

import asyncio
import json

from fastapi.testclient import TestClient

from brasscribe_engine.api import create_app
from brasscribe_engine.config import Settings
from brasscribe_engine.guard import BodyLimit

from .test_api import wait

CAP = 4096


def capped(settings) -> TestClient:
    s = Settings(data_dir=settings.data_dir, adapters_dir=settings.adapters_dir, gpu_lock=settings.gpu_lock,
                 max_upload_bytes=CAP)
    return TestClient(create_app(s))


def test_default_cap_is_generous(settings):
    assert settings.max_upload_bytes == 2 << 30


def test_cap_from_the_environment(settings, monkeypatch):
    monkeypatch.setenv("BRASSCRIBE_MAX_UPLOAD_BYTES", "1000")
    assert Settings(data_dir=settings.data_dir).max_upload_bytes == 1000


def test_an_upload_over_the_cap_gets_413(settings):
    with capped(settings) as c:
        for url in ("/v1/audio", "/v1/jobs/upload"):
            r = c.post(url, files={"file": ("big.wav", b"x" * (CAP + 1))}, data={"profile": "test"})
            assert r.status_code == 413, url
        assert c.post("/v1/audio", files={"file": ("small.wav", b"x" * 100)}).status_code == 201
        assert c.get("/v1/jobs").json() == []
    assert len(list(settings.uploads_dir.iterdir())) == 2  # the small upload and its metadata, nothing else



def test_a_declared_length_over_the_cap_is_refused_before_reading():
    async def app(scope, receive, send):
        raise AssertionError("reached the route")

    async def receive():
        raise AssertionError("read the body")

    sent = []

    async def send(message):
        sent.append(message)

    scope = {"type": "http", "method": "POST", "headers": [(b"content-length", str(CAP + 1).encode())]}
    asyncio.run(BodyLimit(app, max_bytes=CAP)(scope, receive, send))
    assert sent[0]["status"] == 413

def test_a_body_without_length_is_cut_off_at_the_cap(settings):
    boundary = "b0undary"
    head = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"big.wav\"\r\n"
            "Content-Type: audio/wav\r\n\r\n").encode()

    def body():
        yield head
        for _ in range(CAP // 512 + 2):
            yield b"x" * 512
        yield f"\r\n--{boundary}--\r\n".encode()

    with capped(settings) as c:
        r = c.post("/v1/audio", content=body(), headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
        assert r.status_code == 413
    assert not [p for p in settings.uploads_dir.iterdir()]


def test_stored_names_keep_audio_suffixes_only(settings, audio):
    with TestClient(create_app(settings)) as c:
        for name, stored in (("take.M4A", ".m4a"), ("clip.mov", ".mov"), ("x.json", ".wav"), ("notes", ".wav"),
                             ("Rehearsal 12.05.2026", ".wav")):
            data = audio.read_bytes() + name.encode()
            ref = c.post("/v1/audio", files={"file": (name, data)}).json()
            assert ref["filename"] == name
            assert (settings.uploads_dir / f"{ref['audio_id']}{stored}").read_bytes() == data
            meta = json.loads((settings.uploads_dir / f"{ref['audio_id']}.meta.json").read_text())
            assert meta["filename"] == name and meta["path"] == f"{ref['audio_id']}{stored}"
            r = c.post("/v1/jobs", json={"audio_id": ref["audio_id"], "profile": "test"})
            assert r.status_code == 202, name


def test_uploads_from_earlier_versions_still_start_jobs(settings, audio):
    up = settings.uploads_dir
    (up / "0123456789abcdef.wav").write_bytes(audio.read_bytes())
    (up / "0123456789abcdef.json").write_text(json.dumps({
        "audio_id": "0123456789abcdef", "sha256": "0" * 64, "filename": "song.wav", "bytes": 15,
        "path": "0123456789abcdef.wav"}))
    (up / "fedcba9876543210.json").write_text(json.dumps({  # metadata that names something that is not an upload
        "audio_id": "fedcba9876543210", "filename": "song.wav", "path": "../companion/devices.json"}))
    (up / "00000000000000aa.json").write_text("not json")
    with TestClient(create_app(settings)) as c:
        r = c.post("/v1/jobs", json={"audio_id": "0123456789abcdef", "profile": "test"})
        assert r.status_code == 202 and wait(c, r.json()["id"])["status"] == "succeeded"
        for audio_id in ("fedcba9876543210", "00000000000000aa"):
            assert c.post("/v1/jobs", json={"audio_id": audio_id, "profile": "test"}).status_code == 404


def test_an_upload_is_written_once_straight_into_the_uploads_folder(settings, audio, monkeypatch):
    from starlette import formparsers

    spooled = []

    class Spool(formparsers.SpooledTemporaryFile):
        def write(self, data):
            spooled.append(len(data))
            return super().write(data)

    monkeypatch.setattr(formparsers, "SpooledTemporaryFile", Spool)
    data = audio.read_bytes() * 1000
    with TestClient(create_app(settings)) as c:
        ref = c.post("/v1/audio", files={"file": ("take.wav", data)}).json()
        assert (settings.uploads_dir / f"{ref['audio_id']}.wav").read_bytes() == data
        assert ref["bytes"] == len(data) and ref["sha256"] == __import__("hashlib").sha256(data).hexdigest()
        r = c.post("/v1/jobs/upload", files={"file": ("take2.wav", data + b"2")},
                   data={"profile": "test", "transpose": "99"})
        assert r.status_code == 422  # refused after the file was read: nothing is left behind
        r = c.post("/v1/jobs/upload", files={"file": ("take3.wav", data + b"3")}, data={"profile": "test"})
        assert r.status_code == 202
        wait(c, r.json()["id"])
    assert spooled == []
    assert not [p.name for p in settings.uploads_dir.iterdir() if p.name.startswith(".")]
    assert len(list(settings.uploads_dir.iterdir())) == 4  # two uploads and their metadata
