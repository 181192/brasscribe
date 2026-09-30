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


def test_band_takes_are_made_and_checked_as_the_small_band():
    # A brass-band or pop recording is arranged for the small band, whatever lineup the app sent.
    for profile in profiles.BAND_TAKE_PROFILES:
        assert profiles.made_lineup(profile, "full") == profiles.made_lineup(profile, None) == "minimal"
        assert profiles.made_lineup(profile, "quartet") == "quartet"
        # 1st Baritone -> Euphonium in the small band: its tune is allowed, though the full band refuses it.
        assert profiles.job_options(profile, {"seat": "1st-baritone", "lead": "seat", "lineup": "full"})["lead"] == "seat"
    assert profiles.made_lineup("orchestra-with-soloist", None) == "full"
    with pytest.raises(ValueError, match="tune"):
        profiles.job_options("orchestra-with-soloist", {"seat": "1st-baritone", "lead": "seat", "lineup": "full"})


def test_percussion_solo_take_is_refused():
    # The pitch trackers' notes from a drummer's take are no drum part: refused before any transcription.
    with pytest.raises(profiles.OptionError, match="percussion") as e:
        profiles.job_options("solo", {"seat": "percussion"})
    assert e.value.code == "percussion_solo"
    with pytest.raises(profiles.OptionError) as e:
        profiles.job_options("solo", {"lineup": "quartet"})
    assert e.value.code == "quartet_needs_group"
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
        # Each refusal carries a code the apps map to their own words.
        assert bad.json()["code"] == "quartet_needs_group"
        assert post(seat="eb-bass", lead="seat").json()["code"] == "seat_no_tune"
        assert post(seat="solo-cornet", reads="bass").json()["code"] == "reads_not_offered"
        job = post(seat="euphonium", reads="bass")
        assert job.status_code == 202
        wait(c, job.json()["id"])
        src = c.get(f"/v1/jobs/{job.json()['id']}/part-sources")
        assert src.status_code == 200 and src.json()["parts"]["Solo Cornet"] == "recording"
        assert c.get("/v1/jobs/nope/part-sources").status_code == 404


def test_option_refusal_keeps_the_exception_in_the_log(settings, audio, monkeypatch, capsys):
    def fail(profile, params):
        raise ValueError("internal detail /somewhere/engine.py")

    monkeypatch.setattr(profiles, "job_options", fail)
    with TestClient(create_app(settings)) as c:
        ref = c.post("/v1/audio", files={"file": ("a.wav", audio.read_bytes())}).json()
        r = c.post("/v1/jobs", json={"audio_id": ref["audio_id"], "profile": "test"})
    assert r.status_code == 422 and r.json()["code"] == "invalid_options"
    assert "internal detail" not in r.text and r.json()["detail"] == profiles.option_error_message("invalid_options")
    assert "internal detail /somewhere/engine.py" in capsys.readouterr().err
