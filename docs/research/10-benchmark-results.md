# 10 — Benchmark results

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
| Beat This!, penalties ×20 | ~0.45 | **0.92** | 0.76 |

**Findings:**
- With the adopted penalties, remaining quantizer errors are mostly note lengths. Offsets depend on legato vs detached playing; per-voice "hold until next onset" belongs in the voice-separation stage.
- **The weak link is the beat grid, not the snapping.**
  - Chorales have fermatas; Beat This! inserts extra beats during held chords (1.1–1.2 detected beats per notated quarter). Bar positions therefore drift, even though positions within the beat stay 92% right.
  - One 6/4 chorale was tracked at half the metrical level (0.35 beats per quarter).
  - Fixes: meter- and downbeat-constrained beat selection; fermata detection (long simultaneous holds); a user correction pass in the UI.
- Mikkel has a steady ~138 BPM after its intro, so it should be less affected.
- The penalty scale is tuned on rhythmically simple chorales. Revalidate on URMP and faster material.

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

## Capture check

- The `capture/` process tap was verified with a loopback test: a 10 s 440 Hz sine played via `afplay` was captured as 10.000 s at 440.0 Hz.
- The captured file runs longer than `--seconds` only because the stop timer fires late; the content rate is correct.

## Next

- Consensus of MuScriptor medium and Basic Pitch on brass4.
- Separated-stem pipeline (B) on brass4.
- A melody reference for Mikkel.
