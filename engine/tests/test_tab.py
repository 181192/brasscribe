"""The tab profile: one path for every fretted instrument. Its options and presets, the bass as the
bass-tab profile's own pipeline, and a guitar's notes: chords and lines, read differently."""

from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import pytest

from brasscribe_engine import bass_tab, profiles, runner, tab, tuning
from brasscribe_engine import schemas as m
from brasscribe_engine import stages as S

REPO = Path(__file__).resolve().parents[2]
E2, A2, D3, G3, B3, E4 = 40, 45, 50, 55, 59, 64
OPEN_E = [E2, 47, 52, 56, B3, E4]  # an open E major chord, low string first
OPEN_G = [43, 47, D3, G3, B3, 67]


def _core_missing() -> str | None:
    try:
        bass_tab.core_cli()
    except bass_tab.CoreCliMissing as e:
        return str(e)
    return None


needs_core = pytest.mark.skipif(_core_missing() is not None, reason=_core_missing() or "")


def _note(pitch: int, onset: float, length: float = 0.45, amplitude: float = 0.7) -> dict:
    return {"pitch": pitch, "onset": onset, "offset": onset + length, "amplitude": amplitude}


def _beats(n: int = 33, bpm: float = 120.0) -> np.ndarray:
    return np.array([[i * 60 / bpm, i % 4 + 1] for i in range(n)])


def _strummed(chords: list[list[int]], step: float = 1.0, spread: float = 0.008, amplitude: float = 0.7) -> list[dict]:
    """Each chord struck once, low string first, the pick crossing the strings."""
    return [_note(p, i * step + k * spread, 0.9 * step, amplitude) for i, chord in enumerate(chords) for k, p in enumerate(chord)]


# ---------------------------------------------------------------- instruments and options

def test_the_instrument_table_is_every_preset_of_target_fretted():
    source = REPO / "core" / "target-fretted" / "src" / "instrument.rs"
    if not source.exists():
        pytest.skip("core/target-fretted is not in this checkout")
    text = source.read_text()
    ids = re.findall(r'"([^"]+)"', re.search(r"PRESET_IDS: &\[&str\] = &\[(.*?)\];", text, re.S).group(1))
    families = re.findall(r'"([^"]+)"', re.search(r"const FAMILIES: &\[&str\] = &\[(.*?)\];", text).group(1))
    ours = {tab.preset({"instrument": i, "tuning": t}): (i, t) for i, tunings in tab.TUNINGS.items() for t in tunings}
    assert sorted(ours) == sorted(ids) and len(ours) == sum(map(len, tab.TUNINGS.values()))  # one to one
    assert sorted(tab.FAMILIES.values()) == sorted(families) and set(tab.FAMILIES) == set(tab.TUNINGS)
    for family in families:  # each instrument's first tuning is its family's first preset: the standard one
        instrument = next(i for i, f in tab.FAMILIES.items() if f == family)
        first = next(i for i in ids if i == family or (i.startswith(family + "-") and not any(
            i.startswith(longer + "-") for longer in families if len(longer) > len(family) and longer.startswith(family))))
        assert tab.preset({"instrument": instrument, "tuning": tab.TUNINGS[instrument][0]}) == first, family
    assert set(tab.TUNINGS) == set(m.FrettedInstrument.__args__)
    assert set(tab.HEARD) == set(tab.TUNINGS) - set(bass_tab.INSTRUMENTS)
    assert {h.strings for i, h in tab.HEARD.items() if i.startswith("guitar")} == {6, 7, 8}


@pytest.mark.parametrize("instrument,tuning,preset", [
    ("guitar-6", "standard", "guitar-standard"), ("guitar-6", "drop-d", "guitar-drop-d"), ("guitar-6", "dadgad", "guitar-dadgad"),
    ("guitar-7", "eb-standard", "guitar-7-eb-standard"), ("guitar-8", "standard", "guitar-8-standard"),
    ("ukulele", "high-g", "ukulele-high-g"), ("ukulele", "low-g", "ukulele-low-g"), ("ukulele-baritone", "standard", "ukulele-baritone"),
    ("mandolin", "standard", "mandolin"), ("bass-5", "drop-a", "bass-5-drop-a"),
])
def test_an_instrument_and_tuning_name_one_preset(instrument, tuning, preset):
    opts = tab.options({"instrument": instrument, "tuning": tuning, "recording": "instrument"})
    assert tab.preset(opts) == preset and (opts["instrument"], opts["tuning"]) == (instrument, tuning)


def test_defaults_are_a_six_string_guitar_in_a_song_and_each_instruments_first_tuning():
    assert tab.options({}) == {"instrument": "guitar-6", "tuning": "standard", "capo": 0, "style": "as-played", "recording": "song",
                               "octave": "auto", "layout": "tab"}
    assert tab.options({"instrument": "ukulele", "recording": "instrument"})["tuning"] == "high-g"
    assert tab.options({"instrument": "bass-4"}) == {**bass_tab.options({}), "instrument": "bass-4"}
    assert set(tab.options({})) == set(bass_tab.DEFAULTS)  # the same option names as bass-tab: no new field for clients


@pytest.mark.parametrize("params", [
    {"instrument": "banjo"}, {"instrument": "guitar"}, {"instrument": "guitar-6", "tuning": "bead"},
    {"instrument": "ukulele", "tuning": "standard"}, {"instrument": "mandolin", "tuning": "high-g"},
    {"instrument": "guitar-7", "tuning": "drop-d"}, {"capo": 13}, {"capo": -1}, {"capo": "2"}, {"capo": True}, {"style": "shred"},
    {"recording": "band"}, {"octave": "24"}, {"layout": "score"},
    {"lineup": "quartet"}, {"difficulty": "easier"}, {"key": "Bb"}, {"transpose": 2}, {"seat": "eb-bass"}, {"muscriptor": False},
])
def test_what_does_not_fit_the_instrument_is_refused(params):
    with pytest.raises(ValueError):
        tab.options(params)
    with pytest.raises(ValueError):
        profiles.build("tab", Path("song.wav"), params=params)


@pytest.mark.parametrize("instrument", ["ukulele", "ukulele-baritone", "mandolin"])
def test_a_ukulele_or_mandolin_is_taken_alone_and_not_yet_from_a_song(instrument):
    assert tab.options({"instrument": instrument})["recording"] == "instrument"  # the simplest request works: taken alone
    assert profiles.build("tab", Path("uke.wav"), params={"instrument": instrument}).params["recording"] == "instrument"
    with pytest.raises(ValueError, match="recording of .* must be instrument"):
        tab.options({"instrument": instrument, "recording": "song"})  # which stem carries it in a song is not measured
    p = profiles.build("tab", Path("uke.wav"), params={"instrument": instrument, "recording": "instrument"})
    assert [s.name for s in p.stages][1] == f"transcribe.{tab.HEARD[instrument].kind}.basic-pitch"


@pytest.mark.parametrize("profile", ["solo", "brass-band", "pop-rock", "orchestra-with-soloist"])
def test_the_band_profiles_still_refuse_the_tab_options(profile):
    for params in ({"instrument": "guitar-6"}, {"capo": 2}, {"layout": "tab"}):
        with pytest.raises(ValueError, match=f"only the tab profile takes this, not {profile}"):
            profiles.job_options(profile, params)
        with pytest.raises(ValueError):
            profiles.build(profile, Path("song.wav"), params=params)


def test_both_profile_ids_are_tab_profiles_and_bass_tab_keeps_its_own_instruments():
    assert tab.is_tab("tab") and tab.is_tab("bass-tab") and not tab.is_tab("pop-rock")
    assert tab.job_options("bass-tab", {}) == bass_tab.options({}) and tab.job_options("tab", {}) == tab.options({})
    with pytest.raises(ValueError, match="instrument must be one of bass-4, bass-5, bass-6"):
        tab.job_options("bass-tab", {"instrument": "guitar-6"})
    assert list(profiles.PROFILES)[-2:] == ["tab", "bass-tab"]
    assert (profiles.PROFILES["tab"].pipeline, profiles.PROFILES["bass-tab"].pipeline) == ("tab", "tab")  # Studio hides both
    assert "older apps" in profiles.PROFILES["bass-tab"].description
    assert profiles.default_title("tab", Path("my_song.wav")) == "My Song — tab (draft)"
    assert profiles.default_title("bass-tab", Path("my_song.wav")) == "My Song — bass tab (draft)"


# ---------------------------------------------------------------- the pipelines

def _shape(stage) -> tuple:
    return (stage.name, stage.kind, stage.inputs, stage.run, stage.params, stage.adapter, stage.code, stage.outputs,
            stage.reuse_subdir, stage.derive)


@pytest.mark.parametrize("params", [
    {"instrument": "bass-4"}, {"instrument": "bass-4", "recording": "instrument"},
    {"instrument": "bass-5", "tuning": "drop-a", "capo": 2, "style": "lead", "octave": "-12", "layout": "tab-and-notation"},
    {"instrument": "bass-6", "octave": "0"},
])
def test_tab_with_a_bass_is_the_bass_tab_pipeline_stage_for_stage(params):
    ours = profiles.build("tab", Path("song.wav"), "T", params)
    theirs = profiles.build("bass-tab", Path("song.wav"), "T", params)
    assert [_shape(s) for s in ours.stages] == [_shape(s) for s in theirs.stages]  # so the same cache entries
    assert (ours.outputs, ours.params, ours.pipeline) == (theirs.outputs, theirs.params, theirs.pipeline)
    assert (ours.profile, theirs.profile) == ("tab", "bass-tab")


def test_bass_tab_is_as_it_was():
    p = profiles.build("bass-tab", Path("song.wav"), "T")
    assert [s.name for s in p.stages] == ["beats", "stems", "transcribe.bass.basic-pitch", "transcribe.bass.swift-f0", "notes",
                                          "arrange", "export"]
    assert p.params == {"instrument": "bass-4", "tuning": "standard", "capo": 0, "style": "as-played", "recording": "song",
                        "octave": "auto", "layout": "tab"}
    assert p.stage("notes").params == {} and p.stage("notes").run is bass_tab.notes_stage
    assert p.stage("notes").outputs == ("bass-notes.json",)
    assert p.stage("arrange").params == {"title": "T", "layout": "tab", "fingering": {"instrument": "bass-4", "tuning": "standard",
                                                                                     "capo": 0, "style": "as-played"}}
    assert tab.THIS not in p.stage("notes").code + p.stage("arrange").code + p.stage("export").code  # this module is not in its keys


def test_a_guitar_in_a_song_is_read_from_the_separators_guitar_stem():
    p = profiles.build("tab", Path("song.wav"), "T")
    assert [s.name for s in p.stages] == ["beats", "stems", "transcribe.guitar.basic-pitch", "transcribe.guitar.swift-f0", "notes",
                                          "arrange", "export"]
    pop = profiles.build("pop-rock", Path("song.wav"))
    for name in ("beats", "stems"):  # separated once for pop-rock, bass-tab and tab
        assert _shape(p.stage(name)) == _shape(pop.stage(name)), name
    for name in ("transcribe.guitar.basic-pitch", "transcribe.guitar.swift-f0"):
        stage = p.stage(name)
        assert (stage.inputs["audio"].stage, stage.inputs["audio"].file, stage.derive) == ("stems", "guitar.wav", None)
    assert p.stage("notes").params == {"instrument": "guitar-6"} and p.stage("notes").run is tab.notes_stage
    assert (p.pipeline, set(p.outputs)) == ("tab", {"composition.json", "tab.json", "tab.musicxml", "tab.pdf", "tab.mid"})
    assert p.stage("export").run is bass_tab.export_stage and set(p.stage("export").params) == {"musescore"}


def test_a_guitar_alone_is_not_separated_and_both_transcribers_hear_it_retuned():
    p = profiles.build("tab", Path("take.wav"), "T", {"recording": "instrument", "instrument": "guitar-7"})
    assert [s.name for s in p.stages] == ["beats", "transcribe.guitar.basic-pitch", "transcribe.guitar.swift-f0", "notes", "arrange",
                                          "export"]
    for name in ("transcribe.guitar.basic-pitch", "transcribe.guitar.swift-f0"):
        assert (p.stage(name).inputs["audio"].stage, p.stage(name).derive) == ("source", tuning.derive)
    assert p.stage("transcribe.guitar.basic-pitch").run is tuning.transcribe
    assert p.stage("transcribe.guitar.swift-f0").run is tab.second_opinion_retuned
    assert p.stage("notes").params == {"instrument": "guitar-7", "whole_recording": True}


def test_tuning_capo_and_style_are_parameters_of_the_fingering_only_and_the_instrument_of_the_notes_too():
    a = profiles.build("tab", Path("song.wav"), "T")
    b = profiles.build("tab", Path("song.wav"), "T", {"tuning": "drop-d", "capo": 3, "style": "open-position", "layout": "tab-and-notation"})
    for name in ("beats", "stems", "transcribe.guitar.basic-pitch", "transcribe.guitar.swift-f0", "notes", "export"):
        assert a.stage(name).params == b.stage(name).params, name
    assert b.stage("arrange").params == {"title": "T", "layout": "tab-and-notation",
                                         "fingering": {"instrument": "guitar-6", "tuning": "drop-d", "capo": 3, "style": "open-position"}}
    eight = profiles.build("tab", Path("song.wav"), "T", {"instrument": "guitar-8"})
    assert eight.stage("notes").params == {"instrument": "guitar-8"}  # its range reaches lower
    for name in ("beats", "stems", "transcribe.guitar.basic-pitch", "transcribe.guitar.swift-f0"):
        assert _shape(a.stage(name)) == _shape(eight.stage(name)), name
    assert profiles.build("tab", Path("song.wav"), "T", {"octave": "+12"}).stage("notes").params == {"instrument": "guitar-6", "octave": "+12"}


def test_the_profile_builds_and_lists_without_the_core(monkeypatch):
    monkeypatch.setenv(bass_tab.CORE_CLI_ENV, "/nowhere/brasscribe-core")
    assert profiles.PROFILES["tab"].build("-", {}).stage("arrange").params["title"] == "-"
    with pytest.raises(profiles.OptionError) as refused:
        profiles.job_options("tab", {"instrument": "guitar-6"})
    assert refused.value.code == profiles.CORE_MISSING_CODE


# ---------------------------------------------------------------- reading the notes: chords and lines

def test_a_strum_is_written_on_one_onset_and_keeps_when_each_string_was_heard():
    chord = [_note(p, 1.0 + 0.012 * k, 0.8) for k, p in enumerate(OPEN_E)]  # 60 ms from the low string to the high
    out = tab.strums(chord + [_note(E4, 1.2, 0.3)])
    assert [n["onset"] for n in out[:5]] == [1.0] * 5  # within STRUM_SECONDS of the first
    assert out[5]["onset"] == pytest.approx(1.06) and out[6]["onset"] == 1.2  # later: an onset of its own
    assert [round(n.get("heard_at", n["onset"]), 3) for n in out[:5]] == [1.0, 1.012, 1.024, 1.036, 1.048]

    doc = tab.played_notes(_strummed([OPEN_E, OPEN_G, OPEN_E, OPEN_G], spread=0.009), _beats(), "guitar-6")
    assert [(n["start"], n["pitch"]) for n in doc["notes"][:6]] == [(0, p) for p in OPEN_E]  # one event on the grid
    assert sorted({n["start"] for n in doc["notes"]}) == [0, 48, 96, 144]
    assert [round(n["onset_s"], 3) for n in doc["notes"][:3]] == [0.0, 0.009, 0.018]  # what was heard, for the recording's cursor


def test_passages_are_chordal_near_three_strong_notes_together_and_lines_elsewhere():
    melody = [_note(60 + (i % 5), 0.5 * i, 0.4) for i in range(8)]
    chords = _strummed([OPEN_E, OPEN_G], step=1.0)
    chords = [{**n, "onset": n["onset"] + 6.0, "offset": n["offset"] + 6.0} for n in chords]
    notes = sorted(melody + chords, key=lambda n: n["onset"])
    flags = tab.chordal(notes)
    assert flags == [False] * 8 + [True] * 12  # the melody ends 2.5 s before the first chord
    faint = [{**n, "amplitude": 0.3} for n in chords]  # three faint notes together are not a chord: leftovers come in clusters too
    assert not any(tab.chordal(sorted(melody + faint, key=lambda n: n["onset"])))
    dyads = [_note(p, 0.5 * i + 0.004 * k) for i in range(8) for k, p in enumerate((50, 57))]
    assert not any(tab.chordal(dyads))  # two notes together: a double stop in a line
    assert tab.chordal([]) == []


def test_in_a_line_overtones_and_faint_notes_go_and_in_a_chord_the_same_notes_stay():
    line = [_note(E2 + 2 * i, 0.5 * i, 0.45) for i in range(8)]
    overtone = _note(E2 + 12, 0.01, 0.3, amplitude=0.35)  # an octave over the first note, at half its amplitude
    played = _note(E2 + 12, 0.01, 0.3, amplitude=0.65)  # the same octave struck as loud: a double stop
    faint = _note(72, 2.2, 0.2, amplitude=0.3)
    for extra, kept in ((overtone, False), (played, True), (faint, False)):
        notes = sorted(line + [extra], key=lambda n: n["onset"])
        gone, unsure = tab.leftovers(notes, tab.chordal(notes))
        assert (notes.index(extra) not in gone) is kept and len(gone) == (0 if kept else 1) and unsure == []

    # An open E chord holds an octave, a twelfth and two octaves over its low E, and inner notes heard faintly.
    chord = sorted(_strummed([OPEN_E] * 3) + [_note(56, 1.0, 0.8, amplitude=0.3)], key=lambda n: n["onset"])
    assert tab.leftovers(chord, tab.chordal(chord)) == ([], [])
    doc = tab.played_notes(chord, _beats(), "guitar-6")
    assert sorted({n["pitch"] for n in doc["notes"]}) == sorted(OPEN_E) and doc["leftovers_dropped"] == 0
    assert len(doc["notes"]) == 18  # every string of every strum; the faint G# is the second strum's own, once

    doc = tab.played_notes(line + [overtone, faint], _beats(), "guitar-6")
    assert [n["pitch"] for n in doc["notes"]] == [E2 + 2 * i for i in range(8)] and doc["leftovers_dropped"] == 2
    straight = tab.played_notes(line + [overtone, faint], _beats(), "guitar-6", clean=False)  # what the benchmark compares with
    assert len(straight["notes"]) == 10 and {n["confidence"] for n in straight["notes"]} == {1.0}


def test_a_guitars_limits_are_not_applied_to_a_mandolin_or_a_ukulele():
    """The top G of a mandolin's open G chord (0-0-2-3) is two octaves over its G string and above a guitar's 12th fret."""
    mandolin_g, uke_c = [55, 62, 71, 79], [60, 64, 67, 84]  # the ukulele's C with its top string at the 15th fret
    for instrument, chord in (("mandolin", mandolin_g), ("ukulele", uke_c), ("ukulele-baritone", [50, 55, 59, 79])):
        notes = sorted(_strummed([chord] * 4), key=lambda n: n["onset"])
        assert tab.HEARD[instrument].chord_high is None
        assert tab.leftovers(notes, tab.chordal(notes), tab.HEARD[instrument].chord_high) == ([], [])
        doc = tab.played_notes(notes, _beats(), instrument)
        assert sorted({n["pitch"] for n in doc["notes"]}) == sorted(chord) and len(doc["notes"]) == 16, instrument
        assert doc["leftovers_dropped"] == 0
    # On a guitar the same shape of evidence, an overtone above the 12th fret of the top string, is left out and counted.
    guitar = sorted(_strummed([[43, 55, 67, 79]] * 4), key=lambda n: n["onset"])
    assert {tab.HEARD[i].chord_high for i in ("guitar-6", "guitar-7", "guitar-8")} == {76}
    doc = tab.played_notes(guitar, _beats(), "guitar-6")
    assert 79 not in {n["pitch"] for n in doc["notes"]} and doc["leftovers_dropped"] == 4
    t = tab.fingered({**doc, "reference_pitch": None}, tab.options({}), lambda request: {
        "instrument": {"name": "Guitar", "tuning": {"name": "Standard", "strings": []}, "frets": 22, "scale_length_mm": 648.0, "capo": 0},
        "fingering": {"notes": [{"pitch": n["pitch"], "string": 1, "fret": 0, "alternatives": [], "out_of_range": False, "pinned": False}
                                for n in request["notes"]]}, "violations": [], "tuning_suggestions": []})
    assert t["leftovers_dropped"] == 4 and m.Tab.model_validate({**t, "layout": "tab", "adjusted_notes": 0}).leftovers_dropped == 4


def test_a_note_too_short_to_be_one_is_counted_with_what_is_left_out():
    notes = sorted(_strummed([OPEN_E] * 4) + [_note(66, 0.3, 0.04), _note(68, 1.2, 0.05)], key=lambda n: n["onset"])
    for clean in (True, False):
        doc = tab.played_notes(notes, _beats(), "guitar-6", clean=clean)
        assert not {66, 68} & {n["pitch"] for n in doc["notes"]} and doc["leftovers_dropped"] == 2, clean


def test_confidence_in_a_line_is_swiftf0s_and_among_chords_the_amplitude_and_the_next_strum():
    second = [_note(60, 0.0), _note(62, 0.5)]
    sure = tab.confidence(_note(60, 0.0, amplitude=0.42), False, True, second)
    assert sure == 0.71 and tab.confidence(_note(62, 0.0, amplitude=0.42), False, True, second) < tab.DOUBT  # not heard there, and faint
    assert tab.confidence(_note(62, 0.0, amplitude=0.6), False, True, second) == 0.8  # not heard there, but strong: Basic Pitch is believed
    assert tab.confidence(_note(62, 0.0, amplitude=0.42), False, True, None) == 0.71  # no second opinion: no doubt from it
    # Among chords SwiftF0 follows one of the notes and has nothing to say about the others.
    assert tab.confidence(_note(62, 0.0, amplitude=0.42), True, True, second) == 0.71
    assert tab.confidence(_note(62, 0.0, amplitude=0.34), True, True, second) < tab.DOUBT  # faint
    assert tab.confidence(_note(62, 0.0, amplitude=0.42), True, False, second) < tab.DOUBT  # rather faint and never again
    assert tab.confidence(_note(62, 0.0, amplitude=0.5), True, False, second) == 0.75
    assert tab.confidence({"pitch": 62, "onset": 0.0, "offset": 0.4}, True, False, None) == 1.0

    notes = sorted(_strummed([OPEN_E] * 4) + [_note(61, 2.0, 0.5, amplitude=0.42)], key=lambda n: n["onset"])
    again = tab.repeated(notes)
    assert again == [n["pitch"] != 61 for n in notes]
    doc = tab.played_notes(notes, _beats(), "guitar-6")
    assert [n["pitch"] for n in doc["notes"] if n["confidence"] < tab.DOUBT] == [61]  # the note no other strum has


@pytest.mark.parametrize("pitches,instrument,shift", [
    ([52, 55, 59, 64, 67, 71], "guitar-6", 0),  # where a guitar plays
    ([88, 91, 93, 95, 96, 97, 98], "guitar-6", -12),  # above its 22nd fret: an octave lower fits
    ([28, 31, 33, 35, 28, 31], "guitar-6", 12),  # below its lowest tuning: an octave higher fits
    ([30, 32, 35, 37], "guitar-8", 0),  # an eight-string reaches there
    ([84, 86, 88, 90], "guitar-6", 0),  # high, but half of it is on the neck
    ([100, 103, 105, 20, 22], "guitar-6", 0),  # nothing fits
    ([], "guitar-6", 0),
    ([50, 52, 53], "mandolin", 12), ([67, 69, 72], "ukulele", 0),
])
def test_a_passage_heard_an_octave_from_the_instrument_is_moved_and_one_on_it_is_not(pitches, instrument, shift):
    assert tab.octave_shift(pitches, tab.HEARD[instrument]) == shift


def test_the_octave_is_chosen_or_checked_and_the_result_says_which():
    high = [_note(p, 0.5 * i) for i, p in enumerate([88, 91, 93, 95, 96, 98, 97, 96])]
    auto = tab.played_notes(high, _beats(), "guitar-6")
    assert (auto["octave_shift"], auto["octave_source"], auto["notes"][0]["pitch"]) == (-12, "auto", 76)
    kept = tab.played_notes(high, _beats(), "guitar-6", "0")
    assert (kept["octave_shift"], kept["octave_source"], kept["notes"][0]["pitch"]) == (0, "chosen", 88)
    assert tab.played_notes(high, _beats(), "guitar-6", "+12")["notes"][0]["pitch"] == 100


@pytest.mark.parametrize("notes,beats,message", [
    ([], _beats(), "no guitar notes"), ([_note(60, 0.0, 0.03)], _beats(), "no guitar notes"),
    ([_note(60, 0.0)], _beats(1), "too short"), ([_note(60, 0.0)], np.array([[0.0, 1], [0.5, 2], [1.0, 3]]), "downbeats"),
])
def test_a_recording_with_nothing_to_write_says_why(notes, beats, message):
    with pytest.raises(ValueError, match=message):
        tab.played_notes(notes, beats, "guitar-6")


def test_the_same_pitch_twice_on_one_onset_is_one_note_and_lengths_are_straight():
    doc = tab.played_notes([_note(60, 0.0, 0.2), _note(60, 0.02, 0.4), _note(64, 0.5, 0.2), _note(67, 1.0, 0.9), _note(60, 2.0)],
                           _beats(), "guitar-6")
    assert [(n["start"], n["pitch"]) for n in doc["notes"]] == [(0, 60), (24, 64), (48, 67), (96, 60)]
    assert all(n["dur"] % 6 == 0 for n in doc["notes"])  # 0.2 s at 120 BPM would be a triplet's length (#70)
    assert set(doc["notes"][0]) == {"pitch", "start", "dur", "confidence", "onset_s", "offset_s"}
    assert (doc["meter"], doc["tempo_bpm"], doc["ticks_per_beat"]) == ({"beats": 4, "beat_unit": 4}, 120.0, 24)


# ---------------------------------------------------------------- fingering

def _doc(notes: list[dict]) -> dict:
    return {**tab.played_notes(notes, _beats(), "guitar-6"), "reference_pitch": None}


def test_only_what_the_crate_reads_is_sent_and_an_unplayable_note_is_left_out_until_none_is():
    doc = _doc(_strummed([OPEN_E + [68], OPEN_G]))  # seven notes on one onset: one more than there are strings
    doc["notes"][3]["confidence"] = 0.2
    seen: list[dict] = []

    def solver(request: dict) -> dict:
        seen.append(request)
        notes = request["notes"]
        together = [i for i, n in enumerate(notes) if n["start"] == 0]
        places = [{"pitch": n["pitch"], "string": 1 + i % 6, "fret": 0, "alternatives": [], "out_of_range": False, "pinned": False}
                  for i, n in enumerate(notes)]
        violations = [{"kind": "shared-string", "string": 1, "notes": together}] if len(together) > 6 else []
        return {"instrument": {"name": "Guitar", "tuning": {"name": "Standard", "strings": [{"open_pitch": p, "first_fret": 0} for p in (64, 59, 55, 50, 45, 40)]},
                               "frets": 22, "scale_length_mm": 648.0, "capo": request["instrument"]["capo"], "notation": "treble-8vb"},
                "fingering": {"notes": places}, "violations": violations, "tuning_suggestions": []}

    t = tab.fingered(doc, tab.options({"capo": 2, "tuning": "drop-d", "style": "open-position"}), solver)
    assert len(seen) == 2 and seen[0]["instrument"] == {"preset": "guitar-drop-d", "capo": 2}
    assert seen[0]["options"] == {"style": "open-position", "tempo_bpm": 120.0}
    assert all(set(n) == {"pitch", "start", "dur"} for r in seen for n in r["notes"])  # the crate refuses any other key
    assert (len(seen[0]["notes"]), len(seen[1]["notes"])) == (13, 12)
    assert (t["unplayable_dropped"], t["violations"], len(t["notes"])) == (1, [], 12)
    assert 0.2 not in [n["confidence"] for n in t["notes"]]  # the least sure note of the violation went
    m.Tab.model_validate({**t, "layout": "tab", "adjusted_notes": 0})
    assert t["instrument"]["notation"] == "treble-8vb" and t["preset"] == "guitar-drop-d"

    def spans(request: dict) -> dict:  # a crate that objects to any two notes of the first onset together
        answer = solver(request)
        together = [i for i, n in enumerate(request["notes"]) if n["start"] == 0]
        answer["violations"] = [{"kind": "span-too-wide", "notes": together[:2], "span_mm": 200.0}] if len(together) > 1 else []
        return answer

    one = tab.fingered(doc, tab.options({}), spans)  # it goes on until nothing is objected to: no violation is ever written
    assert one["violations"] == [] and one["unplayable_dropped"] == 6 and len([n for n in one["notes"] if n["start"] == 0]) == 1
    assert one["notes"][0]["confidence"] == max(n["confidence"] for n in doc["notes"] if n["start"] == 0)  # the surest stays

    def nameless(request: dict) -> dict:
        return {**solver(request), "violations": [{"kind": "something-new"}]}

    with pytest.raises(RuntimeError, match="violation without a note: something-new"):
        tab.fingered(doc, tab.options({}), nameless)  # nothing to leave out: a failed stage, not a tab with a violation


@needs_core
def test_the_core_fingers_open_chords_as_their_shapes_and_counts_frets_from_a_capo():
    t = tab.fingered(_doc(_strummed([OPEN_E, OPEN_G, [45, 52, 57, 60, 64]])), tab.options({}))
    by_start = {}
    for n in t["notes"]:
        by_start.setdefault(n["start"], []).append((n["string"], n["fret"]))
    assert sorted(by_start[0]) == [(1, 0), (2, 0), (3, 1), (4, 2), (5, 2), (6, 0)]  # E
    assert sorted(by_start[48]) == [(1, 3), (2, 0), (3, 0), (4, 0), (5, 2), (6, 3)]  # G
    assert sorted(by_start[96]) == [(1, 0), (2, 1), (3, 2), (4, 2), (5, 0)]  # A minor
    assert t["violations"] == [] and t["unplayable_dropped"] == 0 and t["instrument"]["notation"] == "treble-8vb"
    assert not any(n["out_of_range"] for n in t["notes"])

    capo = tab.fingered(_doc(_strummed([[p + 2 for p in OPEN_E]])), tab.options({"capo": 2}))
    assert capo["instrument"]["capo"] == 2 and sorted((n["string"], n["fret"]) for n in capo["notes"]) == \
        [(1, 0), (2, 0), (3, 1), (4, 2), (5, 2), (6, 0)]  # the E shape, two frets up


@needs_core
def test_the_core_never_leaves_a_violation_in_a_guitar_tab(tmp_path):
    cluster = [_note(p, 0.0, 0.9) for p in (40, 41, 42, 43, 44, 45, 46, 47, 64)] + _strummed([OPEN_E], step=1.0)[6:]
    wide = [_note(p, 2.0, 0.9) for p in (41, 79)]  # the first fret and the fifteenth
    t = tab.fingered(_doc(cluster + wide + _strummed([OPEN_G])), tab.options({}))
    assert t["violations"] == [] and t["unplayable_dropped"] >= 3
    m.Tab.model_validate({**t, "layout": "tab", "adjusted_notes": 0})
    assert bass_tab.export_tab(t, "Capo & chords", "tab-and-notation", tmp_path) >= 0
    xml = (tmp_path / "tab.musicxml").read_text()
    assert "<sign>TAB</sign>" in xml and "<staff-lines>6</staff-lines>" in xml


@needs_core
def test_a_capo_is_named_in_the_tabs_header(tmp_path):
    t = tab.fingered(_doc(_strummed([[p + 2 for p in OPEN_E]] * 2)), tab.options({"capo": 2}))
    bass_tab.export_tab(t, "Capo", "tab", tmp_path)
    xml = (tmp_path / "tab.musicxml").read_text()
    assert re.search(r"[Cc]apo\D{0,12}2", xml), "the page does not say where the capo is"


@needs_core
@pytest.mark.parametrize("instrument,tuning,strings,clef", [
    ("guitar-7", "standard", 7, "treble-8vb"), ("guitar-8", "standard", 8, "treble-8vb"), ("ukulele", "high-g", 4, "treble"),
    ("ukulele", "low-g", 4, "treble"), ("ukulele-baritone", "standard", 4, "treble-8vb"), ("mandolin", "standard", 4, "treble"),
])
def test_every_instrument_of_the_table_is_fingered_by_the_core(instrument, tuning, strings, clef):
    opts = tab.options({"instrument": instrument, "tuning": tuning, "recording": "instrument"})
    line = [_note(p, 0.5 * i) for i, p in enumerate([67, 69, 71, 72, 74, 72, 71, 69])]
    doc = {**tab.played_notes(line, _beats(), instrument), "reference_pitch": None}
    t = tab.fingered(doc, opts)
    assert len(t["instrument"]["tuning"]["strings"]) == strings and t["instrument"]["notation"] == clef
    assert t["violations"] == [] and all(n["string"] for n in t["notes"]) and t["preset"] == tab.preset(opts)
    m.Tab.model_validate({**t, "layout": "tab", "adjusted_notes": 0})


def test_a_swiftf0_that_hears_no_line_is_no_opinion_and_any_other_failure_is_one(tmp_path, monkeypatch):
    import threading
    from types import SimpleNamespace

    from brasscribe_engine.adapters import AdapterError

    said: list[str] = []
    ctx = SimpleNamespace(out=tmp_path, params={"output": "guitar-sw.mid"}, log=said.append,
                          executor=SimpleNamespace(cancel=threading.Event()))

    def fails(message: str):
        def run(ctx):
            raise AdapterError(message)
        return run

    monkeypatch.setattr(S, "transcribe", fails("swift-f0 failed (1): ValueError: Cannot export empty notes list"))
    tab.second_opinion(ctx)
    assert bass_tab.load_transcription(tmp_path / "guitar-sw.mid") == [] and "no second opinion" in said[0]
    doc = tab.played_notes(_strummed([OPEN_E] * 2) + [_note(64, 4.0, amplitude=0.42)], _beats(), "guitar-6", second=[])
    assert not any(n["confidence"] < tab.DOUBT for n in doc["notes"])  # nothing is doubted for want of an opinion
    monkeypatch.setattr(tuning, "transcribe", fails("swift-f0 failed (1): ModuleNotFoundError: swift_f0"))
    with pytest.raises(AdapterError, match="ModuleNotFoundError"):
        tab.second_opinion_retuned(ctx)
    ctx.executor.cancel.set()
    with pytest.raises(AdapterError):
        tab.second_opinion(ctx)  # a cancelled job stays cancelled


# ---------------------------------------------------------------- end to end

def _write_midi(path: Path, notes: list[dict]) -> None:
    import pretty_midi

    pm = pretty_midi.PrettyMIDI()
    inst = pretty_midi.Instrument(program=25)
    inst.notes = [pretty_midi.Note(velocity=int(round(127 * n["amplitude"])), pitch=n["pitch"], start=n["onset"], end=n["offset"])
                  for n in notes]
    pm.instruments.append(inst)
    pm.write(str(path))


def _wait(client, job_id: str, timeout: float = 60) -> dict:
    import time

    t0 = time.time()
    while time.time() - t0 < timeout:
        job = client.get(f"/v1/jobs/{job_id}").json()
        if job["status"] in ("succeeded", "failed", "cancelled"):
            return job
        time.sleep(0.05)
    raise AssertionError("job did not finish")


@needs_core
def test_a_guitar_job_runs_to_a_tab_and_a_bass_job_of_either_profile_shares_its_stages(settings, audio, monkeypatch):
    """The symbolic stages and the core for real, with the models' outputs written in their place."""
    from brasscribe_music import musescore
    from fastapi.testclient import TestClient

    from brasscribe_engine.api import create_app

    heard = _strummed([OPEN_E, OPEN_G, OPEN_E, OPEN_G]) + [_note(64 + (i % 4), 4.0 + 0.5 * i, 0.4) for i in range(8)]
    monkeypatch.setattr(musescore, "binary", lambda: None)
    monkeypatch.setattr(S, "beats", lambda ctx: np.savetxt(ctx.out / "mix.beats", _beats(25), fmt=["%.3f", "%d"]))
    monkeypatch.setattr(tuning, "transcribe", lambda ctx: _write_midi(ctx.out / ctx.params["output"], heard))
    monkeypatch.setattr(S, "transcribe", lambda ctx: _write_midi(ctx.out / ctx.params["output"], heard))
    with TestClient(create_app(settings)) as c:
        listed = {p["name"]: p for p in c.get("/v1/profiles").json()}
        assert {"tab", "bass-tab"} <= set(listed) and listed["tab"]["pipeline"] == "tab"
        assert "transcribe.guitar.basic-pitch" in listed["tab"]["stages"] and "transcribe.bass.basic-pitch" in listed["bass-tab"]["stages"]
        audio_id = c.post("/v1/audio", files={"file": ("my_take.wav", audio.read_bytes(), "audio/wav")}).json()["audio_id"]

        r = c.post("/v1/jobs", json={"audio_id": audio_id, "profile": "tab", "instrument": "guitar-6", "recording": "instrument",
                                     "capo": 2, "layout": "tab-and-notation"})
        assert r.status_code == 202 and r.json()["title"] == "My Take — tab (draft)"
        job = _wait(c, r.json()["id"])
        assert job["status"] == "succeeded", job["error"]
        assert [s["name"] for s in job["stages"]] == ["beats", "transcribe.guitar.basic-pitch", "transcribe.guitar.swift-f0", "notes",
                                                      "arrange", "export"]
        assert job["outputs"] == ["composition.json", "tab.json", "tab.musicxml"]
        t = m.Tab.model_validate(c.get(f"/v1/jobs/{job['id']}/tab").json())
        assert (t.preset, t.instrument.capo, t.instrument.notation, t.layout) == ("guitar-standard", 2, "treble-8vb", "tab-and-notation")
        assert not t.violations and len({n.start for n in t.notes}) == 12 and max(len([n for n in t.notes if n.start == s]) for s in (0, 48)) >= 5
        xml = c.get(f"/v1/jobs/{job['id']}/musicxml")  # the tab's own file, not a band score
        assert xml.status_code == 200 and "<staves>2</staves>" in xml.text and "<work-title>My Take — tab (draft)</work-title>" in xml.text
        comp = c.get(f"/v1/jobs/{job['id']}/composition").json()
        assert [(v["id"], v["role"]) for v in comp["voices"]] == [("guitar", "harmony")] and len(comp["voices"][0]["notes"]) == len(t.notes)
        manifest = c.get(f"/v1/jobs/{job['id']}/manifest").json()
        assert manifest["profile"] == "tab" and manifest["params"]["instrument"] == "guitar-6"

        # Another tuning and capo: only the fingering runs again.
        again = _wait(c, c.post("/v1/jobs", json={"audio_id": audio_id, "profile": "tab", "instrument": "guitar-6",
                                                  "recording": "instrument", "tuning": "drop-d"}).json()["id"])
        assert {s["name"]: s["status"] for s in again["stages"]}["notes"] == "cached" and again["status"] == "succeeded"

        # A bass through the old id, then through tab: the second finds every stage in the cache, and the tabs are the same.
        old = _wait(c, c.post("/v1/jobs", json={"audio_id": audio_id, "profile": "bass-tab", "recording": "instrument"}).json()["id"])
        new = _wait(c, c.post("/v1/jobs", json={"audio_id": audio_id, "profile": "tab", "instrument": "bass-4",
                                                "recording": "instrument"}).json()["id"])
        assert old["status"] == new["status"] == "succeeded"
        assert {s["status"] for s in new["stages"] if s["name"] not in ("arrange", "export")} == {"cached"}  # the title differs
        a, b = (c.get(f"/v1/jobs/{j['id']}/tab").json() for j in (old, new))
        assert a == b and a["preset"] == "bass-4-standard"

        for body in ({"profile": "tab", "instrument": "guitar-6", "tuning": "bead"}, {"profile": "tab", "instrument": "ukulele", "recording": "song"},
                     {"profile": "bass-tab", "instrument": "guitar-6"}, {"profile": "tab", "lineup": "quartet"}):
            refused = c.post("/v1/jobs", json={"audio_id": audio_id, **body})
            assert refused.status_code == 422 and refused.json()["code"] == "invalid_options", body
        assert c.post("/v1/jobs", json={"audio_id": audio_id, "profile": "tab", "instrument": "banjo"}).status_code == 422
        assert c.post("/v1/jobs", json={"audio_id": audio_id, "profile": "test", "instrument": "guitar-6"}).json()["code"] == "invalid_options"


def test_a_tab_job_without_the_core_is_refused_at_submit_under_both_ids(settings, audio, monkeypatch):
    from fastapi.testclient import TestClient

    from brasscribe_engine.api import create_app

    monkeypatch.setenv(bass_tab.CORE_CLI_ENV, str(settings.data_dir / "no-such-core"))
    with TestClient(create_app(settings)) as c:
        audio_id = c.post("/v1/audio", files={"file": ("song.wav", audio.read_bytes(), "audio/wav")}).json()["audio_id"]
        for profile in ("tab", "bass-tab"):
            r = c.post("/v1/jobs", json={"audio_id": audio_id, "profile": profile})
            assert r.status_code == 422 and r.json()["code"] == "core_missing", profile
        assert {"tab", "bass-tab"} <= {p["name"] for p in c.get("/v1/profiles").json()}  # still listed


def test_the_cli_takes_every_instrument_and_checks_the_core_first(monkeypatch, tmp_path, capsys):
    from brasscribe_engine import cli

    seen = {}
    monkeypatch.setattr(runner, "run", lambda s, audio, profile, **kw: seen.update(kw, profile=profile) or
                        {"run_id": "r", "status": "succeeded", "seconds": 0.0, "devices": [], "stages": []})
    monkeypatch.setenv("BRASSCRIBE_DATA", str(tmp_path))
    core = tmp_path / "brasscribe-core"
    core.write_text("#!/bin/sh\n")
    core.chmod(0o755)
    monkeypatch.setenv(bass_tab.CORE_CLI_ENV, str(core))
    assert cli.main(["run", "song.wav", "--profile", "tab", "--instrument", "ukulele", "--tuning", "low-g", "--recording", "instrument"]) == 0
    assert (seen["profile"], seen["params"]["instrument"], seen["params"]["tuning"]) == ("tab", "ukulele", "low-g")
    monkeypatch.setenv(bass_tab.CORE_CLI_ENV, str(tmp_path / "missing"))
    monkeypatch.setattr(runner, "run", lambda *a, **kw: pytest.fail("the run was started"))
    assert cli.main(["run", "song.wav", "--profile", "tab"]) == 3
    assert "cargo build --release -p brasscribe-cli" in capsys.readouterr().err
