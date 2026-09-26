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


def test_gate_keeps_a_consistent_track_and_single_unlabelled_edits():
    from brasscribe_music.beats import clean_beats_gated
    t = np.delete(grid(), 10)
    lab = np.delete(np.arange(40) % 4 == 0, 10)
    # Labels already agree with the tracked beats before the gap: restoring would not improve them.
    lab2 = np.arange(len(t)) % 4 == 0
    assert not clean_beats_gated(t, lab2, 4, onsets=grid()).applied
    # The labels shift by a beat after the gap, so restoring it makes them agree: applied.
    assert clean_beats_gated(t, lab, 4, onsets=grid()).applied
    # One beat per bar: a single long interval stays (more likely a held note).
    assert not clean_beats_gated(t, np.ones(len(t), bool), 1, onsets=grid()).applied


def _accents(meter, n_bars, ibi=0.5, strong=1.0, weak=0.25):
    """Onsets on every beat; downbeats get long notes."""
    t = np.arange(n_bars * meter) * ibi
    dur = np.array([strong if k % meter == 0 else weak for k in range(len(t))])
    return t, dur


def test_plausible_labels_pass_through():
    from brasscribe_music.beats import meter_of
    t = grid(40)
    lab = np.arange(40) % 4 == 1
    m = meter_of(t, lab, t, np.full(40, 0.2))
    assert m.from_labels and m.beats_per_bar == 4 and m.first_downbeat == 1 and m.times is None


def test_labels_on_every_beat_meter_from_accents():
    from brasscribe_music.beats import meter_of
    for meter in (3, 4):
        t, dur = _accents(meter, 12)
        on = t + 0.01
        lab = np.ones(len(t), bool)  # small0 on a solo: every beat labelled a downbeat
        m = meter_of(t, lab, on, dur)
        assert not m.from_labels and m.beats_per_bar == meter, meter
        assert m.first_downbeat % meter == 0


def test_position_labels_set_the_phase():
    from brasscribe_music.beats import meter_of
    t = grid(48)
    k = np.arange(48)
    # True downbeats at 2, 5, 8, ... are always labelled 1; in every other bar the other beats are too.
    pos = np.where(k % 3 == 2, 1, np.where((k // 3) % 2 == 0, 1, np.where(k % 3 == 0, 2, 3)))
    lab = pos == 1
    m = meter_of(t, lab, t, np.full(48, 0.2), positions=pos)
    assert m.beats_per_bar == 3 and m.first_downbeat % 3 == 2


def test_track_bar_phase_drops_an_inserted_and_restores_a_missed_beat():
    from brasscribe_music.beats import track_bar_phase
    t = grid(40)
    strength = (np.arange(40) % 4 == 0).astype(float)
    t_ins = np.insert(t, 11, 5.25)
    s_ins = np.insert(strength, 11, 0.0)
    out, first = track_bar_phase(t_ins, s_ins, 4)
    assert len(out) == 40 and first == 0
    t_miss = np.delete(t, 10)
    s_miss = np.delete(strength, 10)
    out, first = track_bar_phase(t_miss, s_miss, 4)
    assert len(out) == 40 and np.allclose(out, t)
