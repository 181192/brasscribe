import numpy as np

from brasscribe_music.beats import clean_beats


def grid(n=40, ibi=0.5):
    return np.arange(n) * ibi


def test_missed_beat_is_restored_where_a_note_starts():
    t = np.delete(grid(), 10)  # beat 10 missing: one interval of two beats
    c = clean_beats(t, onsets=grid())
    assert c.inserted == 1 and np.allclose(c.times, grid())


def test_long_interval_without_onsets_is_a_held_chord():
    t = np.delete(grid(), 10)
    onsets = np.delete(grid(), 10)
    c = clean_beats(t, onsets=onsets)
    assert c.inserted == 0


def test_inserted_beat_is_removed_and_downbeat_label_kept():
    t = np.insert(grid(), 11, 5.1)  # a spurious beat 0.1 s after beat 10
    lab = np.insert(np.arange(40) % 4 == 0, 11, False)
    c = clean_beats(t, lab)
    assert c.removed == 1 and np.allclose(c.times, grid())
    assert c.phase(4) == 0


def test_free_time_ranges_are_left_alone():
    t = np.concatenate([[0.0, 2.0, 2.3, 5.0], 5.5 + grid(20)])
    c = clean_beats(t, skip=[(0, 3)], onsets=t)
    assert np.allclose(c.times[:4], t[:4])


def test_phase_by_majority_of_labels():
    lab = np.zeros(40, bool)
    lab[[2, 6, 10, 14, 17]] = True  # one stray label
    from brasscribe_music.beats import CleanBeats
    assert CleanBeats(grid(), lab, 0, 0).phase(4) == 2
