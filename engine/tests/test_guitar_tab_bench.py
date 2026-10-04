"""The guitar tab benchmark (brasscribe_eval.guitar_tab_bench): its reference, its scores and its suite."""

from __future__ import annotations

import json

import pytest

from brasscribe_eval import guitar_tab_bench as G
from brasscribe_eval import suites


def _jams(path, notes_by_source: dict[int, list[tuple[float, float, float]]]) -> None:
    annotations = [{"namespace": "note_midi", "annotation_metadata": {"data_source": str(source)},
                    "data": [{"time": t, "duration": d, "value": v, "confidence": None} for t, d, v in notes]}
                   for source, notes in notes_by_source.items()]
    annotations += [{"namespace": "tempo", "annotation_metadata": {}, "data": [{"time": 0.0, "duration": 4.0, "value": 96.0}]},
                    {"namespace": "key_mode", "annotation_metadata": {}, "data": [{"time": 0.0, "duration": 4.0, "value": "G:major"}]},
                    {"namespace": "beat_position", "annotation_metadata": {}, "data": [
                        {"time": 0.625 * i, "duration": 0.0, "value": {"position": i % 3 + 1, "beat_units": 4, "measure": i // 3 + 1,
                                                                        "num_beats": 3}} for i in range(6)]}]
    path.write_text(json.dumps({"annotations": annotations, "file_metadata": {}, "sandbox": {}}))


def test_the_reference_counts_strings_from_the_top_as_a_tab_does(tmp_path):
    # The annotation's source 0 is the low E string; a tab's string 6. An open low E and an open high e:
    _jams(tmp_path / "04_Rock2-96-G_comp.jams", {0: [(0.0, 0.5, 40.02)], 5: [(0.5, 0.5, 63.97)], 2: [(1.0, 0.4, 57.4)]})
    ref = G.reference(tmp_path / "04_Rock2-96-G_comp.jams")
    assert [(n["pitch"], n["string"]) for n in ref["notes"]] == [(40, 6), (64, 1), (57, 4)]
    assert (ref["player"], ref["style"], ref["tempo_bpm"], ref["beats_per_bar"], ref["key"]) == ("04", "comp", 96.0, 3, "G:major")
    assert ref["notes"][0]["offset"] == 0.5 and len(ref["beats"]) == 6
    (tmp_path / "annotation").mkdir()
    (tmp_path / "04_Rock2-96-G_comp.jams").rename(tmp_path / "annotation" / "04_Rock2-96-G_comp.jams")
    made = G.build(tmp_path, tmp_path / "data")
    assert [d.name for d in made] == ["04_Rock2-96-G_comp"] == [d.name for d in G.entries(tmp_path / "data")]
    assert G.audio_of(made[0], tmp_path) == tmp_path / "audio_mono-mic" / "04_Rock2-96-G_comp_mic.wav"


def test_the_rules_are_set_on_some_players_and_reported_on_the_others():
    assert not set(G.TUNE) & set(G.REPORT) and sorted(G.TUNE + G.REPORT) == ["00", "01", "02", "03", "04", "05"]


def _tab(notes: list[tuple], tempo: float = 96.0, beats: int = 4, **extra) -> dict:
    """notes: (pitch, onset, start tick, string, fret, confidence)."""
    return {"notes": [{"pitch": p, "onset_s": on, "offset_s": on + 0.4, "start": start, "dur": 24, "string": s, "fret": f,
                       "out_of_range": s is None, "confidence": c} for p, on, start, s, f, c in notes],
            "violations": [], "tempo_bpm": tempo, "meter": {"beats": beats, "beat_unit": 4}, **extra}


# An open G chord (six strings), then a three-note line on the top strings.
REF = {"tempo_bpm": 96.0, "beats_per_bar": 4, "notes":
       [{"pitch": p, "onset": 0.01 * k, "offset": 0.6, "string": 6 - k} for k, p in enumerate([43, 47, 50, 55, 59, 67])]
       + [{"pitch": p, "onset": 1.0 + 0.5 * i, "offset": 1.4 + 0.5 * i, "string": s} for i, (p, s) in enumerate([(64, 1), (62, 2), (60, 2)])]}


def test_a_tab_that_matches_its_reference_scores_full_marks():
    chord = [(p, 0.01 * k, 0, 6 - k, f, 1.0) for k, (p, f) in enumerate([(43, 3), (47, 2), (50, 0), (55, 0), (59, 0), (67, 3)])]
    line = [(64, 1.0, 48, 1, 0, 1.0), (62, 1.5, 72, 2, 3, 1.0), (60, 2.0, 96, 2, 1, 1.0)]
    s = G.summarize([G.score_tab(REF, _tab(chord + line))])
    assert s["onset_f1"] == 1.0 and s["chord_recall"] == 1.0 and s["chord_precision"] == 1.0 and s["chords_whole"] == 1.0
    assert s["string_agreement"] == 1.0 and s["string_recall"] == 1.0 and s["violations"] == 0.0 and s["doubt_share"] == 0.0
    assert (s["tempo_ok"], s["meter_ok"]) == (1.0, 1.0)
    assert s["hand_travel"] == 1.5  # the hand's frets, one per onset: 2 (the chord's lowest fretted note), 3, 1; the open e is none


def test_missed_chord_notes_other_strings_split_chords_and_doubt_are_counted():
    # Four of the chord's six notes, one of them an octave high and the last on the next sixteenth; the line on other strings.
    chord = [(43, 0.0, 0, 6, 3, 1.0), (47, 0.01, 0, 5, 2, 1.0), (62, 0.02, 0, 2, 3, 0.3), (67, 0.05, 6, 1, 3, 1.0)]
    line = [(64, 1.0, 48, 2, 5, 1.0), (62, 1.5, 72, 3, 7, 1.0), (61, 2.0, 96, 3, 6, 0.2)]
    row = G.score_tab(REF, _tab(chord + line, tempo=192.0, beats=3, unplayable_dropped=2))
    s = G.summarize([row])
    assert (row["chord_ref"], row["chord_ref_right"]) == (6.0, 3.0) and s["chord_recall"] == 0.5
    assert (row["chord_est"], row["chord_est_right"]) == (3.0, 2.0)  # the three written together; one of them is wrong
    assert s["chords_whole"] == 0.0  # the G on top landed on another onset
    assert s["string_agreement"] == pytest.approx(3 / 5)  # the chord's three right notes; neither note of the line
    assert s["string_recall"] == pytest.approx(3 / 9)  # of all nine notes played: the missed ones are on no string
    # Three missed notes have something an octave away at their onset (the D heard high, and the chord's own octaves).
    assert s["octave_err_rate"] == pytest.approx(3 / 9) and s["doubt_precision"] == 1.0 and s["doubt_recall"] == 1.0
    assert (s["tempo_ok"], s["tempo_ok_level"], s["meter_ok"]) == (0.0, 1.0, 0.0)
    assert s["unplayable_dropped"] == pytest.approx(2 / 7) and s["leftovers_dropped"] == 0.0
    no_strings = {**REF, "notes": [{k: v for k, v in n.items() if k != "string"} for n in REF["notes"]]}
    assert G.summarize([G.score_tab(no_strings, _tab(chord + line))])["string_agreement"] == 0.0  # Slakh: nothing to agree with


def test_a_unison_on_two_strings_agrees_whichever_way_its_notes_are_matched():
    ref = {"notes": [{"pitch": p, "onset": 0.0, "offset": 0.5, "string": s} for p, s in ((67, 4), (62, 3), (67, 2), (71, 1))]}  # a ukulele's G: 0232
    written = [(67, 0.0, 0, 2, 3, 1.0), (62, 0.0, 0, 3, 2, 1.0), (67, 0.0, 0, 4, 0, 1.0), (71, 0.0, 0, 1, 2, 1.0)]
    assert G.summarize([G.score_tab(ref, _tab(written))])["string_agreement"] == 1.0
    one = [(67, 0.0, 0, 2, 3, 1.0), (62, 0.0, 0, 3, 2, 1.0), (71, 0.0, 0, 1, 2, 1.0)]  # the unison written once
    s = G.summarize([G.score_tab(ref, _tab(one))])
    assert s["string_agreement"] == 1.0 and s["string_recall"] == 0.75


def test_the_suite_skips_without_its_data_and_is_gated(tmp_path):
    r = suites.run_suite("guitar-tab", data=tmp_path)
    assert r["status"] == "skipped" and "eval/guitarset" in r["reason"]
    base = suites.load_baselines()["suites"]["guitar-tab"]["metrics"]
    for group in ("tune.solo", "tune.comp", "report.solo", "report.comp", "song"):
        assert base[f"{group}.violations"] == {"value": 0, "tolerance": 0, "higher_is_better": False}, group
        assert f"{group}.onset_f1" in base and f"{group}.chord_recall" in base
    assert "report.comp.string_agreement" in base and "song.string_agreement" not in base  # Slakh has no strings
    assert "report.comp.string_recall" in base and "song.string_recall" not in base
    optional = ("song.", "song_one.", "idmt.")  # Slakh's songs and IDMT-SMT-Guitar: scored where they are
    slakh_free = {k: (v["value"] if isinstance(v, dict) else v) for k, v in base.items() if not k.startswith(optional)}
    report = suites.gate([{"suite": "guitar-tab", "status": "ran", "metrics": slakh_free, "skipped_parts": ["song", "song_one", "idmt"],
                           "seconds": 0.0}])
    assert report["passed"]  # without the Slakh tracks the song part is skipped, not missing


def test_an_idmt_annotation_is_read_with_its_strings_counted_from_the_high_e(tmp_path):
    root = tmp_path / "IDMT"
    for d in ("dataset2/annotation", "dataset2/audio", "dataset3/annotation", "dataset3/audio"):
        (root / d).mkdir(parents=True)
    event = ("<event><pitch>{p}</pitch><onsetSec>{a}</onsetSec><offsetSec>{b}</offsetSec><excitationStyle>FS</excitationStyle>"
             "<stringNumber>{s}</stringNumber><fretNumber>{f}</fretNumber></event>")
    notes = [(45, 0.5, 1.0, 1, 5), (61, 0.5, 1.0, 4, 6), (64, 1.0, 1.5, 6, 0), (59, 1.5, 2.0, 5, 0)]
    xml = "<instrumentRecording><transcription>" + "".join(event.format(p=p, a=a, b=b, s=s_, f=f) for p, a, b, s_, f in notes) + "</transcription></instrumentRecording>"
    for name in ("dataset2/annotation/AR_Lick1_FN.xml", "dataset2/annotation/LP_Lick1_FN.xml", "dataset2/annotation/AR_G_fret_0-20.xml",
                 "dataset3/annotation/nocturne.xml"):
        (root / name).write_text(xml)
        (root / name.replace("annotation", "audio").replace(".xml", ".wav")).write_bytes(b"")
    assert [(x.stem, style) for x, _, style in G.idmt_sources(root)] == [("AR_Lick1_FN", "lick"), ("LP_Lick1_FN", "lick"), ("nocturne", "piece")]
    made = G.build_idmt(root, tmp_path)
    refs = {d.name: json.loads((d / "reference.json").read_text()) for d in made}
    assert {k: (v["player"], v["split"]) for k, v in refs.items()} == {
        "lick-AR_Lick1_FN": ("AR", "tune"), "lick-LP_Lick1_FN": ("LP", "report"), "piece-nocturne": ("piece", "report")}
    first = refs["piece-nocturne"]["notes"]
    assert [(n["pitch"], n["string"]) for n in first] == [(45, 6), (61, 3), (64, 1), (59, 2)]  # its string 1 is the low E
    assert G.evaluate_idmt(tmp_path, "tune") == ({}, [])  # no model outputs: nothing to score


def test_notes_that_were_not_heard_are_counted_and_scored_apart():
    chord = [(p, 0.01 * k, 0, 6 - k, f, 1.0) for k, (p, f) in enumerate([(43, 3), (47, 2), (50, 0), (55, 0), (59, 0), (67, 3)])]
    t = _tab(chord)
    t["notes"][1]["inferred"] = True  # in the reference: a right guess
    t["notes"].append({**t["notes"][0], "pitch": 62, "inferred": True})  # not in the reference: a wrong one
    s = G.summarize([G.score_tab(REF, t)])
    assert s["inferred_share"] == pytest.approx(2 / 7) and s["inferred_right"] == 0.5


def test_the_slakh_songs_are_read_from_slakh_guitar_or_from_a_data_folder_not_yet_moved(tmp_path):
    """The set was `slakh-guitar-as-written` while the references were corrected: a data folder where that is still
    a folder of its own is read from it, one where it is a link to `slakh-guitar` (or gone) from `slakh-guitar`."""
    assert (G.SONG_SET, G.SONG_SET_BEFORE) == ("slakh-guitar", "slakh-guitar-as-written")
    new, before = tmp_path / "eval" / G.SONG_SET, tmp_path / "eval" / G.SONG_SET_BEFORE
    assert G.song_root(tmp_path) == new and G.song_entries(tmp_path) == []
    for root in (new, before):
        (root / "Track00001").mkdir(parents=True)
        (root / "Track00001" / "reference.json").write_text("{}")
    assert G.song_root(tmp_path) == before and G.song_entries(tmp_path) == [before / "Track00001"]
    (before / "Track00001" / "reference.json").unlink()
    (before / "Track00001").rmdir()
    before.rmdir()
    before.symlink_to(new, target_is_directory=True)
    assert G.song_root(tmp_path) == new and G.song_entries(tmp_path) == [new / "Track00001"]
