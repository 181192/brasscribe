# 04 — Rhythm, meter, quantization and structure

Scope: beat/downbeat tracking, tempo and tempo changes, meter/time signature, performance-MIDI → notated rhythm (tuplets, ties, voices), end-to-end audio→score, voice separation for notation, and section/structure segmentation.
**Status (2026-09-29):** desk research, acted on. Beat This! gives the beats (in the engine, and the small model on the phone); quantization, free time and bar-line cleanup are built in-house in `music/` and the Rust core ([10-benchmark-results.md](10-benchmark-results.md)).

Research date: 2026-09-25. Repo/PyPI facts were pulled live with `gh api` / PyPI JSON on that date.

---

## 1. Executive summary

**Beat / downbeat / tempo**
- **PRIMARY: Beat This! (CPJKU, ISMIR 2024), `final0`–`final2` checkpoints, no DBN.**
  - Best openly released offline tracker. It is the baseline every 2025–26 paper and MIREX 2025 compares against ([paper](https://arxiv.org/abs/2407.21658), [repo](https://github.com/CPJKU/beat_this), [MIREX 2025](https://music-ir.org/mirex/wiki/2025:Audio_Beat_Tracking_Results)).
  - MIT for both code and weights. Pure PyTorch, no madmom needed. v1.1.0 released 2026-04-14.
  - Tempo and tempo curves are derived from the beat times.
- **BACKUP: All-In-One (`allin1`).**
  - Gives beats, downbeats, tempo *and* functional sections in one pass. MIT code and weights ([repo](https://github.com/mir-aidj/all-in-one)).
  - Trained only on Harmonix (pop) and needs Demucs stems.
  - Apple Silicon support hinges on an **open** PR that replaces NATTEN with plain PyTorch ([PR #39](https://github.com/mir-aidj/all-in-one/pull/39)).
- **Watch list (ISMIR 2026, Abu Dhabi, 8–12 Nov):**
  - *Masked Diffusion Enables Coherent Beat Tracking*: +9 pts on downbeat continuity over Beat This!. No weights released ([arXiv 2608.04624](https://arxiv.org/abs/2608.04624), [repo](https://github.com/fosfrancesco/md_beat_this)).
  - *Explore This! Beat and Downbeat Tracking From a Learned Tatum Grid*: the CPJKU repo is a placeholder so far ([repo](https://github.com/CPJKU/explore_this)).
  - *Beat This! Live*.
  - Source for all three: the [ISMIR 2026 accepted papers list](https://ismir2026.ismir.net/accepted-papers).

**Meter / time signature**
- No mature open model outputs time signature from audio.
- **Recommendation:** infer beats-per-bar from Beat This! downbeat spacing, per bar, allowing changes. Keep a human-override step.
- madmom's DBN (`beats_per_bar=[…]`) and BeatNet's particle filter are the only packaged "meter" inference. Both need madmom.

**Rhythm quantization (performance MIDI → notated rhythm)**
- **PRIMARY: our own beat-grid-driven quantizer.**
  - Warp note onsets and offsets into *audio* beat time using the Beat This! grid.
  - Snap each note to a per-beat subdivision lattice (24 ticks/beat covers 8ths, 16ths, triplets and 16th-triplets) with a DP/HMM cost over the lattice (Nakamura-style).
  - Then let music21/partitura build ties, tuplets and measures.
  - **Why:** every neural performance-MIDI-to-score model found is piano-only (ASAP/MAESTRO). None consumes an external beat grid out of the box.
- **BACKUP: MuseScore 4 MIDI import (`mscore -M`) or PM2S, to be settled by benchmark.**
  - **MuseScore** is fed MIDI whose tempo map is already locked to our beat grid, and adds tuplet, pickup, swing and voice heuristics.
  - **PM2S** (Liu et al., ISMIR 2022) does neural per-note onset-in-beat and note-value prediction at 24/beat. MIT code, CC-BY-4.0 weights ([repo](https://github.com/cheriell/PM2S), [weights](https://zenodo.org/records/10520196)). Its internals take a beat list, so you can inject our audio beats (see §4.2).
  - PM2S is a candidate *only* because it can use injected beats. On the one MuseScore 4 head-to-head (M2ST paper, ASAP), MuseScore 4 had lower MUSTER errors than PM2S. PM2S's own win was against MuseScore **v3**, on MV2H.
- **Reference: MIDI2ScoreTransformer (Beyer & Dai, ISMIR 2024).**
  - The best published piano PM2S. No LICENSE file, and it needs forked music21 plus a MuseScore binary ([repo](https://github.com/TimFelixBeyer/MIDI2ScoreTransformer)).
  - Use it for piano-reduction experiments, not the brass path.

**Structure / sections**
- **PRIMARY: `allin1`.** Same pass as the beat backup, and its boundaries sit on its own downbeat grid.
- **Challenger: SongFormer.**
  - Better reported numbers than allin1 on its own benchmark.
  - Code CC-BY-4.0. Weights depend on MuQ, which is **CC-BY-NC-4.0** ([repo](https://github.com/ASLP-lab/SongFormer)).
- **Label-free fallback: MSAF.** Repetition-based A/B labels, more honest for marches and hymns ([repo](https://github.com/urinieto/msaf)).
- Both learned models use pop taxonomies (intro, verse, chorus…).

**Biggest risks**
1. **No brass/brass-band beat, meter or structure ground truth exists anywhere.**
   - Training sets are pop, rock, ballroom, jazz and piano. Classical is the weakest genre (RWC Classical 77.1 beat F1 for Beat This!).
2. **Compound meter (6/8 marches) and meter changes in test pieces.**
   - Metrical-level choice is ambiguous. Beat This! lists meter changes as a failure case.
3. **Slow expressive hymns.**
   - The madmom DBN's 55 BPM floor forced double-tempo on 21% of SMC tracks ([arXiv 2605.12287](https://arxiv.org/abs/2605.12287)). Do not enable the DBN with defaults.
4. **madmom is effectively unmaintained on PyPI (0.16.1, 2018).**
   - Git main builds on Python 3.12 only with a Cython pin.
   - It pulls in everything that depends on it: BeatNet, BeatNet+, the allin1 postprocessing, and Beat This! `--dbn`.

---

## 2. Comparison tables

### 2.1 Beat / downbeat / tempo / meter (audio)

| Model | Arch | Latest code activity | Code lic. | Weights lic. | Outputs | Apple Silicon | Py 3.12+ | Headline number (dataset, metric) |
|---|---|---|---|---|---|---|---|---|
| **Beat This!** | Mel → partial (freq/time) RoFormer, ~20 M params, no DBN | v1.1.0 2026-04-14; last commit 2026-05-28 | MIT | MIT | beats, downbeats (tempo derived) | MPS: **reported working** (autocast guard merged, [PR #14](https://github.com/CPJKU/beat_this/pull/14)). The CLI itself only auto-selects CUDA/CPU. C++ and .NET/ONNX community ports exist | yes (PyPI `beat-this` py3 wheel, torch≥2) | GTZAN: beat F1 89.1, downbeat F1 78.3 |
| Masked-diffusion Beat This (md_beat_this) | Beat This! backbone + masked discrete diffusion, 8 steps, ~25 M | repo 2026-08-06 | none stated | **not released** (predictions only) | beats, downbeats | n/a | n/a | GTZAN: beat F1 89.7, downbeat F1 79.5, downbeat CMLt 76.4 |
| **allin1** | Demucs stems → dilated neighbourhood-attention (DiNAT), ~300 K params | last commit 2023-10-10 (PyPI 1.1.0) | MIT | MIT (HF `taejunkim/allinone`) | beats, downbeats, BPM, segments + 10-class labels | NATTEN install fails on macOS ([#11](https://github.com/mir-aidj/all-in-one/issues/11), [#28](https://github.com/mir-aidj/all-in-one/issues/28)). **Open PR #39** reports M5 CPU 11 s / MPS 26 s per song | classifiers stop at 3.11. Not tested | Harmonix 8-fold CV: beat F1 .958, downbeat F1 .915 |
| BeatNet (+BeatNet+) | CRNN + particle filter (online) or madmom DBN (offline) | BeatNet 2026-04-13 (train script); BeatNet+ repo 2026-04 | BeatNet CC-BY-4.0; BeatNet+ **no license** | bundled in repo | beats, downbeats, tempo, meter | unknown | **PyPI 1.1.3 pins `numba==0.54.1` (Python <3.10)**. Git main drops the pin but needs madmom | GTZAN (online): BeatNet+ beat F1 80.62 / downbeat F1 56.51 |
| madmom | RNN/TCN + DBN / HMM bar tracker | PyPI 0.16.1 (2018-11-14). Git main last commit 2024-08-25 | BSD (code) | **CC BY-NC-SA** (models) | beats, downbeats (beats_per_bar set), tempo, onsets | unknown | git main lists 3.9–3.12. Build breaks with Cython ≥3.1 ([#547](https://github.com/CPJKU/madmom/issues/547)) | — (baseline) |
| librosa `beat_track` / `plp` | onset envelope + DP (Ellis 2007) / predominant local pulse | 1.0.0 2026-08-11 | ISC | — | beats, global tempo; PLP for varying tempo | CPU; pure Python | requires ≥3.12 | — (DSP baseline, near-constant tempo assumption) |
| Essentia (`RhythmExtractor2013`, `TempoCNN`, `Meter`) | multi-feature DSP; CNN tempo | PyPI 2.1b6.dev1438 (2026-05-19) | AGPL-3.0 | MTG models CC BY-NC-SA 4.0 | beats, BPM, local tempo; `Meter` is "experimental (not evaluated, do not use)" | macOS arm64 wheels (cp314 latest, cp39–313 in 2025 build) | yes | — |
| Böck & Davies TCN (ISMIR 2020) | multi-task TCN (tempo+beat+downbeat) | 2021-03 | none stated | none stated | beats, downbeats, tempo | unknown | needs madmom | reported in [paper](https://program.ismir2020.net/static/final_papers/223.pdf) |
| Beat Transformer | demixed (Spleeter) + dilated self-attention | 2024-04 | MIT | in repo | beats, downbeats | unknown | unknown | Harmonix CV: beat F1 .954, downbeat F1 .898 (own paper's numbers, extra data/augmentation, as quoted in the allin1 paper's Table 1) |
| KG-ApolloBeats (Kugou, MIREX 2025) | modified Beat This! + BPM and **meter-class** heads, proprietary data | — | closed | closed | beats (+meter, BPM) | — | — | MIREX 2025 Yamaha_Balanced F1 91.97 (held out); SMC 74.15 and GTZAN 92.53 were trained on |

**Comparability warnings**
- The GTZAN numbers use Beat This!'s 993-track protocol; MIREX GTZAN uses 999 tracks.
- The Harmonix numbers are 8-fold CV on pop, so they are not comparable with GTZAN.
- BeatNet/BeatNet+ numbers are *online/causal* and not comparable with offline trackers.
- In MIREX 2025, KG-ApolloBeats was trained on GTZAN *and* SMC, and Beat This! was trained on SMC (asterisked on the results page). Only the private Yamaha sets are held out for everyone.

### 2.2 Quantization / score-level transcription

| Tool | Type | Code lic. | Weights lic. | Instruments trained on | Needs/accepts external beats | Tuplets | Swing | Pickup | Expressive tempo | Voices | Time sig. |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **PM2S** (Liu 2022) | CRNN: beats + per-note onset-in-beat + note value; rule-based MIDI writer | MIT | CC-BY-4.0 (Zenodo) | piano (A-MAPS, CPM, ASAP) | uses its own MIDI beat tracker. Internals take a beat list (§4.2) | 24 ticks/beat, so triplets are representable. Writer snaps to `notes_per_beat=[1,2,3,4,6,8]` | no | no explicit handling | yes, beat-wise tempo | 2 hands only | code: binary 3- vs 4-based, then one of {2/4, 3/4, 4/4, 6/8}. **No changes** |
| **MIDI2ScoreTransformer** (Beyer & Dai 2024) | RoFormer encoder-decoder, 4+4 layers, 512-d; P-MIDI → MusicXML tokens | **no LICENSE file** | ckpt on GH release (390 MB), no licence | piano (ASAP + 58,646 unpaired MuseScore scores) | no (end-to-end from P-MIDI) | 24ths per quarter; tuplets not a primary output | no | implicit via measure-length tokens | yes | voice 1–8, staff, stems | implicit. Paper notes that "assuming a fixed 4 time signature improves results" |
| Wachter et al. T5 quantizer (ICSM 2025) | T5 with beat-based pre-quantization | code not found | not found | piano (ASAP) + instrument-specific fine-tuning | **yes, uses beat annotations** | not stated | not stated | not stated | yes (via beats) | not stated | generalises to unseen TS (claimed) |
| Nakamura/Shibata HMM + heuristics | metrical HMM / merged-output HMM | code not found (on request, [audio2score](https://audio2score.github.io/)) | — | piano; J-pop and classical variants | beat inferred internally | yes (lattice) | no | — | yes | via merged-output HMM | yes |
| **music21 `quantize()`** | nearest-grid snapping in quarterLength | BSD-3 | — | — | **requires input already in beat (quarterLength) time** | default divisors `(4, 3)`: 16ths + 8th-triplets only. No 16th-triplets or quintuplets unless you pass them | no | no | no (fixed grid) | no | no |
| **MuseScore 4 MIDI import** | heuristic importer (C++), CLI via `mscore -M ops.xml` | GPL-3.0 | — | — | `isHumanPerformance` runs the bundled **BeatRoot** beat tracker | `search3plets/5/7/9` on by default, 2-plets off | **`swing` = NONE / SWING / SHUFFLE** | **`searchPickupMeasure` = true** | only when `isHumanPerformance` is set | `maxVoiceCount` 1–4 | user sets numerator {2..21} / denominator |
| Rubato (Tamer et al. 2026) | end-to-end audio → timestamped notation ("InterMo" text) | demo only | not found | piano (MAESTRO, (n)ASAP, PDMX synth) | outputs beats/downbeats itself | — | — | — | yes | — | yes (in barline tokens) |
| TUTTI (ISMIR 2026) | Transformer enc-dec, audio → ABC | MIT (repo has no LICENSE file) | **no weights published** | synthetic multi-instrument; real fine-tunes on piano, string quartet, saxophone | — | not detailed | — | — | — | multi-voice | via ABC |

**Metric warnings**
- MV2H (PM2S, TUTTI), MUSTER / ScoreSimilarity (M2ST) and OMR-NED/CLEWS (Dual Evaluation) are different metrics.
- PM2S's MuseScore comparison used **MuseScore v3**. M2ST used MuseScore 4 as the typesetter for all baselines.

### 2.3 Structure / sections

| Model | Code lic. | Weights lic. | Labels | Reported (dataset, metric) | Apple Silicon |
|---|---|---|---|---|---|
| **allin1** | MIT | MIT | 10 Harmonix classes (start, end, intro, outro, break, bridge, inst, solo, verse, chorus) | Harmonix CV: HR.5F .660, PWF .738, Sf .769 | via open PR #39 |
| **SongFormer** (2025, rev. 2026-04) | CC-BY-4.0 | model card states none. **Inherits MuQ CC-BY-NC-4.0** | 8 (intro, verse, chorus, bridge, inst, outro, silence, pre-chorus) | SongFormBench-HX: ACC .807, HR.5F .70 (allin1 .740/.596 on the same bench) | unknown |
| Stem-Specialized MMoE (ISMIR 2026) | MIT | "code and pretrained models" per README | 7-class taxonomy | not checked (paper not found on arXiv) | unknown |
| MSAF | MIT | — (DSP algorithms) | unsupervised boundaries + repetition clusters (A/B/…) | — | CPU |

---

## 3. Beat / downbeat / tempo / meter — candidate details

### 3.1 Beat This! (PRIMARY)
- **Paper:** Foscarin, Schlüter, Widmer, "Beat This! Accurate beat tracking without DBN postprocessing", ISMIR 2024 ([arXiv 2407.21658](https://arxiv.org/abs/2407.21658)).
- **Architecture** ([paper](https://arxiv.org/abs/2407.21658)):
  - 22.05 kHz mono → 128-bin log-mel (hop 441, i.e. 50 fps), 30 s windows.
  - Partial frequency/time transformers, then a RoFormer. ~20 M parameters, plus a 2 M "small" variant.
  - Shift-tolerant loss and a "sum head" that forces downbeats to coincide with beats.
  - Output is frame-wise beat/downbeat logits with simple peak picking.
- **Training data** ([paper §4.1](https://arxiv.org/abs/2407.21658)): 18 datasets / 4,556 tracks.
  - Simac, SMC, Hainsworth, Ballroom, HJDB, Beatles, Harmonix, RWC ×4 (classical, pop, royalty-free, jazz), TapCorrect, JAAH, Filosax, ASAP, Groove MIDI, GuitarSet, Candombe.
  - GTZAN is held out as the test set.
  - **No brass or wind-band set.** Filosax is solo saxophone. JAAH and RWC Jazz contain brass in jazz contexts.
- **Benchmarks** ([paper Tables 1–2](https://arxiv.org/abs/2407.21658)):

  | Configuration | Beat F1 | Beat CMLt | Beat AMLt | Downbeat F1 | Downbeat CMLt | Downbeat AMLt |
  |---|---|---|---|---|---|---|
  | Beat This! | 89.1 | 79.8 | 89.8 | 78.3 | 67.3 | 79.1 |
  | Beat This! with DBN | 88.1 | 80.5 | 91.1 | 77.4 | 73.3 | 87.8 |
  | Hung et al. | 88.7 | 81.2 | 92.0 | 75.6 | 71.5 | 88.1 |

  - Adding the DBN costs F1 but fixes continuity.
  - 8-fold CV results by genre:
    - Best: Candombe 99.7, Filosax 99.5, Ballroom 97.5.
    - Worst: SMC 62.7, ASAP 76.3, RWC Classical 77.1 beat / 66.3 downbeat, Simac 77.9.
- **MIREX 2025** (as baseline, [results](https://music-ir.org/mirex/wiki/2025:Audio_Beat_Tracking_Results)): GTZAN F1 89.02, SMC 71.81 (trained on SMC), Yamaha_Balanced 90.59, Yamaha_JPop 94.00.
  - On the private held-out Yamaha sets, all three closed submissions beat it:
    - Yamaha_Balanced: KG-ApolloBeats 91.97 and 92.98, BeatU 92.55.
    - Yamaha_JPop: 95.39, 95.87 and 96.58.
  - None of these systems is public, so Beat This! remains the best *released* model.
- **Stated weaknesses:**
  - Non-periodic beats on complex or underrepresented pieces, which lowers CMLt/AMLt.
  - Meter changes, e.g. a 2/4 bar inside 4/4.
  - Classical music ([paper §4.3, §5](https://arxiv.org/abs/2407.21658)).
- **Repo and install** ([repo](https://github.com/CPJKU/beat_this), [releases](https://github.com/CPJKU/beat_this/releases)):
  - Code and weights are MIT ("The code and the published model weights are released under the MIT license"). Training data licences vary.
  - `pip install beat-this` (py3 wheel; deps `torch>=2, torchaudio, einops, rotary-embedding-torch, soxr`).
  - v1.1.0 (2026-04-14) added `weights_only=True` loading and "expanded accelerator compatibility".
  - Checkpoints are downloaded from the JKU cloud: `final0-2` (~78 MB each), `small0-2` (~8 MB), plus `fold0-7` and ablations.
  - `--dbn` needs madmom from git.
- **Apple Silicon:**
  - Autocast crashed on MPS. Fixed by [PR #14](https://github.com/CPJKU/beat_this/pull/14), merged 2026-02-02.
  - The CLI's `--gpu` logic targets CUDA, so use the Python API with `device="mps"` or `"cpu"`.
  - Inference speed and hardware requirements: not reported. Training fits in <8 GiB GPU memory (paper footnote). The model is ~20 M parameters.
- **Ports usable from a Go orchestrator:**
  - C++ port [mosynthkey/beat_this_cpp](https://github.com/mosynthkey/beat_this_cpp), pushed 2026-07-01.
  - .NET/ONNX port [Shirasagi0012/OnnxBeatThis](https://github.com/Shirasagi0012/OnnxBeatThis), 2026-09.
  - Both are community projects and unverified.
- **Brass suitability:**
  - Brass-band textures have no drums (except in some marches), sustained chords, and expressive rubato in hymns and slow melodies.
  - That is closest to the "classical" and "solo instrument" regimes where the model is weakest (≈77 beat F1).
  - Expect good results on marches and pop covers and weaker results on hymns and test-piece slow movements. Plan a correction UI.
- **Tempo:** no separate head. Take the median inter-beat interval for global BPM and the smoothed IBI for the tempo curve.
  - The open [issue #13](https://github.com/CPJKU/beat_this/issues/13) proposes octave correction for BPM.

### 3.2 Masked-diffusion Beat This (ISMIR 2026), plus the other ISMIR 2026 beat papers
- **Masked diffusion.** Foscarin, Korzeniowski, Vogl ([arXiv 2608.04624](https://arxiv.org/abs/2608.04624)).
  - Treats beat/downbeat output as masked discrete diffusion: independent beat/downbeat masking, a balanced unmasking schedule, and peak picking across steps.
  - Targets exactly Beat This!'s weaknesses: consecutive downbeats and erratic tempo.
  - GTZAN, ensemble of 3: beat F1 89.7, CMLt 82.9, AMLt 92.5; downbeat F1 79.5, CMLt 76.4, AMLt 88.5 ([repo README](https://github.com/fosfrancesco/md_beat_this)).
  - Costs 8 forward passes. Long tracks are processed block-autoregressively.
  - **Only predictions and activations are released, not model code or weights** ([repo](https://github.com/fosfrancesco/md_beat_this)).
- **Other ISMIR 2026 accepted beat papers** ([accepted list](https://ismir2026.ismir.net/accepted-papers)):
  - *Explore This! Beat and Downbeat Tracking From a Learned Tatum Grid*. The [CPJKU/explore_this](https://github.com/CPJKU/explore_this) repo (MIT, created 2026-07-31) currently only mirrors the Beat This! README.
  - *Beat This! Live – Online Beat and Downbeat Tracking by Predicting the Future*: preprint and code not found.
  - *FMANet: Efficient and Lightweight Beat Tracking via Fourier Modulation Attention*: preprint and code not found.
  - *GlobalTap: Globally Diverse Beat Tracking Benchmark via Crowdsourced Tapping* ([repo](https://github.com/williambotticelli-wells/GlobalTap)).
  - A tatum-grid model (*Explore This!*) is directly relevant to quantization, because it would give the subdivision grid, not just beats. Re-check in November 2026.
- **"The SMC Blind Spot"**, Ahn, Hwang, Jung ([arXiv 2605.12287](https://arxiv.org/abs/2605.12287); arXiv comment: "prepared for ISMIR 2026". Not on the accepted list as seen).
  - Failure taxonomy of octave errors, continuity errors and complete failure.
  - *"the standard DBN's default minimum tempo of 55 BPM prevents it from inferring the correct tempo for 21% of SMC tracks"*.
  - Recommends multi-hypothesis tempo.
- **BeatFM** ([arXiv 2508.09790](https://arxiv.org/abs/2508.09790)): foundation-model features plus an aggregation module. The authors mark it "Early draft… Do not cite". No code.
- **Beat Tracking as Object Detection** ([arXiv 2510.14391](https://arxiv.org/abs/2510.14391)): FCOS-style detector on a WaveBeat backbone, "competitive" results. No numbers in the abstract.

### 3.3 All-In-One / `allin1` (BACKUP beats + PRIMARY sections)
- **Paper:** Kim & Nam, WASPAA 2023 ([arXiv 2307.16425](https://arxiv.org/abs/2307.16425)).
- **Pipeline:** Demucs source separation → per-stem spectrograms → dilated neighbourhood attention (NATTEN) → joint beat, downbeat, segment-boundary and 10-class label heads.
- **Training:** Harmonix Set only, 8-fold CV. `harmonix-all` is an ensemble of the 8 fold models ([README](https://github.com/mir-aidj/all-in-one)).
- **Harmonix CV** ([paper Table 1](https://arxiv.org/abs/2307.16425)):
  - beat F1 .958 / CMLt .913 / AMLt .964
  - downbeat F1 .915 / CMLt .873 / AMLt .932
  - segment HR.5F .660; label PWF .738, Sf .769
- **Licences:** code MIT (pyproject), weights MIT (HF `taejunkim/allinone` card).
- **Maintenance:** stale. Last commit 2023-10-10, PyPI 1.1.0 (2023-10-10).
  - NATTEN API drift breaks it ([#16](https://github.com/mir-aidj/all-in-one/issues/16), [#30](https://github.com/mir-aidj/all-in-one/issues/30)).
  - macOS installs fail ([#11](https://github.com/mir-aidj/all-in-one/issues/11), [#28](https://github.com/mir-aidj/all-in-one/issues/28)).
  - Postprocessing needs madmom from git (README).
- **Apple Silicon:** [PR #39](https://github.com/mir-aidj/all-in-one/pull/39) (open, 2026-09-20) adds a pure-PyTorch neighbourhood attention.
  - Reported on an **Apple M5** for the structure model alone: NATTEN CPU 148 s vs `natten_torch` CPU 11 s vs MPS 26 s for a 2:24 song.
  - Outputs are identical to NATTEN.
  - Demucs runtime is extra. The maintainer says Demucs dominates runtime ([#17](https://github.com/mir-aidj/all-in-one/issues/17)).
  - README throughput: 10 songs (33 min) in 73 s on a GPU.
- **Brass suitability:**
  - Pop-only training. The model sees Demucs stems, so brass lands in "other" and a near-empty drums stem is out of distribution. Unverified; see open questions.
  - The labels (verse/chorus) don't map to march form (intro, 1st/2nd strain, trio, break-strain) or hymn verses.

### 3.4 BeatNet / BeatNet+
- **BeatNet** ([repo](https://github.com/mjhydri/BeatNet), [arXiv 2108.03576](https://arxiv.org/abs/2108.03576)): CRNN plus a two-stage particle filter for joint beat, downbeat, tempo and **meter**. Also has an offline madmom DBN mode.
  - CC-BY-4.0. Training pipeline added in v1.2.0 (2026-04-13).
  - **PyPI 1.1.3 pins `numba==0.54.1`, which requires Python <3.10** (PyPI metadata). Git main (setup 1.2.0) drops the pin but still requires `madmom`.
- **BeatNet+** ([repo](https://github.com/mjhydri/BeatNet-Plus), [TISMIR](https://transactions.ismir.net/articles/10.5334/tismir.198)): 4-layer LSTM with dual-branch training for non-percussive music and singing voice.
  - GTZAN online: beat F1 80.62 / downbeat F1 56.51 (vs BeatNet 75.44 / 46.69).
  - No LICENSE file. Depends on `madmom>=0.16.1`.
- **Verdict:** the value is the explicit meter inference and the non-percussive adaptation, both relevant to brass. But online-oriented accuracy is far below offline trackers, and the madmom dependency makes it fragile.

### 3.5 madmom (maintenance status)
- **Release status:** PyPI 0.16.1 dated 2018-11-14. Classifiers stop at Python 3.7. Beat This! README: "the current version on PyPI only supports Python<3.10 and numpy<1.20".
- **Git main:** last commit 2024-08-25 ("CI and NumPy compatibility updates", classifiers 3.9–3.12).
  - Building with Cython ≥3.1 fails on `numpy.math` ([#547](https://github.com/CPJKU/madmom/issues/547), open). Workaround: pin `cython<3.1`.
  - Open unmerged PRs for NumPy ≥1.24 ([#557](https://github.com/CPJKU/madmom/issues/557)) and Python 3.14 / NumPy 2.4 ([#559](https://github.com/CPJKU/madmom/issues/559)).
  - "Can we get a new release?" ([#553](https://github.com/CPJKU/madmom/issues/553)) is unanswered.
- **Licences:** code BSD; models CC BY-NC-SA (PyPI licence field).
- **Recommendation:** only as an optional DBN/HMM post-processor in its own venv with pinned Cython. Never a hard dependency.

### 3.6 librosa and Essentia (DSP baselines)
- **librosa 1.0.0** (2026-08-11, requires Python ≥3.12, ISC; [PyPI](https://pypi.org/project/librosa/), [changelog](https://librosa.org/doc/latest/changelog.html)).
  - `beat_track` is the Ellis-2007 dynamic-programming tracker (defaults `start_bpm=120`, `tightness=100`) and assumes roughly constant tempo.
  - `plp` (predominant local pulse) handles varying tempo ([source](https://github.com/librosa/librosa/blob/main/librosa/beat.py)).
  - No downbeats. Useful as a sanity check or tempo prior only.
- **Essentia** (AGPL-3.0; [repo](https://github.com/MTG/essentia)).
  - Beat/tempo algorithms: `RhythmExtractor2013`, `BeatTrackerMultiFeature` and `TempoCNN` (CNN local/global tempo, [models](https://essentia.upf.edu/models.html); MTG models CC BY-NC-SA 4.0).
  - `Meter` estimates time signature from a beatogram, but is documented as *"experimental (not evaluated, do not use)"* ([ref](https://essentia.upf.edu/reference/std_Meter.html)).
  - macOS arm64 wheels on PyPI: cp39–cp313 (2025-07 build) and cp314 (2026-05 build).

### 3.7 TCN-based trackers
- **Böck & Davies, "Deconstruct, Analyse, Reconstruct"** (ISMIR 2020; [paper](https://program.ismir2020.net/static/final_papers/223.pdf), [supplement](https://github.com/superbock/ISMIR2020)): multi-task TCN for tempo, beat and downbeat. This is the lineage behind the allin1 "TCN" baselines.
  - Supplement repo has no licence and was last pushed 2021.
- **Community reimplementation:** [ben-hayes/beat-tracking-tcn](https://github.com/ben-hayes/beat-tracking-tcn), no licence.
- **WaveBeat:** time-domain, GPL-3.0, 2021 ([repo](https://github.com/csteinmetz1/wavebeat)).
- **Beat Transformer:** Spleeter-demixed, MIT, 2024 ([repo](https://github.com/zhaojw1998/Beat-Transformer)).
- All of these are superseded by Beat This! on reported numbers. Not recommended.

### 3.8 Meter / time-signature detection — state of the art
- **No open, maintained audio model outputs an explicit time signature.**
- **Closest options:**
  - **Downbeat trackers + counting:** Beat This!, allin1, madmom `DBNDownBeatTrackingProcessor(beats_per_bar=[…])`.
  - **BeatNet's particle filter:** explicit meter state.
  - **KG-ApolloBeats:** has a meter-classification head but is closed ([MIREX abstract](https://futuremirex.com/portal/wp-content/uploads/2025/audio-beat-tracking/KG-ApolloBeats.pdf)).
- **Training-data bias:** *Skip That Beat* (Morais, McFee, Fuentes, LAMIR 2025; [arXiv 2502.12972](https://arxiv.org/abs/2502.12972)) shows trackers are 4/4-biased.
  - It proposes deleting beats from 4/4 annotations to synthesise 2/4 and 3/4, which improves downbeats in those meters.
  - Relevant if we ever fine-tune on marches (2/4, 6/8).
- **Symbolic side:** PM2S has a time-signature CNN on MIDI (binary 3- vs 4-based since Dec 2023, per [constants.py](https://github.com/cheriell/PM2S/blob/main/pm2s/constants.py)).
- **Recommended approach:** from Beat This! beats and downbeats, compute beats per bar per measure.
  - Choose simple vs compound by testing whether onsets inside a beat group in 2s or 3s. That subdivision evidence comes from the transcribed notes.
  - Allow bar-level changes.
  - Surface low-confidence bars for user correction.

### 3.9 MIREX
- **MIREX 2025 Audio Beat Tracking** ([results](https://music-ir.org/mirex/wiki/2025:Audio_Beat_Tracking_Results)): baselines were QM (CD1) and Beat This!; submissions were KG-ApolloBeats ×2 and BeatU (Yamaha).
  - Best per test set:

    | Dataset | Best system | F1 |
    |---|---|---|
    | GTZAN | Beat This! | 89.02 (ApolloBeats 92.53 was trained on GTZAN) |
    | SMC | — | none held out (ApolloBeats 74.15 and Beat This! 71.81 were both trained on SMC) |
    | Yamaha_Balanced | KG-ApolloBeats 2 | 92.98 |
    | Yamaha_JPop | BeatU | 96.58 |

  - Neither submission released code.
- **MIREX 2026** ([home](https://music-ir.org/mirex/wiki/MIREX_HOME)): runs Audio Beat Tracking, Audio Downbeat Estimation, Music Structure Analysis and a new **Audio-to-Score Transcription** task. Results are due ~2026-10-15, so they are **not yet available**.
  - One public A2S submission: YourMT3 fine-tuned on quartets → voice assignment → **kern ([repo](https://github.com/ld04080106/Quartets_a2s_mirex26), MIT).

---

## 4. Rhythm quantization / score-level transcription — candidate details

### 4.1 Framing for brasscribe
- **Upstream:** stems → note transcription (see the transcription reports) gives *performance* notes in seconds.
- **Goal:** turn those into bars, beats and note values with tuplets, ties and voices, and eventually per-instrument parts.
- **Key design decision: quantize against the *audio* beat grid** from Beat This! run on the full mix, not against a beat grid re-inferred from each transcribed part.
  - The mix carries far more rhythmic evidence than a single transcribed cornet line.
  - All parts then share one measure map.
  - This rules out end-to-end PM2S models that re-infer beats from piano MIDI.

### 4.2 PM2S — Liu, Kong, Morfi, Benetos (ISMIR 2022, best paper)
- **Links:** [paper](https://archives.ismir.net/ismir2022/paper/000047.pdf), [repo](https://github.com/cheriell/PM2S) (MIT, last commit 2024-10-10), [weights](https://zenodo.org/records/10520196) (CC-BY-4.0, 2024-01-16).
- **Architecture:** CRNN on note sequences.
  - Predicts per note: is-beat, is-downbeat, musical onset within the beat, note value, hand part.
  - Separate models for key signature and time signature.
  - Constants: `N_per_beat = 24`, max note value 4 beats, `ticks_per_beat = 240`, BPM range 40–240 ([constants.py](https://github.com/cheriell/PM2S/blob/main/pm2s/constants.py)).
  - The MIDI writer snaps to `notes_per_beat=[1,2,3,4,6,8]` ([pm2s.py](https://github.com/cheriell/PM2S/blob/main/pm2s/pm2s.py)).
- **Results** (ASAP-derived test set, MV2H; [paper Table 5](https://archives.ismir.net/ismir2022/paper/000047.pdf)):

  | System | Overall MV2H F | Metrical-alignment Fme |
  |---|---|---|
  | PM2S | 87.9 | 61.7 |
  | Finale v27 | 65.0 | 9.9 |
  | MuseScore v3 | 54.0 | 15.3 |

  - The authors say Fme is "far from satisfactory" (double/half-tempo errors, missed beats).
  - MuseScore and Finale fail because they quantize to one constant global tempo.
- **Code behaviour vs paper:** `get_score_features` assumes **no time-signature change**. It picks from 2/4, 3/4, 4/4, 6/8 by beats-per-downbeat ratio, then forces downbeats to every n-th beat.
- **External beats:** `beats` flow into `prepare_time2tick`, so injecting Beat This! beats is a small code change. Not a supported API.
- **Inference speed / hardware:** not reported (small CRNN, CPU-class).
- **Brass suitability:** trained on piano only. Monophonic brass lines are a simpler input, but no evidence exists either way.

### 4.3 MIDI2ScoreTransformer — Beyer & Dai (ISMIR 2024)
- **Links:** [arXiv 2410.00210](https://arxiv.org/abs/2410.00210), [repo](https://github.com/TimFelixBeyer/MIDI2ScoreTransformer). Last commit 2024-10-11. v0.0.1 ckpt 390 MB. **No LICENSE file** (all rights reserved by default; fine for private use only).
- **Architecture:** RoFormer encoder-decoder, 4 layers, 8 heads, 512-d.
  - Input: P-MIDI (pitch, onset, duration, velocity).
  - Output: onset and duration in 24ths, measure length, voice (1–8), staff, stem, grace, trill, staccato, accidentals.
  - The 24th resolution "represents 98.6% of notes in ASAP" vs 85.4% for powers of 2.
  - Trained on ASAP (967 pieces) plus 58,646 unpaired MuseScore scores.
- **Results** (ASAP test, MUSTER Eonset / Eoffset / Eavg; [paper Table 3](https://arxiv.org/abs/2410.00210)):

  | System | Eonset | Eoffset | Eavg |
  |---|---|---|---|
  | M2ST | 15.55 | 23.84 | 11.30 |
  | HMM + heuristics (classical, Shibata et al.) | 22.58 | 29.84 | 13.95 |
  | Finale | 31.85 | 45.34 | 20.64 |
  | MuseScore 4 | 47.90 | 49.44 | 23.35 |
  | PM2S ("Neural Beat Tracking (improved)") | 68.28 | 54.11 | 28.04 |

  - Lower is better. † on the HMM rows: some test pieces appeared in training data for subcomponents (optimistic).
  - The PM2S row is the M2ST authors' improved reimplementation of ref. [19] (Liu et al.). Note that MuseScore 4 beats it here.
  - Inference speed: not reported.
- **Dependencies:** a forked music21, a forked ScoreTransformer, a MUSTER fork, and a MuseScore binary for typesetting ([README](https://github.com/TimFelixBeyer/MIDI2ScoreTransformer)).
- **Independent check:** the *Dual Evaluation* study (TISMIR 2026) ran 24 pipelines, audio-to-MIDI × {music21, MuseScore, M2ST} ([arXiv 2608.04511](https://arxiv.org/abs/2608.04511)). Lower OMR-NED is better.

  | Pipeline | OMR-NED (notation) | CLEWS (playback) |
  |---|---|---|
  | Transkun + M2ST | 86.61 (best notation of the pipelines) | 0.52 |
  | Transkun + MuseScore | 92.61 | 0.82 |
  | Transkun + music21 | 96.60 | 0.27 |

  - M2ST gives the best notation but poor playback similarity; MuseScore is the reverse.
  - End-to-end Rubato beat both (OMR-NED 72.30).
- **Brass suitability:** piano-only, classical. Could be useful for a piano-reduction output but not for brass parts.

### 4.4 Other performance-MIDI quantizers
- **Wachter, Murgul, Heizmann** (ICSM 2025; [arXiv 2604.22290](https://arxiv.org/abs/2604.22290)): T5 with **beat-based pre-quantization** (takes beat annotations).
  - ASAP onset F1 97.3%, note-value accuracy 83.3%.
  - Claims generalisation to unseen time signatures and instrument-specific fine-tuning.
  - Code not found. Architecturally the closest match to our "external beat grid" design.
- **Murgul & Heizmann** (SMC 2025; [arXiv 2507.00466](https://arxiv.org/abs/2507.00466)): beat/downbeat tracking *in performance MIDI*, trained on A-MAPS, ASAP, GuitarSet and Leduc. Code not found.
- **Nakamura et al. HMMs:** merged-output HMM for polyphonic rhythm transcription (TASLP 2017) and metrical HMMs ([publications](https://eita-nakamura.github.io/eita-nakamura_publications.html); [SMC 2016 PDF](https://eita-nakamura.github.io/articles/Nakamura_etal_RhythmTranscriptionOfPolyphonicMIDIPerformances_SMC2016.pdf)).
  - The Shibata/Nakamura/Yoshii audio-to-score system ([arXiv 2008.12710](https://arxiv.org/abs/2008.12710)) is the "HMM + heuristics" baseline in M2ST.
  - **Code not found.** The project page offers data only and says to contact the author ([audio2score](https://audio2score.github.io/)).
  - The *method* (HMM/DP over a metrical lattice with note-value priors) is well documented and is what we would reimplement.

### 4.5 music21 and MuseScore import heuristics
- **music21** 10.5.0 (2026-06-17, BSD-3, Python ≥3.11; [repo](https://github.com/cuthbertLab/music21)). `Stream.quantize(quarterLengthDivisors=…)`:
  - Default `defaults.quantizationQuarterLengthDivisors = (4, 3)`: 16ths plus 8th-note triplets ([defaults.py](https://github.com/cuthbertLab/music21/blob/master/music21/defaults.py), [stream/base.py](https://github.com/cuthbertLab/music21/blob/master/music21/stream/base.py)).
  - Nearest-grid snapping with no tempo tracking, so input must already be in beat time.
  - Its real value is *after* quantization: `makeMeasures`, `makeTies`, tuplet brackets, beaming, and MusicXML export.
  - **partitura** (Apache-2.0, 1.9.0, 2026-05-25; [repo](https://github.com/CPJKU/partitura)) is the alternative score model and is used by CPJKU tools.
- **MuseScore 4.7.5** (2026-09-08, GPL-3.0). The MIDI importer in `src/importexport/midi/internal/midiimport/` ([source](https://github.com/musescore/MuseScore/tree/main/src/importexport/midi/internal/midiimport)) exposes these options ([importmidi_operations.h](https://github.com/musescore/MuseScore/blob/main/src/importexport/midi/internal/midiimport/importmidi_operations.h), [importmidi_operation.h](https://github.com/musescore/MuseScore/blob/main/src/importexport/midi/internal/midiimport/importmidi_operation.h)):
  - `quantValue` (1/4 … 1/1024)
  - `searchTuplets` with `search3plets/4/5/7/9` on by default; `search2plets` off
  - `useDots`, `simplifyDurations`
  - `maxVoiceCount` (1–4, default 4)
  - **`swing` (NONE / SWING / SHUFFLE)**
  - **`searchPickupMeasure` (default true)**
  - **`isHumanPerformance`**, which runs the bundled BeatRoot tracker (`thirdparty/beatroot`)
  - time signature numerator/denominator choices
- **Headless use:** `mscore -M <ops file>` passes a MIDI import operations file ([CLI docs](https://handbook.musescore.org/appendix/command-line-usage.md)).
- **Verdict:** best off-the-shelf *notation cleanup* (tuplets, swing display, pickup detection, voices) if fed MIDI whose tempo map already matches our beat grid (constant ticks per beat). Its own tempo inference is the weak part (PM2S Table 5; M2ST Table 3).

### 4.6 End-to-end audio → score (2024–26)
- **Rubato** (Tamer, Ebert, Yang, Smith; [arXiv 2605.24291](https://arxiv.org/abs/2605.24291)): piano audio → timestamped notation text ("InterMo"), with dialects for beats/downbeats.
  - Trained on MAESTRO, (n)ASAP and PDMX-synth.
  - Best OMR-NED in the Dual Evaluation study.
  - Demo only ([site](https://nctamer.github.io/rubato-transcription)); code and weights not found. Piano-only.
- **TUTTI** (ISMIR 2026; [arXiv 2609.00640](https://arxiv.org/abs/2609.00640), [repo](https://github.com/a-musiclover/TUTTI)): Transformer encoder-decoder, audio → ABC.
  - Pre-trained on 363,610 *synthetic* multi-instrument audio/score pairs (TuttiCorpus, CC BY-NC 4.0 on [HF](https://huggingface.co/datasets/pzzzzz/TuttiCorpus)).
  - Fine-tuned on piano (ASAP), string quartet and saxophone.
  - Reports MV2H 95.6 on quartets and ~85 on saxophone, as reported.
  - The top-5 instruments listed are piano and strings; brass counts are not stated.
  - README says MIT but the repo has no LICENSE file. **No pretrained weights published.**
  - The most brass-relevant A2S work, because of synthetic multi-instrument pretraining plus cross-instrument transfer, but it would need our own training.
- **Zeng, He, Wang** (IJCAI 2024; [arXiv 2405.13527](https://arxiv.org/abs/2405.13527)): hierarchical-decoder piano A2S to **kern. Code not found.
- **ISMIR 2026:** *On the use of Pre-trained Audio Encoders for Audio-to-Score Music Transcription* ([repo](https://github.com/ahidalgocenteno/a2s-pretrained), [accepted list](https://ismir2026.ismir.net/accepted-papers)). Not assessed in depth.
- **Verdict:** end-to-end A2S is improving fast but is piano-, string- and sax-centric with no released multi-instrument weights. Not viable for brass in 2026 without training. Keep the modular path.

### 4.7 Voice separation for notation
- **Cluster and Separate** (Foscarin, Karystinaios, Nakamura, Widmer, ISMIR 2024; [arXiv 2407.21030](https://arxiv.org/abs/2407.21030), [repo](https://github.com/CPJKU/piano_svsep), MIT, pretrained models included).
  - A GNN clusters chord notes and links voices. Handles homophonic and cross-staff voices. Piano, on quantized input.
- **Karystinaios et al.:** voice separation as link prediction (IJCAI 2023; [arXiv 2304.14848](https://arxiv.org/abs/2304.14848)).
- **McLeod:** voice-splitting (Java, MIT, 2020; [repo](https://github.com/apmcleod/voice-splitting)). Also the MV2H metric ([repo](https://github.com/apmcleod/MV2H), MIT, active 2026-07).
- **ISMIR 2026:** *A First Benchmark and Metric for Evaluating Polyphony in Symbolic Music using Voice Independence* ([accepted list](https://ismir2026.ismir.net/accepted-papers)).
- **Relevance:** mostly downstream, i.e. splitting a transcribed "brass/other" polyphonic stem into cornet, horn and baritone lines, which the arrangement stage may do anyway. None is trained on brass.

### 4.8 Swing, triplets, pickups, expressive tempo — who handles what
- **Swing:**
  - No neural beat tracker or quantizer found models swing explicitly.
  - Beat This! is trained on swing material (Filosax, JAAH, RWC Jazz), so beats are fine. Eighth-note swing is a quantization/notation choice.
  - MuseScore's import `swing` option is the only explicit handling found.
  - Recommendation: estimate the swing ratio from onset positions inside beats (swingogram idea, [JNMR 2017](https://www.tandfonline.com/doi/full/10.1080/09298215.2017.1367405)). If it is consistently >1.3, notate straight 8ths with a "Swing" marking instead of triplets.
- **Triplets:**
  - 24 ticks/beat grids (PM2S, M2ST) and music21 `(4,3)` represent 8th-triplets.
  - Add 6 and 12 subdivisions for 16th-triplets.
  - MuseScore detects 3/5/7/9-plets.
- **Pickups:**
  - MuseScore `searchPickupMeasure`.
  - Otherwise derive from the first downbeat position in the Beat This! output (beats before the first downbeat form an anacrusis).
- **Expressive tempo:**
  - Beat This! (no tempo prior, no DBN) follows rubato best in principle.
  - The DBN smooths tempo and has a 55 BPM floor.
  - PM2S, M2ST and Rubato were trained on expressive piano.
  - music21 `quantize` and MuseScore without `isHumanPerformance` assume constant tempo.

---

## 5. Structure / section segmentation — details

- **allin1:** see §3.3.
  - Harmonix CV segment HR.5F .660, label PWF .738 ([paper](https://arxiv.org/abs/2307.16425)).
  - Segments align with its downbeats. Pop labels.
- **SongFormer** (Hao, Yuan et al.; [arXiv 2510.02797](https://arxiv.org/abs/2510.02797), rev. 2026-04; [repo](https://github.com/ASLP-lab/SongFormer), last commit 2026-05-14; [HF](https://huggingface.co/ASLP-lab/SongFormer)).
  - Fuses short- and long-window **MuQ** and **MusicFM** SSL features with a learned source embedding, so it can train on heterogeneous labels.
  - Datasets: SongFormDB (14k songs) and SongFormBench (300 songs).
  - Reported on SongFormBench-HarmonixSet ([README](https://github.com/ASLP-lab/SongFormer)):

    | Model | ACC | HR.5F | HR3F |
    |---|---|---|---|
    | SongFormer | .807 | .696 | .780 |
    | allin1 | .740 | .596 | .730 |

  - These are the authors' own benchmark and runs.
  - Code CC-BY-4.0. SongFormer weights licence not stated. The MuQ dependency (`OpenMuQ/MuQ-large-msd-iter`) is **CC-BY-NC-4.0** (HF card).
  - Setup: Python 3.10 conda env; downloads MuQ and MusicFM checkpoints. Speed claimed as "2–4 seconds" per song on a single GPU (README). Apple Silicon unknown.
- **Stem-Specialized MMoE** (ISMIR 2026; [repo](https://github.com/aneeka657/MMOE_MSA), MIT): four stem experts (vocals, drums, bass, other, each + mix) with task-specific gates.
  - Trained on Beatles, SALAMI and RWC with a 7-class taxonomy.
  - Relevant because it can learn to down-weight an empty drum stem. Numbers not checked.
- **MSAF** ([repo](https://github.com/urinieto/msaf), MIT; last commit 2026-03-04; PyPI 0.1.80 from 2023): framework of classic boundary algorithms (foote, sf, olda, cnmf, scluster…) plus unsupervised labelling.
  - Old PyPI release. Setup lists `enum34`, so install from git.
  - Label-free A/B/C clustering suits marches and hymns, where "verse/chorus" is meaningless.
- **Brass-band caveat:** march form, hymn verses, test-piece movements and cornet solos are absent from all MSA training sets. Plan to use learned *boundaries*, cluster sections by repetition for *labels*, and let the user rename.

---

## 6. Open questions only benchmarking can settle

1. **Beat This! on brass band:** beat/downbeat F1 on ~20 hand-annotated brass-band recordings (marches, hymns, test-piece excerpts, pop covers). Compare Beat This! with and without DBN (DBN with `min_bpm` lowered to ~30) against allin1.
2. **Compound meter:** in 6/8 marches, does Beat This! tick dotted quarters (musically correct) or eighths? Check the annotation convention in [beat_this_annotations](https://github.com/CPJKU/beat_this_annotations) for 6/8 material.
3. **Meter changes:** how often does per-bar beat counting from Beat This! downbeats produce spurious 3/4 or 5/4 bars? Is a light HMM smoothing over bar lengths needed?
4. **allin1 with no drums:** does allin1 degrade when the Demucs drums stem is near-silent (hymns)? Does PR #39's MPS path match CUDA/NATTEN output on such material?
5. **Beat grid source:** quantize against the mix-level beat grid vs a per-stem grid. Which gives better MV2H on synthetic brass renders, i.e. MIDI → brass samples → transcription → quantize?
6. **Quantizer choice:** our DP-lattice quantizer vs PM2S (with injected beats) vs MuseScore `-M` import (tempo map pre-aligned) on monophonic brass lines, including swung and triplet passages.
7. **Structure:** SongFormer vs allin1 vs MSAF boundary HR3F on brass-band pieces; label usefulness judged by hand.
8. **Watch list:** re-evaluate in Nov 2026 when *Explore This!* (tatum grid), *Beat This! Live*, masked-diffusion weights, TUTTI weights and MIREX 2026 A2S/downbeat results may be released.

---

## 7. References

**Beat / tempo / meter**
- Beat This! paper: https://arxiv.org/abs/2407.21658 · repo: https://github.com/CPJKU/beat_this · releases: https://github.com/CPJKU/beat_this/releases · MPS PR: https://github.com/CPJKU/beat_this/pull/14 · BPM issue: https://github.com/CPJKU/beat_this/issues/13 · annotations: https://github.com/CPJKU/beat_this_annotations
- Beat This! ports: https://github.com/mosynthkey/beat_this_cpp · https://github.com/Shirasagi0012/OnnxBeatThis
- Masked diffusion (ISMIR 2026): https://arxiv.org/abs/2608.04624 · https://github.com/fosfrancesco/md_beat_this
- Explore This! placeholder repo: https://github.com/CPJKU/explore_this
- ISMIR 2026 accepted papers: https://ismir2026.ismir.net/accepted-papers
- SMC Blind Spot: https://arxiv.org/abs/2605.12287
- BeatFM: https://arxiv.org/abs/2508.09790
- Beat tracking as object detection: https://arxiv.org/abs/2510.14391
- GlobalTap: https://github.com/williambotticelli-wells/GlobalTap
- All-In-One paper: https://arxiv.org/abs/2307.16425 · repo: https://github.com/mir-aidj/all-in-one · MPS PR #39: https://github.com/mir-aidj/all-in-one/pull/39 · issues #11/#17/#28/#30
- BeatNet: https://github.com/mjhydri/BeatNet · https://arxiv.org/abs/2108.03576 · BeatNet+: https://github.com/mjhydri/BeatNet-Plus · https://transactions.ismir.net/articles/10.5334/tismir.198
- madmom: https://github.com/CPJKU/madmom · issues #547, #553, #557, #559 · PyPI https://pypi.org/project/madmom/
- librosa: https://pypi.org/project/librosa/ · https://librosa.org/doc/latest/changelog.html · https://github.com/librosa/librosa/blob/main/librosa/beat.py
- Essentia: https://github.com/MTG/essentia · https://essentia.upf.edu/models.html · https://essentia.upf.edu/reference/std_Meter.html
- Böck & Davies ISMIR 2020: https://program.ismir2020.net/static/final_papers/223.pdf · https://github.com/superbock/ISMIR2020
- WaveBeat: https://github.com/csteinmetz1/wavebeat · Beat Transformer: https://github.com/zhaojw1998/Beat-Transformer · TCN reimpl: https://github.com/ben-hayes/beat-tracking-tcn
- Skip That Beat: https://arxiv.org/abs/2502.12972
- MIREX 2025 beat results: https://music-ir.org/mirex/wiki/2025:Audio_Beat_Tracking_Results · KG-ApolloBeats abstract: https://futuremirex.com/portal/wp-content/uploads/2025/audio-beat-tracking/KG-ApolloBeats.pdf · MIREX 2026: https://music-ir.org/mirex/wiki/MIREX_HOME · MIREX 2026 A2S entry: https://github.com/ld04080106/Quartets_a2s_mirex26

**Quantization / score**
- PM2S paper: https://archives.ismir.net/ismir2022/paper/000047.pdf · repo: https://github.com/cheriell/PM2S · weights: https://zenodo.org/records/10520196
- MIDI2ScoreTransformer: https://arxiv.org/abs/2410.00210 · https://github.com/TimFelixBeyer/MIDI2ScoreTransformer
- Wachter et al. T5 quantizer: https://arxiv.org/abs/2604.22290
- Murgul & Heizmann MIDI beat tracking: https://arxiv.org/abs/2507.00466
- Nakamura publications: https://eita-nakamura.github.io/eita-nakamura_publications.html · SMC 2016: https://eita-nakamura.github.io/articles/Nakamura_etal_RhythmTranscriptionOfPolyphonicMIDIPerformances_SMC2016.pdf · Shibata et al.: https://arxiv.org/abs/2008.12710 · audio2score: https://audio2score.github.io/
- music21: https://github.com/cuthbertLab/music21 · defaults.py / stream/base.py (quantize)
- partitura: https://github.com/CPJKU/partitura
- MuseScore MIDI import source: https://github.com/musescore/MuseScore/tree/main/src/importexport/midi/internal/midiimport · CLI: https://handbook.musescore.org/appendix/command-line-usage.md
- Dual Evaluation for Music Transcription (TISMIR 2026): https://arxiv.org/abs/2608.04511
- Rubato: https://arxiv.org/abs/2605.24291 · demo https://nctamer.github.io/rubato-transcription
- TUTTI: https://arxiv.org/abs/2609.00640 · https://github.com/a-musiclover/TUTTI · https://huggingface.co/datasets/pzzzzz/TuttiCorpus
- Zeng et al. hierarchical A2S: https://arxiv.org/abs/2405.13527
- Pre-trained encoders for A2S (ISMIR 2026): https://github.com/ahidalgocenteno/a2s-pretrained
- Cluster and Separate: https://arxiv.org/abs/2407.21030 · https://github.com/CPJKU/piano_svsep
- Voice separation as link prediction: https://arxiv.org/abs/2304.14848
- McLeod voice-splitting: https://github.com/apmcleod/voice-splitting · MV2H: https://github.com/apmcleod/MV2H
- Swingogram: https://www.tandfonline.com/doi/full/10.1080/09298215.2017.1367405

**Structure**
- SongFormer: https://arxiv.org/abs/2510.02797 · https://github.com/ASLP-lab/SongFormer · https://huggingface.co/ASLP-lab/SongFormer · MuQ card: https://huggingface.co/OpenMuQ/MuQ-large-msd-iter
- Stem-Specialized MMoE: https://github.com/aneeka657/MMOE_MSA
- MSAF: https://github.com/urinieto/msaf
