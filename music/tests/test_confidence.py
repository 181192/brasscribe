import re

import numpy as np

from brasscribe_music import confidence as C
from brasscribe_music.arranger import arrange_layers
from brasscribe_music.durations import Contour
from brasscribe_music.musicxml import band_sounds, build_band_score, write_musicxml
from brasscribe_music.score_model import Composition, KeySig, Meter, Note, Voice, VoiceRole


def test_calibration_is_shipped_and_orders_the_classes():
    m = C.Model.load()
    assert 0 < m.mark_risk < m.very_risk < 1
    only_sw, confirmed = C.p_correct(C.features({"sw"}, 0.3, 0.8), m), C.p_correct(C.features({"sw", "bp"}, 0.3, 0.8), m)
    assert confirmed > only_sw
    # Longer, better-supported notes are more likely right.
    assert C.p_correct(C.features({"sw"}, 0.6, 0.9), m) > C.p_correct(C.features({"sw"}, 0.06, 0.1), m)
    # No contour is its own case, not "no support".
    assert C.p_correct(C.features({"sw", "bp"}, 0.3, None), m) > C.p_correct(C.features({"sw", "bp"}, 0.3, 0.0), m)


def test_support_follows_the_contour():
    t = np.arange(0, 2, 0.016)
    midi = np.full(len(t), 72.0)
    conf = np.where(t < 1, 0.9, 0.1)
    c = Contour(t, midi, np.zeros(len(t)), conf)
    assert C.support(c, 0.2, 72) > 0.8
    assert C.support(c, 1.2, 72) < 0.2
    assert C.support(c, 0.2, 65) == 0.0
    assert C.support(None, 0.2, 72) is None


def test_review_groups_merge_neighbours_within_a_phrase():
    bar = 96
    mark, very = 0.7, 0.4
    notes = [(0, 12, 0.5), (12, 24, 0.9), (24, 36, 0.3), (36, 48, 0.95), (48, 60, 0.96), (60, 72, 0.5),
             (84, 96, 0.5), (96, 108, 0.5), (300, 312, 0.5)]
    g = C.review_groups(notes, bar, mark, very)
    # 0 and 24 join (one unmarked between); 60 starts a new group (two unmarked between);
    # 84 and 96 join 60 across the bar line (no rest of a beat); 300 is after a rest.
    assert [(x.start, x.end, x.notes, x.very) for x in g] == [(0, 36, 2, True), (60, 108, 3, False), (300, 312, 1, False)]


def test_one_mark_per_review_group_in_the_score(tmp_path):
    solo = [Note(72 + i % 3, i * 12, 12, confidence=0.3 if i in (2, 3, 4, 10) else 0.99) for i in range(16)]
    comp = Composition("c", [Voice("solo", VoiceRole.MELODY, solo, layer="solo")], [Meter(0, 4)], [KeySig(0, 0)])
    arr = arrange_layers(comp)
    xml = write_musicxml(build_band_score(arr, comp), tmp_path / "c.musicxml", band_sounds(arr)).read_text()
    solo_part = xml.split('<part id="')[2]  # Soprano is first; the Solo Cornet part follows
    assert len(re.findall(r">\?</words>", solo_part)) == 2
    assert 'line-type="dashed"' in solo_part


def test_review_items_in_the_composition_match_the_marks(tmp_path):
    from brasscribe_music.confidence import review_groups

    solo = [Note(72 + i % 5, i * 12, 12, confidence=0.3 if i % 7 in (0, 1) else 0.99) for i in range(40)]
    comp = Composition("c", [Voice("solo", VoiceRole.MELODY, solo, layer="solo")], [Meter(0, 4)], [KeySig(0, 0)])
    m = C.Model.load()
    groups = review_groups([(n.start, n.end, n.confidence) for n in solo], 96, 1 - m.mark_risk, 1 - m.very_risk)
    arr = arrange_layers(comp)
    xml = write_musicxml(build_band_score(arr, comp), tmp_path / "c.musicxml", band_sounds(arr)).read_text()
    solo_part = xml.split('<part id="')[2]
    assert len(re.findall(r">\?</words>", solo_part)) == len(groups)
