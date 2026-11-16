"""A player's correction of the beat: the option, the stage that applies it, what runs again, and the hints."""

from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np
import pytest

from scribe_engine import bass_tab, beat_hints, profiles, tuning
from scribe_engine import stages as S


def _core_missing() -> str | None:
    try:
        bass_tab.core_cli()
    except bass_tab.CoreCliMissing as e:
        return str(e)
    return None


needs_core = pytest.mark.skipif(_core_missing() is not None, reason=_core_missing() or "")


def _beats(n: int = 33, bpm: float = 120.0, per_bar: int = 4) -> np.ndarray:
    return np.array([[i * 60 / bpm, i % per_bar + 1] for i in range(n)])


def _write_midi(path: Path, notes: list[tuple[int, float, float]]) -> None:
    import pretty_midi

    pm = pretty_midi.PrettyMIDI()
    inst = pretty_midi.Instrument(program=25)
    inst.notes = [pretty_midi.Note(velocity=90, pitch=p, start=a, end=b) for p, a, b in notes]
    pm.instruments.append(inst)
    pm.write(str(path))


def _wait(client, job_id: str, timeout: float = 120) -> dict:
    t0 = time.time()
    while time.time() - t0 < timeout:
        job = client.get(f"/v1/jobs/{job_id}").json()
        if job["status"] in ("succeeded", "failed", "cancelled"):
            return job
        time.sleep(0.05)
    raise AssertionError("job did not finish")


# ---------------------------------------------------------------- the option

def test_a_job_without_a_correction_has_none():
    assert profiles.beat_correction({}) is None and profiles.beat_correction({"beat": None}) is None
    assert profiles.beat_correction({"beat": {}}) is None
    # what says nothing is nothing: a job keeps the stages and keys it has without a correction
    assert profiles.beat_correction({"beat": {"source": "tracked", "level": None, "phase": 0, "holds": []}}) is None


def test_a_correction_is_kept_as_what_the_player_said_with_holds_in_order():
    beat = profiles.beat_correction({"beat": {"level": "third", "phase": 2, "beats_per_bar": 3, "first_downbeat_s": 1,
                                              "holds": [{"start_s": 9, "end_s": 12.5, "beats": 3}, {"start_s": 2.0, "end_s": 4.0, "beats": 2}]}})
    assert beat == {"level": "third", "phase": 2, "beats_per_bar": 3, "first_downbeat_s": 1.0,
                    "holds": [{"start_s": 2.0, "end_s": 4.0, "beats": 2}, {"start_s": 9.0, "end_s": 12.5, "beats": 3}]}
    assert profiles.beat_correction({"beat": beat}) == beat  # a rerun reads its own manifest
    assert json.loads(json.dumps(beat)) == beat


@pytest.mark.parametrize("bad", [
    "double", ["double"], {"levle": "double"}, {"level": "quadruple"}, {"level": 2}, {"source": "other"},
    {"phase": 1}, {"level": "half", "phase": 2}, {"level": "third", "phase": 3}, {"level": "double", "phase": 1},
    {"phase": 0.5}, {"phase": True}, {"level": "double", "beats_per_bar": 1}, {"level": "double", "beats_per_bar": 13},
    {"level": "double", "beats_per_bar": 3.0}, {"level": "double", "beats_per_bar": "4"}, {"first_downbeat_s": -0.1}, {"first_downbeat_s": "1"}, {"first_downbeat_s": float("nan")},
    {"first_downbeat_s": float("inf")}, *({"level": "as-tracked", "holds": holds} for holds in (
        {"start_s": 1, "end_s": 2, "beats": 2}, [[1, 2]], [{"start_s": 1, "end_s": 2}],
        [{"start_s": 1, "end_s": 2, "beats": 2, "more": 1}], [{"start_s": 2, "end_s": 2, "beats": 2}],
        [{"start_s": 3, "end_s": 2, "beats": 2}], [{"start_s": -1, "end_s": 2, "beats": 2}],
        [{"start_s": 1, "end_s": 2, "beats": 0}], [{"start_s": 1, "end_s": 2, "beats": 17}],
        [{"start_s": 1, "end_s": 2, "beats": 1.5}],
        [{"start_s": 1, "end_s": 3, "beats": 2}, {"start_s": 2, "end_s": 4, "beats": 2}],
        [{"start_s": i, "end_s": i + 0.5, "beats": 1} for i in range(65)])),
    {"beats_per_bar": 3}, {"holds": [{"start_s": 1, "end_s": 3, "beats": 2}]},  # beats are counted on a level: none given
    {"first_downbeat_s": 1.0, "beats_per_bar": 4},
])
def test_a_correction_that_does_not_fit_is_refused_with_its_code(bad):
    with pytest.raises(profiles.OptionError) as refused:
        profiles.beat_correction({"beat": bad})
    assert refused.value.code == "beat_invalid" and refused.value.code in profiles.OPTION_ERROR_CODES
    for profile in ("solo", "brass-band", "tab"):  # every profile checks it before anything runs
        with pytest.raises(ValueError):
            profiles.job_options(profile, {"beat": bad})


def test_the_alternative_source_is_refused_on_an_engine_with_one_tracker(monkeypatch):
    assert profiles.ALTERNATIVE_BEATS is None and profiles.beat_sources() == ("tracked",)
    with pytest.raises(profiles.OptionError) as refused:
        profiles.beat_correction({"beat": {"source": "alternative"}})
    assert refused.value.code == "beat_source_unavailable"
    assert "one beat tracker" in profiles.option_error_message(refused.value.code)
    monkeypatch.setattr(profiles, "ALTERNATIVE_BEATS", "swift-f0")
    assert profiles.beat_sources() == ("tracked", "alternative")
    assert profiles.beat_correction({"beat": {"source": "alternative"}}) == {"source": "alternative"}


def test_every_refusal_has_its_own_words():
    for code in ("beat_invalid", "beat_source_unavailable"):
        assert profiles.option_error_message(code) != profiles.option_error_message("invalid_options")


# ---------------------------------------------------------------- the pipeline

PROFILE_PARAMS = {"solo": {}, "brass-band": {}, "pop-rock": {}, "orchestra-with-soloist": {},
                  "tab": {"instrument": "guitar-6"}, "bass-tab": {}}


def _stages(profile: str, beat: dict | None = None, **params):
    return profiles.build(profile, Path("take.wav"), "Take", {**PROFILE_PARAMS[profile], **params, **({"beat": beat} if beat else {})})


@pytest.mark.parametrize("profile", list(PROFILE_PARAMS))
def test_a_correction_adds_one_stage_and_touches_no_model_stage(profile):
    plain, fixed = _stages(profile), _stages(profile, {"level": "double", "beats_per_bar": 3})
    names = [s.name for s in plain.stages]
    assert "beats.corrected" not in names and "beats.alternative" not in names
    assert [s.name for s in fixed.stages] == [names[0], "beats.corrected", *names[1:]]
    reader = "notes" if profile in ("tab", "bass-tab") else "arrange"
    for a in plain.stages:
        b = fixed.stage(a.name)
        if a.name == reader:  # only the stage that reads the beats knows of the correction
            assert b.inputs["beats"].stage == "beats.corrected" and a.inputs["beats"].stage == "beats"
            assert b.params == {**a.params, "beats_given": ["level", "bars"]}
        else:
            assert (b.params, b.inputs, b.adapter) == (a.params, a.inputs, a.adapter), a.name
    corrected = fixed.stage("beats.corrected")
    assert corrected.adapter is None and corrected.params == {"beat": {"level": "double", "beats_per_bar": 3}}
    assert fixed.params["beat"] == {"level": "double", "beats_per_bar": 3}  # the manifest keeps it for the next rerun


def test_a_correction_that_says_nothing_builds_the_plain_pipeline():
    assert [s.name for s in _stages("brass-band", {"level": None, "holds": []}).stages] == [s.name for s in _stages("brass-band").stages]


@pytest.mark.parametrize("profile", list(PROFILE_PARAMS))
def test_a_second_tracker_is_a_stage_of_its_own_and_the_correction_chooses_between_them(profile, monkeypatch):
    plain = [s.name for s in _stages(profile).stages]
    monkeypatch.setattr(profiles, "ALTERNATIVE_BEATS", "swift-f0")
    both = _stages(profile)
    assert [s.name for s in both.stages] == [plain[0], "beats.alternative", *plain[1:]]
    assert both.stage("beats.alternative").adapter == "swift-f0"
    reader = both.stage("notes" if profile in ("tab", "bass-tab") else "arrange")
    assert reader.inputs["beats"].stage == "beats"  # written on the first tracker's until the player says otherwise
    assert (reader.inputs["beats_tracked"].stage, reader.inputs["beats_alternative"].stage) == ("beats", "beats.alternative")
    other = _stages(profile, {"source": "alternative"})
    assert other.stage("beats.corrected").inputs["beats"].stage == "beats.alternative"
    assert other.stage("beats.corrected").params == {"beat": {}}  # the same beats stage, whichever tracker it reads
    assert "beats_given" not in other.stage(reader.name).params  # the engine still reads level and bars itself
    assert _stages(profile, {"level": "half"}).stage("beats.corrected").inputs["beats"].stage == "beats"


def test_no_profile_splits_a_slow_beat_in_three_unasked():
    """A slow beat in three is a hint (in_three) and a level a player can send (triple), not a default: no
    profile asks for the split, and the music library's level rule and quantizer do not split by default."""
    from scribe_music.quantize import TICKS_PER_BEAT, choose_level, in_three, quantize

    slow = _beats(17, bpm=60.0)[:, 0]
    on = np.sort(np.concatenate([slow[:-1] + (slow[1:] - slow[:-1]) * f for f in (0.0, 1 / 3, 2 / 3)]))
    assert in_three(slow, on) and len(choose_level(slow, on, three=True)) == 3 * len(slow) - 2  # the case is one
    assert len(choose_level(slow, on)) == len(slow)
    notes = [{"onset": float(t), "offset": float(t) + 0.2, "pitch": 60} for t in on]
    assert any(q.start % TICKS_PER_BEAT for q in quantize(notes, slow))  # thirds of the tracked beat: not split
    assert not any(q.start % TICKS_PER_BEAT for q in quantize(notes, slow, three=True))  # split: every note on a beat
    assert "three" not in _stages("brass-band", muscriptor=False).stage("arrange").params
    for profile in ("brass-band", "solo", "pop-rock", "orchestra-with-soloist"):
        assert "three" not in _stages(profile).stage("arrange").params


# ---------------------------------------------------------------- the stage

class _Ctx:
    def __init__(self, out: Path, beats: Path, said: dict):
        self.out, self.inputs, self.params, self.logged = out, {"beats": beats}, {"beat": said}, []
        self.stage = type("stage", (), {"name": "beats.corrected"})

    def log(self, message: str) -> None:
        self.logged.append(message)


def test_the_stage_writes_the_corrected_beats_in_the_trackers_format(tmp_path):
    np.savetxt(tmp_path / "in.beats", _beats(9), fmt=["%.3f", "%d"])
    ctx = _Ctx(tmp_path, tmp_path / "in.beats", {"level": "double", "holds": [{"start_s": 1.0, "end_s": 3.0, "beats": 2}]})
    S.correct_beats(ctx)
    out = np.loadtxt(tmp_path / "mix.beats", ndmin=2)
    assert [float(t) for t in out[:, 0]] == [0.0, 0.25, 0.5, 0.75, 1.0, 1.25, 3.0, 3.25, 3.5, 3.75, 4.0]
    assert list(out[:, 1].astype(int)) == [1, 2, 3, 4, 5, 6, 7, 8, 1, 2, 3]
    assert "9 tracked beats, 11 after the correction" in ctx.logged[0]


def test_a_correction_the_beats_cannot_take_fails_the_stage_with_its_reason(tmp_path):
    from scribe_engine.dag import StageFailed

    np.savetxt(tmp_path / "in.beats", _beats(3), fmt=["%.3f", "%d"])
    with pytest.raises(StageFailed, match="too few beats"):
        S.correct_beats(_Ctx(tmp_path, tmp_path / "in.beats", {"level": "third", "phase": 1}))
    (tmp_path / "empty.beats").write_text("")  # nothing tracked: nothing to correct, and the arranger says so
    S.correct_beats(_Ctx(tmp_path, tmp_path / "empty.beats", {"level": "double"}))
    assert (tmp_path / "mix.beats").read_text() == ""


# ---------------------------------------------------------------- through the API: a tab

STRUM = [(p, i * 1.0 + k * 0.008, i * 1.0 + 0.9) for i in range(8) for k, p in enumerate([40, 47, 52, 56, 59, 64])]
LINE = [(64 + (i % 4), 8.0 + 0.5 * i, 8.0 + 0.5 * i + 0.4) for i in range(8)]


@pytest.fixture
def tab_client(settings, audio, monkeypatch):
    """The engine with the symbolic stages and the core for real, and the models' outputs written in their place.
    `ran` counts the model stages that ran."""
    from fastapi.testclient import TestClient
    from scribe_music import musescore

    from scribe_engine.api import create_app

    ran: list[str] = []

    def beats(ctx):
        ran.append(ctx.stage.name)
        np.savetxt(ctx.out / "mix.beats", _beats(25), fmt=["%.3f", "%d"])

    def alternative(ctx):
        ran.append(ctx.stage.name)
        np.savetxt(ctx.out / "mix.beats", _beats(17, bpm=80.0, per_bar=3), fmt=["%.3f", "%d"])

    def transcribe(ctx):
        ran.append(ctx.stage.name)
        _write_midi(ctx.out / ctx.params["output"], STRUM + LINE)

    monkeypatch.setattr(musescore, "binary", lambda: None)
    monkeypatch.setattr(S, "beats", beats)
    monkeypatch.setattr(S, "beats_alternative", alternative)
    monkeypatch.setattr(tuning, "transcribe", transcribe)
    monkeypatch.setattr(S, "transcribe", transcribe)
    with TestClient(create_app(settings)) as c:
        c.ran = ran
        c.audio_id = c.post("/v1/audio", files={"file": ("my_take.wav", audio.read_bytes(), "audio/wav")}).json()["audio_id"]
        yield c


def _tab_job(c) -> dict:
    r = c.post("/v1/jobs", json={"audio_id": c.audio_id, "profile": "tab", "instrument": "guitar-6", "recording": "instrument"})
    assert r.status_code == 202, r.text
    job = _wait(c, r.json()["id"])
    assert job["status"] == "succeeded", job["error"]
    return job


def _rerun(c, job: dict, body: dict | None = None) -> dict:
    r = c.post(f"/v1/jobs/{job['id']}/rerun", **({"json": body} if body is not None else {}))
    assert r.status_code == 202, r.text
    again = _wait(c, r.json()["id"])
    assert again["status"] == "succeeded", again["error"]
    assert again["previous_run_id"] == job["id"]
    return again


def _tab(c, job: dict) -> dict:
    return c.get(f"/v1/jobs/{job['id']}/tab").json()


def _status(job: dict) -> dict[str, str]:
    return {s["name"]: s["status"] for s in job["stages"]}


@needs_core
def test_a_corrected_job_runs_no_model_again_and_is_written_on_the_new_beats(tab_client):
    c = tab_client
    first = _tab_job(c)
    assert first["beat"] is None and first["beat_sources"] == ["tracked"]
    assert (_tab(c, first)["tempo_bpm"], _tab(c, first)["meter"]["beats"]) == (120.0, 4)
    models = list(c.ran)
    assert len(models) == 3

    t0 = time.time()
    half = _rerun(c, first, {"beat": {"level": "half"}, "allow_heavy": False})
    seconds = time.time() - t0
    assert c.ran == models  # nothing was listened to again
    assert _status(half) == {"beats": "cached", "beats.corrected": "ran", "transcribe.guitar.basic-pitch": "cached",
                             "transcribe.guitar.swift-f0": "cached", "notes": "ran", "arrange": "ran", "export": "ran"}
    assert half["beat"] == {"source": None, "level": "half", "phase": None, "beats_per_bar": None, "first_downbeat_s": None,
                            "holds": None}
    tab = _tab(c, half)
    assert (tab["tempo_bpm"], tab["meter"]["beats"]) == (60.0, 4)  # a bar of two is written as half a bar of four
    assert len(tab["notes"]) == len(_tab(c, first)["notes"])
    assert seconds < 30  # the arranging and the export, not the listening
    manifest = c.get(f"/v1/jobs/{half['id']}/manifest").json()
    assert manifest["params"]["beat"] == {"level": "half"} and manifest["previous_run_id"] == first["id"]


@needs_core
def test_a_rerun_keeps_the_correction_until_it_is_taken_away(tab_client):
    c = tab_client
    first = _tab_job(c)
    fixed = _rerun(c, first, {"beat": {"level": "double", "beats_per_bar": 3}})
    assert fixed["beat_hints"]["level"] == "double" and fixed["beat_hints"]["beats_per_bar"] == 3
    kept = _rerun(c, fixed)  # no body: the same job again
    assert kept["beat"] == fixed["beat"] and set(_status(kept).values()) == {"cached"}
    also = _rerun(c, fixed, {"cold": []})
    assert also["beat"] == fixed["beat"]
    for clear in ({"beat": None}, {"beat": {}}):
        plain = _rerun(c, fixed, clear)
        assert plain["beat"] is None and "beats.corrected" not in _status(plain)
        assert set(_status(plain).values()) == {"cached"}  # the first job's own stages
        assert _tab(c, plain)["tempo_bpm"] == 120.0
    replaced = _rerun(c, fixed, {"beat": {"first_downbeat_s": 0.5}})  # the whole correction, not a change to it
    assert replaced["beat"]["level"] is None and replaced["beat"]["first_downbeat_s"] == 0.5


@needs_core
def test_each_part_of_a_correction_reaches_the_written_tab(tab_client):
    c = tab_client
    first = _tab_job(c)
    plain = _tab(c, first)
    assert plain["first_downbeat"] == 0

    double = _tab(c, _rerun(c, first, {"beat": {"level": "double"}}))
    assert (double["tempo_bpm"], double["meter"]["beats"]) == (240.0, 4)  # eight to the tracked bar, written as two bars
    triple = _tab(c, _rerun(c, first, {"beat": {"level": "triple"}}))
    assert triple["tempo_bpm"] == 360.0 and triple["meter"]["beats"] == 12
    third = _tab(c, _rerun(c, first, {"beat": {"level": "third", "phase": 1}}))
    assert third["tempo_bpm"] == 40.0 and third["beat_times"][0] == 0.5
    same = _tab(c, _rerun(c, first, {"beat": {"level": "as-tracked"}}))
    assert same["beat_times"] == plain["beat_times"] and same["notes"] == plain["notes"]

    three = _tab(c, _rerun(c, first, {"beat": {"level": "as-tracked", "beats_per_bar": 3}}))
    assert three["meter"]["beats"] == 3 and three["beat_times"] == plain["beat_times"]
    two = _tab(c, _rerun(c, first, {"beat": {"level": "as-tracked", "beats_per_bar": 2}}))
    assert two["meter"]["beats"] == 2  # the player's bar, not the bar of four the engine makes of two

    moved = _tab(c, _rerun(c, first, {"beat": {"first_downbeat_s": 0.52}}))
    assert moved["meter"]["beats"] == 4 and moved["first_downbeat"] == -3  # a bar starts on the second beat: three beats of pickup
    assert [n["start"] for n in moved["notes"]][0] == 3 * 24

    # The chord at 7.0 s is held to 8.0 s and written one beat long: the beat the tracker counted inside it goes.
    held = _tab(c, _rerun(c, first, {"beat": {"level": first["beat_hints"]["level"], "holds": [{"start_s": 7.0, "end_s": 8.0, "beats": 1}]}}))
    assert len(held["beat_times"]) == len(plain["beat_times"]) - 1 and 7.5 not in held["beat_times"]
    late = [n["start"] for n in plain["notes"] if n["onset_s"] >= 8.0]
    assert [n["start"] for n in held["notes"] if n["onset_s"] >= 8.0] == [s - 24 for s in late]

    everything = _rerun(c, first, {"beat": {"level": "half", "phase": 1, "beats_per_bar": 3, "first_downbeat_s": 1.5,
                                            "holds": [{"start_s": 4.0, "end_s": 8.0, "beats": 2}]}})
    tab = _tab(c, everything)
    assert tab["meter"]["beats"] == 3 and tab["tempo_bpm"] == 60.0
    assert [t for t in tab["beat_times"] if 4.0 < t < 8.0] == [4.5]  # 5.5 and 6.5 taken out, 7.5 is the next note's
    assert tab["beat_times"][tab["first_downbeat"] % 3] == 1.5 or tab["beat_times"][tab["first_downbeat"] + 3] == 1.5


@needs_core
def test_a_correction_that_does_not_fit_is_a_422_with_its_code_and_starts_nothing(tab_client):
    c = tab_client
    first = _tab_job(c)
    before = len(c.get("/v1/jobs").json())
    for body, code in (({"beat": {"level": "half", "phase": 2}}, "beat_invalid"),
                       ({"beat": {"level": "double", "holds": [{"start_s": 1, "end_s": 3, "beats": 2}, {"start_s": 2, "end_s": 4, "beats": 2}]}}, "beat_invalid"),
                       ({"beat": {"beats_per_bar": 3}}, "beat_invalid"),
                       ({"beat": {"source": "alternative"}}, "beat_source_unavailable")):
        r = c.post(f"/v1/jobs/{first['id']}/rerun", json=body)
        assert r.status_code == 422 and r.json()["code"] == code and r.json()["detail"], body
    # What the request schema refuses comes back the same way, in the engine's words for what does not fit.
    for body, says in (({"beat": {"level": "quadruple"}}, "level must be one of"),
                       ({"beat": {"level": "double", "beats_per_bar": 1}}, "beats_per_bar is 2 to 12"),
                       ({"beat": {"level": "double", "beats_per_bar": 13}}, "beats_per_bar is 2 to 12"),
                       ({"beat": {"level": "double", "holds": [{"start_s": i, "end_s": i + 0.5, "beats": 1} for i in range(65)]}},
                        "at most 64"),
                       ({"beat": {"tempo": 90}}, "beat takes"), ({"beat": {"holds": [{"start_s": 1, "end_s": 2}]}}, "a hold is"),
                       ({"beat": "double"}, "beat takes")):
        r = c.post(f"/v1/jobs/{first['id']}/rerun", json=body)
        assert r.status_code == 422 and r.json()["code"] == "beat_invalid" and says in r.json()["detail"], (body, r.text)
    # Each refusal says which part does not fit, not every rule there is.
    overlap = c.post(f"/v1/jobs/{first['id']}/rerun", json={"beat": {"level": "double", "holds": [
        {"start_s": 1, "end_s": 3, "beats": 2}, {"start_s": 2, "end_s": 4, "beats": 2}]}}).json()["detail"]
    assert overlap == "beat: holds do not overlap"
    assert c.post(f"/v1/jobs/{first['id']}/rerun", json={"cold": "x"}).json()["detail"][0]["loc"] == ["body", "cold"]  # not a correction
    assert len(c.get("/v1/jobs").json()) == before


@needs_core
def test_a_correction_past_the_end_or_that_changes_nothing_is_refused(tab_client, monkeypatch):
    from scribe_engine import api

    c = tab_client
    monkeypatch.setattr(api, "recording_seconds", lambda path: 20.0)
    first = _tab_job(c)
    before = len(c.get("/v1/jobs").json())
    for beat, says in (({"first_downbeat_s": 9999}, "after the end of the recording"),
                       ({"first_downbeat_s": 1e308}, "after the end of the recording"),
                       ({"level": "as-tracked", "holds": [{"start_s": 500, "end_s": 600, "beats": 1}]}, "after the end"),
                       ({}, "nothing would change")):
        r = c.post(f"/v1/jobs/{first['id']}/rerun", json={"beat": beat})
        assert (r.status_code, r.json()["code"]) == (422, "beat_invalid") and says in r.json()["detail"], (beat, r.text)
    assert len(c.get("/v1/jobs").json()) == before
    # A hold that runs past the end is cut at the end; sending the job's own correction again changes nothing.
    held = _rerun(c, first, {"beat": {"level": "as-tracked", "holds": [{"start_s": 18.0, "end_s": 30.0, "beats": 1}]}})
    assert held["beat"]["holds"] == [{"start_s": 18.0, "end_s": 20.0, "beats": 1}]
    r = c.post(f"/v1/jobs/{held['id']}/rerun", json={"beat": held["beat"]})
    assert (r.status_code, r.json()["code"]) == (422, "beat_invalid") and "nothing would change" in r.json()["detail"]


@needs_core
def test_a_correction_the_recording_cannot_take_fails_the_job_and_says_why(tab_client):
    c = tab_client
    first = _tab_job(c)
    r = c.post(f"/v1/jobs/{first['id']}/rerun", json={"beat": {"level": "as-tracked", "holds": [{"start_s": 0.0, "end_s": 60.0, "beats": 1}]}})
    failed = _wait(c, r.json()["id"])
    assert failed["status"] == "failed" and "fewer than two beats" in failed["error"]
    assert _status(failed)["beats.corrected"] == "failed" and failed["beat_hints"] is None
    # Only a written score is corrected: a job that failed (or has not finished) has none, and nothing starts.
    r = c.post(f"/v1/jobs/{failed['id']}/rerun", json={"beat": {"level": "double"}})
    assert (r.status_code, r.json()["code"]) == (409, "job_not_finished") and "failed" in r.json()["detail"]


@needs_core
def test_a_correction_never_runs_a_model_even_when_heavy_ones_are_allowed(tab_client, monkeypatch):
    from scribe_engine import api

    c = tab_client
    first = _tab_job(c)
    asked: list[bool] = []
    submit = api.JobManager.submit

    def watched(self, *args, **kwargs):
        asked.append(kwargs["allow_heavy"])
        return submit(self, *args, **kwargs)

    monkeypatch.setattr(api.JobManager, "submit", watched)
    _rerun(c, first, {"beat": {"level": "double"}, "allow_heavy": True})
    _rerun(c, first)  # a plain rerun keeps its own choice
    assert asked == [False, True]


@needs_core
def test_with_a_second_tracker_a_job_can_be_written_on_its_beats(tab_client, monkeypatch):
    c = tab_client
    monkeypatch.setattr(profiles, "ALTERNATIVE_BEATS", "swift-f0")
    first = _tab_job(c)
    assert first["beat_sources"] == ["tracked", "alternative"] and "beats.alternative" in _status(first)
    assert _tab(c, first)["tempo_bpm"] == 120.0
    assert "trackers_disagree" in [h["code"] for h in first["beat_hints"]["hints"]]
    models = list(c.ran)
    other = _rerun(c, first, {"beat": {"source": "alternative"}})
    assert c.ran == models and other["beat"]["source"] == "alternative"
    assert (_tab(c, other)["tempo_bpm"], _tab(c, other)["meter"]["beats"]) == (80.0, 3)
    both = _rerun(c, other, {"beat": {"source": "alternative", "level": "double"}})
    assert _tab(c, both)["tempo_bpm"] == 160.0 and c.ran == models
    back = _rerun(c, other, {"beat": {"source": "tracked"}})
    assert back["beat"] is None and _tab(c, back)["tempo_bpm"] == 120.0


# ---------------------------------------------------------------- through the API: a band

HYMN = [(60 + [0, 2, 4, 5, 7, 5, 4, 2][i % 8], i * 0.5, i * 0.5 + 0.45) for i in range(32)]
HYMN_BASS = [(36 + [0, 5, 7, 0][i % 4], i * 1.0, i * 1.0 + 0.9) for i in range(16)]


@pytest.mark.slow
def test_a_band_score_is_written_again_on_corrected_beats(settings, audio, monkeypatch):
    """The band's arranger for real (its own process), on notes written in the models' place."""
    from fastapi.testclient import TestClient
    from scribe_music import musescore

    from scribe_engine.api import create_app

    ran: list[str] = []
    monkeypatch.setattr(musescore, "binary", lambda: None)
    monkeypatch.setattr(S, "beats", lambda ctx: (ran.append("beats"), np.savetxt(ctx.out / "mix.beats", _beats(33), fmt=["%.3f", "%d"])))
    for module in (S, tuning):
        monkeypatch.setattr(module, "transcribe", lambda ctx: (ran.append(ctx.stage.name), _write_midi(ctx.out / ctx.params["output"], HYMN + HYMN_BASS)))
    with TestClient(create_app(settings)) as c:
        audio_id = c.post("/v1/audio", files={"file": ("hymn.wav", audio.read_bytes(), "audio/wav")}).json()["audio_id"]
        first = _wait(c, c.post("/v1/jobs", json={"audio_id": audio_id, "profile": "brass-band", "render_audio": False}).json()["id"])
        assert first["status"] == "succeeded", first["error"]
        assert "beat-hints.json" in first["outputs"] and first["beat_hints"]["tempo_bpm"] == 120.0
        comp = c.get(f"/v1/jobs/{first['id']}/composition").json()
        assert comp["meters"][0]["beats"] == 4 and len(comp["beat_times"]) == 33
        models = list(ran)

        fixed = _rerun(c, first, {"beat": {"level": "half", "beats_per_bar": 3, "first_downbeat_s": 1.0,
                                           "holds": [{"start_s": 8.0, "end_s": 12.0, "beats": 2}]}})
        assert ran == models
        assert _status(fixed) == {"beats": "cached", "beats.corrected": "ran", "transcribe.mix.muscriptor": "cached",
                                  "transcribe.mix.basic-pitch": "cached", "arrange": "ran", "export": "ran"}
        comp = c.get(f"/v1/jobs/{fixed['id']}/composition").json()
        assert comp["meters"][0]["beats"] == 3
        assert comp["beat_times"] == [float(t) for t in range(0, 9)] + [9.0] + [float(t) for t in range(12, 17)]
        assert comp["beat_times"][comp["first_downbeat"] % 3] == 1.0 or comp["first_downbeat"] == -2
        assert fixed["beat_hints"]["tempo_bpm"] == 60.0 and fixed["beat_hints"]["beats_per_bar"] == 3
        xml = c.get(f"/v1/jobs/{fixed['id']}/musicxml").text
        assert "<beats>3</beats>" in xml


# ---------------------------------------------------------------- the hints

def _codes(found: dict) -> list[str]:
    return [h["code"] for h in found["hints"]]


def _hint(found: dict, code: str) -> dict:
    return next(h for h in found["hints"] if h["code"] == code)


def _on(beats: np.ndarray, fractions: list[float]) -> np.ndarray:
    return np.array([t + (u - t) * f for t, u in zip(beats, beats[1:]) for f in fractions])


def test_a_steady_score_has_no_hints():
    t = np.arange(33) * 0.5
    found = beat_hints.hints(t, 0, 4, _on(t, [0.0, 0.5]))
    assert found == {"tempo_bpm": 120.0, "beats_per_bar": 4, "hints": []}


def test_a_tempo_out_of_range_suggests_the_other_level():
    slow = np.arange(20) * 1.5  # 40 BPM
    found = beat_hints.hints(slow, 0, 4, _on(slow, [0.0, 0.5]))
    assert _hint(found, "tempo_slow") == {"code": "tempo_slow", "level": "double", "score": 40.0}
    fast = np.arange(120) * 0.25  # 240 BPM
    assert _hint(beat_hints.hints(fast, 0, 4, fast[::2]), "tempo_fast")["level"] == "half"
    threes = beat_hints.hints(slow, 0, 4, _on(slow, [0.0, 1 / 3, 2 / 3]))
    assert _hint(threes, "tempo_slow")["level"] == "triple" and "in_three" not in _codes(threes)  # one hint, one suggestion


def test_notes_fast_or_slow_for_the_beat_suggest_the_other_level():
    t = np.arange(40) * 0.7  # 86 BPM
    assert _hint(beat_hints.hints(t, 0, 4, _on(t, [0.0, 0.25, 0.5, 0.75])), "notes_fast")["level"] == "double"
    quick = np.arange(80) * 0.4  # 150 BPM
    assert _hint(beat_hints.hints(quick, 0, 4, quick[::2]), "notes_slow")["level"] == "half"
    assert _codes(beat_hints.hints(quick, 0, 4, _on(quick, [0.0, 0.25, 0.5, 0.75]))) == []  # doubled, it would be out of range


def test_a_slow_beat_in_three_is_hinted_where_it_is_not_split():
    t = np.arange(40) * 0.8  # 75 BPM
    found = beat_hints.hints(t, 0, 2, _on(t, [0.0, 1 / 3, 2 / 3]))
    assert _hint(found, "in_three") == {"code": "in_three", "level": "triple"}
    quick = np.arange(40) * 0.5
    assert "in_three" not in _codes(beat_hints.hints(quick, 0, 4, _on(quick, [0.0, 1 / 3, 2 / 3])))


def test_long_stretches_without_a_new_note_are_offered_as_holds():
    t = np.arange(41) * 0.5
    on = np.array([x for x in t if not 4.0 < x < 6.5 and not 12.0 < x < 15.0])
    spans = _hint(beat_hints.hints(t, 0, 4, on), "held_notes")["spans"]
    assert spans == [[4.0, 6.5], [12.0, 15.0]]
    assert "held_notes" not in _codes(beat_hints.hints(t, 0, 4, t[::4]))  # a whole note is four beats, not a hold
    many = np.concatenate([[k * 10.0, k * 10.0 + 0.5, k * 10.0 + 1.0] for k in range(20)])
    grid = np.arange(0, 200, 0.5)
    assert len(_hint(beat_hints.hints(grid, 0, 4, many), "held_notes")["spans"]) == beat_hints.HELD_MAX


def test_a_bar_with_far_more_notes_than_the_rest_is_named():
    t = np.arange(41) * 0.5
    on = np.concatenate([t[:-1], np.arange(8.0, 10.0, 0.125)])  # the fifth bar holds sixteen notes
    assert _hint(beat_hints.hints(t, 0, 4, on), "uneven_bars")["bars"] == [5]
    assert _hint(beat_hints.hints(t, 4, 4, on), "uneven_bars")["bars"] == [4]  # counted from the first downbeat


def test_a_bar_that_seems_to_start_on_another_beat_says_where():
    t = np.arange(41) * 0.5
    on = np.concatenate([t[1::4], t[1::4] + 1.5])  # a long note on every second beat of the bar, a short one before the next
    found = _hint(beat_hints.hints(t, 0, 4, on), "downbeat_unsure")
    assert found["first_downbeat_s"] == 0.5 and found["score"] >= beat_hints.DOWNBEAT_RATIO
    assert "downbeat_unsure" not in _codes(beat_hints.hints(t, 1, 4, on))  # the same notes with the bar where they put it


def test_two_trackers_that_differ_are_reported_and_the_same_grid_is_not():
    t = np.arange(41) * 0.5
    on = _on(t, [0.0, 0.5])
    assert "trackers_disagree" not in _codes(beat_hints.hints(t, 0, 4, on, trackers=(t, t + 0.02)))
    found = _hint(beat_hints.hints(t, 0, 4, on, trackers=(t, t[::2])), "trackers_disagree")
    assert 0.6 < found["score"] < 0.7  # one counts twice as fast: two beats in three are shared
    assert beat_hints.agreement(t, np.array([])) == 0.0 and beat_hints.agreement(t, t) == 1.0


def test_a_guessed_grid_and_an_empty_one():
    t = np.arange(9) * 0.5
    assert _codes(beat_hints.hints(t, 0, 4, t, tempo_estimated=True)) == ["tempo_guessed"]
    assert beat_hints.hints([], 0, 4, []) == {"tempo_bpm": None, "beats_per_bar": 4, "hints": []}
    assert beat_hints.hints(t, 0, 4, []) == {"tempo_bpm": 120.0, "beats_per_bar": 4, "hints": []}


def test_every_code_is_in_the_api_schema():
    from typing import get_args

    from scribe_engine import schemas as m

    assert set(get_args(m.BeatHintCode)) == set(beat_hints.CODES)
    from scribe_music.beats import LEVELS

    assert set(get_args(m.BeatLevel)) == set(LEVELS) and set(get_args(m.BeatSource)) == set(profiles.BEAT_SOURCES)


def test_the_hints_of_a_composition_and_of_a_tabs_notes_are_the_same(tmp_path):
    t = [i * 0.5 for i in range(41)]
    notes = [{"pitch": 60, "start": 24 * i, "dur": 24, "onset_s": 0.5 * i} for i in range(40) if not 8 < i < 14]
    comp = {"voices": [{"notes": notes}, {"notes": [{"pitch": 48, "start": 0, "dur": 96, "onset_s": None}]}],
            "meters": [{"tick": 0, "beats": 3, "beat_unit": 4}], "beat_times": t, "first_downbeat": 0, "ticks_per_beat": 24}
    tab = {"notes": notes, "meter": {"beats": 3, "beat_unit": 4}, "beat_times": t, "first_downbeat": 0, "ticks_per_beat": 24}
    found = beat_hints.of_score(comp)
    assert found == beat_hints.of_score(tab) and found["beats_per_bar"] == 3
    assert _hint(found, "held_notes")["spans"] == [[4.0, 7.0]]
    np.savetxt(tmp_path / "mix.beats", np.column_stack([t[::2], np.ones(21)]))
    written = beat_hints.write(tmp_path, tab, tmp_path / "mix.beats")
    assert written == json.loads((tmp_path / beat_hints.FILE).read_text()) == {**found, "level": "double"}


def test_a_hints_level_is_given_as_a_correction_names_it():
    assert beat_hints.level_to_send("as-tracked", "double") == "double"
    assert beat_hints.level_to_send("double", "half") == "as-tracked" and beat_hints.level_to_send("half", "double") == "as-tracked"
    assert beat_hints.level_to_send("third", "triple") == "as-tracked" and beat_hints.level_to_send("as-tracked", "half") == "half"
    assert beat_hints.level_to_send("double", "double") is None and beat_hints.level_to_send("double", "triple") is None


@needs_core
def test_a_jobs_hints_suggest_the_level_to_send(tab_client, settings):
    c = tab_client
    job = _rerun(c, _tab_job(c), {"beat": {"level": "half"}})
    hints = settings.runs_dir / job["id"] / "outputs" / "beat-hints.json"
    hints.write_text(json.dumps({"tempo_bpm": 60.0, "beats_per_bar": 4, "level": "as-tracked", "hints": [
        {"code": "notes_fast", "level": "double"}, {"code": "notes_slow", "level": "half"}, {"code": "held_notes", "spans": [[1.0, 4.0]]}]}))
    found = c.get(f"/v1/jobs/{job['id']}").json()["beat_hints"]
    assert found["level"] == "half"  # the correction's, not what the file read from the beats it was given
    assert [(h["code"], h["level"]) for h in found["hints"]] == [("notes_fast", "as-tracked"), ("notes_slow", None), ("held_notes", None)]
    assert found["hints"][2]["spans"] == [[1.0, 4.0]]


def test_a_solo_take_is_written_on_the_players_beats(tmp_path):
    """The layered arranger (a solo take) with a correction: no clean-up, no level of its own, the player's bar."""
    import shutil

    from scribe_eval import arrange_layers_song
    from scribe_eval.solo_instruments_bench import FIXTURES
    from scribe_music.beats import Correction, Hold, correct, write_beats

    song, stem = FIXTURES / "Drese_JesuGehVoran", "04_bar"
    if not (song / f"{stem}.beats").exists():
        pytest.skip("the frozen ChoraleBricks stems are not in this checkout")
    tracked = np.loadtxt(song / f"{stem}.beats", ndmin=2)

    def take(name: str, c: Correction | None) -> dict:
        layers = tmp_path / name / "layers"
        layers.mkdir(parents=True)
        for suffix, model in (("sw", "sw"), ("bp", "bp"), ("mus", "bp")):
            shutil.copy(song / f"{stem}.{model}.mid", layers / f"solo-{suffix}.mid")
        beats = song / f"{stem}.beats"
        flags: list[str] = []
        if c is not None:
            beats = tmp_path / name / "mix.beats"
            write_beats(beats, correct(tracked, c))
            flags = ["--beats-given", *c.given]
        arrange_layers_song.main(["--layers", str(layers), "--beats", str(beats), "--out", str(tmp_path / name / "out"),
                                  "--title", name, "--no-render", "--lineup", "minimal", *flags])
        return json.loads((tmp_path / name / "out" / "composition.json").read_text())

    plain = take("plain", None)
    half = take("half", Correction(level="half", beats_per_bar=3))
    assert half["beat_times"] == [float(t) for t in tracked[::2, 0]] and half["meters"][0]["beats"] == 3
    exact = take("exact", Correction(level="as-tracked", beats_per_bar=4, first_downbeat_s=float(tracked[2, 0])))
    assert exact["beat_times"] == [float(t) for t in tracked[:, 0]] and exact["meters"][0]["beats"] == 4
    assert exact["first_downbeat"] % 4 == 2
    span = (float(tracked[8, 0]), float(tracked[13, 0]))
    held = take("held", Correction(level="as-tracked", holds=(Hold(*span, 2),)))
    assert len(held["beat_times"]) == len(tracked) - 3 and not held.get("free_regions")
    moved = take("moved", Correction(first_downbeat_s=float(tracked[1, 0])))  # the engine's level and bar, the player's downbeat
    assert moved["meters"][0]["beats"] == plain["meters"][0]["beats"]
    assert abs(moved["beat_times"][moved["first_downbeat"] % moved["meters"][0]["beats"]] - tracked[1, 0]) < 1e-6 or moved["first_downbeat"] < 0


def test_the_level_the_engine_chose_is_read_from_the_beats_length():
    t = np.arange(40) * 0.6
    assert beat_hints.chosen_level(t, t) == "as-tracked"
    assert beat_hints.chosen_level(t, np.arange(79) * 0.3) == "double"
    assert beat_hints.chosen_level(t, np.arange(118) * 0.2) == "triple"
    assert beat_hints.chosen_level(t, np.delete(np.arange(79) * 0.3, [10, 11, 30])) == "double"  # beats cleaned up or held
    assert beat_hints.chosen_level(np.zeros(0), t) == "as-tracked"


@needs_core
def test_a_job_carries_its_hints_and_a_run_without_them_has_none(tab_client, settings):
    c = tab_client
    job = _tab_job(c)
    assert job["beat_hints"] == {"tempo_bpm": 120.0, "beats_per_bar": 4, "level": "as-tracked", "phase": 0, "hints": []}
    third = _rerun(c, job, {"beat": {"level": "third", "phase": 1}})
    assert (third["beat_hints"]["level"], third["beat_hints"]["phase"]) == ("third", 1)  # what to send to keep it
    assert "beat-hints.json" in job["outputs"]
    listed = next(j for j in c.get("/v1/jobs").json() if j["id"] == job["id"])
    assert listed["beat_hints"] == job["beat_hints"]
    hints = settings.runs_dir / job["id"] / "outputs" / "beat-hints.json"
    hints.unlink()  # a run made before the engine wrote them
    assert c.get(f"/v1/jobs/{job['id']}").json()["beat_hints"] is None
    hints.write_text(json.dumps({"tempo_bpm": 90.0, "beats_per_bar": 4, "hints": [{"code": "from_a_newer_engine"}, {"code": "tempo_slow", "level": "double"}]}))
    assert [h["code"] for h in c.get(f"/v1/jobs/{job['id']}").json()["beat_hints"]["hints"]] == ["tempo_slow"]
