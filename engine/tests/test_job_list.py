"""GET /v1/jobs parses a finished run's manifest once, and again only when it changes."""

from __future__ import annotations

import json
import os
from datetime import datetime

from brasscribe_engine.jobs import JobManager


def _run(settings, run_id: str, title: str) -> None:
    d = settings.runs_dir / run_id
    (d / "outputs" / "parts").mkdir(parents=True)
    (d / "outputs" / "brass-band.musicxml").write_text("<score-partwise/>")
    (d / "outputs" / "parts" / "cornet.musicxml").write_text("<score-partwise/>")
    (d / "events.jsonl").write_text(json.dumps({"id": 0, "type": "job", "status": "succeeded"}) + "\n")
    manifest = {"run_id": run_id, "profile": "test", "title": title, "status": "succeeded",
                "input": {"path": "/x.wav"}, "stages": [{"stage": "arrange", "kind": "arrange", "status": "ran",
                                                         "seconds": 1.5}]}
    (d / "manifest.json").write_text(json.dumps(manifest))


def test_list_reparses_only_changed_manifests(settings):
    _run(settings, "run-a", "A")
    _run(settings, "run-b", "B")
    jobs = JobManager(settings)

    first = {j.id: j for j in jobs.list()}
    assert set(first) == {"run-a", "run-b"} and jobs.manifest_parses == 2
    assert first["run-a"].events == []  # the list never reads events.jsonl
    assert jobs.outputs(first["run-a"]) == ["brass-band.musicxml", "parts/cornet.musicxml"]

    jobs.list()
    assert jobs.manifest_parses == 2

    mpath = settings.runs_dir / "run-a" / "manifest.json"
    m = json.loads(mpath.read_text())
    m["title"] = "A, renamed"
    mpath.write_text(json.dumps(m))
    st = mpath.stat()
    os.utime(mpath, ns=(st.st_atime_ns, st.st_mtime_ns + 1_000_000))
    again = {j.id: j for j in jobs.list()}
    assert jobs.manifest_parses == 3 and again["run-a"].title == "A, renamed" and again["run-b"] is first["run-b"]

    (settings.runs_dir / "run-b" / "manifest.json").unlink()
    assert [j.id for j in jobs.list()] == ["run-a"]
    # a single job still comes with its events
    assert jobs.get("run-a").events[0]["status"] == "succeeded"


def test_renaming_a_run_keeps_its_place_in_the_list(settings):
    from fastapi.testclient import TestClient

    from brasscribe_engine.api import create_app

    for run_id, created in (("run-old", "2026-01-01T10:00:00+00:00"), ("run-new", "2026-02-01T10:00:00+00:00")):
        _run(settings, run_id, run_id)
        mpath = settings.runs_dir / run_id / "manifest.json"
        mpath.write_text(json.dumps({**json.loads(mpath.read_text()), "created": created}))
    with TestClient(create_app(settings)) as c:
        assert [j["id"] for j in c.get("/v1/jobs").json()] == ["run-new", "run-old"]
        assert c.patch("/v1/runs/run-old", json={"title": "Renamed"}).status_code == 200
        listed = c.get("/v1/jobs").json()
        assert [j["id"] for j in listed] == ["run-new", "run-old"]
        assert listed[1]["created"] == datetime.fromisoformat("2026-01-01T10:00:00+00:00").timestamp()
