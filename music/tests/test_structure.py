import numpy as np

from brasscribe_music.structure import MAX_GAP, MIN_GAP, letters, section_starts


def test_boundary_where_a_layer_enters_and_forced_a_tempo():
    feats = np.full((40, 3), -40.0)
    feats[20:, 2] = -5.0  # drums enter at bar 20
    starts = section_starts(feats, forced=[6])
    assert 6 in starts and 20 in starts
    assert all(b - a >= MIN_GAP for a, b in zip(starts, starts[1:]))


def test_long_stretches_get_a_letter():
    feats = np.zeros((100, 2))
    starts = section_starts(feats)
    edges = [0] + starts + [100]
    assert all(b - a <= MAX_GAP for a, b in zip(edges, edges[1:]))


def test_letters_skip_i():
    assert letters(10) == list("ABCDEFGHJK")
