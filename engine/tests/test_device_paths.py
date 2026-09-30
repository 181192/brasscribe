"""Paired devices never see the computer's paths or host details; Studio on the computer sees them in full."""

from __future__ import annotations

import json
import shutil

from fastapi.testclient import TestClient

from brasscribe_engine import history
from brasscribe_engine.api import create_app

from .test_api import wait, wait_with


def test_paired_devices_get_paths_relative_to_the_data_folder(settings, audio):
    item = settings.datasets_dir / "demo-set" / "piece1"
    item.mkdir(parents=True)
    shutil.copy(audio, item / "mix.wav")
    (item / "reference.json").write_text("{}")
    history.save(settings, {"passed": True, "suites": [{"suite": "arrange", "status": "pass", "checks": []}]},
                 "arrange", "cached")
    data = str(settings.data_dir.resolve())

    with TestClient(create_app(settings, trust_loopback=False)) as c:
        token = c.post("/v1/pair", json={"code": c.app.state.pairing.code, "device_name": "Phone"}).json()["token"]
        h = {"Authorization": f"Bearer {token}"}
        r = c.post("/v1/jobs/upload", files={"file": ("song.wav", audio.read_bytes())}, data={"profile": "test"},
                   headers=h)
        job = wait_with(c, r.json()["id"], h)
        roundtrip = settings.runs_dir / job["id"] / "roundtrip.json"
        roundtrip.write_text(json.dumps({"status": "pass", "musescore": "/Applications/MuseScore 4.app/mscore"}))

        for url in (f"/v1/jobs/{job['id']}/manifest", f"/v1/jobs/{job['id']}/artifacts/manifest.json"):
            m = c.get(url, headers=h).json()
            assert m["input"]["path"] == f"uploads/{job['audio_id']}.wav", url
            assert not {"git", "host", "out"} & set(m), url
        assert c.get(f"/v1/jobs/{job['id']}/roundtrip", headers=h).json()["musescore"] == "mscore"
        assert c.get("/v1/sources", headers=h).json()[0]["path"] == "eval/demo-set/piece1/mix.wav"
        ds = {d["name"]: d for d in c.get("/v1/registry/datasets", headers=h).json()}
        assert ds["demo-set"]["path"] == "eval/demo-set"
        assert c.get("/v1/suites/history", headers=h).json()[0]["manifest"].startswith("bench/history/")
        seen = json.dumps([c.get(u, headers=h).json() for u in (
            f"/v1/jobs/{job['id']}/manifest", "/v1/sources", "/v1/registry/datasets", "/v1/suites/history")])
        assert data not in seen

    with TestClient(create_app(settings)) as c:  # Studio, on the computer
        m = c.get(f"/v1/jobs/{job['id']}/manifest").json()
        assert m["input"]["path"].startswith(data) and "host" in m and "git" in m
        assert c.get(f"/v1/jobs/{job['id']}/artifacts/manifest.json").json()["host"] == m["host"]
        assert c.get("/v1/sources").json()[0]["path"].startswith(data)
        assert c.get(f"/v1/jobs/{job['id']}/roundtrip").json()["musescore"].startswith("/Applications/")
        assert wait(c, job["id"])["status"] == "succeeded"
