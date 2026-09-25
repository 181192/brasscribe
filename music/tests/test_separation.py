import numpy as np

from brasscribe_music.separation import check_stem

SR = 1000


def _tone(seconds, level):
    return (level * np.sin(np.arange(int(seconds * SR)) * 0.2)).astype(np.float32)


def test_stem_with_the_soloist_passes():
    solo = _tone(30, 0.3)
    mix = solo + _tone(30, 0.5)
    c = check_stem(solo, mix, SR)
    assert not c.failed and c.quiet_windows == []


def test_near_silent_stem_fails():
    mix = _tone(30, 0.5)
    c = check_stem(mix * 0.005, mix, SR)
    assert c.failed and c.stem_minus_mix_db < -40


def test_quiet_window_is_listed():
    solo = _tone(30, 0.3)
    solo[10 * SR:20 * SR] *= 0.001
    mix = _tone(30, 0.5)
    c = check_stem(solo, mix, SR)
    assert not c.failed and [(a, b) for a, b, _ in c.quiet_windows] == [(10.0, 20.0)]
