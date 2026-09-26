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


def test_conformance_default_is_only_the_summary(settings, monkeypatch, tmp_path):
    root = tmp_path / "core-conformance"
    (root / "case1" / "py").mkdir(parents=True)
    (root / "case1" / "py" / "composition.json").write_text(json.dumps({"big": [0] * 1000}))
    monkeypatch.setenv("BRASSCRIBE_CONFORMANCE_REPORTS", str(root))
    with TestClient(create_app(settings)) as c:
        assert c.get("/v1/conformance").json() == []  # no report yet
        (root / "report.json").write_text(json.dumps({"git_sha": "abc", "sets": []}))
        assert c.get("/v1/conformance").json() == [{"git_sha": "abc", "sets": [], "_file": "report.json"}]
        assert len(c.get("/v1/conformance", params={"all": True}).json()) == 2


def test_conformance_run_lifecycle(settings, monkeypatch, tmp_path):
    import time

    from brasscribe_engine import conformance

    project = tmp_path / "proj"
    (project / "brasscribe_conformance").mkdir(parents=True)
    (project / "brasscribe_conformance" / "run.py").write_text("")
    with TestClient(create_app(settings)) as c:
        runner = c.app.state.conformance
        runner.project = project
        monkeypatch.setattr(conformance.ConformanceRunner, "command",
                            lambda self: ["python3", "-c", "import time; print('case OK'); time.sleep(0.5)"])
        assert c.get("/v1/conformance/run").json()["status"] == "idle"
        r = c.post("/v1/conformance/run")
        assert r.status_code == 202 and r.json()["status"] == "running"
        assert c.post("/v1/conformance/run").status_code == 409
        for _ in range(100):
            s = c.get("/v1/conformance/run").json()
            if s["status"] != "running":
                break
            time.sleep(0.05)
        assert s["status"] == "succeeded" and s["exit_code"] == 0 and "case OK" in s["log_tail"]
        runner.project = tmp_path / "nowhere"
        assert c.post("/v1/conformance/run").status_code == 503
