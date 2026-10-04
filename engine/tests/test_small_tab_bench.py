"""The ukulele and mandolin tab benchmark (brasscribe_eval.small_tab_bench): its passages and its suites."""

from __future__ import annotations

import json

import pytest

from brasscribe_eval import small_tab_bench as B
from brasscribe_eval import suites


def test_the_passages_are_the_same_every_time_and_on_the_instruments_strings():
    for group, (params, _, strings, shapes, scale) in B.GROUPS.items():
        held_out = group.endswith(B.HELDOUT)
        assert B.patterns(group) == ((*B.PATTERNS, "chord-melody") if held_out else B.PATTERNS) + B.EXTRA_PATTERNS.get(group, ())
        for pattern in B.patterns(group):
            notes = B.passage(group, pattern, 96.0)
            assert notes == B.passage(group, pattern, 96.0)
            assert min(n["pitch"] for n in notes) >= min(strings) and len(notes) >= 6 * B.BARS, (group, pattern)
            assert notes[0]["onset"] == pytest.approx(4 * 60 / 96)  # a bar's count-in
            for n in notes:
                if "string" in n:  # a chord's notes say their string: at or above its open pitch; the first frets where rules are chosen
                    assert 0 <= n["pitch"] - strings[n["string"] - 1] <= (15 if held_out else 4 if group.startswith("guitar") else 3), (group, pattern, n)
            assert ("string" in notes[0]) == (pattern not in ("melody", B.TREMOLO))
    assert {g: p["instrument"] for g, (p, *_) in B.GROUPS.items() if not g.endswith(B.HELDOUT) and not g.startswith("guitar")} == {
        "ukulele-high-g": "ukulele", "ukulele-low-g": "ukulele", "ukulele-baritone": "ukulele-baritone", "mandolin": "mandolin"}
    assert all(B.GROUPS[g + B.HELDOUT][0] == B.GROUPS[g][0] and B.GROUPS[g + B.HELDOUT][3] != B.GROUPS[g][3]
               for g in B.GROUPS if not g.endswith(B.HELDOUT) and not g.startswith("guitar"))  # each group has a held-out one: the same instrument, other chords
    guitars = [g for g in B.GROUPS if g.startswith("guitar")]
    assert tuple(guitars) == B.SUITES["guitar-rendered"] and sum(g.endswith("-heldout") for g in guitars) == 2
    picked = B.passage("guitar-nylon", "picked", 96.0)[:8]  # C: the bass string, then the top three strings in turn
    assert [(n["string"], n["pitch"]) for n in picked] == [(5, 48), (3, 55), (2, 60), (1, 64), (2, 60), (3, 55), (2, 60), (1, 64)]
    assert sorted(g for groups in B.SUITES.values() for g in groups) == sorted(B.GROUPS)


def test_the_held_out_melody_over_a_ringing_chord_is_high_on_the_top_string():
    notes = B.passage("ukulele-high-g" + B.HELDOUT, "chord-melody", 120.0)
    bar = [n for n in notes if 2.0 <= n["onset"] < 4.0]  # the first bar, after the count-in
    chord, melody = [n for n in bar if n["onset"] < 2.1], [n for n in bar if n["onset"] >= 2.4]
    assert sorted((n["string"], n["pitch"]) for n in chord) == [(1, 69), (2, 66), (3, 62), (4, 69)]  # D: 2220
    assert all(n["offset"] - n["onset"] > 1.8 for n in chord if n["string"] != 1)  # it rings under the melody
    assert [(n["string"], n["pitch"] - 69) for n in melody] == [(1, f) for f in (12, 14, 15, 14, 12, 14)]
    assert melody[0]["onset"] == pytest.approx(2.5)  # a beat after the chord


def test_the_high_g_chords_have_their_fourth_string_above_their_third():
    first = [n for n in B.passage("ukulele-high-g", "strummed", 96.0) if n["onset"] < 4 * 60 / 96 + 0.1]
    assert sorted((n["string"], n["pitch"]) for n in first) == [(1, 72), (2, 64), (3, 60), (4, 67)]  # C: 0003, g above c
    low = [n for n in B.passage("ukulele-low-g", "strummed", 96.0) if n["onset"] < 4 * 60 / 96 + 0.1]
    assert sorted((n["string"], n["pitch"]) for n in low) == [(1, 72), (2, 64), (3, 60), (4, 55)]
    mandolin = [n for n in B.passage("mandolin", "strummed", 96.0) if n["onset"] < 4 * 60 / 96 + 0.1]
    assert sorted((n["string"], n["pitch"]) for n in mandolin) == [(1, 79), (2, 71), (3, 62), (4, 55)]  # G: 0023


def test_every_preset_has_its_sounding_octave_pinned():
    """A strum's partials read as an octave lower (sounding_shift's ratio up to 0.32 on rendered strums, against 0.25):
    the reference octave is pinned per preset, not read from each passage."""
    assert {preset for _, preset, *_ in B.GROUPS.values()} <= set(B.SOUNDING)
    assert set(B.SOUNDING.values()) == {0}


def test_the_bank_is_selected_before_the_program():
    mid = B.midi_file([(8, 24, False, [(67, 0.0, 0.5, 90)]), (0, 33, False, [(36, 0.0, 0.5, 90)]), (0, 0, True, [(36, 0.0, 0.1, 90)])], 120.0)
    lead = [m for m in mid.tracks[0] if not m.is_meta]
    assert [(m.type, getattr(m, "control", None), getattr(m, "value", None), getattr(m, "program", None)) for m in lead[:2]] == \
        [("control_change", 0, 8, None), ("program_change", None, None, 24)]
    assert [m.type for m in lead[2:]] == ["note_on", "note_off"] and lead[3].time == 480  # half a second at 120 BPM
    assert {m.channel for m in mid.tracks[2] if not m.is_meta} == {9}  # the drums' channel
    assert len({next(m.channel for m in t if not m.is_meta) for t in mid.tracks}) == 3


def test_a_song_run_reads_the_stem_the_profile_reads(tmp_path, monkeypatch):
    from brasscribe_eval import guitar_tab_bench as G

    entry = tmp_path / "eval" / B.SET / "ukulele-high-g-melody"
    entry.mkdir(parents=True)
    (entry / "reference.json").write_text(json.dumps({"group": "ukulele-high-g", "params": {"instrument": "ukulele", "tuning": "high-g"},
                                                      "tempo_bpm": 96.0, "beats_per_bar": 4, "style": "melody", "player": "synthesized",
                                                      "notes": [{"pitch": 67, "onset": 0.0, "offset": 0.4}]}))
    seen = []
    monkeypatch.setattr(G, "tab_of", lambda entry, clean, params, files: seen.append((params, files)) or {
        "notes": [{"pitch": 67, "onset_s": 0.0, "offset_s": 0.4, "start": 0, "dur": 24, "string": 4, "fret": 0, "out_of_range": False,
                   "confidence": 1.0}], "violations": [], "tempo_bpm": 96.0, "meter": {"beats": 4, "beat_unit": 4}})
    out, _ = B.evaluate(tmp_path, ("ukulele-high-g",), "song")
    assert seen[-1] == ({"instrument": "ukulele", "tuning": "high-g", "recording": "song"},
                        {"beats": "song.beats", "bp": "song-guitar-bp.mid", "sw": "song-guitar-sw.mid"})
    assert out["onset_f1"] == 1.0 and out["excerpts"] == 1.0
    B.evaluate(tmp_path, ("ukulele-high-g",), "instrument")
    assert seen[-1][1] == B.FILES["instrument"] and seen[-1][0]["recording"] == "instrument"
    assert B.evaluate(tmp_path, ("mandolin",), "song")[1] == []  # another instrument's suite does not see it


def test_a_held_out_groups_development_passages_are_scored_apart():
    """The held-out passages a rule was chosen on are not in the group's held-out numbers."""
    assert B.split("ukulele-high-g") == (("", B.PATTERNS),)
    parts = dict(B.split("mandolin" + B.HELDOUT))
    assert parts[B.DEV] == B.DEVELOPMENT and set(parts[""]) == set(B.HELDOUT_PATTERNS) - set(B.DEVELOPMENT)


def test_a_mandolin_tremolo_is_scored_apart_and_skipped_where_it_was_not_rendered(tmp_path, monkeypatch):
    """The tremolo passages have keys of their own: the group's numbers stay the same with or without them."""
    assert B.split("mandolin") == (("", B.PATTERNS), ("_tremolo", (B.TREMOLO,)))
    assert dict(B.split("mandolin" + B.HELDOUT))["_tremolo"] == (B.TREMOLO,)
    assert all(B.TREMOLO not in B.patterns(g) for g in B.GROUPS if not g.startswith("mandolin"))
    notes = B.passage("mandolin", B.TREMOLO, 96.0)
    bar = [n for n in notes if 4 * 60 / 96 <= n["onset"] < 8 * 60 / 96]
    assert len(bar) == 32 and len({n["pitch"] for n in bar}) == 2  # two notes a bar, each in thirty-seconds
    seen = []
    monkeypatch.setattr(B, "entries", lambda data, groups=None: [tmp_path / "x"])
    monkeypatch.setattr(B, "evaluate", lambda data, groups, mode, only=None: seen.append(only) or (
        ({"onset_f1": 1.0}, [{}]) if B.TREMOLO not in only else ({}, [])))
    monkeypatch.setattr(B, "stem_scores", lambda data, groups: {})
    monkeypatch.setattr("brasscribe_engine.bass_tab.core_cli", lambda: None)
    for f in [*B.FILES["instrument"].values(), *(f for stem in B.STEMS for f in B.song_files(stem).values())]:
        (tmp_path / "x").mkdir(exist_ok=True)
        (tmp_path / "x" / f).write_text("")
    r = suites.run_suite("mandolin-tab", data=tmp_path)
    assert r["status"] == "ran" and r["skipped_parts"] == ["mandolin_tremolo", "mandolin_heldout_tremolo"]
    assert not any("tremolo" in k for k in r["metrics"]) and r["metrics"]["mandolin.song.onset_f1"] == 1.0
    report = suites.gate([r])  # the stub's numbers are not the baselines': only the tremolo keys are looked at
    tremolo = [c for c in report["suites"][0]["checks"] if "tremolo" in c["metric"]]
    assert tremolo and {c["status"] for c in tremolo} == {"skipped"}


@pytest.mark.parametrize("suite,groups", [("ukulele-tab", ("ukulele_high_g.song", "ukulele_low_g.instrument", "ukulele_baritone.song",
                                                           "ukulele_high_g_heldout.instrument", "ukulele_baritone_heldout.song")),
                                          ("mandolin-tab", ("mandolin.song", "mandolin.instrument", "mandolin_heldout.instrument"))])
def test_the_suites_skip_without_their_data_and_are_gated(suite, groups, tmp_path):
    r = suites.run_suite(suite, data=tmp_path)
    assert r["status"] == "skipped" and "eval/small-tab" in r["reason"]
    base = suites.load_baselines()["suites"][suite]["metrics"]
    for group in groups:
        assert base[f"{group}.violations"] == {"value": 0, "tolerance": 0, "higher_is_better": False}
        assert f"{group}.onset_f1" in base and f"{group}.string_agreement" in base
    assert base["stem.guitar.recall"] > 0.8 > 0.2 > base["stem.other.recall"]  # where the separator puts it
