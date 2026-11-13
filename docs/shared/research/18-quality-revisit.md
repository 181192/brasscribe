# 18 — Quality revisit: where the errors are, and what moved them

Date: 2026-11-13. A second look at how accurately notes and tabs are recovered from recordings, six weeks after
the models were chosen ([00](00-summary.md), [10](10-benchmark-results.md)). Every number here was measured on
this date with `scribe bench` or with the script named beside it; the gated numbers live in
`eval/baselines.json`. Findings that did not help are kept, with their numbers, so they are not tried again
blind.

## Short answer

- **The notes are mostly there; the rhythm they are written in is the weaker half.** On every set where a score
  exists, pitch and onset errors are smaller than the errors of the beat grid and of the slot a note is written
  on.
- **Brass ensembles:** with the true beats, 94 to 98 % of the transcribed notes are written on the right
  position. With tracked beats it is 44 to 50 %. The loss is the beat grid: held chords (fermatas), and pieces
  tracked at half the notated level. No rule tried here fixes either without knowing the score.
- **Tabs:** one in twenty notes played on a 16th slot is written on another slot, and a triplet is never
  written. Choosing the grid for the distinct onsets of the instrument, not per note, takes the 16th-slot
  errors from 3.7–6.2 % to 1.2–2.7 % on GuitarSet, but regresses gated metrics on the chord-melody passages.
  The quantizer has the option and the bench has the metric; the tab profiles do not use it yet (§2).
- **6/8 counted in two** was lost to 10 ms of timing jitter. Landed ([#150](https://github.com/181192/brasscribe/issues/150)).
- **A newer beat tracker (md_beat_this) writes more notes on the right beat** on the brass ensembles (0.49 →
  0.53 and 0.45 → 0.57) but loses two pieces Beat This! had; five more models are worth a bench (§4).

## 1. Where the errors are

### Brass ensembles (ChoraleBricks brass quartets, URMP brass)

Each reference note is given one outcome (`hit` within 50 ms; else `early`/`late` within 150 ms; else an
estimate an octave or a semitone away; else `missed`). Extra notes are what is left of the estimate. Shares of
the reference notes.

| | hit | early | late | octave | semitone | missed | extra |
|---|---|---|---|---|---|---|---|
| Chorales, MuScriptor medium | 0.624 | 0.253 | 0.027 | 0.039 | 0.005 | 0.053 | 0.278 |
| Chorales, Basic Pitch | 0.634 | 0.015 | 0.235 | 0.024 | 0.013 | 0.078 | 0.815 |
| URMP, MuScriptor medium | 0.691 | 0.167 | 0.039 | 0.008 | 0.010 | 0.086 | 0.074 |
| URMP, Basic Pitch | 0.673 | 0.007 | 0.104 | 0.017 | 0.004 | 0.195 | 0.362 |

- **MuScriptor is early, Basic Pitch is late.** MuScriptor's onsets have a median of −27 ms on the chorales
  (10th percentile −91 ms); Basic Pitch's +9 ms (90th percentile +96 ms). That is the whole gap between its
  onset F1 at 50 ms (0.56) and at 100 ms (0.75).
- **It does not matter for the score.** With the true beats, MuScriptor's notes are written on the right
  position 97.9 % (chorales) and 93.8 % (URMP) of the time, against 98.7 % and 95.3 % for the reference notes
  themselves (`quant_bench --source muscriptor-medium.mid --beats reference`). Refining onsets (a constant shift,
  taking Basic Pitch's onset, a spectral-flux snap) could win at most that one point, and was not built.
- **MuScriptor's extra notes on the chorales are overtones.** Of its unmatched notes (at 100 ms), 385 sound an
  octave, a twelfth or two octaves over a note that is sounding (20 % of the reference count), 127 an octave
  under one. On URMP the same class is 3 %.
- **The beat grid is the large error.** Written position, exact, from `quant_bench`:

| Notes / beats | Chorales | URMP |
|---|---|---|
| reference notes, true beats | 0.987 | 0.953 |
| MuScriptor notes, true beats | 0.979 | 0.938 |
| reference notes, Beat This! | 0.490 | 0.445 |
| MuScriptor notes, Beat This! | 0.497 | 0.441 |

  Per piece (`barline_bench`): eight of the ten chorales drift at their fermatas, where the tracker goes on
  counting through a held chord (1.08 to 1.23 beats per notated quarter, 2 to 7 drift events a piece, 42 in
  all); one 6/4 chorale is tracked at a third of the level. On URMP four of eight pieces are tracked at half the
  notated level after `choose_level` (Fugue in 2/2, Chorale, Arioso, Entertainer before the clean-up), and those
  carry the drift.
- **Written durations** on URMP stay at 0.54 with everything else true: the score writes an 8th and a rest where
  the player holds a quarter ([10](10-benchmark-results.md), "Notation").

### Guitar (GuitarSet, the guitar alone)

Raw Basic Pitch, same outcome classes. Tune: players 00 to 02; report: 03 to 05.

| | hit | late/early | octave | missed | extra | of the extra: same pitch again / overtone / other |
|---|---|---|---|---|---|---|
| tune, single lines | 0.858 | 0.032 | 0.004 | 0.097 | 0.232 | 0.058 / 0.064 / 0.110 |
| report, single lines | 0.851 | 0.032 | 0.004 | 0.106 | 0.135 | 0.028 / 0.037 / 0.071 |
| tune, comping | 0.678 | 0.025 | 0.017 | 0.276 | 0.165 | 0.071 / 0.038 / 0.055 |
| report, comping | 0.716 | 0.024 | 0.016 | 0.237 | 0.248 | 0.109 / 0.065 / 0.074 |

- **Missed notes dominate in comping**: a quarter of the notes of a strummed chord are not heard at all.
- **Timing is not a problem**: onsets are within 20 ms.
- **The player's string** is the tab's weakest number: `string_agreement` 0.38 to 0.46 on single lines and 0.70
  on comping. The tab fingers a line where it is easiest to play; the players of GuitarSet improvise up the
  neck. Nothing in the audio is used to tell which string sounded.
- **The rhythm that is written** (new metric, below): 94 to 96 % of the notes played on a 16th slot of the click
  were written on it, and none of the notes played on a triplet slot.
- **Tempo and bar** on single lines: `tempo_ok` 0.61 to 0.72, `bar_ok` 0.59 to 0.70
  ([#245](https://github.com/181192/brasscribe/issues/245)).

## 2. What landed, and what is ready but not switched on

### Tab rhythm: a grid for the onsets, not for the notes (measured; not switched on)

The quantizer chooses a subdivision per beat by snap error plus a penalty per note. For one instrument that
plays chords this is fragile: a beat with an 8th and two 16ths costs 0.0925 on the grid of 8ths and 0.09 on the
grid of 16ths, so a few milliseconds decide, and on the 8ths the last strum lands on the one before it or on the
next beat. A dotted 8th and a 16th ties with a grid of quarters the same way. Exact triplets always lose to
8ths.

`quantize(dense=True)` without `monophonic` (Python reference and Rust core, with reference cases) now chooses
the grids for the instrument's distinct onsets (a strum counts once) and lets a beat whose grid would put two
onsets on one slot choose again, with the evidence rules the solo line already has (a tuplet needs a run of
beats that hold exactly three onsets and fit it four times better than 16ths).

`guitar-tab` has new gated metrics, `slot_*` (`guitar_tab_bench.written_slots`: the tab's reader on the click's
beats, the share of correctly heard notes written on the slot they were played on). With the tab reader
switched to the option (`dense=clean` in `tab.played_notes`):

| | 16th slots, today → with the option | all slots | notes compared |
|---|---|---|---|
| tune, single lines | 0.945 → 0.986 | 0.810 → 0.847 | 4 269 → 4 340 |
| tune, comping | 0.938 → 0.973 | 0.774 → 0.806 | 8 894 → 9 065 |
| report, single lines | 0.944 → 0.978 | 0.738 → 0.768 | 3 383 → 3 408 |
| report, comping | 0.963 → 0.988 | 0.829 → 0.864 | 8 625 → 8 798 |

No constant was chosen on GuitarSet. On synthetic strums (16 beats, 30 draws): an 8th and two 16ths 0.72–0.88 →
0.99–1.00 of the onsets on their slot; a dotted 8th and a 16th 0.72–0.92 → 0.91–0.99; triplets 0.33 → 1.00 up
to 10 ms of jitter at 120 BPM; straight 8ths, 16ths and swung 8ths unchanged.

**Why it is not switched on.** `scribe bench fretted` with the option: 46 gated metrics improve beyond
tolerance (onset recall +1 on GuitarSet, chord precision +1 to +3 on most sets, fewer notes left out as
unplayable) and 25 regress. The regressions:

- the chord-melody and strummed development passages (`ukulele_*_heldout_dev`, `guitar_*_heldout_dev`): onset
  precision −1.7 to −2.6, `out_of_range` +1 to +2.5 points, hand travel up to +0.24;
- GuitarSet single lines: `string_agreement` 0.378 → 0.366 and 0.457 → 0.432, `report.solo.chord_precision`
  0.746 → 0.671;
- `triplet_lengths` 0.000 → 0.010–0.016 on GuitarSet. That metric counts a triplet length on a note that starts
  on a 16th slot; it was written when a tab had no triplets and needs a new definition before it can judge.

Likely cause of the first group, not verified: the rules for a chord that rings on under a melody
(`rings_on`, `rung`) tell a re-heard note by its sharing a written onset with the melody note. On a finer grid
the two no longer share a slot. Counting a pitch heard again within 0.2 or 0.3 of a beat as the same onset did
not change any of the regressions.

**To switch it on:** make the ringing-chord rules compare onsets in seconds, redefine `triplet_lengths`, then
set `dense=clean` in `tab.played_notes` and rerun `scribe bench fretted`.

**Still open in [#159](https://github.com/181192/brasscribe/issues/159) either way:** swing. A swung 8th is
played on a triplet slot and written as a straight 8th (`slot_triplet` 0.00 → 0.02–0.12 with the option). Two
onsets to the beat are not evidence of a triplet, and a tab has no "swing" marking yet to make the straight 8ths
true.

### 6/8 counted in two (landed)

`bass_tab.compound()` counted an onset for every subdivision within reach, and the windows of a third and of a
quarter overlap. Each onset now counts for the subdivision it is nearest to, and the share that says "in three"
is 0.92. Straight 6/8 at 100 BPM with 10 ms of jitter: called compound in 0.19 → 1.00 of 200 draws; 15 ms: 0.04
→ 0.92. With the share left at 0.8, three GuitarSet takes in 4/4 and one triplet bass line became bars of two.

What it does not reach: `COMPOUND_NEAR` is a fixed fraction of the beat, so the gain fades as the tempo rises
(10 ms of jitter: 140 BPM 0.28 → 0.94, 180 BPM 0.12 → 0.28) and with a beat grid that is itself off (grid 20 ms
late and 10 ms of jitter at 100 BPM: 0.00 → 0.04). `meter-tab` cannot see the change: only its 6/8 arpeggio
reaches the rule, and it has no long-short (trochaic) 6/8 passage.

## 3. Tried and not kept

| Idea | Measured | Verdict |
|---|---|---|
| Lower the quantizer's penalty for 16ths (0.03 → 0.02, 0.015, 0.01), so dotted rhythms win | Position with true beats, reference notes: chorales 0.987 → 0.979 / 0.972 / 0.950; URMP 0.953 → 0.949 / 0.941 / 0.921. Higher (0.04, 0.05): chorales 0.988 / 0.992, URMP 0.951 / 0.952 | The penalties sit on a plateau and hold on busier material; left alone. This is the revalidation [10](10-benchmark-results.md) asked for |
| The chord-aware grid choice for brass ensembles too | Reference notes, true beats: chorales 0.987 → 0.892, URMP 0.953 → 0.905. Four players' "same" onset is spread wider than a strum, and reads as two onsets | Kept to one instrument (the tab profiles) |
| Drop an unconfirmed MuScriptor note below middle C that is an overtone of a sounding note | Consensus onset F1 (100 ms): chorales 0.759 → 0.795 (P 0.69 → 0.78, R 0.84 → 0.81), URMP 0.884 → 0.885. A seat's voice picked by range (`seat-voices`): tenor F1 0.305 → 0.495, alto 0.829 → 0.811. But the quartet from recordings (`quartet-audio`), fed the filtered notes: alto recall 0.537 → 0.523, tenor 0.439 → 0.398 | Not landed: the arrangement reads pitch classes per beat and wants recall. Worth taking up when a seat's own voice is shown ("follow my line"): it is the largest single step measured for the tenor |
| MuScriptor-only harmony (no Basic Pitch notes) for the quartet | alto 0.537 → 0.520, tenor 0.439 → 0.417, parallels 5.1 → 6.5 per 100 | The union stays |
| Onset refinement for MuScriptor | See §1: at most one point of written position | Not built |
| A fermata rule (take the tracker's extra beats out of a held chord) | Looked at beat by beat on the ten chorales: the hold is 1 to 3 beats longer than written, and what was written is only decidable from the bar it must complete; the tracker's downbeats on chorales are too irregular to say (bars of 1 to 5 beats) | Not built. It needs the player to mark the hold, or a meter that is known |
| Nearest-subdivision count for 6/8 with the share kept at 0.8, 0.85 or 0.9 | `guitar-tab` `tune.solo.meter_ok` 0.967 → 0.956, `report.comp.meter_ok` 1.0 → 0.978 (0.8); `bass-tab` `instrument.meter_ok` 0.923 → 0.846 (all three) | 0.92 |
| Basic Pitch writing notes down to 58 ms (its default drops everything under 128 ms), for tabs | Raw onset F1 on GuitarSet: recall +4 to +7 points, precision −7; with notes under 128 ms kept only when heard at 0.5 or more, through the tab profile: GuitarSet `onset_f1` tune 0.825 → 0.828 (single lines), 0.722 → 0.739 (comping), report 0.853 → 0.870, 0.721 → 0.735; IDMT-SMT-Guitar 0.699 → 0.712 and 0.719 → 0.741; rendered guitar, ukulele and mandolin within ±0.006; bass lines 0.83 → 0.79 mean (no amplitude rule there) | A real gain of 1.3 to 2.2 points on recorded guitars, not landed: it needs every cached Basic Pitch output of the tab sets made again under new names (about 850 files) and the bass kept on the default. The adapter change is one option (`--minimum-note-length`); the rule is two constants in `tab.played_notes` |

### The "?" marks on a solo line: what they miss

`solo-instruments` reports that a "?" sits on 17 to 33 % of the wrong notes of a seat's take (`q_hit`). The 93
ChoraleBricks parts it is scored on are in the set the confidence model was fitted on, so that number is not
held out. Two measurements:

- **What the wrong notes are** (all 93 parts, 4 176 written notes, 105 wrong at 100 ms):

| Wrong note | Count | Marked |
|---|---|---|
| right pitch, onset 100 to 250 ms off | 34 | 0 |
| one or two semitones off (30 of them the tuba) | 48 | 13 |
| a held note heard as two | 14 | 1 |
| an octave off | 2 | 0 |
| no note there at all | 7 | 7 |

  The marks find the notes that are not there. They do not find a wrong semitone that both transcribers agree on
  (confidence 0.94 at the median), and a late onset is not something the model was asked about.
- **Held out for real.** Fitted on the URMP parts and the separated stems only and scored on the ChoraleBricks
  parts (1 346 candidate notes, 60 wrong): marking 8 % of the notes catches 0.32 of the wrong ones at a
  precision of 0.18. On the bench's own split (odd recordings of the same sets) the same model catches 0.65 at
  0.60. The model does not carry from one set of recordings to another.
- **Tried:** how far the SwiftF0 contour sits from the written semitone over the note (median distance after
  taking out the recording's own tuning, and the share of frames nearer another semitone), as one and two more
  inputs. Held out, recall at 8 % marked fell from 0.32 to 0.28, 0.23 and 0.25; on the fitting data nothing
  moved. Not kept. Sixty wrong notes are too few to choose features on.

What this needs is more wrong notes with a reference from recordings the model has not seen (the tuba's
semitone errors above all), and a decision on whether a late onset should carry a mark at all. Refitting the
shipped model without the ChoraleBricks parts would make `q_hit` honest, and changes every solo note's
confidence, so it comes with new reference outputs.

## 4. Not run: models worth a bench

Only the first was run, and only on the 18 brass ensemble recordings; the others are listed in the order they
should be tried. Licences and training data are as their pages state them on 2026-11-13; "unverified" means the
page could not be opened or does not say. Models trained on one of our eval sets must be scored on the others.

**md_beat_this on the brass ensembles** (model `run1`, its beats beside Beat This!'s; `quant_bench --beats`,
reference notes):

| | Chorales: position / subdivision | URMP: position / subdivision |
|---|---|---|
| Beat This! | 0.490 / 0.930 | 0.445 / 0.830 |
| md_beat_this | 0.526 / 0.940 | 0.574 / 0.797 |

Per piece it is a different set of failures, not fewer of the same. It finds the notated level where Beat This!
tracked half of it or a third (Entertainer 0.48 → 0.95, Arioso 0.23 → 0.94, the 6/4 chorale 0.09 → 0.85, Drese
0.72 → 1.00, Fugue 0.26 → 0.52 after the bar-line clean-up), and it tracks two pieces one beat to the bar that
Beat This! had right or nearly (Slavonic Dance in a fast 3/4: 0.52 → 0.01; Gesius *Du Friedensfürst*: 0.46 →
0.05). The fermata chorales are unchanged. Not adopted on 18 pieces: next is the same comparison on the single
parts, GuitarSet and the meter passages, and a level rule that can split a beat in three, which the one-beat-bar
pieces need.

| Candidate | What it could fix | Weights and licence | Training data that overlaps ours | Reported |
|---|---|---|---|---|
| md_beat_this ([arXiv 2608.04624](https://arxiv.org/abs/2608.04624), github.com/fosfrancesco/md_beat_this) | The beat grid, §5: downbeats most of all | Released; CC BY-NC 4.0 | Unverified | GTZAN against Beat This!: beat F1 89.7 / 89.1, downbeat CMLt 76.4 / 67.3, AMLt 88.5 / 79.1 |
| Guitar model of the GAPS paper ([arXiv 2408.08653](https://arxiv.org/abs/2408.08653), `hf-midi-transcription`, hf.co/xavriley/midi-transcription-models) | The quarter of comping's notes Basic Pitch misses; notes only, our rules still choose the string | Released; MIT (unverified on the checkpoints) | A GAPS-only and a GAPS + GuitarSet checkpoint exist; which file is which is unverified | Onset F1 88.1 on GuitarSet without training on it; 84.8 against Basic Pitch's 66.1 on another set |
| Saxophone model in the same repository (`filosax_25k.pth`) | Re-tongued notes on one pitch in a solo line: it regresses onsets, where SwiftF0 sees only pitch | Released; MIT | Unverified | None for brass |
| guitab (hf.co/danmor/guitab) | The player's string, from the sound | Released; code MIT, weights CC BY-NC-SA | **GuitarSet**, GAPS, SynthTab: score on IDMT-SMT-Guitar only | String and fret F1 0.838 on GuitarSet, 0.721 on EGDB (its authors') |
| timbreAMT (github.com/madderscientist/timbreAMT) | Basic Pitch's role on brass ensembles | ONNX files said to be released (unverified); Apache-2.0 | None stated (URMP is its test set) | URMP note F1 71.4 against 60.4 for its re-implementation of Basic Pitch |
| Noise2Fret ([arXiv 2608.30854](https://arxiv.org/abs/2608.30854)) | String and fret | Checkpoints unverified; MIT | **GuitarSet** | Tab F1 0.845 on GuitarSet |

Found with no weights to download: TART, Harmonica, Fretting-Transformer, FretNet. Found nothing at all for: a
model that outputs the time signature, tabs for bass, ukulele or mandolin, a pitch tracker that beats SwiftF0, a
detector for soft wind onsets, published numbers for test-time augmentation or voting, and a quantizer that is
not piano-only or that is evaluated on triplets. Fine-tuning on brass was not reached.

## 5. The top weakness that remains

The beat grid under free or slow playing. Half the notes of a brass ensemble are written on the wrong beat
because of a handful of events a piece, while the notes themselves and the slots within the beat are right 83 to
93 % of the time.

What a correction by the player would recover, measured with the answer known (written position, reference
notes, Beat This!'s beats as the start; "holds" takes the tracker's surplus beats out of every gap of two
notated beats or more in which no part starts a note):

| | as tracked | best level (×2, ×3, ÷2, ÷3) | holds marked | level and holds | the better of two trackers, per piece |
|---|---|---|---|---|---|
| Chorales | 0.490 | 0.563 (1 piece of 10 changes) | 0.591 (20 holds) | 0.658 | 0.599 |
| URMP | 0.445 | 0.471 (2 of 8) | 0.432 (3 holds) | 0.457 | 0.641 |

- Marking the holds is worth the most on hymn tunes and nothing elsewhere; one piece gets worse when a long note
  that is no fermata is treated as one, so a hold must be the player's mark, not a rule.
- The level is wrong less often than it looks: `choose_level` and the bar-line clean-up already take most of
  it.
- On URMP what is left is beats put in or left out along the way (Fugue, Arioso, Chorale, Air). Neither
  correction reaches that. A second tracker does, on some pieces: offering the player "the other beat" is worth
  more there than any single correction, and the notes cannot choose between the two grids by themselves (the
  grid the onsets fit best, the more regular one and the one with more onsets on 8ths were each tried: 0.43 to
  0.51 on the chorales and 0.47 to 0.48 on URMP, under md_beat_this alone).

So the order for the engine is: a second set of beats to choose from, then the player's marks (hold, level,
first downbeat, beats in a bar), each applied to the cached transcription without running a model again. None
of that is built.
