import json
import shutil

from fastapi.testclient import TestClient

from brasscribe_engine import history
from brasscribe_engine.api import create_app

from .test_api import wait


def run_job(c, audio):
    r = c.post("/v1/jobs/upload", files={"file": ("song.wav", audio.read_bytes())}, data={"profile": "test"})
    return wait(c, r.json()["id"])


def test_stages_input_and_rerun(settings, audio):
    with TestClient(create_app(settings)) as c:
        job = run_job(c, audio)
        stages = {s["stage"]: s for s in c.get(f"/v1/jobs/{job['id']}/stages").json()}
        f = stages["transcribe.mix.swift-f0"]["files"][0]
        assert f["name"] == "mix-sw.mid" and f["media_type"] == "audio/midi" and f["sha256"]
        assert c.get(f["url"]).content == b"RIFF-fake-audioswift-f0"
        assert c.get(f"/v1/jobs/{job['id']}/stages/arrange/files/../../manifest.json").status_code == 404
        assert c.get(f"/v1/jobs/{job['id']}/input").content == audio.read_bytes()
        r = c.post(f"/v1/jobs/{job['id']}/rerun", json={"cold": ["all"]})
        assert r.status_code == 202 and r.json()["previous_run_id"] == job["id"]
        again = wait(c, r.json()["id"])
        assert all(s["status"] == "ran" for s in again["stages"])
        cmp = c.get(f"/v1/jobs/{again['id']}/compare", params={"job": job["id"]}).json()
        assert cmp["composition_identical"] is True


def test_references_and_compare(settings, audio):
    ref = settings.golden_dir / "demo"
    ref.mkdir(parents=True)
    with TestClient(create_app(settings)) as c:
        job = run_job(c, audio)
        out = settings.runs_dir / job["id"] / "outputs"
        for f in ("composition.json", "brass-band.musicxml"):
            shutil.copy(out / f, ref / f)
        refs = c.get("/v1/references").json()
        assert refs[0]["name"] == "demo" and {f["name"] for f in refs[0]["files"]} == {"composition.json", "brass-band.musicxml"}
        assert c.get("/v1/references/demo/files/composition.json").status_code == 200
        r = c.get(f"/v1/jobs/{job['id']}/compare", params={"reference": "demo"}).json()
        assert r["ok"] is True
        assert c.get(f"/v1/jobs/{job['id']}/compare").status_code == 422
        assert c.get(f"/v1/jobs/{job['id']}/roundtrip").json()["status"] == "not_run"


def test_sources_and_job_from_source(settings, audio):
    item = settings.datasets_dir / "demo-set" / "piece1"
    item.mkdir(parents=True)
    shutil.copy(audio, item / "mix.wav")
    (item / "reference.json").write_text("{}")
    with TestClient(create_app(settings)) as c:
        src = c.get("/v1/sources").json()
        assert src[0]["id"] == "dataset:demo-set/piece1" and src[0]["kind"] == "dataset"
        r = c.post("/v1/jobs", json={"source_id": src[0]["id"], "profile": "test"})
        assert r.status_code == 202 and r.json()["title"] == "Piece1 test"
        assert wait(c, r.json()["id"])["status"] == "succeeded"
        assert c.post("/v1/jobs", json={"path": "/etc/hosts", "profile": "test"}).status_code == 404
        assert c.post("/v1/jobs", json={"profile": "test"}).status_code == 422
        ds = {d["name"]: d for d in c.get("/v1/registry/datasets").json()}
        assert ds["demo-set"]["items"] == 1 and ds["choralebricks-brass4"]["present"] is False


def test_registry_history_and_reports(settings, monkeypatch, tmp_path):
    monkeypatch.setenv("BRASSCRIBE_PARITY_REPORTS", str(tmp_path / "parity"))
    (tmp_path / "parity").mkdir()
    (tmp_path / "parity" / "swift-f0-coreml.json").write_text(json.dumps({"model": "swift-f0", "f1": 0.99}))
    history.save(settings, {"passed": True, "suites": [{"suite": "arrange", "status": "pass", "metrics": {"x": 1.0},
                                                          "checks": [], "seconds": 0.1}]}, "arrange", "cached")
    with TestClient(create_app(settings)) as c:
        adapters = {a["name"]: a for a in c.get("/v1/registry/adapters").json()}
        assert adapters["swift-f0"]["version"] == "9.9.9" and adapters["muscriptor"]["licence"] == "CC BY-NC 4.0"
        h = c.get("/v1/suites/history", params={"suite": "arrange"}).json()
        assert h[0]["suite"] == "arrange" and h[0]["metrics"] == {"x": 1.0} and h[0]["time"] > 0
        assert c.get("/v1/parity").json() == [{"model": "swift-f0", "f1": 0.99, "_file": "swift-f0-coreml.json"}]
        assert c.get("/v1/conformance").json() == []
