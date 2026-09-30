"""One id format for jobs, uploads, references and sources, checked before anything touches the file system."""

import json
import os
import shutil
from pathlib import PureWindowsPath

import pytest
from fastapi.testclient import TestClient

from brasscribe_engine.api import create_app
from brasscribe_engine.names import valid_id, valid_relpath

from .test_inspection import run_job

WINDOWS_NAMES = ["..\\..\\Users", "\\\\host\\share", "\\\\host\\share\\x.wav", "C:\\Windows\\win.ini", "C:x",
                 "c:", "D:x", "\\x", "a\\b", "//host/share"]


@pytest.mark.parametrize("name", ["20260101-120000-solo-a1b2c3", "demo.v1", "choralebricks-brass4", "A_b-9"])
def test_valid_ids(name):
    assert valid_id(name)


@pytest.mark.parametrize("name", ["", ".", "..", "...", "abc.", "a/b", "../x", "a b", "é", "x\0", "x" * 201,
                                  *WINDOWS_NAMES])
def test_invalid_ids(name):
    assert not valid_id(name)


@pytest.mark.parametrize("name", ["\\\\host\\share", "//host/share", "C:\\Windows\\win.ini", "\\x", "D:x"])
def test_names_a_windows_join_would_put_outside_the_root_are_refused(name):
    root = PureWindowsPath("C:\\data\\runs")
    assert root not in (root / name).parents  # the join itself drops the root: no later check could catch it
    assert not valid_id(name) and not valid_relpath(name)


@pytest.mark.parametrize("rel", ["mix-sw.mid", "parts/01-Solo-Cornet.brf", "layers/a b.mid"])
def test_valid_relpaths(rel):
    assert valid_relpath(rel)


@pytest.mark.parametrize("rel", ["", "/etc/hosts", "../manifest.json", "a/../../b", "a//b", "a/./b", "a/",
                                 *WINDOWS_NAMES])
def test_invalid_relpaths(rel):
    assert not valid_relpath(rel)


@pytest.fixture
def no_backslash_paths(monkeypatch):
    """Fail if the engine stats a path with a backslash in it: on Windows that could be a network share."""
    touched = []
    real_stat, real_lstat = os.stat, os.lstat

    def watch(real):
        def stat(path, *a, **kw):
            if isinstance(path, (str, os.PathLike)) and "\\" in os.fspath(path):
                touched.append(os.fspath(path))
            return real(path, *a, **kw)
        return stat

    monkeypatch.setattr(os, "stat", watch(real_stat))
    monkeypatch.setattr(os, "lstat", watch(real_lstat))
    yield touched
    assert touched == []


def test_ids_with_windows_separators_never_reach_the_file_system(settings, audio, no_backslash_paths):
    (settings.golden_dir / "demo").mkdir(parents=True)
    with TestClient(create_app(settings)) as c:
        job = run_job(c, audio)
        jid = job["id"]
        for url in ("/v1/jobs/%5C%5Chost%5Cshare", "/v1/jobs/%5C%5Chost%5Cshare/input",
                    "/v1/jobs/..%5C..%5Cx/manifest", "/v1/references/..%5C..%5CUsers/files/x",
                    "/v1/references/demo/files/..%5C..%5Cx", f"/v1/jobs/{jid}/artifacts/..%5C..%5Cx",
                    f"/v1/jobs/{jid}/artifacts/%5C%5Chost%5Cshare%5Cx",
                    f"/v1/jobs/{jid}/stages/arrange/files/..%5Cmanifest.json",
                    f"/v1/jobs/{jid}/stages/..%5C..%5Cx/files/y"):
            assert c.get(url).status_code == 404, url
        assert c.get(f"/v1/jobs/{jid}/compare", params={"reference": "..\\..\\x"}).status_code == 404
        assert c.delete("/v1/runs/%5C%5Chost%5Cshare").status_code == 404
        assert c.patch("/v1/runs/..%5Cx", json={"title": "x"}).status_code == 404
        for source in ("capture:C:\\Windows\\win.ini", "capture:\\\\host\\share\\x.wav", "capture:../x.wav",
                       "dataset:..\\..\\x", "dataset:a/../../b", "dataset:a/b/c", "other:x"):
            assert c.post("/v1/jobs", json={"source_id": source, "profile": "test"}).status_code == 404, source
        assert c.post("/v1/jobs", json={"audio_id": "..\\x", "profile": "test"}).status_code == 404


def test_sources_list_only_what_a_job_accepts(settings, audio):
    cap = settings.data_dir / "captures"
    cap.mkdir()
    shutil.copy(audio, cap / "take-1.wav")
    shutil.copy(audio, cap / "take 2.wav")
    (cap / "elsewhere.wav").symlink_to(audio)  # a capture that is really a file outside the data folder
    with TestClient(create_app(settings)) as c:
        ids = [s["id"] for s in c.get("/v1/sources").json()]
        assert ids == ["capture:take-1.wav"]
        assert c.post("/v1/jobs", json={"source_id": ids[0], "profile": "test"}).status_code == 202
        assert c.post("/v1/jobs", json={"source_id": "capture:take 2.wav", "profile": "test"}).status_code == 404


def test_run_folders_with_other_names_are_not_listed(settings, audio):
    with TestClient(create_app(settings)) as c:
        job = run_job(c, audio)
        copy = settings.runs_dir / "copy of run"
        shutil.copytree(settings.runs_dir / job["id"], copy)
        m = json.loads((copy / "manifest.json").read_text())
        (copy / "manifest.json").write_text(json.dumps({**m, "run_id": copy.name}))
        assert [j["id"] for j in c.get("/v1/jobs").json()] == [job["id"]]
