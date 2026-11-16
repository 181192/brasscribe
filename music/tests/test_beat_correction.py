"""A player's correction of the beat (beats.correct) and the level rule that splits a beat in three."""

from __future__ import annotations

import numpy as np
import pytest

from scribe_music.beats import GIVEN, LEVELS, Correction, Hold, correct, tracked_bars, write_beats
from scribe_music.quantize import choose_level, in_three, level_factor, split


def _beats(n: int = 17, bpm: float = 120.0, per_bar: int = 4, first: int = 0) -> np.ndarray:
    return np.array([[i * 60 / bpm, (i - first) % per_bar + 1] for i in range(n)])


def _downbeats(table: np.ndarray) -> list[float]:
    return [round(float(t), 6) for t, pos in table if int(pos) == 1]


# ---------------------------------------------------------------- nothing said

def test_a_correction_that_says_nothing_returns_the_tracked_beats():
    b = _beats()
    b[5, 1] = 1  # a stray downbeat label stays as the tracker gave it
    assert correct(b, Correction()) is not None and np.array_equal(correct(b, Correction()), b)
    assert np.array_equal(correct(b, Correction(level="as-tracked")), b)
    assert Correction().given == () and Correction(level="as-tracked").given == ("level",)


def test_a_hold_with_no_surplus_beats_changes_nothing():
    b = _beats()
    assert np.array_equal(correct(b, Correction(holds=(Hold(2.0, 3.0, 2),))), b)  # one beat inside, two written


def test_under_two_beats_there_is_nothing_to_correct():
    one = np.array([[0.5, 1.0]])
    assert np.array_equal(correct(one, Correction(level="double", beats_per_bar=3)), one)
    assert correct(np.zeros((0, 2)), Correction(level="half")).shape == (0, 2)


# ---------------------------------------------------------------- the level

def test_double_and_triple_split_every_beat_and_keep_the_bar_as_long_in_time():
    b = _beats(9, per_bar=4, first=1)
    two, three = correct(b, Correction(level="double")), correct(b, Correction(level="triple"))
    assert len(two) == 17 and np.allclose(np.diff(two[:, 0]), 0.25)
    assert len(three) == 25 and np.allclose(np.diff(three[:, 0]), 0.5 / 3)
    assert tracked_bars(two[:, 1]) == (8, 2) and tracked_bars(three[:, 1]) == (12, 3)
    assert _downbeats(two) == _downbeats(b) == _downbeats(three)  # the bars start where they did


@pytest.mark.parametrize("level, keep", [("half", 2), ("third", 3)])
def test_half_and_third_keep_every_second_or_third_beat_from_the_phase(level, keep):
    b = _beats(25, per_bar=keep * 2)
    for phase in range(keep):
        out = correct(b, Correction(level=level, phase=phase))
        assert np.array_equal(out[:, 0], b[phase::keep, 0])
        assert tracked_bars(out[:, 1])[0] == 2  # the bar is as long in time
        assert _downbeats(out)[0] == pytest.approx(b[phase, 0])  # the first kept beat at or after the tracked downbeat


def test_half_keeps_the_tracked_downbeat_when_it_is_among_the_kept_beats():
    b = _beats(17, per_bar=4, first=2)
    out = correct(b, Correction(level="half"))
    assert _downbeats(out)[0] == pytest.approx(1.0) and tracked_bars(out[:, 1]) == (2, 1)
    off = correct(b, Correction(level="half", phase=1))  # beats 1, 3, 5: the downbeat (2) is not kept, the next one is first
    assert _downbeats(off)[0] == pytest.approx(1.5)


def test_a_bar_that_does_not_divide_keeps_its_number_of_beats():
    out = correct(_beats(19, per_bar=3), Correction(level="half"))
    assert tracked_bars(out[:, 1])[0] == 3


def test_too_few_beats_to_halve_is_refused():
    with pytest.raises(ValueError, match="too few beats"):
        correct(_beats(3), Correction(level="third", phase=1))


def test_bad_values_are_refused_when_the_correction_is_made():
    for bad in (dict(level="quadruple"), dict(phase=1), dict(level="half", phase=2), dict(level="third", phase=3),
                dict(beats_per_bar=0), dict(beats_per_bar=13), dict(holds=(Hold(2.0, 1.0, 2),)), dict(holds=(Hold(1.0, 2.0, 0),))):
        with pytest.raises(ValueError):
            Correction(**bad)
    assert set(LEVELS) == {"as-tracked", "double", "half", "triple", "third"}


# ---------------------------------------------------------------- holds

def test_a_hold_takes_out_the_beats_the_tracker_counted_through_it():
    b = _beats(21)  # a beat every 0.5 s; a chord held from 2.0 to 5.0 is written two beats long
    out = correct(b, Correction(holds=(Hold(2.0, 5.0, 2),)))
    assert [round(float(t), 2) for t in out[:, 0] if 1.9 < t < 5.1] == [2.0, 2.5, 5.0]  # its own beat, one more, the next note's
    assert len(out) == len(b) - 4
    one = correct(b, Correction(holds=(Hold(2.0, 5.0, 1),)))
    assert [round(float(t), 2) for t in one[:, 0] if 1.9 < t < 5.1] == [2.0, 5.0]


def test_the_bars_run_on_through_a_hold():
    b = _beats(21)
    out = correct(b, Correction(holds=(Hold(2.0, 5.0, 2),)))
    assert list(out[:, 1].astype(int)) == [(i % 4) + 1 for i in range(len(out))]  # every bar four beats, no gap in the count


def test_a_hold_over_the_first_downbeat_moves_it_to_the_next_beat_left():
    b = _beats(21, first=1)
    out = correct(b, Correction(holds=(Hold(0.2, 1.5, 1),)))  # the beats at 0.5 (the downbeat) and 1.0 go
    assert _downbeats(out)[0] == pytest.approx(1.5)


def test_holds_that_leave_under_two_beats_are_refused():
    with pytest.raises(ValueError, match="fewer than two beats"):
        correct(_beats(5), Correction(holds=(Hold(0.0, 2.0, 1), Hold(0.0, 2.1, 1))))


def test_holds_count_in_the_corrected_level():
    b = _beats(11, bpm=60.0)  # tracked at half speed: doubled, a beat every 0.5 s
    out = correct(b, Correction(level="double", holds=(Hold(2.0, 5.0, 2),)))
    assert [round(float(t), 2) for t in out[:, 0] if 1.9 < t < 5.1] == [2.0, 2.5, 5.0]


# ---------------------------------------------------------------- the bar

def test_beats_per_bar_and_the_first_downbeat_are_the_players():
    b = _beats(13)
    out = correct(b, Correction(beats_per_bar=3, first_downbeat_s=1.07))
    assert tracked_bars(out[:, 1]) == (3, 2) and _downbeats(out)[:2] == [1.0, 2.5]
    assert np.array_equal(out[:, 0], b[:, 0])
    assert Correction(beats_per_bar=3, first_downbeat_s=1.07).given == ("bars", "downbeat")


def test_a_first_downbeat_alone_keeps_the_tracked_bar_length():
    out = correct(_beats(13, per_bar=3), Correction(first_downbeat_s=0.5))
    assert tracked_bars(out[:, 1]) == (3, 1)
    assert list(out[:4, 1].astype(int)) == [3, 1, 2, 3]  # the beat before the downbeat ends a bar


def test_everything_at_once_applies_level_then_holds_then_bars():
    b = _beats(11, bpm=60.0, per_bar=2)
    c = Correction(level="double", beats_per_bar=3, first_downbeat_s=0.5, holds=(Hold(2.0, 5.0, 2),))
    out = correct(b, c)
    assert c.given == GIVEN
    assert len(out) == 21 - 4 and tracked_bars(out[:, 1]) == (3, 1)
    assert [round(float(t), 2) for t in out[:, 0] if 1.9 < t < 5.1] == [2.0, 2.5, 5.0]


def test_the_corrected_beats_are_written_as_the_tracker_writes_them(tmp_path):
    out = correct(_beats(9), Correction(level="triple"))
    write_beats(tmp_path / "mix.beats", out)
    back = np.loadtxt(tmp_path / "mix.beats", ndmin=2)
    assert np.array_equal(back, out)  # to the last bit
    assert (tmp_path / "mix.beats").read_text().splitlines()[0] == "0.0\t1"


# ---------------------------------------------------------------- a beat split in three

def _onsets(beats: np.ndarray, fractions: list[float]) -> np.ndarray:
    return np.array([t + (u - t) * f for t, u in zip(beats, beats[1:]) for f in fractions])


def test_a_slow_beat_the_notes_divide_in_three_is_split_in_three_when_asked():
    beats = np.arange(0, 40) * 0.9  # 67 BPM: a bar of three counted in one
    on = _onsets(beats, [0.0, 1 / 3, 2 / 3])
    assert in_three(beats, on)
    out = choose_level(beats, on, three=True)
    assert level_factor(beats, out) == 3 and np.allclose(np.diff(out), 0.3)
    assert np.array_equal(out, split(beats, 3))


def test_without_being_asked_the_level_rule_is_as_it_was():
    beats = np.arange(0, 40) * 0.9
    on = _onsets(beats, [0.0, 1 / 3, 2 / 3])
    assert np.array_equal(choose_level(beats, on), beats)  # a third of a beat apart is not dense enough to double
    dense = _onsets(beats, [0.0, 0.25, 0.5, 0.75])
    for three in (False, True):
        doubled = choose_level(beats, dense, three)
        assert level_factor(beats, doubled) == 2 and np.array_equal(doubled, np.sort(np.concatenate([beats, (beats[:-1] + beats[1:]) / 2])))


def test_a_shuffle_and_a_fast_beat_are_not_split_in_three():
    slow = np.arange(0, 40) * 0.9
    shuffle = _onsets(slow, [0.0, 2 / 3])  # long-short: only the second third
    assert not in_three(slow, shuffle) and level_factor(slow, choose_level(slow, shuffle, three=True)) == 1
    fast = np.arange(0, 40) * 0.5  # 120 BPM
    assert in_three(fast, _onsets(fast, [0.0, 1 / 3, 2 / 3]))
    assert level_factor(fast, choose_level(fast, _onsets(fast, [0.0, 1 / 3, 2 / 3]), three=True)) == 1


def test_a_few_triplets_among_even_notes_do_not_split_the_beat():
    beats = np.arange(0, 40) * 0.9
    on = np.concatenate([_onsets(beats[:30], [0.0, 0.5]), _onsets(beats[30:], [0.0, 1 / 3, 2 / 3])])
    assert not in_three(beats, on)
