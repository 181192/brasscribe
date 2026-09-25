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

## Capture check

- The `capture/` process tap was verified with a loopback test: a 10 s 440 Hz sine played via `afplay` was captured as 10.000 s at 440.0 Hz.
- The captured file runs longer than `--seconds` only because the stop timer fires late; the content rate is correct.

## Next

- Consensus of MuScriptor medium and Basic Pitch on brass4.
- Separated-stem pipeline (B) on brass4.
- A melody reference for Mikkel.
