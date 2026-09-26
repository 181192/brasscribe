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
