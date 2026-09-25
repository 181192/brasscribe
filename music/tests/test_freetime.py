import numpy as np

from brasscribe_music.freetime import local_tempo, mark_fermatas, plan_free_time, unstable_runs
from brasscribe_music.quantize import TICKS_PER_BEAT, choose_grids
from brasscribe_music.score_model import Articulation, Note

# Mikkel's detected beats: a free-time intro (1-6 s apart), then a steady ~136 BPM.
MIKKEL = np.array([2.94, 8.92, 10.3, 12.82, 14.9, 15.94, 17.22, 18.28, 21.8, 23.5, 29.76, 30.62, 31.52, 32.38, 32.82,
                   33.26, 34.1, 34.54, 34.98, 35.84, 36.3, 36.74, 37.16, 37.6, 38.04] + list(38.46 + 0.44 * np.arange(60)))


def steady(n=80, ibi=0.5):
    return np.arange(n) * ibi


def test_detects_mikkel_intro_only():
    assert unstable_runs(MIKKEL) == [(0, 10)]


def test_steady_level_switches_splits_and_single_fermata_are_not_free_time():
    t = list(steady())
    t = t[:20] + [t[20] + 1.6] + [x + 1.6 for x in t[21:]]  # one held chord (fermata): a single long interval
    t = t[:40] + [t[40] + 0.1] + t[40:]  # a beat split in two
    t = np.array(t)
    t = np.concatenate([t[:60], t[60::2]])  # tracker switches to half notes
    assert unstable_runs(np.sort(t)) == []


def test_ritardando_run_is_detected_mid_piece():
    t = list(steady(40))
    x = t[-1]
    for ibi in (0.8, 1.3, 2.1, 0.9, 3.4, 1.5):
        x += ibi
        t.append(x)
    t += list(x + 0.5 * np.arange(1, 30))
    runs = unstable_runs(np.array(t))
    assert len(runs) == 1 and runs[0][0] == 40  # 0.8 s fits the double beat; 1.3 s does not


def test_plan_replaces_intro_with_whole_bars_and_resumes_on_the_downbeat():
    pos = np.array([1, 2, 1, 1, 1, 2, 1, 1, 1, 1, 1] + [2, 3, 4, 1] * 30)[:len(MIKKEL)]
    melody = np.array([0.03, 2.77, 6.7, 11.01, 14.37, 16.74, 18.26, 20.64, 24.16, 26.3, 29.3])
    plan = plan_free_time(MIKKEL, melody, 4, 0, downbeats=pos == 1, tempo_onsets=melody)
    (a, b, s0, s1, bpm), = plan.spans
    assert a == 0 and b % 4 == 0 and s0 == 0.03 and s1 == 29.76
    assert 40 <= bpm <= 100
    synth = plan.beat_times[a:b]
    assert np.allclose(np.diff(synth), (s1 - s0) / b)
    assert plan.beat_times[b] == 29.76 and np.allclose(plan.beat_times[b:], MIKKEL[10:])
    r, = plan.regions()
    assert r.start == 0 and r.end == b * TICKS_PER_BEAT and r.label == "ad lib."


def test_user_tempo_and_no_runs():
    plan = plan_free_time(MIKKEL, np.array([0.5]), 4, 0, tempo=60)
    assert plan.regions()[0].notation.value == "tempo"
    assert plan_free_time(steady(), np.array([0.1]), 4, 0).spans == []


def test_local_tempo_from_melody_gaps():
    assert abs(local_tempo(np.array([0, 2, 4, 6, 8.0]), 0, 10) - 60) < 1e-6
    assert local_tempo(np.array([0, 10, 20.0]), 0, 30) == 40  # clamped


def test_coarse_ranges_use_quarters_and_eighths_only():
    onsets = np.array([0.0, 0.25, 0.5, 0.75, 5.0, 5.25, 5.5, 5.75])  # 16ths
    free = choose_grids(onsets, coarse=[(0, 4)])
    assert free[0] in (1, 2) and free[5] == 4


def test_fermata_on_last_note_of_region():
    notes = [Note(60, 0, 24), Note(62, 48, 24), Note(64, 120, 24)]
    from brasscribe_music.score_model import FreeRegion
    mark_fermatas(notes, [FreeRegion(0, 96, 0.0, 4.0, 60.0)])
    assert notes[1].articulations == [Articulation.FERMATA] and not notes[0].articulations and not notes[2].articulations


def test_mid_piece_region_keeps_bars_before_and_resumes_on_a_bar_line():
    t = list(steady(41))  # beats 0..40 at 0.5 s; bars of 4 from beat 0
    x = t[-1]
    for ibi in (0.8, 1.3, 2.1, 0.9, 3.4, 1.5):
        x += ibi
        t.append(x)
    t += list(x + 0.5 * np.arange(1, 30))
    t = np.array(t)
    plan = plan_free_time(t, t[:60], 4, 0)
    (a, b, s0, s1, bpm), = plan.spans
    assert plan.first_downbeat == 0
    assert a % 4 == 0 and (b - a) % 4 == 0 and a <= 40
    assert np.allclose(plan.beat_times[:a], t[:a])
    resume = int(np.searchsorted(t, s1))
    assert s1 == t[resume] and (resume % 4) == 0  # labelled by the old bar numbering
    assert np.allclose(plan.beat_times[b:], t[resume:])
    r, = plan.regions()
    assert r.start == a * TICKS_PER_BEAT and r.end == b * TICKS_PER_BEAT


def test_clip_to_regions_ends_notes_at_the_region_end():
    from brasscribe_music.freetime import clip_to_regions
    from brasscribe_music.score_model import FreeRegion
    notes = [Note(60, 0, 6), Note(62, 60, 40), Note(64, 88, 20), Note(65, 96, 24)]
    region = FreeRegion(0, 96, 0.0, 4.0, 60.0)
    clip_to_regions(notes, [region])
    mark_fermatas(notes, [region])
    assert notes[0].dur == 12  # at least an 8th in free time
    assert notes[2].end == 96 and notes[3].dur == 24
    # The fermata goes on the last note of a beat or longer, not on the short one before a tempo.
    assert notes[1].articulations == [Articulation.FERMATA] and not notes[2].articulations
