from brasscribe_music.rhythm_spelling import SINGLE, TRIPLET, pieces

BAR = 96  # 4/4


def _check(start, end, bar=BAR):
    ps = pieces(start, end, bar)
    assert ps[0][0] == start and ps[-1][1] == end
    assert all(a[1] == b[0] for a, b in zip(ps, ps[1:]))
    for a, b in ps:
        assert (b - a) in SINGLE | TRIPLET, (a, b)
        assert a // bar == (b - 1) // bar  # never across a bar line
    return ps


def test_simple_values_stay_whole():
    assert _check(0, 96) == [(0, 96)]
    assert _check(0, 72) == [(0, 72)]
    assert _check(48, 96) == [(48, 96)]
    assert _check(12, 24) == [(12, 24)]


def test_no_double_dots_and_middle_of_bar_shown():
    assert _check(24, 66) == [(24, 48), (48, 66)]  # double-dotted quarter from beat 2
    assert _check(24, 72) == [(24, 48), (48, 72)]  # half on beat 2 shows beat 3
    assert _check(0, 84) == [(0, 72), (72, 84)]  # double-dotted half


def test_offbeat_values_split_at_the_beat():
    assert _check(18, 42) == [(18, 24), (24, 42)]
    assert _check(18, 30) == [(18, 30)]  # an anticipated 8th stays one symbol
    assert _check(42, 54) == [(42, 54)]  # also over the middle of the bar
    assert _check(42, 66) == [(42, 48), (48, 66)]  # a longer value still shows beat 3
    assert _check(6, 30) == [(6, 24), (24, 30)]  # dotted 8th inside the beat


def test_triple_dotted_rest_and_long_spans():
    assert _check(6, 96) == [(6, 24), (24, 48), (48, 96)]
    for s, e in [(0, 300), (30, 222), (3, 11), (8, 40), (90, 190)]:
        _check(s, e)


def test_three_four_has_no_middle():
    assert _check(24, 72, bar=72) == [(24, 72)]
