"""Titles and pairing lifetimes the engine accepts."""

import argparse
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from brasscribe_engine import stages
from brasscribe_engine.api import create_app


@pytest.fixture
def client(settings):
    with TestClient(create_app(settings)) as c:
        yield c


def arrange_args(monkeypatch, title: str) -> list[str]:
    seen = []
    monkeypatch.setattr(stages, "_python", lambda ctx, module, *args: seen.extend(args))
    monkeypatch.setattr(stages, "_arrangement_flags", lambda ctx, module: [])
    monkeypatch.setattr(stages, "_stable_musicxml", lambda ctx: None)
    ins = {k: Path(f"/x/{k}") for k in ("beats", "melody", "bass", "harmony")}
    stages.arrange_band(SimpleNamespace(inputs=ins, out=Path("/x/out"), params={"title": title}))
    return seen


@pytest.mark.parametrize("title", ["-Intro", "--no-render", "March -- slow"])
def test_a_title_that_looks_like_an_option_stays_the_title(monkeypatch, title):
    args = arrange_args(monkeypatch, title)
    parser = argparse.ArgumentParser()  # the arrangers parse their arguments with argparse
    for flag in ("--beats", "--melody", "--bass", "--out", "--title"):
        parser.add_argument(flag)
    parser.add_argument("--harmony", nargs="+")
    parser.add_argument("--no-render", action="store_true")
    parsed = parser.parse_args(args)
    assert parsed.title == title and parsed.no_render


def test_titles_are_at_most_200_characters(client, audio):
    long = "x" * 201
    assert client.post("/v1/jobs", json={"path": "x.wav", "profile": "test", "title": long}).status_code == 422
    r = client.post("/v1/jobs/upload", files={"file": ("song.wav", audio.read_bytes())},
                    data={"profile": "test", "title": long})
    assert r.status_code == 422
    assert not list(client.app.state.settings.uploads_dir.iterdir())
    r = client.post("/v1/jobs/upload", files={"file": ("song.wav", audio.read_bytes())},
                    data={"profile": "test", "title": "x" * 200})
    assert r.status_code == 202


@pytest.mark.parametrize("ttl, status", [(1e308, 422), (86401, 422), (29, 422), (-1, 422), (30, 200), (86400, 200),
                                         (None, 200)])
def test_pairing_lifetime_bounds(client, ttl, status):
    before = client.get("/v1/pairing").json()
    r = client.post("/v1/pairing", json={"ttl_s": ttl})
    assert r.status_code == status
    if status == 422:
        assert client.get("/v1/pairing").json() == before  # nothing was opened
    elif ttl is None:
        assert r.json()["expires_at"] is None
