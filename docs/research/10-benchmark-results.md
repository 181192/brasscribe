# 10 — Benchmark results

**Status (2026-09-29):** a living record; `eval/baselines.json` is the source of truth for the gated numbers. "Difficulty modes and lineups", "Readability" and "Rust core conformance" were rerun on the fast-notes golden (2026-09-29). At faithful the Solo Cornet is 63.6 % 16ths (gate 65 %; `docs/plan/fast-notes.md` §7).

## Reproducing these numbers

**Regression suites.** `pixi run brasscribe bench <suite>` (or `all`, or `ci` for the subset that gates in CI) runs every benchmark below from cached model outputs and gates against `eval/baselines.json` (±0.01 F1 unless a metric says otherwise). `eval/README.md` lists which suites gate in CI and which need local data.

Individual benchmarks run from `eval/` with `uv run python -W ignore -m <module> ...`. Eval sets live in `data/eval/`; they are built by `brasscribe_eval.choralebricks`, `.urmp` and `.slakh` from the downloaded datasets.

**From committed commands:**

| Result | Command |
|---|---|
| Transcription per model (chorales, URMP, Slakh) | `brasscribe_eval.bench <eval_dir> <adapter run.sh> --name <label>` |
| Pipeline B (separate → transcribe) | `bench ... ../ml/pipelines/separate_transcribe.sh` |
| Consensus sweeps | `brasscribe_eval.consensus_bench <eval_dir> label=file.mid[:split] ...` |
| Rhythm / quantization | `brasscribe_eval.quant_bench <eval_dir> [--beats reference] [--source file.mid]` |
| Melody line | `brasscribe_eval.melody_bench` |
| Solo three-way vote | `brasscribe_eval.solo_vote_bench` (needs `data/mega53-out-bench`, made with `ml/adapters/mega53/run.sh` on each mix) |
| Arrangement on ground truth | `brasscribe_eval.arrange_bench <eval_dir>` |
| MuseScore round trip | `brasscribe_eval.musescore_roundtrip <musicxml> <composition.json>` |
| Mikkel end to end | `brasscribe_eval.song_pipeline data/mikkel/mikkel.wav --out <dir>`. The golden output is in `data/golden/mikkel-arranged-band/`. A fresh run reproduced all 18 parts note for note. Upstream orchestra-hit detection varied slightly between runs (2 184 vs 2 212 notes), and the harmony reduction absorbed it |

**One-off measurements.** These were made with inline scripts during research and not committed. Treat them as findings to re-derive, not as regression baselines:
- pitch-spelling accuracy (ps13 99.9%)
- gap-fill duration variants
- harmony-reduction fidelity (0.98 / 0.96)
- float16 vs float32
- ChoraleBricks tuba intonation statistics
- Slakh bass octave check (pYIN)
- onset-offset analysis (trumpet +55 ms)
- Mega-53 melody-extraction table
- Viterbi melody sweep
- Mikkel stem energy tables

## Setup

- **Eval set: `choralebricks-brass4`.** Built by `eval/brasscribe_eval/choralebricks.py`.
  - 10 ChoraleBricks v1.1.0 chorales, each a mono mix of four isolated real recordings.
  - Parts: S = trumpet (cornet proxy), A = flugelhorn, T = baritone, B = tuba.
  - Ground truth: per-part note CSVs with audio-aligned onset/offset and sounding pitch; 1 887 notes total.
- **Metrics:** `eval/brasscribe_eval/score.py`, mir_eval, 50 ms onset tolerance.
  - Instrument-agnostic onset F1 and onset+offset F1.
  - Octave-error rate: an unmatched reference note with an estimate ±12/24 semitones away at the same onset.
  - Per-part recall.
- **Runner:** `eval/brasscribe_eval/bench.py <eval_dir> <adapter run.sh> --name <label>`.
- **Machine:** M5 Pro, 48 GB. Runtime is wall-clock per song, including model load (songs are 15–60 s).

## Results (mean over 10 chorales)

| Model | onset F1 | on+off F1 | P | R | octave err | recall S / A / T / B | s/song |
|---|---|---|---|---|---|---|---|
| Basic Pitch (CoreML) | 0.468 | 0.281 | 0.37 | 0.64 | 10.8% | .74 / .66 / .71 / .46 | 1.9 |
| **MuScriptor medium** | **0.562** | **0.477** | 0.51 | 0.63 | 2.7% | .84 / .77 / .48 / .45 | 5.7 |
| MuScriptor large | 0.441 | 0.390 | 0.41 | 0.48 | 6.2% | .73 / .60 / .35 / .24 | 31.3 |
| MuScriptor medium, `--instruments` brass | 0.333 | 0.296 | 0.30 | 0.38 | 0.4% | .60 / .46 / .22 / .23 | 7.0 |
| MuScriptor large, `--instruments` brass | 0.275 | 0.251 | — | — | 0.4% | .57 / .38 / .19 / .21 | 25.3 |

## Findings

1. **MuScriptor medium is the best single model** on real brass-quartet audio, by +9 onset F1 and +20 on+off F1 over Basic Pitch. It also has far fewer octave errors.
2. **Large is not better than medium; it is erratic.**
   - It matches or beats medium on some songs (Bach 0.617 vs 0.604).
   - It collapses on others (Jan 0.388 vs 0.532).
   - float32 vs float16 (the MPS default) changes nothing (checked on 3 songs), so precision is not the cause.
   - Use medium.
3. **Conditioning MuScriptor on brass instruments hurts badly** (−23 onset F1). Don't pass `--instruments` for brass; treat its labels as hints only.
4. **The models are complementary.**
   - MuScriptor gets the outer and upper voices (S .84) but loses the inner and lower ones (T .48, B .45).
   - Basic Pitch catches the tenor (.71) at low precision.
   - This is direct evidence for consensus (pipeline C). Voice-aware fusion could lift T/B recall without Basic Pitch's false positives.
5. **The bass voice is weakest everywhere** (≤ .46).
   - Partly real difficulty: tuba around G1 in a 4-part mix.
   - Partly data: the ChoraleBricks tuba is often out of tune. Mean deviation is +22 cents and 16% of its notes are more than 40 cents off, against 0–1% for the other instruments.
   - A dedicated low-register f0 tracker on a separated bass stem is worth testing.
6. **Labels on real recordings are unreliable.**
   - On "Mikkel" (Antonsen, *Landscapes*, 2007) MuScriptor labelled the lead trumpet "distorted electric guitar".
   - BS-RoFormer SW put 0% of the energy in the guitar stem, and PANNs tags trumpet at 0.6–0.7 in most 15 s windows.

## Song benchmark: Slakh trumpet-lead tracks

Mikkel has no ground truth, so it is the end-to-end test only. The song-level benchmark is `slakh-trumpet`, built by `eval/brasscribe_eval/slakh.py`:
- **BabySlakh Track00006** (241 s): trumpet melody, 2× string ensemble, French horn, trombone, fretless bass, drums, EP, guitars. The closest Mikkel-like texture available with exact notes.
- **Track00014** (269 s): trumpet lead with band.
- Each has `mix.wav` (16 kHz), per-stem MIDI ground truth, and `score.musicxml` (MuseScore conversion of the MIDI).
- **Caveat:** the audio is synthetic (sample-library render).

### Onset timing

Separated-stem transcription found almost every Track00006 trumpet note at the right pitch but 50–150 ms late. The median offset is about +55 ms (IQR 34–79 ms), against about 0 ms for bass and piano. That is the soft brass attack: the note speaks after its MIDI note-on.

Strict 50 ms matching therefore undercounts melody recovery. For notation, anything under a 16th note (about 125 ms here) is absorbed by quantization, so `score.py` now also reports a 100 ms tolerance ("100" columns).

### Results (100 ms tolerance; strict 50 ms in brackets)

| Pipeline | slakh onset F1 | Track00006 trumpet melody recall | fretless bass recall | Track00014 trumpet recall |
|---|---|---|---|---|
| A: Basic Pitch on mix | 0.43 (0.36) | 0.79 (0.42) | 0.54 | 0.57 |
| A: MuScriptor medium on mix | 0.48 (0.43) | 0.62 (0.49) | 0.26 | 0.65 |
| B: SW separation → MuScriptor per stem | **0.60** (0.52) | 0.79 (0.41) | 0.27 | **0.69** |
| B: SW separation → Basic Pitch per stem | 0.52 (0.46) | **0.87** (0.49) | **0.68** | 0.68 |

Chorales re-scored at 100 ms:
- MuScriptor medium: onset F1 0.75; recall S .97 / A .92 / T .76 / B .72.
- Basic Pitch: onset F1 0.60; recall S .90 / A .89 / T .82 / B .66.

Per-part recall is measured against *all* estimated notes, so a note can be credited to the melody when another stem produced the same pitch. Treat it as an upper bound.

### What this says

1. **Separation helps on full-band songs** (pipeline B beats A by +8 to +12 F1). It is unnecessary for brass-only chorales.
2. **The best source differs per role.**
   - MuScriptor is strongest for upper and melodic voices.
   - Basic Pitch on a separated stem is far better for bass (0.68 vs 0.27) and at least as good for the trumpet line.
   - The consensus design should route by role: melody from agreement of both, bass from Basic Pitch on the bass stem, inner voices from union with voting.
3. **Melody recovery at notation tolerance is roughly 80–90%** on synthetic trumpet-lead songs and above 95% on real brass chorales.

### Ground-truth fix: Slakh bass octave

- Both models consistently put the Slakh bass notes 12 semitones below the MIDI.
- pYIN on the rendered bass stems confirms it: Track00014 audio median MIDI 39 against 51 in the MIDI file.
- Slakh renders bass patches an octave below the written MIDI. `slakh.py` now shifts Bass-class stems −12 to sounding pitch.
- Every other part lines up at 0 semitones except Track00014's Rock Organ (−24, a minor part; not corrected).
- The table above predates this fix.

Corrected results (100 ms):

| Pipeline | onset F1 | trumpet recall (T06 / T14) | bass recall (T06 / T14) |
|---|---|---|---|
| A: Basic Pitch on mix | 0.47 | .79 / .57 | .77 / .75 |
| A: MuScriptor on mix | 0.56 | .62 / .65 | .86 / .78 |
| **B: SW → MuScriptor per stem** | **0.70** | .79 / .69 | .96 / .93 |
| B: SW → Basic Pitch per stem | 0.56 | .87 / .68 | .91 / .84 |

### Consensus (`eval/brasscribe_eval/consensus.py`, `consensus_bench.py`)

**Method:**
- Notes from all sources are clustered on equal pitch with onsets within 100 ms.
- Confidence = 1 − Π(1 − precision) over supporting *models*.
- A model's stems vote once, using the stem's precision. Stems are not independent because separation bleed duplicates notes.
- Precision is estimated leave-one-song-out.
- Rejected candidates are kept as `alternatives`.

**Chorales (MuScriptor + Basic Pitch on mix):**
- Weighted vote: F1 0.76 against 0.75 for MuScriptor alone.
- **Agreement-only notes are 92% precise.**
- The union recalls 94% (tuba 87%, baritone 95%).

**Slakh (4 sources: both models × mix and SW stems):**
- The best F1 is 0.63 at threshold 0.8, *below* pipeline B with MuScriptor alone (0.70). The mix-level sources add accompaniment false positives.
- At threshold 0.7, trumpet recall reaches .95 and bass .995, against .79 / .96 for B alone. Precision drops to 0.60.

**Verdict:**
- Consensus does not yet beat the best single pipeline on overall F1.
- It does deliver what the spec needs for the arranger: near-complete melody and bass recall, plus a usable confidence signal (agreement ⇒ high precision).
- Two songs are too few to fit per-stem precision. Revisit with URMP and more Slakh tracks, and add a role-aware metric (melody/bass precision, not only recall).

## Rhythm: beat tracking and quantization

**Ground truth.**
- Slakh MIDI is largely *unquantized*. It is live-played Lakh MIDI: only 12–25% of Track00014's trumpet onsets sit on any 1/4–1/12 grid. So it cannot serve as notation ground truth.
- The ChoraleBricks alignments pair every performed note with its notated position (`start_quarter`, `dur_quarter`, time signature). `choralebricks.py` stores these in `reference.json`.

**Method.** `music/src/brasscribe_music/quantize.py`:
- Warp times onto the beat grid, piecewise linear.
- Per beat, pick the subdivision in {1, 2, 4, 3, 6} that minimizes squared snap error plus a complexity penalty.
- 24 ticks per beat.

`eval/brasscribe_eval/quant_bench.py` scores:
- position (exact notated position, after an integer beat-offset alignment)
- subdivision (position within the beat)
- duration.

**Results (10 chorales, reference notes):**

| Beats | position | subdivision | duration |
|---|---|---|---|
| Reference beats (from alignments), original penalties | 0.89 | 0.89 | 0.76 |
| Reference beats, penalties ×20 (adopted) | **0.99** | 0.99 | 0.88 |
| Beat This!, penalties ×20 (9 chorales, without Drese) | 0.46 | **0.92** | 0.76 |
| Beat This!, penalties ×20 (all 10; current baseline) | 0.49 | 0.93 | 0.77 |

**Findings:**
- With the adopted penalties, remaining quantizer errors are mostly note lengths. Offsets depend on legato vs detached playing; per-voice "hold until next onset" belongs in the voice-separation stage.
- **The weak link is the beat grid, not the snapping.**
  - Chorales have fermatas; Beat This! inserts extra beats during held chords (1.1–1.2 detected beats per notated quarter). Bar positions therefore drift, even though positions within the beat stay 92% right.
  - One 6/4 chorale was tracked at half the metrical level (0.35 beats per quarter).
  - Fixes: meter- and downbeat-constrained beat selection; fermata detection (long simultaneous holds); a user correction pass in the UI.
- Mikkel has a steady ~138 BPM after its intro, so it should be less affected.
- The penalty scale is tuned on rhythmically simple chorales. Revalidate on URMP and faster material.

## Melody extraction (Slakh, trumpet line vs reference trumpet part, 100 ms)

"Line" means the top note per onset within E3–D6 (`lead_sheet.line`).

| Melody source | T06 P / R / F | T14 P / R / F |
|---|---|---|
| MuScriptor on the SW "other" stem | .63 / .77 / .69 | .62 / .51 / .56 |
| **Agreement of MuScriptor ∧ Basic Pitch on "other"** | .73 / .80 / **.76** | .69 / .50 / **.58** |
| Mega-53 trumpet stem → Basic Pitch | .65 / .72 / .68 | .73 / .47 / .57 |
| Mega-53 trumpet stem → MuScriptor | .03 / .06 / .04 | .19 / .17 / .18 |

- **MuScriptor hallucinates on second-stage separated stems.** On the Mega-53 trumpet stem it produced 2 672 "piano" notes. Timing is intact, since Basic Pitch on the same file is fine.
- After a second separation stage, use Basic Pitch.
- Mega-53's trumpet stem does not beat simple two-model agreement on synthetic Slakh brass. Its SDR on Slakh trumpet is likely poor because Slakh's trumpet patch reads to it as sax or harmonica. On Mikkel's real trumpet it holds 24% of the "other" energy, so judge it by ear there.
- "Top line" fails when the melody is not the highest voice (T14 recall ≈ .5). The next step is melody-vs-accompaniment selection by continuity and salience, not pitch height.

## URMP brass (real recordings)

**Set.** `urmp-brass`, built by `eval/brasscribe_eval/urmp.py`: 8 brass-only URMP pieces, 5 129 notes.
- Pieces: Entertainer, Air on the G String, Surprise, Slavonic Dance, Für Elise, Art of the Fugue, Arioso, Chorale (quintet).
- Meters: 4/4, 2/4, 3/4, 6/8, 2/2.
- Performed notes come from the per-track annotations.
- Notated positions come from pitch-DTW alignment to the score MIDI: 94–99% of notes aligned.
- File instrument tags in URMP are sometimes wrong (Surprise track 3 is filed as `tpt` but is the trombone), so tracks are matched by number.

**Transcription (mix, 100 ms):**

| Model | onset F1 (100 ms) | strict onset F1 | octave err | s/piece |
|---|---|---|---|---|
| Basic Pitch | 0.73 | 0.66 | 4.1% | 3 |
| **MuScriptor medium** | **0.88** | 0.69 | 1.2% | 34 |
| Consensus, agreement threshold 0.8 | 0.88 (P 0.89) | — | — | — |

- MuScriptor fails on Air on the G String (0.32 strict), a slow legato piece. It is the only outlier.
- Consensus at 0.8 ties MuScriptor on F1 with higher precision, so agreement works as a confidence flag.

**Rhythm (reference notes):**

| Beats | position | subdivision | duration |
|---|---|---|---|
| Reference beats | **0.95** | 0.96 | 0.54 |
| Beat This! (raw) | 0.33 | 0.69 | 0.37 |
| Beat This! + metrical-level selection | 0.45 | **0.83** | 0.45 |

- **The quantizer generalizes.** 95% exact positions with true beats on busier real material validates the penalty tuning.
- **Performed durations ≠ notated durations** (0.54). Players shorten notes, so notated length must be inferred per voice ("until next onset" with articulation), not measured.
- **Beat This! picked the half-note level on 5 of 8 pieces.**
  - `choose_level()` in `quantize.py` doubles the grid when tempo is under 90 BPM and the median IOI is ≤ 0.3 beats.
  - It fixes 4 of 6 half-level tracks across URMP and chorales with no false doubles.
  - Air on the G String and the Chorale stay ambiguous; their notated beat is a convention the audio cannot fully determine.
- **Remaining position errors** are beat insertions/deletions (drift in bar count). The next steps are downbeat-constrained beat cleanup and a UI step to confirm meter and pickup.

## Basic Pitch on the recording retuned to A = 440

The brass-band profile retunes the recording to A = 440 before Basic Pitch when it sits more than 5 cents off
(`engine/src/brasscribe_engine/tuning.py`). `basic-pitch-retuned.mid` is that output for the 10 chorales, which sit
−1 to +17 cents from A = 440 (9 of the 10 are retuned). `brasscribe bench chorales-transcription --mode live`
writes a missing one the same way.

| Chorales (mean over 10) | Basic Pitch | Basic Pitch, retuned |
|---|---|---|
| onset F1, 50 ms | 0.468 | 0.483 |
| onset + offset F1 | 0.281 | 0.334 |
| octave error rate | 0.108 | 0.102 |
| onset F1, 100 ms | 0.595 | 0.618 |
| consensus with MuScriptor, best F1 over thresholds (100 ms) | 0.76 | 0.756 |

Quartet from recordings (MuScriptor with Basic Pitch support, `mus` against `mus-retuned`): melody kept 0.848 → 0.841,
alto pitch-class recall 0.534 → 0.537, tenor 0.426 → 0.439, bass kept 0.922 → 0.922, parallels per 100 5.5 → 5.1.

## Notation: spelling, durations, melody line

**Pitch spelling (`music/src/brasscribe_music/spelling.py`).**
- partitura's ps13s1 runs on the whole ensemble at concert pitch.
- Ground truth is `pitch_written_name` in the ChoraleBricks alignments. `pitch_name` there is naive MIDI naming, not the score's spelling.
- Accuracy: **99.9%** (2 errors in 1 887), against 99.1% for naive sharp naming.
- ps13 emits double flats in dense chromatic runs, so they are rewritten to single accidentals.
- The key comes from partitura's Krumhansl–Kessler estimate on the same notes.

**Notated durations (`quantize.fill_gaps`).**
- Each note in a voice is held until the next onset when the gap is ≤ an 8th.
- Scored against the notated length (±1/24 tolerance; URMP score MIDI stores a quarter as 23/24).

| Variant | URMP brass | Chorales |
|---|---|---|
| Performed length, snapped | 0.58 | 0.85 |
| **Fill gaps ≤ 8th** (earlier rule) | **0.61** | **0.88** |
| Fill gaps ≤ beat | 0.61 | 0.88 |

These figures came from an uncommitted script. The committed `duration_bench` (whole ensemble quantized together, ±1 tick, weighted by note count) gives 0.631 / 0.911 for the same rule; see "Durations from audio" below for the current rule.

- The dominant remaining error on URMP is 899 notes where the score has an 8th plus an 8th rest and we write a quarter (staccato themes in Surprise and Slavonic).
- That is a notation choice audio cannot settle. It should become staccato marks when the performed length is under half the written one.

**Melody line (`eval/brasscribe_eval/melody_bench.py`).**
- Cases: Slakh trumpet, URMP track 1, chorale soprano. Metric: onset F1 at 100 ms.

| Candidates → top line | Slakh | URMP | Chorales | mean |
|---|---|---|---|---|
| Union of MuScriptor + Basic Pitch | 0.36 | 0.55 | 0.36 | 0.42 |
| **MuScriptor-supported** (confidence ≥ 0.5) | 0.65 | **0.72** | **0.90** | **0.76** |
| Agreement only | **0.67** | 0.65 | 0.80 | 0.71 |

- Basic Pitch's false positives (mostly upper harmonics) sit above the melody. The top line must only see notes MuScriptor supports.
- A Viterbi picker (salience minus leap penalty) never beat the top line in a parameter sweep. In these sets the melody is almost always the top voice, so there is nothing for it to win. It was removed.
- Revisit with material where the tune is an inner voice.
- In the score, melody notes Basic Pitch did not confirm keep confidence 0.6 and are **coloured red** as "unconfirmed". This is the first piece of the confidence display.

## Arrangement (Milestone 7, minimal band)

**Pipeline:**
- `music/src/brasscribe_music/score_model.py`: the canonical Composition (concert pitch, ticks, voices tagged by role, confidence and sources). It is the only thing the arranger reads.
- `arranger.py`: melody → Solo Cornet (octave chosen per phrase); bass → E♭ Bass (lowest comfortable octave) with B♭ Bass an octave lower where comfortable; inner parts voiced greedily per harmony slot.
- `harmony.py`: dense accompaniment → per-beat pitch-class sets.
- `musicxml.build_band_score`: transposing parts, converted to written pitch once at export.
- Durations are snapped to notatable ticks (16th or triplet-8th positions).

**Tests (`music/tests/test_band_export.py`):**
- Export → re-import → sounding pitch equals the arranger's concert pitches in every part.
- In concert F, B♭ parts read G major and E♭ parts D major.

**Ground-truth benchmark (`eval/brasscribe_eval/arrange_bench.py`, no audio):**

| Set | melody kept | bass kept | harmony fidelity | impossible | uncomfortable / piece | crossings |
|---|---|---|---|---|---|---|
| Chorales (10) | 1.00 | 1.00 | 0.99 | 0 | 0 | 0 |
| URMP brass (8) | 1.00 | 1.00 | 0.98 | 0 | 3.8 | 0 |
| Chorales, inner voices replaced by reduced harmonic rhythm | — | — | 0.98 | — | — | — |
| URMP, same | — | — | 0.96 | — | — | — |

**Fixes found by looking at rendered scores:**
- Centring the bass octave squeezed five inner parts into an octave, forcing unisons. Basses now take their lowest comfortable octave.
- B♭ Bass pedal notes are no longer used by default.
- URMP's 23/24-beat MIDI durations produced 64th rests and 12:11 tuplets that MuseScore rejects. Tiny gaps are now held, and ends are snapped to notatable positions.

**MuseScore gate (`eval/brasscribe_eval/musescore_roundtrip.py`).**
- The check re-exports through the MuseScore CLI, re-imports, collapses ties and compares sounding pitch per part.
- Mikkel: **all 8 parts match** the arranger's concert pitches.
- MuseScore assigns brass.cornet / flugelhorn / alto-horn / trombone / euphonium / tuba.

Two issues it caught:
1. music21 writes no `<instrument-sound>`, so MuseScore read "E♭ Bass" as a *vocal* bass. The export post-pass now writes the sound IDs, and the basses are named "E♭/B♭ Tuba" internally (part names stay "E♭ Bass").
2. music21's `stripTies` misses mid-bar `continue` ties. That was a comparison artifact, not a file bug.

**What the arranger metrics do and don't show.**
- Melody kept, bass kept and zero crossings are guaranteed by construction: lines are only octave-shifted and the voicer cannot cross parts.
- Harmony fidelity is partly guaranteed, since the pitch classes come from the source.
- These numbers prove that range, transposition and export logic are sound and don't regress. They say nothing about musical quality. The rendered scores are the evidence for that, and they show block chords and doubling.

**End-to-end Mikkel:** `data/mikkel/arranged/brass-band.{musicxml,pdf,mp3}`, from `arrange_song.py`. The MP3 is MuseScore's playback, for comparison with `mikkel.wav`.

Visible limits:
- Inner parts are block chords, one per beat. No rhythmic figuration or countermelody yet.
- Trombone and euphonium still double often.
- The bass is empty through the first ~29 bars. Verified: the SW bass stem's RMS is 0.0000 until 70 s, and `bass-medium.mid` has no notes before 50 s.
- The melody contains many red, unconfirmed 16th runs, probably orchestral figuration rather than trumpet.
- Percussion is deferred; drum transcription exists but no kit part is written yet.

## Quartet arrangement

The quartet lineup (`instruments.QUARTET`: 1st Cornet, 2nd Cornet, Tenor Horn, Euphonium, one player each) puts the melody on the 1st Cornet and the bass on the Euphonium, and voices 2nd Cornet and Tenor Horn together as alto and tenor with `arranger.voice_satb`. Plan: `docs/plan/kvartett.md`.

**Voicing rules (`voice_satb`, frozen; `arranger.rs` follows them exactly).** Every (alto, tenor) pair in the two parts' ranges is tried. Hard rules: S > A ≥ T > B, S–A and A–T at most an octave, chord tones only. A lead that moves inside a slot counts with its lowest note for crossing and its highest for spacing; a bass with its highest. Among the pairs left, the smallest of, in this order:
1. chord tones left out (the fifth of a triad does not count)
2. parallel perfect fifths and octaves against the previous slot, over all six voice pairs
3. doubling: 1 for a missing fifth, 1 per extra copy of a tone that is neither the root nor the bass's tone
4. movement |ΔA| + |ΔT|
5. the higher alto, then the higher tenor

A slot with no legal pair falls back to the band voicer and is reported in the warnings.

**Tuning on the chorales.** ChoraleBricks brass4 is itself a brass quartet playing SATB chorales, so A and T are ground truth for 2nd Cornet and Tenor Horn. The arranger sees only the harmony's pitch classes.

| Scoring order | alto recall (pc) | tenor recall (pc) | parallels / 100 |
|---|---|---|---|
| coverage, doubling (third doubled 2), parallels, movement: the plan's first order | 0.70 | 0.65 | 13.7 |
| coverage, parallels, doubling (third doubled 2), movement | 0.73 | 0.66 | 0.94 |
| same, a doubled third costs 1 and the bass's tone may be doubled freely (**frozen**) | **0.80** | **0.78** | **0.94** |
| whole-chorale least-cost path instead of slot by slot (not adopted) | 0.83 | 0.75 | 1.12 |
| chorales' own voices (reference row) | 1 | 1 | 0.79 |

Parallels must come before doubling: with doubling first the voicer happily moves in octaves with the bass. The remaining misses are mostly alto and tenor swapping the same two pitch classes, and passing tones the chorales' composers resolve differently (only one of the ten chorales is by Bach); the voicer cannot tell those apart from pitch classes alone. **`alto_recall_pc` ≥ 0.85 (plan §3.8) is not reached**; the baseline is set at the measured 0.80.

**Symbolic benchmark (`brasscribe bench arrange`, keys `quartet.*`, `quartet-standard.*`, `quartet-easier.*`):**

| Chorales (10) | melody kept | bass kept | harmony fidelity | alto recall exact / pc | tenor recall exact / pc | parallels / 100 | spacing faults | crossings | impossible | uncomfortable |
|---|---|---|---|---|---|---|---|---|---|---|
| faithful | 1.00 | 1.00 | 0.995 | 0.803 / 0.803 | 0.774 / 0.779 | 0.94 | 0 | 0 | 0 | 0 |
| standard | 1.00 | 1.00 | 0.995 | 0.803 / 0.803 | 0.774 / 0.779 | 0.94 | 0 | 0 | 0 | 0 |
| easier | 1.00 | 1.00 | 0.994 | 0.793 / 0.793 | 0.769 / 0.773 | 0.94 | 0 | 0 | 0 | 0 |
| reference voices | | | | | | 0.79 | 0 | 0 | | |

The chorale bass (tuba, mean MIDI 38, lowest 28) is below the Euphonium's reading floor (40), so every chorale moves up an octave as a whole phrase. Tenor over bass still holds everywhere.

**From recordings (`brasscribe bench quartet-audio`):** cached transcriptions of the ChoraleBricks recordings through `arrange_song --lineup quartet`, scored in seconds against the chorale (pitch class sounding 50 ms after each reference attack).

| Source | melody kept | bass kept | alto recall (pc) | tenor recall (pc) | parallels / 100 | spacing faults | impossible | uncomfortable |
|---|---|---|---|---|---|---|---|---|
| MuScriptor medium, Basic Pitch support | 0.85 | 0.92 | 0.55 | 0.41 | 5.4 | 0.1 | 0 | 0 |
| Basic Pitch only | 0.68 | 0.58 | 0.17 | 0.18 | 3.0 | 2.5 | 0 | 1.3 |

Transcription costs about 0.25 of alto recall and 0.37 of tenor recall on top of the arrangement. The cornet's placement limit is its playable top (MIDI 82), so no lead note is impossible. Before, the limit was 84 and the Basic Pitch row had 0.6 impossible notes per piece on the 1st Cornet; lowering the passages that reached 83–84 costs 0.3 spacing faults and 0.2 uncomfortable notes per piece.

**Mikkel (layered, `difficulty_bench --mikkel`):**

| Mikkel, quartet | Solo / other 16ths | Uncomfortable | Harmony fidelity | Melody kept | Contour | Figuration recall |
|---|---|---|---|---|---|---|
| faithful | 38.8 / 2.2% | 29 | 0.689 | 1.0 | 1.0 | 0.39 |
| standard | 15.4 / 0.5% | 0 | 0.691 | 0.79 | 0.78 | 0.93 |
| easier | 8.6 / 0% | 0 | 0.699 | 0.74 | 0.73 | 0.94 |

Faithful keeps every transcribed note, so it keeps the solo's uncomfortable notes; none is impossible, since the passages that reached above the cornet's playable 82 are written an octave lower, and 8 low Euphonium notes. The band's Solo Cornet is the soloist lead instead: in faithful it writes those passages as played, up to the cornet's solo range of 84 (`docs/plan/trumpet.md` §2). No crossings in any mode; spacing faults only in the 61–86 slots that fell back to the band voicer (warned); parallels 2.2–3.0 per 100 changes.

## Solo line: three-way vote (MuScriptor, Basic Pitch, SwiftF0)

**Setup.** `eval/brasscribe_eval/solo_vote_bench.py`.
- Solo stems separated with Mega-53 from mixes with a known solo part: 10 ChoraleBricks brass quartets (trumpet = soprano) and Slakh T06/T14.
- Each source is reduced to one line.
- Notes are clustered across sources at 100 ms.
- Adapter: `ml/adapters/swift-f0` (SwiftF0 contour → built-in DP note segmentation). About 1 s for a 4-minute solo on CPU.
- On a clean isolated URMP trumpet it scores onset F1 0.994.

| Source on separated solo stem | mean onset F1 (100 ms) |
|---|---|
| **SwiftF0** | **0.75** |
| MuScriptor | 0.50 (0.00 on 3 chorales, 0.06–0.08 on Slakh: hallucination on separated stems) |
| Basic Pitch | 0.42 |
| ≥ 2 votes | 0.73 (P 0.89, R 0.66) |

| Agreement | Precision (n) |
|---|---|
| all three | **0.98** (193) |
| SwiftF0 + MuScriptor | 0.99 (110) |
| SwiftF0 + Basic Pitch | 0.91 (578) |
| SwiftF0 only | 0.54 (297) |
| MuScriptor + Basic Pitch (no SwiftF0) | 0.36 (14) |
| MuScriptor only / Basic Pitch only | 0.02 / 0.05 |

**Adopted rule for solo lines:**
- SwiftF0 supplies the notes.
- A note is *confirmed* (black) when another model agrees, and *unconfirmed* (red, 0.54) when SwiftF0 is alone.
- Notes without SwiftF0 are dropped.
- The previous rule treated MuScriptor + Basic Pitch agreement as confirmed, which is only 36% precise on separated stems.

**Mikkel:** red solo notes fell from 540/694 (78%) to 214/689 (31%).

**Separation failures:** two chorales (Gesius *Du Friedensfürst*, Jan) fail for every model (F1 ≤ 0.35). Mega-53 did not isolate the trumpet there, and no vote can recover missing audio.

## Free time (rubato)

`music/src/brasscribe_music/freetime.py`; benchmark `brasscribe_eval.freetime_bench ../data/eval/urmp-brass ../data/eval/choralebricks-brass4`.
- Detection: runs of ≥ 3 beat intervals and ≥ 4 s that match neither the piece's beat nor its double, half or split, with spread ≥ 0.2 of the mean interval.
- Fires on 1 of 18 eval pieces (Air on the G String, 169.6–181.1 s, a ritardando into a 4.5 s hold). Strict-passage position / subdivision / duration change by 0.000 on every piece (mean 0.474 / 0.886 / 0.627 in both runs).
- Mikkel: 0.03–29.76 s detected, notated as 7 bars *ad lib.* at ♩≈57. Solo Cornet 16ths in the intro fall from 30.8% to 5.6% (`qa/tools/musicxml_readability.py --range`).
- Open: the region-tempo rule (median melody gap = half note, clamped 40–100 BPM) is tuned on Mikkel only.

## Durations from audio

`music/src/brasscribe_music/durations.py`; benchmark `brasscribe_eval.duration_bench <eval_dir> [--contours <dir>]`.

| Offsets | URMP: fill ≤ 8th → new rule | Chorales: fill ≤ 8th → new rule |
|---|---|---|
| Annotated | 0.631 → **0.654** | 0.911 → **0.929** |
| SwiftF0 contour of each part | 0.629 → 0.647 | 0.907 → 0.908 |

- Contour offsets land within 100 ms of the annotation for 91% (URMP) / 84% (chorales) of notes.
- Staccato fires 17–22 times on URMP, and 15–16 of those are where the score wrote a shorter value instead of a staccato mark. Unvalidated: no articulation ground truth.
- Open: both thresholds were chosen on the data they are scored on; a held-out set is needed.

## Bar-line cleanup

`beats.clean_beats_gated`; benchmark `brasscribe_eval.barline_bench ../data/eval/urmp-brass ../data/eval/choralebricks-brass4`. The cleanup is applied only when the tracker's own downbeat labels agree better afterwards (by ≥ 0.02), or on one-beat-per-bar tracks with ≥ 3 edits.

| Beats | Position | Subdivision | Duration | Drift events |
|---|---|---|---|---|
| Raw | 0.470 | 0.885 | 0.627 | 268 |
| Gated cleanup | 0.519 | 0.905 | 0.654 | 139 |

Changed pieces all improve (Entertainer position 0.48 → 0.90, Air 0.07 → 0.31, Arioso 0.23 → 0.45); the other 15 are identical. Thresholds are tuned on this data.

## Difficulty modes and lineups

`music/src/brasscribe_music/difficulty.py`; benchmark `brasscribe_eval.difficulty_bench ../data/eval/choralebricks-brass4 ../data/eval/urmp-brass --mikkel ../data/golden/mikkel-arranged-band/composition.json`. Faithful at default options stays identical to the golden output. Rerun 2026-09-29 on the fast-notes golden: faithful writes the solo's fast notes as played, so its solo 16ths rose from 38.8 % to 66.6 % (the bench counts the solo layer; the readability tool's Solo Cornet part is 63.6 %), and standard and easier now keep less of the melody than before.

| Mikkel, full band | Solo / other 16ths | Uncomfortable | Harmony fidelity | Melody kept | Contour | Key changes |
|---|---|---|---|---|---|---|
| faithful | 66.6 / 2.9% | 32 | 0.839 | 1.0 | 1.0 | 8 |
| standard | 20.1 / 1.7% | 0 | 0.767 | 0.603 | 0.575 | 8 |
| easier | 9.0 / 0% | 0 | 0.769 | 0.552 | 0.561 | 4 |

URMP: uncomfortable 1.0 / 0 / 0, harmony fidelity 0.971 / 0.958 / 0.958. Separating reading ranges from playable ranges took URMP uncomfortable notes from 3.8 to 1.0 (current baseline).
Open: large transpositions put the basses on ledger lines (E♭ Bass with 3+ ledger lines: 6.0% at +5 semitones, 7.7% at −5; limit 5%).

## Readability (Mikkel)

`qa/tools/musicxml_readability.py <musicxml> --check --baseline qa/reports/mikkel-golden-readability.json` (the baseline is the tool's `--json` output for the golden). Solo Cornet, from the first golden to the current one: uncertain notes by colour only 230 → 0; double dots 9 → 0; printed accidentals 37.5 % → 6.7 %; 16ths 40.2 % → 63.6 %. The 16ths rose with the fast-notes golden (2026-09-29), which writes the solo's fast notes as played; the faithful Solo Cornet gate is 65 % 16ths (`FAITHFUL_LIMITS` in `eval/brasscribe_eval/suites.py`), and every other threshold is unchanged. Whole score: dynamics 0 → 209, rehearsal marks 0 → 11, key changes 0 → 8.

## Rust core conformance

`cd core/conformance && uv run python -m brasscribe_conformance.run --musescore` (rerun 2026-09-29 on the fast-notes golden, 28 min on an M-series Mac): 413/413 cases and 4974/4974 files identical to the Python reference (golden Mikkel, option variants, eval songs, per-seat solo takes, arranger and quantize benches), with the talking score and the humanization compared inside each case; the committed golden 34/34 files identical. MuseScore round trip 208/211: three band arrangements (URMP 34 Fugue; ChoraleBricks Jan "Du großer Schmerzensmann" A and Telemann "Der lieben Sonne Licht und Pracht" B) were not written back by MuseScore 4. Mikkel layers case: 53.5 s for the Python reference with its exports, 0.78 s for Rust. The Python reference is exact only on macOS arm64 with NumPy 2.5.3 (argsort tie order, FMA in `interp`).

## On-device model parity

See `convert/README.md` (regenerate with `python3 convert/summarize.py`; reports in `convert/reports/`). Gate: note F1 ≥ 0.98 against the reference framework's output.

## Realistic sound

`sounds/` (see `sounds/README.md`). Spectral centroid per part in harmonics against held-out ChoraleBricks references: the realistic tier is closer than MS Basic on 16/16 parts. Blind A/B material for 5 listeners × 5 excerpts, plain and room-matched, is in `data/runs/sound/ab-test{,-room}/`. The listening test has not been run.

## Capture check

- The `capture/` process tap was verified with a loopback test: a 10 s 440 Hz sine played via `afplay` was captured as 10.000 s at 440.0 Hz.
- The captured file runs longer than `--seconds` only because the stop timer fires late; the content rate is correct.

## Next

See `docs/plan/apps-plan.md` §8 for the engine backlog.
