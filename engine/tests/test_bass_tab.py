"""The bass-tab profile: its options, its stages, the notes on the beat grid, the octave check and the
fingering from the Rust core (target-fretted through `brasscribe-core fret`)."""

from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
from pathlib import Path

import numpy as np
import pytest

from brasscribe_engine import bass_tab, profiles, runner, tuning
from brasscribe_engine import schemas as m
from brasscribe_engine import stages as S
from brasscribe_engine.adapters import AdapterRegistry
from brasscribe_engine.config import Settings
from brasscribe_engine.hashing import HashIndex

REPO = Path(__file__).resolve().parents[2]
BRASS_PROFILES = ("solo", "brass-band", "pop-rock", "orchestra-with-soloist")
E1, A1, D2, G2 = 28, 33, 38, 43
BASS_4 = [G2, D2, A1, E1]


def _core_missing() -> str | None:
    try:
        bass_tab.core_cli()
    except bass_tab.CoreCliMissing as e:
        return str(e)
    return None


needs_core = pytest.mark.skipif(_core_missing() is not None, reason=_core_missing() or "")


# ---------------------------------------------------------------- options

def test_defaults_are_a_four_string_bass_in_standard_tuning_separated_from_a_song():
    assert bass_tab.options({}) == {"instrument": "bass-4", "tuning": "standard", "capo": 0, "style": "as-played",
                                    "recording": "song", "octave": "auto", "layout": "tab"}
    assert bass_tab.preset(bass_tab.options({"instrument": "bass-5", "tuning": "drop-a"})) == "bass-5-drop-a"


@pytest.mark.parametrize("params", [
    {"instrument": "guitar"}, {"instrument": "bass-7"}, {"tuning": "open-g"}, {"instrument": "bass-5", "tuning": "drop-d"},
    {"capo": -1}, {"capo": 13}, {"capo": "2"}, {"capo": True}, {"capo": 1.5}, {"style": "shred"}, {"recording": "band"},
    {"layout": "score"}, {"layout": "tab+notation"}, {"octave": "12"}, {"octave": -12}, {"octave": "-24"}, {"octave": "down"},
])
def test_values_outside_the_instrument_are_refused(params):
    with pytest.raises(ValueError):
        bass_tab.options(params)
    with pytest.raises(ValueError):
        profiles.job_options("bass-tab", params)
    with pytest.raises(ValueError):
        profiles.build("bass-tab", Path("song.wav"), params=params)


@pytest.mark.parametrize("params", [
    {"lineup": "quartet"}, {"difficulty": "easier"}, {"key": "Bb"}, {"transpose": 2}, {"seat": "eb-bass"},
    {"reads": "bass"}, {"lead": "seat"}, {"muscriptor": False},
])
def test_brass_band_options_are_refused(params):
    with pytest.raises(ValueError, match=next(iter(params))):
        profiles.job_options("bass-tab", params)


def test_the_brass_band_defaults_the_api_always_sends_are_accepted():
    sent = {"audio": True, "lineup": None, "difficulty": "faithful", "key": None, "transpose": None, "seat": None,
            "reads": None, "lead": "lineup"}
    assert profiles.job_options("bass-tab", sent) == bass_tab.options({})


@pytest.mark.parametrize("profile", BRASS_PROFILES)
@pytest.mark.parametrize("option", list(bass_tab.DEFAULTS))
def test_brass_profiles_refuse_the_fretted_options(profile, option):
    params = {option: bass_tab.DEFAULTS[option]}
    with pytest.raises(ValueError, match=option):
        profiles.job_options(profile, params)
    with pytest.raises(ValueError, match=option):
        profiles.build(profile, Path("song.wav"), params=params)


def test_a_job_that_names_no_fretted_option_has_none_in_its_parameters():
    assert bass_tab.given(instrument=None, tuning=None, capo=None, style=None, recording=None, octave=None, lineup="full") == {}
    assert bass_tab.given(instrument="bass-5", capo=0, style=None) == {"instrument": "bass-5", "capo": 0}


def test_the_instrument_table_is_target_fretteds_bass_presets():
    source = REPO / "core" / "target-fretted" / "src" / "instrument.rs"
    if not source.exists():
        pytest.skip("core/target-fretted is not in this checkout")
    ids = re.search(r"PRESET_IDS: &\[&str\] = &\[(.*?)\];", source.read_text(), re.S).group(1)
    in_crate = [i for i in re.findall(r'"([^"]+)"', ids) if i.startswith("bass-")]
    assert in_crate == [f"{inst}-{t}" for inst, tunings in bass_tab.INSTRUMENTS.items() for t in tunings]
    assert set(bass_tab.INSTRUMENTS) == set(m.FrettedInstrument.__args__)
    assert set(bass_tab.STYLES) == set(m.FingeringStyle.__args__)
    assert set(bass_tab.RECORDINGS) == set(m.Recording.__args__)
    assert set(bass_tab.OCTAVES) == set(m.Octave.__args__)
    assert set(bass_tab.LAYOUTS) == set(m.TabLayout.__args__)
    assert bass_tab.MAX_CAPO == next(x.le for x in m.JobCreate.model_fields["capo"].metadata if hasattr(x, "le"))


@needs_core
@pytest.mark.parametrize("instrument,tunings", list(bass_tab.INSTRUMENTS.items()))
def test_the_core_knows_every_instrument_and_style(instrument, tunings):
    for t, style in zip(tunings, bass_tab.STYLES * 2):
        answer = bass_tab.solve({"instrument": {"preset": f"{instrument}-{t}", "capo": bass_tab.MAX_CAPO}, "notes": [],
                                 "options": {"style": style}})
        assert len(answer["instrument"]["tuning"]["strings"]) == int(instrument[-1])
        assert [s["preset"] for s in answer["tuning_suggestions"]][0] == f"{instrument}-standard"


# ---------------------------------------------------------------- the brass paths keep their parameters

def _stages(profile: str, params: dict) -> dict:
    p = profiles.build(profile, Path("song.wav"), "T", params)
    return {s.name: (s.kind, s.params, s.inputs, s.run, s.adapter, s.code, s.outputs, s.derive) for s in p.stages}


@pytest.mark.parametrize("profile", BRASS_PROFILES)
def test_a_brass_job_from_the_api_has_the_parameters_it_had(profile, settings, audio, monkeypatch):
    from fastapi.testclient import TestClient

    from brasscribe_engine.api import create_app
    from brasscribe_engine.jobs import JobManager

    seen = {}
    monkeypatch.setattr(JobManager, "submit", lambda self, path, profile, **kw: seen.update(kw) or
                        (_ for _ in ()).throw(RuntimeError("not started")))
    with TestClient(create_app(settings), raise_server_exceptions=False) as c:
        audio_id = c.post("/v1/audio", files={"file": ("song.wav", audio.read_bytes(), "audio/wav")}).json()["audio_id"]
        c.post("/v1/jobs", json={"audio_id": audio_id, "profile": profile})
    assert seen["params"] == {"audio": True, "lineup": None, "difficulty": "faithful", "key": None, "transpose": None,
                              "seat": None, "reads": None, "lead": "lineup"}
    # ... and they build the stages of a job with no options at all: nothing of the tab options reaches a stage.
    assert _stages(profile, seen["params"]) == _stages(profile, {})
    assert set(seen["params"]).isdisjoint(bass_tab.DEFAULTS)


def test_the_cli_passes_only_the_fretted_options_that_are_given(monkeypatch, tmp_path):
    from brasscribe_engine import cli

    seen = {}
    monkeypatch.setattr(runner, "run", lambda s, audio, profile, **kw: seen.update(kw) or
                        {"run_id": "r", "status": "succeeded", "seconds": 0.0, "devices": [], "stages": []})
    monkeypatch.setenv("BRASSCRIBE_DATA", str(tmp_path))
    assert cli.main(["run", "song.wav", "--profile", "solo"]) == 0
    assert seen["params"] == {"audio": True, "lineup": None, "difficulty": "faithful", "key": None, "transpose": None,
                              "seat": None, "reads": None, "lead": "lineup"}
    assert cli.main(["run", "song.wav", "--profile", "bass-tab", "--instrument", "bass-5", "--capo", "2",
                     "--recording", "instrument", "--octave", "-12"]) == 0
    assert {k: seen["params"][k] for k in ("instrument", "capo", "recording", "octave")} == \
        {"instrument": "bass-5", "capo": 2, "recording": "instrument", "octave": "-12"}
    assert "tuning" not in seen["params"] and "style" not in seen["params"]


# ---------------------------------------------------------------- the pipeline

def test_a_song_is_separated_and_its_bass_stem_transcribed_as_in_pop_rock():
    tab = profiles.build("bass-tab", Path("song.wav"))
    assert [s.name for s in tab.stages] == ["beats", "stems", "transcribe.bass.basic-pitch", "notes", "arrange", "export"]
    pop = profiles.build("pop-rock", Path("song.wav"))
    for name in ("beats", "stems", "transcribe.bass.basic-pitch"):  # the same stages, so the same cache entries
        a, b = tab.stage(name), pop.stage(name)
        assert (a.kind, a.inputs, a.run, a.params, a.adapter, a.code, a.outputs, a.reuse_subdir, a.derive) == \
            (b.kind, b.inputs, b.run, b.params, b.adapter, b.code, b.outputs, b.reuse_subdir, b.derive), name
    assert tab.stage("transcribe.bass.basic-pitch").derive is None  # a stem's tuning estimate is not trusted
    assert set(tab.outputs) == {"tab.json", "composition.json", "tab.musicxml", "tab.pdf", "tab.mid"}


def test_a_recording_of_the_bass_alone_is_not_separated_and_is_retuned_like_any_whole_recording():
    p = profiles.build("bass-tab", Path("bass.wav"), params={"recording": "instrument"})
    assert [s.name for s in p.stages] == ["beats", "transcribe.bass.basic-pitch", "notes", "arrange", "export"]
    t = p.stage("transcribe.bass.basic-pitch")
    assert t.inputs["audio"].stage == "source" and t.derive is tuning.derive and t.run is tuning.transcribe
    assert p.stage("notes").params == {"whole_recording": True}


def test_the_instrument_is_a_parameter_of_the_fingering_stage_only():
    a = profiles.build("bass-tab", Path("song.wav"), "T")
    b = profiles.build("bass-tab", Path("song.wav"), "T", {"instrument": "bass-5", "tuning": "drop-a", "capo": 2, "style": "lead"})
    for name in ("beats", "stems", "transcribe.bass.basic-pitch", "notes"):
        assert a.stage(name).params == b.stage(name).params, name
    assert b.stage("arrange").params == {"title": "T", "layout": "tab",
                                         "fingering": {"instrument": "bass-5", "tuning": "drop-a", "capo": 2, "style": "lead"}}
    assert b.params == {"instrument": "bass-5", "tuning": "drop-a", "capo": 2, "style": "lead", "recording": "song",
                        "octave": "auto", "layout": "tab"}
    both = profiles.build("bass-tab", Path("song.wav"), "T", {"layout": "tab-and-notation"})
    assert both.stage("arrange").params["layout"] == "tab-and-notation"
    assert both.stage("notes").params == a.stage("notes").params and both.stage("export").params == a.stage("export").params


def test_a_chosen_octave_is_a_parameter_of_the_notes_stage_only():
    auto = profiles.build("bass-tab", Path("song.wav"), "T")
    assert auto.stage("notes").params == profiles.build("bass-tab", Path("song.wav"), "T", {"octave": "auto"}).stage("notes").params == {}
    for octave in ("0", "-12", "+12"):
        chosen = profiles.build("bass-tab", Path("song.wav"), "T", {"octave": octave})
        assert chosen.stage("notes").params == {"octave": octave}
        for name in ("beats", "stems", "transcribe.bass.basic-pitch", "arrange", "export"):
            assert chosen.stage(name).params == auto.stage(name).params, name
    both = profiles.build("bass-tab", Path("bass.wav"), "T", {"octave": "+12", "recording": "instrument"})
    assert both.stage("notes").params == {"whole_recording": True, "octave": "+12"}


def test_the_profile_is_listed_with_a_title_and_builds_without_the_core(monkeypatch):
    monkeypatch.setenv(bass_tab.CORE_CLI_ENV, "/nowhere/brasscribe-core")
    assert profiles.PROFILES["bass-tab"].validated is False
    assert profiles.default_title("bass-tab", Path("my_song.wav")) == "My Song — bass tab (draft)"
    assert profiles.PROFILES["bass-tab"].build("-", {}).stage("arrange").params["title"] == "-"
    with pytest.raises(bass_tab.CoreCliMissing, match="cargo build --release -p brasscribe-cli"):
        bass_tab.core_cli()


# ---------------------------------------------------------------- notes on the grid

def _beats(n: int = 17, bpm: float = 120.0, per_bar: int = 4, first_down: int = 0) -> np.ndarray:
    return np.array([[i * 60 / bpm, (i - first_down) % per_bar + 1] for i in range(n)])


def _played(pitches: list[int], step: float = 0.5, length: float = 0.45, start: float = 0.0) -> list[dict]:
    return [{"pitch": p, "onset": start + i * step, "offset": start + i * step + length} for i, p in enumerate(pitches)]


def test_quarter_notes_land_on_the_beats_with_meter_tempo_and_key():
    doc = bass_tab.transcribed_line(_played([E1, E1, 35, 40, A1, A1, 40, 45, 35, 35, 30, 35, E1, E1, 35, 40]), _beats())
    assert [n["start"] for n in doc["notes"]] == [24 * i for i in range(16)]
    assert {n["dur"] for n in doc["notes"]} == {24}
    assert [n["pitch"] for n in doc["notes"][:4]] == [E1, E1, 35, 40]
    assert doc["meter"] == {"beats": 4, "beat_unit": 4} and doc["tempo_bpm"] == 120.0
    assert doc["key"] == {"name": "E", "fifths": 4, "mode": "major"}
    assert doc["ticks_per_beat"] == 24 and doc["first_downbeat"] == 0 and len(doc["beat_times"]) == 17
    assert set(doc["notes"][0]) == {"pitch", "start", "dur", "confidence", "onset_s", "offset_s"}


def test_tick_zero_is_the_downbeat_before_the_first_note():
    # The tracker's first downbeat is beat 2; the line starts on beat 4, in the bar that began there.
    doc = bass_tab.transcribed_line(_played([E1, A1, E1, A1], start=2.0), _beats(first_down=2, per_bar=3))
    assert doc["first_downbeat"] == 2 and doc["meter"]["beats"] == 3
    assert [n["start"] for n in doc["notes"]] == [48, 72, 96, 120]
    # A note before the first tracked downbeat opens a bar of its own: nothing precedes tick 0.
    doc = bass_tab.transcribed_line(_played([E1, A1, E1, A1], start=0.5), _beats(first_down=2, per_bar=3))
    assert doc["first_downbeat"] == -1 and [n["start"] for n in doc["notes"]][0] == 48


def test_the_bottom_line_is_kept_whatever_its_register_and_the_octave_check_sees_it():
    heard = _played([76, 76, 83, 88]) + [{"pitch": 100, "onset": 0.0, "offset": 0.45}]  # far too high, with an overtone
    doc = bass_tab.transcribed_line(heard, _beats())
    assert [n["pitch"] for n in doc["notes"]] == [52, 52, 59, 64] and doc["octave_shift"] == -24
    low = bass_tab.transcribed_line(_played([E1, E1, 35, 40]), _beats())
    assert [n["pitch"] for n in low["notes"]] == [E1, E1, 35, 40] and low["octave_shift"] == 0
    assert doc["octave_source"] == low["octave_source"] == "auto"


@pytest.mark.parametrize("octave,shift", [("0", 0), ("-12", -12), ("+12", 12)])
def test_a_chosen_octave_replaces_the_check(octave, shift):
    high = [p + 12 for p in TYPICAL_LINE]  # the check would write this an octave lower
    doc = bass_tab.transcribed_line(_played(high), _beats(17), octave)
    assert (doc["octave_shift"], doc["octave_source"]) == (shift, "chosen")
    assert [n["pitch"] for n in doc["notes"]] == [p + shift for p in high]
    low = bass_tab.transcribed_line(_played(LOW_LINE), _beats(17), octave)  # and leave this one alone
    assert [n["pitch"] for n in low["notes"]] == [p + shift for p in LOW_LINE] and low["octave_source"] == "chosen"


def test_detached_notes_get_a_readable_length_and_held_ones_reach_the_next():
    doc = bass_tab.transcribed_line(_played([E1, E1], step=1.0, length=0.9) + _played([A1], start=2.0, length=0.25)
                                    + _played([E1], start=3.0, length=0.9), _beats())
    assert [(n["start"], n["dur"]) for n in doc["notes"]] == [(0, 48), (48, 48), (96, 12), (144, 48)]


@pytest.mark.parametrize("notes,beats,message", [
    ([], _beats(), "no bass notes"),
    (_played([E1]), _beats(1), "too short"),
    (_played([E1]), np.zeros((0, 2)), "too short"),
    (_played([E1]), np.array([[0.0, 1], [0.5, 2], [1.0, 3]]), "downbeats"),
])
def test_a_recording_with_nothing_to_write_says_why(notes, beats, message):
    with pytest.raises(ValueError, match=message):
        bass_tab.transcribed_line(notes, beats)


def test_reference_pitch_of_a_whole_recording_and_of_a_song(tmp_path):
    sf = pytest.importorskip("soundfile")
    sr, cents = 22050, 30.0
    t = np.arange(4 * sr) / sr
    tone = sum(np.sin(2 * np.pi * f * 2 ** (cents / 1200) * k * t) / k for f in (110.0, 164.81) for k in (1, 2, 3))
    sf.write(tmp_path / "sharp.wav", 0.2 * tone, sr)
    whole = bass_tab.reference_pitch(tmp_path / "sharp.wav", whole_recording=True)
    assert abs(whole["cents"] - cents) < 2 and whole["retuned"] is True and whole["concentration"] > 0.3
    assert bass_tab.reference_pitch(tmp_path / "sharp.wav", whole_recording=False)["retuned"] is False
    sf.write(tmp_path / "noise.wav", 0.1 * np.random.default_rng(1).standard_normal(4 * sr), sr)
    assert bass_tab.reference_pitch(tmp_path / "noise.wav", whole_recording=True) is None
    (tmp_path / "broken.wav").write_bytes(b"RIFF-fake-audio")
    assert bass_tab.reference_pitch(tmp_path / "broken.wav", whole_recording=True) is None


# ---------------------------------------------------------------- the octave check

LOW_LINE = [E1, E1, 35, 40, A1, A1, 40, 45, 31, 31, 38, 43]  # E1..A2, around the open strings


TYPICAL_LINE = [35, 35, 38, 40, 43, 43, 45, 43, 36, 36, 43, 45, 38, 38, 40, 43]  # B1..A2, median G2 - 2


@pytest.mark.parametrize("pitches,shift", [
    (LOW_LINE, 0),  # where a bass plays
    (TYPICAL_LINE, 0),
    ([p + 12 for p in TYPICAL_LINE], -12),  # heard an octave high
    ([p + 24 for p in TYPICAL_LINE], -24),  # and two
    ([p + 12 for p in LOW_LINE], 0),  # a riff on the low string heard an octave high sits where other lines do: left
    ([23, 23, 30, 35, 28, 28, 35, 40], 0),  # a line on a five-string's low B
    ([45, 47, 48, 50, 52, 50, 48, 47, 33, 33, 35, 36], 0),  # a high fill over low roots: the roots say where it is
    ([43, 43, 40, 43, 45, 43, 40, 38], 0),  # around the top open string: high for a bass, but in place
    ([46, 46, 46, 47, 45, 45, 46, 46], 0),  # a median of exactly OCTAVE_MEDIAN stays
    ([55, 57, 59, 60, 62, 64, 28, 28, 28], 0),  # too many notes would fall below a bass
    ([], 0),
])
def test_octave_shift(pitches, shift):
    assert bass_tab.octave_shift(pitches) == shift


def test_the_octave_is_decided_from_what_was_heard_not_from_the_players_instrument():
    doc = _doc([p + 12 for p in TYPICAL_LINE])
    shifts = {(bass_tab.preset(o), o["capo"]): bass_tab.fingered(doc, o, _fake_solver([]))["octave_shift"]
              for o in (bass_tab.options({}), bass_tab.options({"instrument": "bass-6"}), bass_tab.options({"capo": 5}),
                        bass_tab.options({"tuning": "bead"}))}
    assert set(shifts.values()) == {-12} and len(shifts) == 4


# ---------------------------------------------------------------- fingering

def _doc(pitches: list[int]) -> dict:
    doc = bass_tab.transcribed_line(_played(pitches), _beats(len(pitches) + 1))
    return {**doc, "reference_pitch": {"cents": 12.0, "concentration": 0.6, "retuned": False}}


def _fake_solver(seen: list[dict]):
    def solve(request: dict) -> dict:
        seen.append(request)
        strings = [{"open_pitch": p, "first_fret": 0} for p in BASS_4]
        places = [{"pitch": n["pitch"], "string": 4, "fret": n["pitch"] - E1, "alternatives": [], "out_of_range": False,
                   "pinned": False} for n in request["notes"]]
        return {"instrument": {"name": "Bass", "tuning": {"name": "Standard", "strings": strings}, "frets": 21,
                               "scale_length_mm": 864.0, "capo": request["instrument"]["capo"]},
                "fingering": {"notes": places}, "violations": [], "tuning_suggestions": []}
    return solve


def test_the_request_is_the_crates_and_the_tab_joins_each_note_with_its_place():
    seen: list[dict] = []
    tab = bass_tab.fingered(_doc(LOW_LINE), bass_tab.options({"style": "lead"}), _fake_solver(seen))
    assert len(seen) == 1 and tab["octave_shift"] == 0 and [n["pitch"] for n in seen[0]["notes"]] == LOW_LINE
    assert seen[0]["instrument"] == {"preset": "bass-4-standard", "capo": 0}
    assert seen[0]["options"] == {"style": "lead", "tempo_bpm": 120.0}
    assert all(set(n) == {"pitch", "start", "dur"} for n in seen[0]["notes"])  # the crate refuses unknown keys
    first = tab["notes"][0]
    assert (first["pitch"], first["start"], first["dur"], first["string"], first["fret"]) == (E1, 0, 24, 4, 0)
    assert first["onset_s"] == 0.0 and first["out_of_range"] is False
    m.Tab.model_validate({**tab, "layout": "tab", "adjusted_notes": 0})  # the two the MusicXML export adds
    assert tab["reference_pitch"]["cents"] == 12.0 and tab["preset"] == "bass-4-standard" and tab["style"] == "lead"


def test_a_line_heard_an_octave_high_is_fingered_an_octave_lower_and_says_so():
    seen: list[dict] = []
    tab = bass_tab.fingered(_doc([p + 12 for p in TYPICAL_LINE]), bass_tab.options({}), _fake_solver(seen))
    assert len(seen) == 1 and (tab["octave_shift"], tab["octave_source"]) == (-12, "auto")
    assert [n["pitch"] for n in seen[0]["notes"]] == TYPICAL_LINE == [n["pitch"] for n in tab["notes"]]
    comp = bass_tab.composition(tab, "Title")
    assert [n.pitch for n in comp.voices[0].notes] == TYPICAL_LINE and comp.title == "Title"
    assert (comp.meters[0].beats, comp.keys[0].fifths, comp.keys[0].mode) == (4, tab["key"]["fifths"], tab["key"]["mode"])


def test_an_answer_that_lost_notes_is_an_error():
    def half(request):
        answer = _fake_solver([])(request)
        answer["fingering"]["notes"] = answer["fingering"]["notes"][:2]
        return answer

    with pytest.raises(RuntimeError, match="placed 2 notes of 12"):
        bass_tab.fingered(_doc(LOW_LINE), bass_tab.options({}), half)


@needs_core
def test_the_core_fingers_the_line_and_suggests_the_tuning_it_sounds_like():
    line = [26, 26, 33, 38, 26, 26, 31, 33]  # down to D1: below a four-string bass in standard tuning
    tab = bass_tab.fingered(_doc(line), bass_tab.options({}))
    m.Tab.model_validate({**tab, "layout": "tab", "adjusted_notes": 0})
    assert [n["out_of_range"] for n in tab["notes"]] == [p == 26 for p in line]
    assert tab["notes"][0]["string"] is None and tab["notes"][0]["alternatives"] == []
    assert (tab["notes"][2]["string"], tab["notes"][2]["fret"]) == (3, 0)  # A1: the open A string
    assert {"string": 4, "fret": 5} in tab["notes"][2]["alternatives"]
    assert tab["violations"] == [] and tab["octave_shift"] == 0
    assert tab["tuning_suggestions"][0]["preset"] == "bass-4-drop-d"
    assert [len(tab["instrument"]["tuning"]["strings"]), tab["instrument"]["frets"]] == [4, 21]

    dropped = bass_tab.fingered(_doc(line), bass_tab.options({"tuning": "drop-d"}))
    assert not any(n["out_of_range"] for n in dropped["notes"])
    assert (dropped["notes"][0]["string"], dropped["notes"][0]["fret"]) == (4, 0)
    assert dropped["tuning_suggestions"][0]["preset"] == dropped["preset"] == "bass-4-drop-d"


@needs_core
def test_the_core_gets_the_line_an_octave_lower_and_a_capo_counts_frets_from_itself():
    tab = bass_tab.fingered(_doc([p + 12 for p in TYPICAL_LINE]), bass_tab.options({"instrument": "bass-5"}))
    assert tab["octave_shift"] == -12 and [n["pitch"] for n in tab["notes"]] == TYPICAL_LINE
    assert all(n["fret"] is not None and n["fret"] <= 7 for n in tab["notes"]) and tab["violations"] == []
    capo = bass_tab.fingered(_doc([30, 35, 40, 45]), bass_tab.options({"capo": 2}))
    assert capo["instrument"]["capo"] == 2 and [(n["string"], n["fret"]) for n in capo["notes"]] == [(4, 0), (3, 0), (2, 0), (1, 0)]


@needs_core
def test_a_request_the_core_refuses_fails_with_its_message():
    with pytest.raises(RuntimeError, match="brasscribe-core fret failed.*bass-9"):
        bass_tab.solve({"instrument": {"preset": "bass-9"}, "notes": []})


# ---------------------------------------------------------------- the tab as MusicXML

def test_the_tab_is_written_in_one_call_where_the_fingering_put_it(tmp_path):
    tab = bass_tab.fingered(_doc(LOW_LINE), bass_tab.options({"capo": 2}), _fake_solver([]))
    tab["notes"][1]["confidence"] = 0.2
    seen: list[dict] = []

    def stub(request: dict) -> dict:
        seen.append(request)
        return {"musicxml": "<score-partwise/>", "adjusted_notes": 3}

    assert bass_tab.export_tab(tab, "My song", "tab-and-notation", tmp_path, stub) == 3
    assert (tmp_path / "tab.musicxml").read_text() == "<score-partwise/>" and len(seen) == 1
    r = seen[0]
    assert set(r) == {"title", "instrument", "notes", "fingering", "tempo_bpm", "meter", "key", "tab"}  # the crate refuses others
    assert (r["title"], r["instrument"], r["tab"]) == ("My song", {"preset": "bass-4-standard", "capo": 2}, {"layout": "tab-and-notation"})
    assert (r["tempo_bpm"], r["meter"], r["key"]) == (120.0, {"beats": 4, "beat_unit": 4}, {"fifths": tab["key"]["fifths"], "mode": tab["key"]["mode"]})
    assert r["notes"][1] == {"pitch": E1, "start": 24, "dur": 24, "confidence": 0.2}
    assert r["fingering"]["notes"][2] == {"pitch": 35, "string": 4, "fret": 7, "alternatives": [], "out_of_range": False, "pinned": False}
    assert len(r["notes"]) == len(r["fingering"]["notes"]) == len(LOW_LINE)


@needs_core
@pytest.mark.parametrize("layout,tab_staff,notation_staff", [("tab", True, False), ("tab-and-notation", True, True),
                                                             ("notation", False, True)])
def test_the_core_writes_each_layout_with_the_title_and_the_frets_of_the_tab(layout, tab_staff, notation_staff, tmp_path):
    tab = bass_tab.fingered(_doc(LOW_LINE), bass_tab.options({}))
    tab["notes"][2].update(string=4, fret=7)  # as a player moved it: B1 on the E string, not the A string's 2nd fret
    assert bass_tab.export_tab(tab, "Low & slow", layout, tmp_path) == 0
    xml = (tmp_path / "tab.musicxml").read_text()
    assert "<work-title>Low &amp; slow</work-title>" in xml
    assert ("<sign>TAB</sign>" in xml) == tab_staff and ("<sign>F</sign>" in xml) == notation_staff
    if tab_staff:
        assert re.search(r"<string>4</string>\s*<fret>7</fret>|<fret>7</fret>\s*<string>4</string>", xml)
    assert xml.count("<note") >= len(LOW_LINE)


def test_a_long_title_is_cut_to_the_page_and_the_job_keeps_its_name(tmp_path):
    assert bass_tab.page_title("Old Hundredth") == "Old Hundredth"
    assert bass_tab.page_title("  Old\tHundredth \n take\x01 2 ") == "Old Hundredth take 2"
    words = "All people that on earth do dwell, sing to the Lord with cheerful voice"
    assert bass_tab.page_title(words) == "All people that on earth do dwell, sing to the…"
    unbroken = bass_tab.page_title("x" * 200)
    assert unbroken == "x" * 47 + "…" and len(unbroken) == bass_tab.PAGE_TITLE_MAX
    assert bass_tab.page_title("y" * 30 + " " + "z" * 100) == "y" * 30 + "…"  # cut at the word

    tab = bass_tab.fingered(_doc(LOW_LINE), bass_tab.options({}), _fake_solver([]))
    seen: list[dict] = []
    bass_tab.export_tab(tab, "x" * 200, "tab", tmp_path, lambda r: seen.append(r) or {"musicxml": "<x/>", "adjusted_notes": 0})
    assert seen[0]["title"] == unbroken
    assert bass_tab.composition(tab, "x" * 200).title == "x" * 200


def test_the_export_is_keyed_on_the_musescore_that_would_render_it(tmp_path, monkeypatch):
    from brasscribe_music import musescore

    def key() -> dict:
        return profiles.build("bass-tab", Path("song.wav"), "T").stage("export").params

    monkeypatch.setattr(musescore, "binary", lambda: None)
    assert key() == {"musescore": None}
    exe = tmp_path / "mscore"
    exe.write_text("#!/bin/sh\n")
    exe.chmod(0o755)
    monkeypatch.setattr(musescore, "binary", lambda: str(exe))
    installed = key()["musescore"]
    assert installed and key()["musescore"] == installed and str(tmp_path) not in installed
    exe.write_text("#!/bin/sh\n# an update\n")
    assert key()["musescore"] not in (None, installed)
    monkeypatch.setattr(musescore, "binary", lambda: str(tmp_path / "gone"))
    assert key() == {"musescore": None}
    for name in ("beats", "stems", "transcribe.bass.basic-pitch", "notes", "arrange"):  # only the export
        assert "musescore" not in profiles.build("bass-tab", Path("song.wav"), "T").stage(name).params


@needs_core
def test_a_run_made_without_musescore_is_rendered_once_it_is_installed(settings, audio, monkeypatch, tmp_path):
    from brasscribe_music import musescore

    monkeypatch.setattr(S, "beats", lambda ctx: np.savetxt(ctx.out / "mix.beats", _beats(25), fmt=["%.3f", "%d"]))
    monkeypatch.setattr(tuning, "transcribe", lambda ctx: _write_midi(ctx.out / ctx.params["output"], _played(TYPICAL_LINE)))
    monkeypatch.setattr(musescore, "binary", lambda: None)
    without = runner.run(settings, audio, "bass-tab", params={"recording": "instrument"})
    assert without["status"] == "succeeded" and "tab.pdf" not in without["outputs"] and "tab.musicxml" in without["outputs"]

    exe = tmp_path / "mscore"
    exe.write_text("#!/bin/sh\n")
    exe.chmod(0o755)
    monkeypatch.setattr(musescore, "binary", lambda: str(exe))
    monkeypatch.setattr(musescore, "convert_many", lambda jobs: [Path(d).write_bytes(b"rendered") for _, ds in jobs for d in ds] and [])
    installed = runner.run(settings, audio, "bass-tab", params={"recording": "instrument"})
    assert {s["stage"]: s["status"] for s in installed["stages"]} == {
        "beats": "cached", "transcribe.bass.basic-pitch": "cached", "notes": "cached", "arrange": "cached", "export": "ran"}
    assert {"tab.pdf", "tab.mid"} <= set(installed["outputs"])
    again = runner.run(settings, audio, "bass-tab", params={"recording": "instrument"})
    assert again["stages"][-1]["status"] == "cached" and "tab.pdf" in again["outputs"]


def test_renaming_a_run_never_writes_a_control_character_into_its_musicxml(settings, audio, monkeypatch):
    from xml.etree import ElementTree

    from brasscribe_engine.jobs import JobManager, _retitle_musicxml

    for xml in ("<score-partwise><work><work-title>Old</work-title></work></score-partwise>", "<score-partwise/>",
                '<score-partwise version="4.0"><part-list/></score-partwise>'):
        renamed = _retitle_musicxml(xml, "a\x01b\x7f \x00c\td\ne & <f>")
        assert ElementTree.fromstring(renamed).findtext("work/work-title") == "ab c d e & <f>"

    jobs = JobManager(settings)
    m1 = runner.run(settings, audio, "test")  # a band job: brass-band.musicxml
    out = settings.runs_dir / m1["run_id"] / "outputs"
    (out / "brass-band.musicxml").write_text("<score-partwise><work><work-title>Old</work-title></work></score-partwise>")
    (out / "tab.musicxml").write_text("<score-partwise><work><work-title>Old</work-title></work></score-partwise>")
    assert jobs.rename(m1["run_id"], "a\x01b " + "x" * 200) == "renamed"
    band = ElementTree.parse(out / "brass-band.musicxml").findtext("work/work-title")
    tab = ElementTree.parse(out / "tab.musicxml").findtext("work/work-title")
    assert band == "ab " + "x" * 200  # the band score keeps the whole title, as before
    assert tab == bass_tab.page_title("ab " + "x" * 200) and len(tab) == bass_tab.PAGE_TITLE_MAX
    jobs.shutdown()


def test_without_musescore_the_export_says_what_it_skipped(tmp_path, monkeypatch):
    from types import SimpleNamespace

    from brasscribe_music import musescore

    monkeypatch.setattr(musescore, "binary", lambda: None)
    (tmp_path / "score").mkdir()
    (tmp_path / "score" / "tab.musicxml").write_text("<score-partwise/>")
    said: list[str] = []
    ctx = SimpleNamespace(out=tmp_path, inputs={"score": tmp_path / "score"}, log=said.append, stage=SimpleNamespace(name="export"),
                          params={"musescore": None})
    bass_tab.export_stage(ctx)
    assert json.loads((tmp_path / "export.json").read_text()) == {"musescore": None, "written": [], "skipped": ["tab.pdf", "tab.mid"]}
    assert said == ["mscore not found: PDF and MIDI skipped"]

    # With a MuseScore that writes one of the two files, the stage fails and names the other.
    monkeypatch.setattr(musescore, "binary", lambda: "mscore")
    ctx.params = {"musescore": "0123456789abcdef"}
    monkeypatch.setattr(musescore, "convert_many", lambda jobs: [Path(jobs[0][1][1])])
    with pytest.raises(bass_tab.StageFailed, match="MuseScore did not write tab.mid"):
        bass_tab.export_stage(ctx)
    monkeypatch.setattr(musescore, "convert_many", lambda jobs: [])
    bass_tab.export_stage(ctx)
    assert json.loads((tmp_path / "export.json").read_text()) == {"musescore": "mscore", "written": ["tab.pdf", "tab.mid"], "skipped": []}


# ---------------------------------------------------------------- end to end

def _write_midi(path: Path, notes: list[dict]) -> None:
    import pretty_midi

    pm = pretty_midi.PrettyMIDI()
    inst = pretty_midi.Instrument(program=33)
    inst.notes = [pretty_midi.Note(velocity=90, pitch=n["pitch"], start=n["onset"], end=n["offset"]) for n in notes]
    pm.instruments.append(inst)
    pm.write(str(path))


@needs_core
def test_a_job_runs_to_a_tab_the_api_serves(settings, audio, monkeypatch):
    """The symbolic stages and the core for real, with the models' outputs written in their place."""
    from fastapi.testclient import TestClient

    from brasscribe_engine.api import create_app

    from brasscribe_music import musescore

    heard = _played([p + 12 for p in TYPICAL_LINE])
    monkeypatch.setattr(musescore, "binary", lambda: None)  # the rendering has a test of its own
    monkeypatch.setattr(S, "beats", lambda ctx: np.savetxt(ctx.out / "mix.beats", _beats(25), fmt=["%.3f", "%d"]))
    monkeypatch.setattr(tuning, "transcribe", lambda ctx: _write_midi(ctx.out / ctx.params["output"], heard))
    with TestClient(create_app(settings)) as c:
        audio_id = c.post("/v1/audio", files={"file": ("my_bass.wav", audio.read_bytes(), "audio/wav")}).json()["audio_id"]
        r = c.post("/v1/jobs", json={"audio_id": audio_id, "profile": "bass-tab", "recording": "instrument",
                                     "instrument": "bass-5", "style": "open-position"})
        assert r.status_code == 202 and r.json()["title"] == "My Bass — bass tab (draft)"
        job = _wait(c, r.json()["id"])
        assert job["status"] == "succeeded", job["error"]
        assert [s["name"] for s in job["stages"]] == ["beats", "transcribe.bass.basic-pitch", "notes", "arrange", "export"]
        assert job["outputs"] == ["composition.json", "tab.json", "tab.musicxml"]

        tab = c.get(f"/v1/jobs/{job['id']}/tab")
        assert tab.status_code == 200 and tab.headers["content-type"] == "application/json"
        tab = m.Tab.model_validate(tab.json())
        assert tab.preset == "bass-5-standard" and tab.style == "open-position" and tab.octave_shift == -12
        assert [n.pitch for n in tab.notes] == TYPICAL_LINE and not tab.violations
        assert all(n.string and n.fret is not None and n.fret <= 5 for n in tab.notes)
        assert tab.tuning_suggestions[0].preset == "bass-5-standard" and tab.reference_pitch is None
        assert (tab.layout, tab.adjusted_notes) == ("tab", 0)
        xml = c.get(f"/v1/jobs/{job['id']}/musicxml")
        assert xml.status_code == 200 and xml.headers["content-type"].startswith("application/vnd.recordare.musicxml")
        assert "<work-title>My Bass — bass tab (draft)</work-title>" in xml.text and "<sign>TAB</sign>" in xml.text
        assert c.get(f"/v1/jobs/{job['id']}/artifacts/tab.musicxml").text == xml.text
        assert c.get(f"/v1/jobs/{job['id']}/pdf").status_code == 404  # no MuseScore here
        assert c.patch(f"/v1/runs/{job['id']}", json={"title": "Renamed"}).status_code == 200
        assert "<work-title>Renamed</work-title>" in c.get(f"/v1/jobs/{job['id']}/musicxml").text
        assert (tab.tempo_bpm, tab.meter.beats) == (120.0, 4)

        comp = c.get(f"/v1/jobs/{job['id']}/composition").json()
        assert comp["title"] == "Renamed" and [v["role"] for v in comp["voices"]] == ["bass"]
        assert [n["pitch"] for n in comp["voices"][0]["notes"]] == TYPICAL_LINE
        assert (comp["keys"][0]["fifths"], comp["keys"][0]["mode"]) == (tab.key.fifths, tab.key.mode)
        manifest = c.get(f"/v1/jobs/{job['id']}/manifest").json()
        assert manifest["params"] == {"instrument": "bass-5", "tuning": "standard", "capo": 0, "style": "open-position",
                                      "recording": "instrument", "octave": "auto", "layout": "tab"}

        # The player says the line is where it was heard: the notes are written again, not transcribed again.
        kept = c.post("/v1/jobs", json={"audio_id": audio_id, "profile": "bass-tab", "recording": "instrument",
                                        "instrument": "bass-5", "octave": "0"})
        kept = _wait(c, kept.json()["id"])
        assert {s["name"]: s["status"] for s in kept["stages"]} == {
            "beats": "cached", "transcribe.bass.basic-pitch": "cached", "notes": "ran", "arrange": "ran", "export": "ran"}
        chosen = m.Tab.model_validate(c.get(f"/v1/jobs/{kept['id']}/tab").json())
        assert (chosen.octave_shift, chosen.octave_source, tab.octave_source) == (0, "chosen", "auto")
        assert [n.pitch for n in chosen.notes] == [p + 12 for p in TYPICAL_LINE]
        assert c.post("/v1/jobs", json={"audio_id": audio_id, "profile": "bass-tab", "octave": "-24"}).status_code == 422

        # Another tuning for the same song: only the fingering runs again.
        again = c.post("/v1/jobs", json={"audio_id": audio_id, "profile": "bass-tab", "recording": "instrument",
                                         "instrument": "bass-4", "tuning": "drop-d"})
        again = _wait(c, again.json()["id"])
        assert {s["name"]: s["status"] for s in again["stages"]} == {
            "beats": "cached", "transcribe.bass.basic-pitch": "cached", "notes": "cached", "arrange": "ran", "export": "ran"}

        # Notation above the tab: the fingering stage writes the page again, and the tab says which.
        paged = c.post("/v1/jobs", json={"audio_id": audio_id, "profile": "bass-tab", "recording": "instrument",
                                         "instrument": "bass-4", "tuning": "drop-d", "layout": "tab-and-notation"})
        paged = _wait(c, paged.json()["id"])
        assert paged["status"] == "succeeded" and m.Tab.model_validate(c.get(f"/v1/jobs/{paged['id']}/tab").json()).layout == "tab-and-notation"
        assert "<staves>2</staves>" in c.get(f"/v1/jobs/{paged['id']}/musicxml").text
        assert c.post("/v1/jobs", json={"audio_id": audio_id, "profile": "bass-tab", "layout": "grand-staff"}).status_code == 422

        refused = c.post("/v1/jobs", json={"audio_id": audio_id, "profile": "bass-tab", "instrument": "bass-5", "tuning": "bead"})
        assert refused.status_code == 422 and refused.json()["code"] == "invalid_options"
        assert c.post("/v1/jobs", json={"audio_id": audio_id, "profile": "bass-tab", "instrument": "guitar"}).status_code == 422
        assert c.post("/v1/jobs", json={"audio_id": audio_id, "profile": "bass-tab", "lineup": "quartet"}).status_code == 422
        brass = c.post("/v1/jobs", json={"audio_id": audio_id, "profile": "test", "capo": 2})
        assert brass.status_code == 422 and brass.json()["code"] == "invalid_options"
        other = c.post("/v1/jobs", json={"audio_id": audio_id, "profile": "test"}).json()
        _wait(c, other["id"])
        assert c.get(f"/v1/jobs/{other['id']}/tab").status_code == 404


def test_a_job_without_the_core_fails_at_the_fingering_and_says_how_to_get_it(settings, audio, monkeypatch):
    monkeypatch.setenv(bass_tab.CORE_CLI_ENV, str(settings.data_dir / "no-such-core"))
    monkeypatch.setattr(S, "beats", lambda ctx: np.savetxt(ctx.out / "mix.beats", _beats(25), fmt=["%.3f", "%d"]))
    monkeypatch.setattr(tuning, "transcribe", lambda ctx: _write_midi(ctx.out / ctx.params["output"], _played(LOW_LINE)))
    manifest = runner.run(settings, audio, "bass-tab", params={"recording": "instrument"})
    assert manifest["status"] == "failed" and manifest["error"].startswith("arrange: ")
    assert "cargo build --release -p brasscribe-cli" in manifest["error"]
    assert [s["status"] for s in manifest["stages"]] == ["ran", "ran", "ran", "failed"]


def test_a_job_is_refused_at_submit_when_the_core_is_missing_and_the_profile_stays_listed(settings, audio, monkeypatch):
    from fastapi.testclient import TestClient

    from brasscribe_engine.api import create_app

    missing = settings.data_dir / "no-such-core"
    monkeypatch.setenv(bass_tab.CORE_CLI_ENV, str(missing))
    with pytest.raises(profiles.OptionError) as refused:
        profiles.job_options("bass-tab", {})
    assert refused.value.code == profiles.CORE_MISSING_CODE == "core_missing"
    assert profiles.build("bass-tab", Path("song.wav")).stage("arrange").params["title"]  # building needs no core
    with TestClient(create_app(settings)) as c:
        assert "bass-tab" in {p["name"] for p in c.get("/v1/profiles").json()}
        audio_id = c.post("/v1/audio", files={"file": ("song.wav", audio.read_bytes(), "audio/wav")}).json()["audio_id"]
        r = c.post("/v1/jobs", json={"audio_id": audio_id, "profile": "bass-tab"})
        assert r.status_code == 422 and r.json()["code"] == "core_missing"
        assert "cargo build --release -p brasscribe-cli" in r.json()["detail"] and str(missing.parent) not in r.text
        assert c.get("/v1/jobs").json() == []  # nothing was started
        # A wrong option is still the first thing said, and the band profiles do not need the core.
        bad = c.post("/v1/jobs", json={"audio_id": audio_id, "profile": "bass-tab", "instrument": "bass-5", "tuning": "bead"})
        assert bad.json()["code"] == "invalid_options"
        assert c.post("/v1/jobs", json={"audio_id": audio_id, "profile": "test"}).status_code == 202


def test_the_cli_refuses_the_run_before_any_model_when_the_core_is_missing(monkeypatch, tmp_path, capsys):
    from brasscribe_engine import cli

    monkeypatch.setenv(bass_tab.CORE_CLI_ENV, str(tmp_path / "no-such-core"))
    monkeypatch.setenv("BRASSCRIBE_DATA", str(tmp_path))
    monkeypatch.setattr(runner, "run", lambda *a, **kw: pytest.fail("the run was started"))
    assert cli.main(["run", "song.wav", "--profile", "bass-tab"]) == 3
    assert "cargo build --release -p brasscribe-cli" in capsys.readouterr().err


@pytest.mark.skipif(os.name == "nt", reason="POSIX permissions and scripts")
def test_a_core_that_cannot_run_is_missing_and_one_that_cannot_start_fails_without_its_path(tmp_path, monkeypatch):
    plain = tmp_path / "private-folder" / "brasscribe-core"
    plain.parent.mkdir()
    plain.write_text("not a program")
    monkeypatch.setenv(bass_tab.CORE_CLI_ENV, str(plain))
    with pytest.raises(bass_tab.CoreCliMissing) as e:  # not executable: refused at submit, like a missing one
        bass_tab.solve({"instrument": {"preset": "bass-4-standard"}, "notes": []})
    assert "private-folder" not in str(e.value)
    plain.chmod(0o755)  # executable, but not a program: the system refuses to start it
    with pytest.raises(RuntimeError, match="could not be started") as e:
        bass_tab.solve({"instrument": {"preset": "bass-4-standard"}, "notes": []})
    assert "private-folder" not in str(e.value) and not isinstance(e.value, bass_tab.CoreCliMissing)


@pytest.mark.skipif(os.name == "nt", reason="a shell script stands in for the core")
def test_a_core_that_fails_or_hangs_is_reported_and_stopped(tmp_path, monkeypatch):
    import threading
    import time

    core = tmp_path / "private-folder" / "brasscribe-core"
    core.parent.mkdir()
    core.write_text('#!/bin/sh\necho "$3: no such preset" >&2\nexit 1\n')
    core.chmod(0o755)
    monkeypatch.setenv(bass_tab.CORE_CLI_ENV, str(core))
    with pytest.raises(RuntimeError, match="fret failed.*no such preset") as e:
        bass_tab.solve({"instrument": {"preset": "x"}, "notes": []})
    assert "./request.json" in str(e.value) and tempfile.gettempdir() not in str(e.value)  # the temp folder is not named

    core.write_text("#!/bin/sh\nexec sleep 60\n")
    monkeypatch.setattr(bass_tab, "FRET_TIMEOUT_S", 0.3)
    t0 = time.monotonic()
    with pytest.raises(RuntimeError, match="time limit"):
        bass_tab.solve({"instrument": {"preset": "x"}, "notes": []})
    assert time.monotonic() - t0 < 10

    monkeypatch.setattr(bass_tab, "FRET_TIMEOUT_S", 600.0)
    cancel = threading.Event()
    threading.Timer(0.3, cancel.set).start()
    t0 = time.monotonic()
    with pytest.raises(RuntimeError, match="cancelled"):
        bass_tab.solve({"instrument": {"preset": "x"}, "notes": []}, cancel)
    assert time.monotonic() - t0 < 10


@pytest.mark.skipif(os.name == "nt", reason="a shell script stands in for the core")
def test_a_core_from_the_path_is_named_in_the_engines_log_and_only_mentioned_in_the_jobs(tmp_path, monkeypatch, capsys):
    core = tmp_path / "private-folder" / "brasscribe-core"
    core.parent.mkdir()
    core.write_text('#!/bin/sh\necho \'{"ok": true}\' > "$5"\n')
    core.chmod(0o755)
    monkeypatch.delenv(bass_tab.CORE_CLI_ENV, raising=False)
    monkeypatch.setattr(bass_tab, "REPO_ROOT", tmp_path / "no-checkout")
    monkeypatch.setenv("PATH", f"{core.parent}{os.pathsep}{os.environ['PATH']}")
    said: list[str] = []
    assert bass_tab.solve({"notes": []}, log=said.append) == {"ok": True}
    assert said == ["brasscribe-core taken from the PATH"]
    assert str(core) in capsys.readouterr().err
    monkeypatch.setenv(bass_tab.CORE_CLI_ENV, str(core))  # named: nothing to say
    said.clear()
    assert bass_tab.solve({"notes": []}, log=said.append) == {"ok": True} and said == []


def _mscore_missing() -> str | None:
    from brasscribe_music import musescore

    return _core_missing() or (None if musescore.available() else "MuseScore is not installed: the tab's PDF and MIDI are not rendered")


@pytest.mark.slow
@pytest.mark.skipif(_mscore_missing() is not None, reason=_mscore_missing() or "")
def test_a_job_renders_the_tab_as_pdf_and_midi_and_serves_them(settings, audio, monkeypatch):
    """The core and MuseScore for real, with the models' outputs written in their place."""
    from fastapi.testclient import TestClient

    from brasscribe_engine.api import create_app

    monkeypatch.setattr(S, "beats", lambda ctx: np.savetxt(ctx.out / "mix.beats", _beats(25), fmt=["%.3f", "%d"]))
    monkeypatch.setattr(tuning, "transcribe", lambda ctx: _write_midi(ctx.out / ctx.params["output"], _played(TYPICAL_LINE)))
    with TestClient(create_app(settings)) as c:
        audio_id = c.post("/v1/audio", files={"file": ("old_hundredth.wav", audio.read_bytes(), "audio/wav")}).json()["audio_id"]
        job = c.post("/v1/jobs", json={"audio_id": audio_id, "profile": "bass-tab", "recording": "instrument"}).json()
        job = _wait(c, job["id"], timeout=300)
        assert job["status"] == "succeeded", job["error"]
        assert job["outputs"] == ["composition.json", "tab.json", "tab.mid", "tab.musicxml", "tab.pdf"]
        pdf = c.get(f"/v1/jobs/{job['id']}/pdf")
        assert pdf.status_code == 200 and pdf.headers["content-type"] == "application/pdf" and pdf.content[:5] == b"%PDF-"
        midi = c.get(f"/v1/jobs/{job['id']}/midi")
        assert midi.status_code == 200 and midi.content[:4] == b"MThd"
        import io

        import pretty_midi

        played = [n.pitch for i in pretty_midi.PrettyMIDI(io.BytesIO(midi.content)).instruments for n in i.notes]
        assert played == TYPICAL_LINE  # the bass line at the pitches the tab is written at
        assert {a["name"] for a in c.get(f"/v1/jobs/{job['id']}/artifacts").json()} == set(job["outputs"])


def _wait(client, job_id: str, timeout: float = 60) -> dict:
    import time

    t0 = time.time()
    while time.time() - t0 < timeout:
        job = client.get(f"/v1/jobs/{job_id}").json()
        if job["status"] in ("succeeded", "failed", "cancelled"):
            return job
        time.sleep(0.05)
    raise AssertionError("job did not finish")


def _models_missing() -> str | None:
    """Why the models cannot run here, or None: the adapters' launcher, their environments and Beat This!'s weights."""
    s = Settings()
    registry = AdapterRegistry(s.adapters_dir, s.models_dir, HashIndex(None))
    if not shutil.which("uv") and not shutil.which("pixi"):
        return "neither uv nor pixi is installed: the model adapters cannot start"
    for name in ("beat-this", "basic-pitch"):
        if not (registry.dir(name) / "pyproject.toml").exists():
            return f"the {name} adapter is not in this checkout (ml/adapters/{name})"
        absent = [f["name"] for f in registry.models(name) if not f["present"]]
        if absent:
            return f"{name}'s weights are not downloaded ({', '.join(absent)}): run the adapter once with network access"
    return _core_missing()


@pytest.mark.slow
@pytest.mark.skipif(_models_missing() is not None, reason=_models_missing() or "")
def test_a_synthetic_bass_take_becomes_a_playable_tab(tmp_path, monkeypatch):
    """Beat This!, Basic Pitch and the core on a synthesized line: E1 A1 D2 G2 (the open strings) in quarters."""
    sf = pytest.importorskip("soundfile")
    sr, bpm, line = 22050, 100.0, [E1, A1, D2, G2] * 6
    beat = 60 / bpm
    audio = np.zeros(int((len(line) + 2) * beat * sr))
    t = np.arange(int(0.9 * beat * sr)) / sr
    for i, pitch in enumerate(line):
        f = 440 * 2 ** ((pitch - 69) / 12)
        tone = sum(np.sin(2 * np.pi * f * k * t) / k for k in range(1, 9)) * np.exp(-3 * t)  # a plucked string, roughly
        tone[: int(0.005 * sr)] *= np.linspace(0, 1, int(0.005 * sr))
        at = int((i + 1) * beat * sr)
        audio[at:at + len(tone)] += 0.25 * tone
    take = tmp_path / "open-strings.wav"
    sf.write(take, audio, sr)
    monkeypatch.setenv("BRASSCRIBE_DATA", str(tmp_path / "data"))
    settings = Settings(models_override=Settings().models_dir)
    manifest = runner.run(settings, take, "bass-tab", params={"recording": "instrument"}, out=tmp_path / "out")
    assert manifest["status"] == "succeeded", manifest.get("error")
    tab = m.Tab.model_validate_json((tmp_path / "out" / "tab.json").read_text())
    assert not tab.violations and not any(n.out_of_range for n in tab.notes)
    assert 0.75 * len(line) <= len(tab.notes) <= 1.25 * len(line)
    played = [n.pitch for n in tab.notes]
    assert sum(p in (E1, A1, D2, G2) for p in played) >= 0.75 * len(played)
    assert sum(n.fret == 0 for n in tab.notes) >= 0.75 * len(tab.notes)  # the open strings
    assert 95 <= tab.tempo_bpm <= 105 or 190 <= tab.tempo_bpm <= 210 or 47 <= tab.tempo_bpm <= 53
