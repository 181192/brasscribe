"""A soloist phrase that goes past even the solo range keeps its contour.

A phrase that peaks above the solo range must not lose its peak an octave down note by note: a
rising line would then fall a seventh and climb back, and a trill would become leaps of a tenth.
Only a lone outlier (both neighbours inside the range, far from it) moves on its own.
"""

import pytest

from brasscribe_music.arranger import place_soloist
from brasscribe_music.instruments import BRASS_BAND
from brasscribe_music.score_model import Note


def line(pitches):
    return [Note(p, 12 * i, 12) for i, p in enumerate(pitches)]


def direction(ps):
    return [(b > a) - (b < a) for a, b in zip(ps, ps[1:])]


@pytest.mark.parametrize("pitches", [
    [76, 79, 81, 84, 86, 88, 86, 84, 81, 79],  # an arch that peaks two tones above the range
    [72, 74, 76, 77, 79, 81, 83, 84, 86, 87],  # a run that ends above it
    [84, 86, 84, 86, 84, 86, 84],              # a trill across the top
])
def test_a_phrase_past_the_solo_range_keeps_its_direction(pitches):
    placed = [n.pitch for n in place_soloist(line(pitches), BRASS_BAND.lead_part, [])]
    lo, hi = BRASS_BAND.lead_part.instrument.solo_range
    assert all(lo <= p <= hi for p in placed)
    assert direction(placed) == direction(pitches), placed


def test_a_lone_outlier_still_moves_alone():
    placed = [n.pitch for n in place_soloist(line([72, 74, 76, 90, 79, 81]), BRASS_BAND.lead_part, [])]
    assert placed == [72, 74, 76, 78, 79, 81]
