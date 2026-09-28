"""The seat, reads and lead job options: validation, cache keys, the solo profile's lead, part sources."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from brasscribe_engine import profiles
from brasscribe_engine.api import create_app

from .test_api import wait


def test_seat_options_only_when_set():
    # A job without a seat keeps its cache keys: the defaults never enter the options.
    assert profiles.arrangement_options({"seat": None, "reads": None, "lead": "lineup"}) == {}
    assert profiles.arrangement_options({"seat": "euphonium", "reads": "bass", "lead": "seat"}) == {
        "seat": "euphonium", "reads": "bass", "lead": "seat"}
    default = profiles.build("orchestra-with-soloist", Path("m.wav"), params={"lead": "lineup"}).stage("arrange").params
    assert "arrangement" not in default


def test_seat_options_validated():
    for bad in ({"seat": "tuba"}, {"reads": "bass"}, {"seat": "solo-cornet", "reads": "bass"},
                {"lead": "seat"}, {"seat": "euphonium", "lead": "tune"}):
        with pytest.raises(ValueError):
            profiles.arrangement_options(bad)
    # The tune moves to the seat's part in the band lineups only, and onto a part that can carry it.
    assert profiles.job_options("orchestra-with-soloist", {"seat": "euphonium", "lead": "seat"})["lead"] == "seat"
    with pytest.raises(ValueError, match="quartet"):
        profiles.job_options("orchestra-with-soloist", {"seat": "euphonium", "lead": "seat", "lineup": "quartet"})
    with pytest.raises(ValueError, match="tune"):
        profiles.job_options("orchestra-with-soloist", {"seat": "eb-bass", "lead": "seat"})


def test_percussion_solo_take_is_refused():
    # The pitch trackers' notes from a drummer's take are no drum part: refused before any transcription.
    with pytest.raises(ValueError, match="percussion"):
        profiles.job_options("solo", {"seat": "percussion"})
    with pytest.raises(ValueError, match="percussion"):
        profiles.build("solo", Path("a.wav"), params={"seat": "percussion"})
    # A band recording with drums still gets the percussion part.
    assert profiles.job_options("orchestra-with-soloist", {"seat": "percussion"}) == {"seat": "percussion"}


def test_solo_profile_with_a_seat_writes_on_the_seat():
    arrange = profiles.build("solo", Path("a.wav"), params={"seat": "1st-baritone"}).stage("arrange").params
    assert arrange["arrangement"] == {"lineup": "minimal", "seat": "1st-baritone", "lead": "seat"}
    plain = profiles.build("solo", Path("a.wav")).stage("arrange").params
    assert plain["arrangement"] == {"lineup": "minimal"}


def test_seat_options_over_the_api(settings, audio):
    with TestClient(create_app(settings)) as c:
        ref = c.post("/v1/audio", files={"file": ("a.wav", audio.read_bytes())}).json()
        post = lambda **kw: c.post("/v1/jobs", json={"audio_id": ref["audio_id"], "profile": "test", **kw})  # noqa: E731
        assert post(seat="tuba").status_code == 422
        assert post(reads="alto", seat="euphonium").status_code == 422
        assert post(reads="bass").status_code == 422
        bad = post(seat="euphonium", lead="seat", lineup="quartet")
        assert bad.status_code == 422 and "quartet" in bad.json()["detail"]
        job = post(seat="euphonium", reads="bass")
        assert job.status_code == 202
        wait(c, job.json()["id"])
        src = c.get(f"/v1/jobs/{job.json()['id']}/part-sources")
        assert src.status_code == 200 and src.json()["parts"]["Solo Cornet"] == "recording"
        assert c.get("/v1/jobs/nope/part-sources").status_code == 404
