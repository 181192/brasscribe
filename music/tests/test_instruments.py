from brasscribe_music.instruments import BRASS_BAND, INSTRUMENTS, validate_range

# MIDI numbers
C4, D4, Bb3, A4, Bb2, C5 = 60, 62, 58, 69, 46, 72


def test_bb_cornet_reads_a_tone_above_sounding():
    cnt = INSTRUMENTS["bb-cornet"]
    assert cnt.written(Bb3) == C4
    assert cnt.sounding(D4) == C4


def test_eb_instruments():
    # Eb soprano sounds a minor 3rd above written; Eb tenor horn a major 6th below.
    assert INSTRUMENTS["eb-soprano-cornet"].written(63) == C4  # concert Eb4 -> written C4
    assert INSTRUMENTS["eb-tenor-horn"].written(51) == C4  # concert Eb3 -> written C4
    # Eb bass: an octave plus a major 6th below written.
    assert INSTRUMENTS["eb-bass"].written(39) == C4  # concert Eb2 -> written C4


def test_treble_clef_bb_low_brass_is_a_ninth():
    for iid in ("baritone", "tenor-trombone", "euphonium"):
        assert INSTRUMENTS[iid].written(Bb2) == C4, iid
    assert INSTRUMENTS["bb-bass"].written(34) == C4  # concert Bb1 -> written C4


def test_bass_trombone_is_concert_pitch_bass_clef():
    btb = INSTRUMENTS["bass-trombone"]
    assert btb.written(40) == 40 and btb.clef == "bass"


def test_written_ranges_are_consistent_for_cornet_family():
    # All treble-clef upper brass share the written amateur range F#3..A5.
    for iid in ("bb-cornet", "flugelhorn", "eb-soprano-cornet", "eb-tenor-horn"):
        inst = INSTRUMENTS[iid]
        lo, hi = inst.comfortable
        assert (inst.written(lo), inst.written(hi)) == (54, 81), iid


def test_range_checks_and_octave_fit():
    cnt = INSTRUMENTS["bb-cornet"]
    assert cnt.check(C5) == "ok"
    assert cnt.check(81) == "uncomfortable"
    assert cnt.check(90) == "impossible"
    assert cnt.fit_octave(96) == C5
    assert INSTRUMENTS["eb-bass"].fit_octave(A4) == 57


def test_validate_range_reports_written_pitch():
    solo = BRASS_BAND.by_name("Solo Cornet")
    issues = validate_range(solo, [C4, 90, 81])
    assert [(i.index, i.level) for i in issues] == [(1, "impossible"), (2, "uncomfortable")]
    assert issues[0].written == 92


def test_score_order():
    names = [p.name for p in BRASS_BAND.parts]
    assert names[0] == "Soprano Cornet" and names[-1] == "B♭ Bass"
    assert names.index("Flugelhorn") < names.index("Solo Horn") < names.index("1st Baritone") < names.index("1st Trombone")


def test_double_accidentals_are_simplified():
    from brasscribe_music.spelling import _simplify
    assert _simplify("E", -2, 4, 62) == ("D", 0, 4)
    assert _simplify("F", 2, 4, 67) == ("G", 0, 4)
    assert _simplify("G", 2, 4, 69) == ("A", 0, 4)
    assert _simplify("C", -2, 5, 70) == ("B", -1, 4)
