import numpy as np

from brasscribe_music.durations import FRAME, Contour, apply_written, contour_offsets, written_durations
from brasscribe_music.quantize import BeatMap, QNote

BM = BeatMap(np.arange(0, 20, 0.5))  # 120 BPM: one beat = 0.5 s = 24 ticks


def q(start_beat: float, on: float, off: float, pitch: int = 60) -> QNote:
    s = int(start_beat * 24)
    return QNote(pitch, s, s + 6, on, off)


def test_legato_note_is_held_to_next_onset():
    notes = [q(0, 0.0, 0.40), q(1, 0.5, 0.9)]  # played 80% of the beat
    w = written_durations(notes, BM)
    assert w[0].dur == 24 and not w[0].staccato


def test_detached_note_gets_readable_value_and_rest():
    notes = [q(0, 0.0, 0.24), q(2, 1.0, 1.4)]  # an 8th's length, next onset two beats later
    w = written_durations(notes, BM)
    assert w[0].dur == 12 and not w[0].staccato


def test_long_silence_before_next_onset_is_a_rest_even_if_played_over_half():
    notes = [q(0, 0.0, 1.1), q(4, 2.0, 2.4)]  # 2.2 beats of 4: gap 1.8 beats > dotted 8th
    w = written_durations(notes, BM)
    assert w[0].dur == 48  # half note, then rests


def test_staccato_when_played_under_half_the_written_length():
    notes = [q(0, 0.0, 0.05), q(0.5, 0.25, 0.3)]  # 16th room, performed a 40th
    w = written_durations(notes, BM)
    assert w[0].dur == 6 and w[0].staccato


def test_apply_written_sets_ends():
    notes = [q(1, 0.5, 0.9), q(0, 0.0, 0.45)]
    out = apply_written(notes, BM)
    assert [(n.start, n.end) for n, _ in out] == [(0, 24), (24, 42)]  # 0.8 beat played at the end -> dotted 8th


def _contour(segments, total=4.0):
    t = np.arange(0, total, FRAME)
    midi = np.full(len(t), np.nan)
    db = np.full(len(t), -140.0)
    for a, b, p, level in segments:
        sel = (t >= a) & (t < b)
        midi[sel] = p
        db[sel] = level
    return Contour(t, midi, db)


def test_contour_offset_follows_sustain_and_stops_at_pitch_change():
    c = _contour([(0.0, 0.1, 72, -25), (0.1, 1.5, 72.1, -60), (1.5, 2.0, 74, -30)])
    end, = contour_offsets(c, [(0.0, 72)])
    assert abs(end - 1.5) < 2 * FRAME


def test_contour_offset_stops_at_next_onset_and_folds_octaves():
    c = _contour([(0.0, 2.0, 60 + 12, -30)])  # tracker an octave up
    ends = contour_offsets(c, [(0.0, 60), (1.0, 60)])
    assert abs(ends[0] - 1.0) < 2 * FRAME and abs(ends[1] - 2.0) < 2 * FRAME


def test_contour_level_gate_cuts_quiet_tail():
    c = _contour([(0.0, 0.1, 72, -20), (0.1, 2.0, 72, -95)])
    end, = contour_offsets(c, [(0.0, 72)])
    assert end < 0.2
    loose, = contour_offsets(c, [(0.0, 72)], drop_db=80, floor_db=-115)
    assert abs(loose - 2.0) < 2 * FRAME


def test_keep_grid_gives_a_detached_note_on_a_straight_beat_a_straight_value():
    # 0.4 of a beat, then rests to the next onset two beats later: the nearest readable value is a triplet 8th
    # (8 ticks); on the beat's own straight grid it is an 8th (12), the nearer of a 16th and an 8th.
    notes = [q(0, 0.0, 0.2), q(2, 1.0, 1.4)]
    assert written_durations(notes, BM)[0].dur == 8
    assert written_durations(notes, BM, keep_grid=True)[0].dur == 12


def test_keep_grid_gives_a_detached_note_on_a_triplet_beat_a_triplet_value():
    # Triplet 8ths on beat 0; the last is played a 16th long, then two beats rest.
    notes = [q(0, 0.0, 0.3), q(1 / 3, 1 / 6, 0.3), q(2 / 3, 1 / 3, 1 / 3 + 0.125), q(3, 1.5, 1.9)]
    assert written_durations(notes, BM)[2].dur == 6
    assert written_durations(notes, BM, keep_grid=True)[2].dur == 8


def test_beat_values_follow_the_grid_quantize_chose():
    from brasscribe_music.durations import STRAIGHT, TRIPLET, beat_values
    from brasscribe_music.quantize import TICKS_PER_BEAT, choose_grids, choose_grids_dense, quantize

    rng = np.random.default_rng(70)
    beats = np.arange(0, 40, 0.5)
    bm = BeatMap(beats)
    for case in range(200):
        dense = bool(case % 2)
        grid = rng.choice([2, 3, 4, 6])
        steps = rng.choice([1, 1, 2, 3], size=60) / grid
        on_beats = np.cumsum(steps) + rng.normal(0, 0.03, size=60)
        on_beats = on_beats[(on_beats > 0) & (on_beats < 70)]
        onsets = bm.to_seconds(on_beats)
        raw = [{"pitch": 60, "onset": float(o), "offset": float(o) + 0.1} for o in onsets]
        notes = quantize(raw, beats, monophonic=dense, auto_level=False, dense=dense)
        on = bm.to_beats(onsets)
        grids = choose_grids_dense(on, None, np.r_[np.diff(bm.t), bm.t[-1] - bm.t[-2]]) if dense else choose_grids(on)
        values = beat_values(notes)
        for n in notes:
            k = n.start // TICKS_PER_BEAT
            if values[k] is TRIPLET:
                assert grids.get(k, 4) in (3, 6), (case, n)
            if grids.get(k, 4) not in (3, 6):
                assert values[k] is STRAIGHT, (case, n)
