# 11 — Overlapping instruments and in-between tones

Date: 2026-09-27. Desk research plus one-off measurements on the existing eval sets and the Mikkel run. The scripts were inline and are not committed. As in [10-benchmark-results.md](10-benchmark-results.md), treat the numbers as findings to re-derive, not as regression baselines.

**Status (2026-09-29):** recommendation 3 (contour segmentation for the solo line) is built for fast notes and bends in `docs/plan/fast-notes.md`: a short semitone into or off a held note is now its bend, and alternations are split on contour plateaus. Recommendation 1 (voice separation that allows unisons) is open. Recommendation 2 is started (2026-10-01): in the brass-band profile, Basic Pitch hears the recording retuned to A = 440 (`engine/src/brasscribe_engine/tuning.py`). Retuning MuScriptor (it gains on average but collapses on single pieces), SwiftF0 and separated stems (whose estimates are unreliable), and the confidence feature are open.

"Mellom toner" covers two different problems, and this report covers both:
- **(a) Notes hidden where instruments overlap:** unisons (cornet + flugel on one pitch), octaves (E♭ and B♭ bass, euphonium under cornet), an upper note sitting on a partial of a lower one, and close voicings.
- **(b) Pitches between semitones:** tuning offset, intonation drift, vibrato, scoops, falls, doits and glissandi, which get snapped to the wrong note or split into extra notes.

## Short answer

**Have we covered this before?** Only as a limitation. The docs say several times that unisons collapse and that same-timbre voices are not separated. They list octave errors and close harmony as open benchmark questions. For bends, the only advice so far is to keep Basic Pitch's contour "as side data". No strategy for either problem has been proposed or tested. The history is in §1.

**What the data says now (§2):**
1. **Unisons are the biggest overlap loss, and the models are not failing to hear them.** Both models find the unison pitch 88–93% of the time, but only once. Recall of unison notes is 0.48–0.61 against 0.82–0.92 for notes with no overlap. The information that is missing is "how many players", not "which pitch". That makes this a symbolic problem we can solve.
2. **Octaves, partials and close intervals cost almost nothing with MuScriptor.** The chorale bass looks hidden under the octave (recall 0.73), but the tuba scores the same without an octave above it (0.72 vs 0.71). That deficit comes from the tuba itself (low register, intonation), not from masking.
3. **Intonation hurts Basic Pitch badly and MuScriptor much less.** On chorale tuba notes, Basic Pitch recall falls from 0.78 (under 20 cents off) to 0.48 (35–50 cents) and 0.03 (over 50 cents). MuScriptor goes 0.75 → 0.68 → 0.52. Every eval piece is 6–20 cents sharp of A440, and so is Mikkel's solo (+20 cents).
4. **Mikkel is full of in-between pitch.** In the middle of 19% of SwiftF0's solo notes the pitch moves by more than 50 cents, and in 9% by more than 100 cents (vibrato, bends, falls). There is no ground truth for any of it.

**Top 3 to try next (§3):**
1. **Voice separation that allows unisons.** Build the planned symbolic voice-separation stage so that one detected note can belong to two parts. Voice-leading decides, and acoustic cues break ties.
2. **Tuning-aware pitch decisions.** Estimate the tuning offset and retune before transcribing. Carry each note's cents deviation, and use its distance to the rounding boundary as a confidence feature.
3. **Contour segmentation that knows ornaments,** for the solo line. The segmenter recognises scoops, falls, doits, vibrato and glissandi as parts of one note rather than as extra notes, and writes them as MusicXML ornaments. It needs a synthetic benchmark, because no brass ornament dataset exists.

---

## 1. What we have said before

**Repo docs:**

| Where | What it says |
|---|---|
| [00-summary.md:69–71](00-summary.md) | "No model separates same-timbre voices. Three cornets in close harmony become one stream … MT3-style tokens cannot even represent a unison on one instrument. Voice separation, and assigning notes to brass-band parts, must be a symbolic stage we build ourselves." |
| [00-summary.md:225](00-summary.md) | Open question 5: "SwiftF0 vs torchcrepe on real cornet/euphonium lines; octave errors in the bass register." |
| [02-amt-multi-instrument.md:15](02-amt-multi-instrument.md) | "Same-timbre voices are not separated … multiple instances of the same 'instrument' … are not distinguished" (MuScriptor #91). Keeping same-pitch notes in MuScriptor's test set costs 8.6 onset F1. |
| [02-amt-multi-instrument.md:172–173](02-amt-multi-instrument.md) | Open questions: "Close-harmony, same-timbre voice separation … brass-band unisons may cost more" and "Octave errors on low brass". |
| [03-amt-polyphonic-stem.md:28](03-amt-polyphonic-stem.md) | "Close-voiced chords within one timbre are the weak point everywhere … MuScriptor cannot represent two notes of the same pitch on the same instrument, so unisons collapse." |
| [03-amt-polyphonic-stem.md:99, 103](03-amt-polyphonic-stem.md) | MuScriptor "drops simultaneous same-pitch, same-instrument notes, so unisons collapse", and has "no pitch bends". |
| [03-amt-polyphonic-stem.md:110–112](03-amt-polyphonic-stem.md) | Basic Pitch bends resolve to about 33 cents. "Quantize to notes for the score and keep the contour as side data (vibrato, falls, scoops) rather than writing it as MIDI bends." |
| [03-amt-polyphonic-stem.md:175](03-amt-polyphonic-stem.md) | "f0 trackers give continuous pitch, which captures scoops, falls and vibrato." |
| [03-amt-polyphonic-stem.md:296](03-amt-polyphonic-stem.md) | Proposed octave arbitration: move polyphonic notes that sit exactly ±12 from a confident monophonic f0 onto the tracker's octave. It was never built. |
| [03-amt-polyphonic-stem.md:305–306](03-amt-polyphonic-stem.md) | Open: "Are unisons between parts collapsed?" and "octave-error rate on tuba, which has a strong upper-partial spectrum". |
| [10-benchmark-results.md:71–74](10-benchmark-results.md) | Bass weakest everywhere. The ChoraleBricks tuba is often out of tune: "+22 cents and 16% of its notes are more than 40 cents off". |

**Code touchpoints:**
- `sounds/render.py:12–13, 457–459`: the renderer gives each player its own detune and lag "so unison desks never sum as sample clones". This is the synthesis side of the same effect, and it is useful for building test audio.
- `music/src/brasscribe_music/confidence.py:33`: `SUPPORT_TOL = 1.0` semitone. A note 50 cents off still counts as fully supported by the contour.
- `eval/brasscribe_eval/urmp.py:24`: URMP reference pitches are the annotated frequency rounded at A440.
- `docs/songs/mikkel.md:54`: the *arranger* writes unisons for paired parts. That is the output side, not detection.

**Session memory:** `/Users/k/private/brasscribe/.remember` does not exist. `/Users/k/private/.remember` mentions unisons once (`today-2026-09-25.done.md:27`, "fixed unisons"), and that refers to the arranger forcing unisons ([10-benchmark-results.md:304](10-benchmark-results.md)), not to detection. The auto-memory files say nothing on the topic.

---

## 2. Measurements

**Method:**
- Every reference note in `choralebricks-brass4` (1 887 notes) and `urmp-brass` (5 129) is classed by its relation to notes of *other* parts that overlap it by more than 50 ms. The first matching class wins:
  1. **unison**: same pitch
  2. **octave**: ±12/24/36, split into lower and upper note
  3. **partial**: the note is 19, 28, 31 or 34 semitones above a sounding note, i.e. on its 3rd, 5th, 6th or 7th partial
  4. **close**: 1–2 semitones apart
  5. **clear**: none of the above
- Matching is mir_eval one-to-one, 100 ms onset, pitch equality, using the cached `muscriptor-medium.mid` and `basic-pitch.mid`.
- "Present" means any estimate at that pitch within 100 ms (many-to-one).

### 2.1 Overlap classes

| Set | unison | octave (lower / upper) | partial | close | clear |
|---|---|---|---|---|---|
| Chorales | 2.3% | 24.9% / 24.1% | 28.9% | 1.1% | 18.7% |
| URMP brass | 12.4% | 14.2% / 13.5% | 8.4% | 5.4% | 46.1% |

**Recall by class:**

| Set · model | unison R (present) | octave-lower | octave-upper | partial | close | clear |
|---|---|---|---|---|---|---|
| Chorales · MuScriptor | **0.48 (0.93)** | 0.73 | 0.89 | 0.90 | 0.85 | 0.82 |
| Chorales · Basic Pitch | **0.52 (0.93)** | 0.71 | 0.88 | 0.83 | 0.60 | 0.85 |
| URMP · MuScriptor | **0.61 (0.88)** | 0.91 | 0.91 | 0.91 | 0.87 | 0.92 |
| URMP · Basic Pitch | **0.56 (0.80)** | 0.83 | 0.74 | 0.66 | 0.69 | 0.81 |

**Findings:**
- **Unison.** The pitch is found, but once. When both players attack together, one estimate can at best give the pair 0.5 recall. Recall of 0.48–0.61 is close to that ceiling. URMP sits higher because some of its unison notes start at a different time from their partner. By part:
  - Flugelhorn in unison with the trumpet: 0.36.
  - Trumpet in the same pairs: 0.71.
  - The model keeps the top instrument's note and drops the other.
- **Octave-lower (chorales).** Almost all of these are tuba. Tuba recall is 0.71 under an octave and 0.72 when clear. Masking by the octave above is not the cause. The low register and the tuba's intonation are (§2.2).
- **URMP unisons are real.** No cross-part unison pair has onset and offset within 5 ms of each other, apart from one pair in Arioso, so duplicate annotation is not inflating the count. Arioso alone has 208 of the 358 pairs, so report URMP per piece.
- **The eval sets understate the problem.** Brass-band scoring doubles constantly: 2nd/3rd cornets, repiano and flugel on the solo line, basses in octaves, euphonium on the bass. The chorales have only 22 unison pairs.

### 2.2 Intonation

We measured each note's median f0 over the middle 60% of the note, from the datasets' own f0 annotations, against the reference pitch. URMP's reference pitch is itself rounded from the annotated frequency, so URMP can show offset and wobble but not snapping errors. The ChoraleBricks reference comes from the score.

- **Piece tuning:**
  - All 18 pieces are sharp of A440: chorales −1 to +20 cents, URMP +12 to +20.
  - Mikkel's solo stem sits at +20 cents (circular mean of confident SwiftF0 frames), i.e. about A = 445 Hz.
- **ChoraleBricks tuba:**
  - 24.9% of notes are more than 35 cents off the written pitch, and 6.2% more than 50 cents off. Those 6.2% round to the wrong semitone at A440.
  - Other chorale instruments: 0–3% over 35 cents, and none over 50.

**Chorales, recall by distance from the written pitch:**

| Notes | < 20 c | 20–35 c | 35–50 c | > 50 c |
|---|---|---|---|---|
| Tuba · MuScriptor | 0.75 (246) | 0.72 (104) | 0.68 (87) | 0.52 (29) |
| Tuba · Basic Pitch | 0.78 | 0.70 | **0.48** | **0.03** |
| Others · MuScriptor | 0.87 (1127) | 0.87 (260) | 0.85 (34) | — |
| Others · Basic Pitch | 0.86 | 0.83 | 0.76 | — |

- Basic Pitch's note output rounds at A440 and has no idea of tuning. Its recall collapses as notes approach the semitone boundary.
- MuScriptor degrades gracefully. It seems to have learned tuning from real recordings.

**Mikkel solo** (SwiftF0 notes and contour from the latest `orchestra-with-soloist` run, 811 measurable notes):
- 27% of notes sit 30–50 cents sharp of the A440 grid, close to the rounding boundary.
- 6.7% sit 30–50 cents flat. These would round differently on a +20-cent grid.
- The pitch in the middle of the note moves by more than 50 cents in 19% of notes and by more than 100 cents in 9%.

### 2.3 A metric flaw found on the way

`score.py`'s `octave_err_rate` counts an unmatched reference note as an octave error if *any* estimate sits ±12/24 away at the same onset. In octave-heavy textures that estimate is usually the correctly transcribed partner voice. The fix is to count only estimates not matched to another reference note:

| Metric | Chorales MuS | Chorales BP | URMP MuS | URMP BP |
|---|---|---|---|---|
| Current definition | 2.7% | 10.6% | 1.4% | 4.5% |
| Only unmatched estimates | 2.4% | 7.0% | 0.6% | 2.4% |

Basic Pitch's octave-error rate is overstated by about a third on chorales and by half on URMP. Fix it before any octave experiment. The baseline in `eval/baselines.json` changes with it.

---

## 3. Ranked recommendations

### 1. Voice separation that allows unisons (problem a)

**Why first:**
- It fixes the largest measured overlap loss: unison recall 0.48–0.61, with the pitch present 88–93% of the time.
- It uses no new model.
- It builds the stage the architecture already needs. Voice separation is "the single most important piece of in-house algorithmic work" ([00-summary.md §6](00-summary.md)), and it does not exist yet: `musicxml.py:5` says "Real voice separation belongs to a later stage".

**Design:**
- **Input:**
  - consensus notes (pitch, onset, offset, confidence, sources)
  - the lineup: number of parts and their ranges.
- **Model:** a DP or HMM over onset slices that assigns each of N voices a note, a hold or a rest. Costs:
  - leap size
  - range
  - voice crossing
  - a voice going idle while the texture is full.
- **Unisons:** a note may be assigned to up to two voices, at a duplication cost. The cost goes down when:
  - **Voice-leading says so.** Both voices arrive by step from different pitches, or leave to different pitches. Gray and Bunescu define voice separation the same way: "a voice [may] diverge to multiple voices and … multiple voices [may] converge to the same voice" ([arXiv 2011.03028](https://arxiv.org/abs/2011.03028)).
  - **The level jumps.** Two equal players add about 3 dB (incoherent sum) over the local level of that voice.
  - **The attack flams.** Two players rarely start within 10 ms of each other, so the attack transient shows a double onset 10–40 ms apart.
  - **Upper partials beat.** Two tones Δ cents apart beat at about f·Δ/1731 Hz, and the k-th partial beats k times faster. At B♭4 (466 Hz) and 5 cents the fundamental beats at 1.3 Hz, too slow to see within a note, but the 5th partial beats at 6.7 Hz. Measure amplitude modulation of the 3rd–8th partials in the 2–15 Hz band over the sustain.
- **Order:** start with voice-leading alone and add the acoustic cues as an ablation.
- **Library option:** GNN voice separators exist ([Foscarin et al., ISMIR 2024](https://arxiv.org/abs/2407.21030), [code](https://github.com/CPJKU/piano_svsep), CC BY 4.0). They are trained on piano and have no unison sharing, so use them as a reference, not a drop-in.

**Experiment:**
1. **Harness:** commit the overlap-class script (§2.1) as an eval module. Add a *per-part* note F1: after voice separation each estimated voice is matched to one reference part. Both eval sets have part labels.
2. **Baselines:** unison-class recall today, and per-part F1 of a trivial "sort by pitch" voice separation.
3. **Runs:** voice-leading only; plus level; plus flam; plus partial beating.
4. **Synthetic check:** render controlled unisons through `sounds/` with per-player detune of 0, 2, 5 and 10 cents and onset lag of 0–30 ms, from ChoraleBricks and URMP scores. This isolates each acoustic cue.
5. **Caveat:** ChoraleBricks and URMP parts were recorded separately and summed. Their unisons are more detuned and less synchronised than a band that tunes and breathes together, so the acoustic cues will look better there than on real band recordings. The synthetic sweep shows how fast each cue fails as detune goes to zero.

**Success:**
- Unison-class recall ≥ 0.80 on both sets.
- Onset precision drops by ≤ 0.01.
- Per-part F1 beats the pitch-sort baseline.
- No regression in `bench ci`.

**Cost:** medium. It is a new `music/` module (not an adapter) and part of the canonical Composition path, so it needs a Rust port and conformance cases like every other stage.

### 2. Tuning-aware pitch decisions (problem b)

**Why:**
- Every piece is 6–20 cents sharp.
- Basic Pitch loses almost all notes more than 50 cents off, and half of those at 35–50 cents.
- Nothing in the pipeline estimated tuning: `durations.py:62` and `urmp.py:24` hard-code 440.
- The confidence model cannot see a note that sits on the boundary (`SUPPORT_TOL = 1.0` semitone).
- It is the cheapest fix in this report.

**Design:**
1. **Estimate the offset.** Use a circular mean of cents-mod-100 over confident SwiftF0 frames, or a spectral estimator such as librosa's `estimate_tuning`. Do it per piece, and per stem after separation, because a single player can sit apart from the band (the chorale tuba).
2. **Retune before transcribing.** Resample the audio by 2^(−offset/1200) and scale the output note times back by the same ratio. That is exact and artefact-free, unlike a phase-vocoder shift. It works for any transcriber, so it fits as a pre-stage wrapper in `ml/pipelines/` around an unchanged adapter `run.sh`.
3. **Keep the cents.** SwiftF0 already reports each note's `pitch_hz` to the cent ([README](https://github.com/lars76/swift-f0)); the adapter throws it away when writing MIDI. Keep it in a sidecar, as `contour.sh` already does for the contour.
4. **Add a confidence feature:** distance to the rounding boundary on the tuned grid. Refit `calibration.json` with `confidence_bench`.

**Experiment:**
- (a) Chorales and URMP as they are, with and without retuning, for Basic Pitch and MuScriptor.
- (b) A detune sweep: pitch-shift every eval mix by −45, −30, −15, +15, +30 and +45 cents, then run each model with and without retuning. Real recordings span at least A = 438–446, and older recordings drift further.
- (c) `confidence_bench` with and without the boundary feature.

**Success:**
- Basic Pitch tuba recall in the 35–50 c bucket goes from 0.48 to ≥ 0.70.
- With retuning, onset F1 across the detune sweep stays within 0.01 of the undetuned value for both models.
- The confidence model's held-out log loss improves, and at the same mark rate the "?" marks catch more wrong notes.

**Cost:** low. One estimator, one wrapper script, one sidecar field and one calibration feature. The Rust side only needs the new confidence feature.

### 3. Contour segmentation that knows ornaments (problem b, solo line)

**Why:**
- Mikkel is a trumpet solo by a player whose style is bends, falls and scoops.
- 19% of its solo notes move by more than 50 cents in the middle of the note.
- SwiftF0's `segment_notes` has one knob, `pitch_hold_ms`: a new semitone becomes its own note once it lasts longer than that ([README](https://github.com/lars76/swift-f0)). A fall therefore either splits into a run of short chromatic notes or smears into the next note.
- Basic Pitch drops notes under about 120 ms and caps its contour at about 33-cent resolution ([03 §3.2](03-amt-polyphonic-stem.md)).
- MuScriptor has no bends.
- MusicXML has the notation we need: `<scoop>`, `<plop>`, `<doit>` and `<falloff>` have been in the standard since 1.0, plus `<glissando>` and `<slide>` ([MusicXML 4.0 `<notations>`](https://www.w3.org/2021/06/musicxml40/musicxml-reference/elements/notations/), [`<falloff>`](https://www.w3.org/2021/06/musicxml40/musicxml-reference/elements/falloff/), [`<scoop>`](https://www.w3.org/2021/06/musicxml40/musicxml-reference/elements/scoop), [`<plop>`](https://www.w3.org/2021/06/musicxml40/musicxml-reference/elements/plop/)). MuseScore's import of these is unverified: a [feature request](https://musescore.org/en/node/14895) exists.

**Design:**
- **Model:** an HMM over the tuned SwiftF0 contour, in the spirit of pYIN's note tracker, which has attack, stable and silent states per pitch ([Mauch et al. 2015, Tony](https://www.tenor-conference.org/proceedings/2015/04-Mauch-Tony.pdf)). Per note it adds sub-states:
  - scoop-in: rising into the target within about 150 ms
  - stable: within about ±35 cents of the tuned target, with 4–7 Hz vibrato allowed around it
  - fall-out or doit-out: a monotone departure of more than 100 cents at the end, with loudness decaying
  - glide: a continuous path to the next note with no loudness dip, written as glissando.
- **Output:** the note at its stable pitch plus an ornament tag. The Composition gets an `ornament` field, and the MusicXML export writes it.
- **Where it lives:** in the SwiftF0 adapter (contour → notes), because that is where segmentation happens today. The ornament field touches the score model, the Rust core and the MusicXML writer.

**Experiment:**
- **Synthetic set:** impose known contours on real, isolated notes. Take ChoraleBricks and URMP trumpet tracks, which have note ground truth, and resynthesize selected notes with a vocoder that edits f0. WORLD/pyworld is one option; check its licence before adopting it. Contour types:
  - scoop (−100 to −300 cents into the note)
  - fall (−200 to −1200 cents out)
  - doit (upward out)
  - vibrato (±20–60 cents, 4–7 Hz)
  - glissando between adjacent notes.

  A synthetic pitch-contour dataset of the same kind exists for vibrato, glissando and bends ([SPC, arXiv 2503.19161](https://arxiv.org/html/2503.19161)). A violin study shows that technique-aware transcription trained on synthetic data carries over to real recordings ([VioPTT, arXiv 2509.23759](https://arxiv.org/abs/2509.23759)).
- **Real check:** hand-label 60 s of Mikkel's solo (notes plus ornaments). It is the only real Antonsen ground truth we can get.

**Success:**
- Extra notes per ornament below 0.1. The current segmenter's number is the baseline to measure first.
- Stable-pitch accuracy of at least 95% on ornamented notes.
- Ornament detection F1 of at least 0.7.
- Onset F1 on unornamented notes unchanged (±0.01, `solo_vote_bench`).

**Cost:** medium. The HMM itself is small; building the synthetic set and the score-model field is most of the work.

---

## 4. Other techniques considered

Each row ends with where to benchmark it. "Overlap classes" means the per-class recall of §2.1; "tuba buckets" means the intonation buckets of §2.2.

| Technique | Solves | Evidence | Licence | Cost / fit | Bench on | Verdict |
|---|---|---|---|---|---|---|
| **Iterative separate-and-transcribe per voice.** Transcribe, then run score-informed separation per voice, then SwiftF0 on each voice stem, then correct | Hidden inner voices; octave-lower notes | A score-only separation model gave URMP horn 3.70 dB and trumpet 5.47 dB SDR, against 1.34 / 2.11 for the baseline ([Tunturi et al. 2025, arXiv 2503.07352](https://arxiv.org/abs/2503.07352)). SwiftF0 scores 0.994 onset F1 on a clean isolated trumpet ([10](10-benchmark-results.md)) | Code and aligned scores CC BY 4.0 (per the paper) | High. Trained on orchestral instruments, not brass band; needs training or fine-tuning; a new adapter plus a loop in the orchestrator | Per-part F1 and the octave-lower class on both sets | Next after the top 3, once voice separation exists to supply per-voice scores |
| **Timbre-conditioned separation**: Mega-53 brass sub-stems (`ml/adapters/mega53`) | One player sitting apart from the band in tuning or register (the chorale tuba) | Already in use for solo stems. It cannot split same-timbre voices ([00-summary](00-summary.md) finding 3) | Weights licence not stated | Low. The adapter exists. Its tuba stem is the natural input for the per-stem retune in rec. 2. SwiftF0's floor is 46.9 Hz (F♯1), so tuba notes around G1 are marginal and E♭1 and below need CREPE or Basic Pitch | Tuba buckets and B recall on chorales, with and without the per-stem retune | Use inside rec. 2, not on its own |
| **Basic Pitch contour / pitch-bend output** (`--save-model-outputs`) | Tuning estimate; bend and vibrato evidence in polyphonic stems | Contour has 3 bins per semitone, so bends resolve to about 33 cents ([03 §3.2](03-amt-polyphonic-stem.md)) | Apache-2.0 | Low. A small adapter change that writes a contour `.npz` sidecar, the way `swift-f0/contour.sh` does | Offset-estimate error against the f0 annotations (§2.2); the detune sweep in rec. 2 | Second tuning source for rec. 2; possible polyphonic input for rec. 3 |
| **NMF with brass templates** (score-informed residual) | Checking whether a hidden octave or unison note is really there | Already the planned verification signal ([00-summary](00-summary.md) §2, verification loop). Templates can be learned per instrument and pitch from the isolated ChoraleBricks tracks | Our own code | Medium. A `music/` post-check on the mix, not an adapter | Octave-lower and unison classes on chorales; injected-error localisation ([05, open question 6](05-harmony-melody-embeddings.md)) | After rec. 1, as the acoustic tie-breaker it proposes |
| **YourMT3+ / MT3** | Multi-instrument notes | Same MT3-style tokens, so the same limit on same-pitch notes within one instrument ([02:15](02-amt-multi-instrument.md)). Never integrated ([00-summary](00-summary.md) §0) | GPL-3.0 vs Apache-2.0, ambiguous | Medium (own venv, numpy 1.26) | Overlap classes, if ever run | No. It cannot express multiplicity any better than MuScriptor |
| **Multi-f0 salience as an extra voter**: Deep Salience `multif0` | Recall of inner voices; a frame-level vote for fusion | ISMIR 2017, general music. Weights for multif0, melody, bass and vocal are in the repo | MIT ([repo](https://github.com/rabitt/ismir2017-deepsalience)), last push 2019 | Medium. Keras/TF of 2017–19 vintage needs its own pinned venv or an ONNX port. Fits `run.sh` with a salience `.npz` sidecar | Overlap classes; consensus precision with it as a third voter | Low priority. MuScriptor already hears the overlapped pitches (§2.1); what we lack is multiplicity, and salience cannot give that |
| **Phase-aware multi-f0 for same-timbre ensembles** | Close same-timbre voices, unison sections | CNN on magnitude + phase differentials. Phase raised precision, and the model was robust to unison (several singers per part) and reverb on choir data ([Cuesta et al., ISMIR 2020, arXiv 2009.04172](https://arxiv.org/abs/2009.04172)) | MIT, weights included ([repo](https://github.com/helenacuesta/multif0-estimation-polyvocals)); TF 1.x | Medium to high. Vocal-trained and an old stack. "Robust to unison" means it finds the pitch, not the player count | Close and unison classes on URMP | Watch. Re-training the recipe on brass would be the real experiment |
| **Synchrosqueezing / ConceFT** time–frequency analysis | Resolving close components such as detuned unisons | Su et al., cited in Cuesta et al. 2020 for choir and symphonic multi-f0 (not read directly) | — | Physics limits it: resolving 2–5 cent detune needs windows of seconds | Synthetic unisons (rec. 1) | No. Use partial beating (rec. 1) instead |
| **Polyphony per instrument (PPI)**: MPE that also estimates how many notes each instrument plays | Multiplicity inside a family | Multi-channel U-Net; PPI improved MPE ([EURASIP JASMP 2025](https://asmp-eurasipjournals.springeropen.com/articles/10.1186/s13636-025-00398-2)) | Code not found | High (training) | Unison class | Watch. It is the closest learned answer to "how many players", but it is not available |
| **Slot-attention multi-instrument MPE** | Source-wise pitch maps | On URMP, family decomposition improved but stem-level assignment "remains more challenging" ([arXiv 2606.01460](https://arxiv.org/abs/2606.01460)) | CC BY-NC-SA (paper); code not found | High | Per-part F1 on URMP | Watch |
| **Count-supervised training (CountEM)** | Fine-tuning on unaligned brass-band recordings with known scores | Matches weakly supervised methods using note-count histograms only ([arXiv 2511.14250](https://arxiv.org/abs/2511.14250)) | Code not found | High | Held-out chorales and URMP after fine-tuning | Relevant later, if we fine-tune on band recordings with scores |
| **MuScriptor instrument conditioning** | Same-timbre voices | Measured: −23 onset F1 on chorales ([10](10-benchmark-results.md)). Its tokens cannot hold two same-pitch notes on one instrument (#91) | CC BY-NC weights | — | Already measured | No |
| **Odd-partial octave test.** A lower octave note shows its odd partials (1, 3, 5·f), which the upper note cannot supply | Octave-hidden lower notes | Our data: tuba recall is the same with and without an octave above (§2.1) | — | Low (NMF or harmonic-template check on the mix) | Octave-lower class; synthetic octaves via `sounds/` | Not now. Revisit on real band audio, where the basses double constantly |
| **Octave arbitration from a monophonic tracker** ([03:296](03-amt-polyphonic-stem.md)) | Octave errors on single-voice stems | MuScriptor's corrected octave error is already 0.6–2.4% | — | Low | Corrected octave-error rate (§2.3), per voice | After voice separation, per voice |

## 5. How to benchmark overlaps and in-between tones

| Eval set | Unisons | Octaves | Intonation / ornaments | Use |
|---|---|---|---|---|
| `choralebricks-brass4` | Few (22 pairs) | Many (49% of notes) | Tuba out of tune; no ornaments | Octave and partial classes; intonation buckets (score-based pitch) |
| `urmp-brass` | Many (358 pairs, 208 in Arioso) | 28% | Reference pitch rounded from f0, so no snapping truth | Unison class; per-part F1 |
| `slakh-trumpet` | Synthetic, sample-rendered | — | None | Not useful here |
| Synthetic via `sounds/` | Controlled detune and lag | Controlled | Controlled detune | Acoustic unison cues, the detune sweep |
| Synthetic contour set (rec. 3) | — | — | Known scoops, falls, doits, vibrato | Ornament segmentation |
| Mikkel, 60 s hand-labelled | Few (solo + band) | — | Real Antonsen bends | Final check only |

Reporting rules:
- Always report per overlap class and per piece. URMP's unison count is dominated by one piece.
- Report the corrected octave-error rate (§2.3).

## 6. References

**Our docs and code:** [00-summary](00-summary.md), [02](02-amt-multi-instrument.md), [03](03-amt-polyphonic-stem.md), [10](10-benchmark-results.md), `music/src/brasscribe_music/confidence.py`, `sounds/render.py`, `eval/brasscribe_eval/score.py`, `eval/brasscribe_eval/urmp.py`.

**Voice separation and unisons:**
- Chord-level voice separation with converging and diverging voices: https://arxiv.org/abs/2011.03028
- Voice separation as link prediction (IJCAI 2023): https://www.ijcai.org/proceedings/2023/0430.pdf
- Foscarin, Karystinaios, Nakamura, Widmer, *Cluster and Separate* (ISMIR 2024): https://arxiv.org/abs/2407.21030 · code (CC BY 4.0) https://github.com/CPJKU/piano_svsep
- MuScriptor same-instrument limitation: https://github.com/muscriptor/muscriptor/issues/91

**Multi-f0 and overlap:**
- Deep Salience: https://github.com/rabitt/ismir2017-deepsalience (MIT, weights in `predict/weights`) · paper https://archives.ismir.net/ismir2017/paper/000085.pdf
- Cuesta, McFee, Gómez, *Multiple F0 Estimation in Vocal Ensembles* (ISMIR 2020): https://arxiv.org/abs/2009.04172 · https://github.com/helenacuesta/multif0-estimation-polyvocals (MIT)
- Polyphony per instrument (EURASIP JASMP 2025): https://asmp-eurasipjournals.springeropen.com/articles/10.1186/s13636-025-00398-2
- Slot-attention MI-MPE: https://arxiv.org/abs/2606.01460
- CountEM: https://arxiv.org/abs/2511.14250

**Separation loop:**
- Tunturi, Diaz-Guerra, Politis, Virtanen, score-informed separation, URMP: https://arxiv.org/abs/2503.07352

**Pitch contours and ornaments:**
- SwiftF0 (`segment_notes`, `pitch_hold_ms`, cent-resolution `pitch_hz`): https://github.com/lars76/swift-f0
- pYIN note HMM / Tony: https://www.tenor-conference.org/proceedings/2015/04-Mauch-Tony.pdf · https://github.com/sonic-visualiser/tony
- Synthetic Pitch Contours (vibrato, glissando, bends): https://arxiv.org/html/2503.19161
- VioPTT, technique-aware transcription from synthetic data: https://arxiv.org/abs/2509.23759
- MusicXML 4.0 `<notations>`, `<falloff>`, `<scoop>`, `<plop>`: https://www.w3.org/2021/06/musicxml40/musicxml-reference/elements/notations/ · https://www.w3.org/2021/06/musicxml40/musicxml-reference/elements/falloff/ · https://www.w3.org/2021/06/musicxml40/musicxml-reference/elements/scoop · https://www.w3.org/2021/06/musicxml40/musicxml-reference/elements/plop/
- MuseScore import request for these elements: https://musescore.org/en/node/14895
