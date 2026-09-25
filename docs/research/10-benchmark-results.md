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

## Capture check

- The `capture/` process tap was verified with a loopback test: a 10 s 440 Hz sine played via `afplay` was captured as 10.000 s at 440.0 Hz.
- The captured file runs longer than `--seconds` only because the stop timer fires late; the content rate is correct.

## Next

- Consensus of MuScriptor medium and Basic Pitch on brass4.
- Separated-stem pipeline (B) on brass4.
- A melody reference for Mikkel.
