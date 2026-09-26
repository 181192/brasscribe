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


def test_evidence_compares_transcribers_at_uncertain_notes(settings, audio):
    import pretty_midi

    with TestClient(create_app(settings)) as c:
        job = run_job(c, audio)
        run_dir = settings.runs_dir / job["id"]
        comp = json.loads((run_dir / "outputs" / "composition.json").read_text())
        comp["voices"] = [{"id": "melody", "role": "melody", "notes": [
            {"pitch": 67, "start": 0, "dur": 24, "confidence": 0.5, "sources": ["melody"], "onset_s": 1.0},
            {"pitch": 69, "start": 24, "dur": 24, "confidence": 0.9, "sources": ["melody"], "onset_s": 2.0}]}]
        (run_dir / "outputs" / "composition.json").write_text(json.dumps(comp))
        for stage, name, pitches in (("transcribe.mix.swift-f0", "mix-sw.mid", [67]),
                                     ("transcribe.mix.basic-pitch", "mix-bp.mid", [48, 69])):
            pm = pretty_midi.PrettyMIDI()
            inst = pretty_midi.Instrument(0)
            inst.notes = [pretty_midi.Note(80, p, 1.02, 1.5) for p in pitches]
            pm.instruments.append(inst)
            pm.write(str(run_dir / "stages" / stage / name))
        e = c.get(f"/v1/jobs/{job['id']}/evidence").json()
        assert [m["model"] for m in e["models"]] == ["basic-pitch", "swift-f0"]
        note = e["notes"][0]
        assert len(e["notes"]) == 1 and note["confidence"] == 0.5 and note["voice"] == "melody"
        heard = {m["model"]: (m["pitch"], m["agrees"]) for m in note["models"]}
        assert heard == {"swift-f0": (67, True), "basic-pitch": (69, False)}
        assert c.get("/v1/jobs/nope/evidence").status_code == 404


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


def test_rename_run_updates_title_everywhere(settings, audio):
    with TestClient(create_app(settings)) as c:
        job = run_job(c, audio)
        r = c.patch(f"/v1/runs/{job['id']}", json={"title": "Rehearsal & run"})
        assert r.status_code == 200 and r.json()["title"] == "Rehearsal & run"
        assert c.get(f"/v1/jobs/{job['id']}").json()["title"] == "Rehearsal & run"
        assert c.get(f"/v1/jobs/{job['id']}/composition").json()["title"] == "Rehearsal & run"
        assert "<work-title>Rehearsal &amp; run</work-title>" in c.get(f"/v1/jobs/{job['id']}/musicxml").text
        assert c.patch(f"/v1/runs/{job['id']}", json={"title": "   "}).status_code == 422
        assert c.patch("/v1/runs/nope", json={"title": "x"}).status_code == 404


def test_delete_run(settings, audio):
    with TestClient(create_app(settings)) as c:
        job = run_job(c, audio)
        run_dir = settings.runs_dir / job["id"]
        assert run_dir.is_dir()
        cache_before = sorted(p for p in settings.cache_dir.rglob("*") if p.is_file())
        assert c.delete(f"/v1/runs/{job['id']}").status_code == 204
        assert not run_dir.exists()
        assert c.get(f"/v1/jobs/{job['id']}").status_code == 404
        assert sorted(p for p in settings.cache_dir.rglob("*") if p.is_file()) == cache_before
        assert c.delete(f"/v1/runs/{job['id']}").status_code == 404
        assert c.delete("/v1/runs/x..y").status_code == 404
        assert c.delete("/v1/runs/..%2Fcache").status_code in (404, 405) and settings.cache_dir.is_dir()
        # the next run of the same input is served from the cache
        again = run_job(c, audio)
        assert all(s["status"] == "cached" for s in again["stages"])


def test_delete_active_run_is_refused(settings):
    from brasscribe_engine.jobs import Job

    with TestClient(create_app(settings)) as c:
        jobs = c.app.state.jobs
        jobs.jobs["20990101-000000-test-abcdef"] = Job("20990101-000000-test-abcdef", "test", None, None,
                                                        settings.data_dir / "x.wav", {}, status="running")
        assert c.delete("/v1/runs/20990101-000000-test-abcdef").status_code == 409
