"""A take with fewer than two tracked beats gets a beat grid from its onsets (beats.fallback_beats)."""

import numpy as np

from brasscribe_music.beats import FALLBACK_PREFERRED, fallback_beats


def test_grid_from_8th_notes_at_120():
    on = 1.0 + np.arange(16) * 0.25
    t, pos = fallback_beats(np.array([1.0]), on)
    assert np.allclose(np.diff(t), 0.5)
    assert t[0] <= on[0] and t[-1] >= on[-1] and 1.0 in np.round(t, 6)
    assert set(pos) <= {1, 2, 3, 4}


def test_no_beats_and_no_onsets():
    t, pos = fallback_beats(np.array([]), np.array([]))
    assert len(t) >= 2 and np.allclose(np.diff(t), FALLBACK_PREFERRED)
