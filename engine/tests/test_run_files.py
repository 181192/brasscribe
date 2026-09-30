"""A finished run's files: how they are listed and what renaming a run changes."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from brasscribe_engine.api import create_app


def finished_run(settings, run_id: str, files: dict[str, str], title: str = "Old") -> None:
    d = settings.runs_dir / run_id
    (d / "outputs").mkdir(parents=True)
    for name, text in files.items():
        (d / "outputs" / name).parent.mkdir(parents=True, exist_ok=True)
        (d / "outputs" / name).write_text(text)
    manifest = {"run_id": run_id, "profile": "test", "title": title, "status": "succeeded",
                "created": "2026-01-02T03:04:05+00:00", "input": {"path": str(settings.uploads_dir / "a.wav")},
                "stages": []}
    (d / "manifest.json").write_text(json.dumps(manifest))


@pytest.fixture
def client(settings):
    with TestClient(create_app(settings)) as c:
        yield c


def test_artifacts_are_listed_with_the_type_they_are_served_with(settings, client):
    finished_run(settings, "run-a", {"brass-band.pdf": "%PDF", "brass-band.brf": "x", "talking-score.html": "<p>",
                                     "talking-score.txt": "x", "parts/01-solo-cornet.pdf": "%PDF"})
    listed = {a["name"]: a["media_type"] for a in client.get("/v1/jobs/run-a/artifacts").json()}
    assert listed["brass-band.pdf"] == listed["parts/01-solo-cornet.pdf"] == "application/pdf"
    for name, media in listed.items():
        served = client.get(f"/v1/jobs/run-a/artifacts/{name}").headers["content-type"]
        assert served.split(";")[0] == media.split(";")[0], name


def test_rename_replaces_outputs_that_are_read_only_links_into_the_cache(settings, client, monkeypatch):
    import os
    import stat

    from brasscribe_engine import jobs
    from brasscribe_engine.cache import _read_only

    finished_run(settings, "run-a", {})
    cached = settings.cache_dir / "composition.json"
    cached.write_text(json.dumps({"title": "Old"}))
    _read_only(cached)
    os.link(cached, settings.runs_dir / "run-a" / "outputs" / "composition.json")
    replace = os.replace

    def like_windows(src, dst):  # Windows refuses to replace a read-only file
        if os.path.exists(dst) and not os.stat(dst).st_mode & stat.S_IWUSR:
            raise PermissionError(13, "Access is denied", str(dst))
        replace(src, dst)

    monkeypatch.setattr(jobs.os, "replace", like_windows)
    r = client.patch("/v1/runs/run-a", json={"title": "New"})
    assert r.status_code == 200
    assert client.get("/v1/jobs/run-a/composition").json()["title"] == "New"
    assert json.loads(cached.read_text()) == {"title": "Old"}
