# 03 — Per-stem AMT (instrument-agnostic polyphonic) and monophonic pitch tracking

Scope: models that turn **one separated stem at a time** into notes, whether the stem is polyphonic (a brass section, piano, guitar) or monophonic (a melody, bass line, single brass voice, or vocal). Also: how per-stem outputs can be fused. Multi-instrument end-to-end models such as MT3, YourMT3+ and MuScriptor belong to a separate report. They appear here only when they are a realistic choice for **per-stem** use.

Research date: 2026-09-25. Every number below is quoted from the linked source. Numbers from different papers are **not comparable** unless this report says they are.

---

## 1. Executive summary

**The field changed in 2026.** Two releases matter:
- **MuScriptor** (Kyutai/Mirelo, ISMIR 2026) is an open-weight 103M–1.4B decoder-only transformer. It is trained on about 11k hours of real audio and has explicit `trumpet / trombone / tuba / french_horn / brass_section` classes ([paper](https://arxiv.org/abs/2607.08168), [repo](https://github.com/muscriptor/muscriptor)).
- **Harmonica** (BandLab, Sep 2026) compares 11 AMT models (8 retrained, 3 released checkpoints) under one **instrument-agnostic** protocol ([arXiv 2609.04640](https://arxiv.org/abs/2609.04640)). Its own weights are **not released**, so it serves here only as the evaluation reference.

**Basic Pitch** (2022) is still the only small, permissively licensed, instrument-agnostic note model with **pitch-bend output** and an official CoreML path. It is clearly beaten on accuracy.

### Picks

| Use | PRIMARY | BACKUP | Why |
|---|---|---|---|
| **Polyphonic brass stem** (section chords after separation) | **MuScriptor medium/large**, conditioned on the instrument (`brass_section` or `trumpet`…) | **Basic Pitch** (CoreML) | MuScriptor is the strongest model with public weights on real audio. Weights are CC BY-NC (fine for personal use), and MPS is claimed. Basic Pitch is Apache-2.0, tiny and CoreML-native, and it gives bends and a raw multipitch posteriorgram for fusion. Run both and fuse them (§7). |
| **Monophonic line** (lead, a single cornet or bass part) | **SwiftF0** → note segmentation | **torchcrepe (full, Viterbi)** + **CREPE Notes** segmentation | SwiftF0 has the best pitch F1 on URMP (orchestral instruments incl. brass) in pitch-benchmark v2, with low octave-error rates. It is MIT and ONNX-only. It **cannot see below 46.9 Hz (F♯1)**, so the lowest Eb/BBb bass notes need CREPE, RMVPE or FCPE, whose ranges reach about 32 Hz. BBb pedal Bb0 (≈29 Hz) is below all of those; only Basic Pitch (27.5 Hz) and PESTO (27.5 Hz VQT) nominally cover it. |
| **Vocal stem → notes** | **GAME** (openvpi, 2026, MIT) | **ROSVOT** (ACL'24, MIT) | Both are built for singing voice and robust to noisy or separated vocals. GAME is the successor to SOME. |
| **Piano stem** (if present in source) | **Transkun V2** (MIT, weights shipped) | **Kong high-res** (weights CC-BY-4.0) | Both are strong piano-only checkpoints. Do not use them on brass (§5). |

### Biggest risks
1. **No model is trained or evaluated on brass-band audio.** The closest proxies are URMP stems (single trumpet, horn, trombone and tuba players), PHENICX-Anechoic section stems (horn and trumpet sections) and Slakh "brass" (synthesized). The 2025 AMT Challenge had trombone as its only brass instrument ([arXiv 2603.27528](https://arxiv.org/html/2603.27528v1)).
2. **Close-voiced chords within one timbre are the weak point everywhere.** Polyphony accuracy collapses as voices are added: MIROS falls from 0.72 to 0.44 F1 going from one to three instruments ([AMT Challenge](https://arxiv.org/html/2603.27528v1)). MuScriptor **cannot represent two notes of the same pitch on the same instrument**, so unisons collapse ([model card](https://huggingface.co/MuScriptor/muscriptor-medium)).
3. **MuScriptor was trained on mixes, and isolated stems are out of distribution for it.** In Harmonica's table its released checkpoint scores Slakh-stem OnP .457 and URMP-stem .711, only slightly above Basic Pitch (.394 / .687) ([Harmonica Table 1](https://arxiv.org/html/2609.04640)). It may do better on the original mix with instrument conditioning than on a separated stem. Only benchmarking can settle this.
4. **No published work on note-level fusion of AMT models was found** (§7). Any consensus layer is an untested design.
5. **Basic Pitch fails to install on macOS arm64 with Python 3.12** ([issue #203](https://github.com/spotify/basic-pitch/issues/203); fix [PR #204](https://github.com/spotify/basic-pitch/pull/204) still open). Pin its subprocess venv to Python 3.10, which the README documents for M1; 3.11 is unverified.

---

## 2. Comparison table

**Column meanings:**
- **Public weights trained on**: what the downloadable checkpoint actually learned from. Harmonica's numbers for Transkun, hFT and others come from checkpoints **the Harmonica authors retrained** instrument-agnostic, which are not downloadable. The public checkpoints of those models are piano-only.
- **URMP-stem / Slakh-stem OnP**: note F1 (onset + pitch, 50 ms) from [Harmonica Table 1](https://arxiv.org/html/2609.04640), measured on an RTX 4090.
  - ⚑ = released checkpoint whose training data overlaps the test set. The Harmonica authors flag Basic Pitch and MT3 this way, and it favors them.
  - R = architecture retrained by the Harmonica authors; the public weights differ.

| Model | Type | Code lic. | Weights lic. | Public weights trained on | Bends / continuous f0 | URMP-stem OnP | Slakh-stem OnP | Apple Silicon | Last activity |
|---|---|---|---|---|---|---|---|---|---|
| **MuScriptor** (small 103M / med 307M / large 1.4B) | poly, multi-inst, instrument-conditioned | MIT | **CC BY-NC 4.0** (HF gated) | synth pretrain + ~11k h real + RL | no (MIDI notes, no velocity) | .711 (med, released) | .457 (med, released) | **claimed** (MPS); **reported** ggml/Metal in NeuralNote v2 (M1 Pro ~1.5× RT for medium); counter-report [NeuralNote #163](https://github.com/DamRsn/NeuralNote/issues/163) app fails to start on macOS Tahoe 26.0.1 | 2026-09-04 |
| **Basic Pitch** (16.8K) | poly, instrument-agnostic | Apache-2.0 | Apache-2.0 (in repo) | GuitarSet, iKala, MAESTRO, MedleyDB-Pitch, Slakh | **yes**, per-note pitch bends (~33-cent bins) | .687 ⚑ | .394 ⚑ | **claimed**: CoreML default on macOS; py3.12 install broken (#203) | 2025-11-13 (release v0.4.0 2024-08) |
| Harmonica (26K–15.1M) | poly, instrument-agnostic | **not released** | **not released** | 8 datasets, 1,385 h | no | .925 (x-large) | .918 (x-large) | n/a (iPhone deployment reported) | paper 2026-09-04 |
| MT3 | poly, multi-inst | Apache-2.0 | Apache-2.0 | not verified from primary source (see MT3 paper) | no | .829 ⚑ | .900 ⚑ | unknown (JAX/T5X) | 2026-09-15 |
| YourMT3+ | poly, multi-inst | GPL-3.0 | not found (HF Space demo only verified) | multi-dataset + stem augmentation | no | .926 (R) | .896 (R) | unknown | 2024-11-29 |
| Transkun V2 | poly, piano | MIT | MIT (in pip) | MAESTRO (piano only) | no | .921 (R) | .833 (R) | unknown | 2024-11-22 |
| hFT-Transformer (5.5M) | poly, piano | MIT | MIT (GitHub release) | MAESTRO v3 (piano only) | no | .802 (R) | .624 (R) | unknown | 2023-07-11 |
| Kong high-res (piano_transcription_inference) | poly, piano + pedal | **none stated** (no LICENSE file) | CC-BY-4.0 (Zenodo 4034264) | MAESTRO (piano only) | no | not evaluated | not evaluated | unknown (docs: `cuda`/`cpu` only) | 2025-01-26 |
| Timbre-Trap | MPE (frame), instrument-agnostic, low-resource | MIT | HF Space file (license not stated) | 35 URMP pieces | frame-level only | – | – | unknown | 2024-05-05 |
| **SwiftF0** | mono f0 | MIT | MIT (bundled ONNX) | pitch-benchmark train split | **continuous f0** | pitch F1 on URMP **.836** (pitch-benchmark) | – | inference unknown (numpy + onnxruntime only); training README: "On macOS arm64 training runs on the CPU" → claimed in docs (training) | 2026-09-25 (v0.3.0) |
| RMVPE | mono (vocal) f0 | Apache-2.0 (Dream-High) | yxlllc fork release `230917` (rmvpe.zip / rmvpe-onnx.zip), license not stated | paper evaluates MIR-1K, MIR-ST500, Cmedia (training set not verified) | continuous f0 | pF1 .689 | – | unknown | 2024-01-25 |
| FCPE / torchfcpe | mono f0 | MIT | MIT (bundled) | not found | continuous f0 | pF1 .763 | – | unknown | 2025-10-14 |
| CREPE / torchcrepe | mono f0 | MIT | MIT (bundled) | MIR-1K, Bach10, RWC-Synth, MedleyDB, MDB-STEM-Synth, NSynth ([README](https://github.com/marl/crepe)); Bach10 overlaps the benchmark's Bach10-synth | continuous f0 | pF1 .750 / .737 | – | unknown | 2024-08-19 / 2025-05-16 |
| PESTO v2 | mono f0, self-supervised | **LGPL-3.0** | bundled | MIR-1K, MDB-stem-synth, PTDB evaluated (SSL; training set per paper) | continuous f0 | pF1 .747 | – | unknown (ONNX export supported) | 2025-10-15 |
| **GAME** | vocal → notes | MIT | GitHub releases | singing corpora | float note pitch | – | – | unknown | 2026-08-29 |
| ROSVOT | vocal → notes | MIT | Google Drive (license not stated) | M4Singer | note-level | – | – | unknown | 2024-11-20 |
| CREPE Notes | mono f0 → notes (post-proc.) | **GPL-3.0** | uses CREPE | – | – | – | – | n/a (post-proc.) | 2026-03-13 |

The pitch-tracker "URMP" column is pitch F1@50 cents from [pitch-benchmark v2](https://github.com/lars76/pitch-benchmark) (a different metric from AMT OnP). It is **not** comparable with the AMT columns.

Repo activity was checked with `gh api repos/OWNER/REPO` on 2026-09-25.

---

## 3. Polyphonic / instrument-agnostic note transcribers

### 3.1 MuScriptor (Kyutai & Mirelo, 2026). PRIMARY for polyphonic stems
- **Architecture:** Decoder-only transformer over 16 kHz mel spectrograms (5 s windows) that emits MT3-style MIDI tokens. It has optional **instrument conditioning** with classifier-free guidance ([paper HTML](https://arxiv.org/html/2607.08168v1)).
  - Paper sizes: 60M, 100M, 300M, 1.3B.
  - Released sizes: small 103M, medium 307M (default) and large 1.4B ([README](https://github.com/muscriptor/muscriptor)).
- **Dates:** arXiv 2026-07-09, revised 2026-08-03, ISMIR 2026. Repo last pushed 2026-09-04.
- **Licenses:** code MIT. Weights **CC BY-NC 4.0**, gated on Hugging Face ([README](https://github.com/muscriptor/muscriptor), [HF card](https://huggingface.co/MuScriptor/muscriptor-medium)).
- **Training data:**
  - 1.45M synthesized MIDI files
  - 170k real recordings (~11,000 h) with aligned notes
  - 300 hand-verified tracks for GRPO-style RL post-training
- **Instrument vocabulary:** 36 MT3_FULL_PLUS groups. Brass groups are `trumpet` (19), `trombone` (20), `tuba` (21), `french_horn` (22) and `brass_section` (23) ([tokenizer/mt3.py](https://github.com/muscriptor/muscriptor/blob/main/muscriptor/tokenizer/mt3.py)).
  - There is **no cornet, flugelhorn, tenor horn, baritone or euphonium**. Mapping brass-band parts onto these classes (e.g. cornet→trumpet, tenor horn→french_horn, euphonium→trombone or tuba) is **our assumption and untested**.
  - Brass instruments are each about 3–7 % of training tracks (paper Fig. 2, per the [HTML](https://arxiv.org/html/2607.08168v1)).
- **Benchmarks** (paper, 1.3B, internal test set of 372 tracks): Onset F1 60.4, Frame 72.4, Offset 48.6, Multi-F1 47.8.
  - Cross-dataset vs YourMT3+: RWC-J onset 59.4 vs 52.9; Dagstuhl ChoirSet frame 80.7 vs 51.0.
  - **PHENICX-Anechoic offset F1 32.6 vs 18.7.** PHENICX contains horn and trumpet sections ([UPF](https://www.upf.edu/web/mtg/phenicx-anechoic)), so this is the most brass-relevant number available.
  - The medium card reports Onset 52.4, Frame 68.0, Offset 40.3.
  - Harmonica's common protocol (released medium checkpoint, stems): URMP-stem OnP .711 / Frm .835; Slakh-stem .457 / .488; MAESTRO .766.
- **Hardware / Apple Silicon:**
  - README: "On Apple Silicon the model runs on Metal (MPS) automatically" → **claimed**.
  - The ggml port in [NeuralNote v2](https://github.com/DamRsn/NeuralNote) (Apache-2.0 code, GGUF weights under the same NC license) reports M1 Pro real-time factors:
    - small: ~3.5× on GPU, ~2× on CPU
    - medium: ~1.5× on GPU, ~0.7× on CPU
    - large: ~0.5× on GPU
  - An M5 Pro with 48 GB should run large comfortably in offline batch.
- **Strengths:** trained on real audio; explicit brass classes; conditioning lets us force "this stem is brass_section"; exports MusicXML/PDF via MuseScore.
- **Weaknesses:**
  - No velocity.
  - Drops simultaneous same-pitch, same-instrument notes, so unisons collapse.
  - The card warns it degrades on "dense mixes, unusual timbres".
  - Out of distribution on isolated stems (see above).
  - Autoregressive decoding can hallucinate or drop notes across window boundaries (no study found).
  - No pitch bends.
- **Brass suitability:** Best available prior for brass timbres. Whether it separates three cornets in close harmony into correct simultaneous pitches is **unknown**, since no per-instrument brass numbers are published.

### 3.2 Basic Pitch (Spotify, ICASSP 2022). BACKUP / fusion partner
- **Architecture:** harmonic-stacked CQT (3 bins per semitone, starting at 27.5 Hz, 88 semitones) feeding a small CNN. It outputs three posteriorgrams: onset, note, and **contour** (3 bins per semitone). The model has 16,782 parameters ([paper](https://arxiv.org/abs/2203.09893), [constants.py](https://github.com/spotify/basic-pitch/blob/main/basic_pitch/constants.py)).
  - Frame rate is 22050/256 ≈ 86 fps (11.6 ms).
  - Notes shorter than about 120 ms are removed by post-processing (paper §3). This matters for fast brass passages; the minimum note length is configurable in the CLI.
- **Pitch bends:** `get_pitch_bends` takes the argmax of the contour posteriorgram within ±25 bins of the note, so bends resolve to about 33 cents ([note_creation.py](https://github.com/spotify/basic-pitch/blob/main/basic_pitch/note_creation.py)).
  - `multiple_pitch_bends=False` by default, because MIDI pitch bend is **channel-wide**, so bends on overlapping notes conflict.
  - Recommendation: quantize to notes for the score and keep the contour as side data (vibrato, falls, scoops) rather than writing it as MIDI bends.
- **Licenses:** Apache-2.0 for code and bundled weights ([repo](https://github.com/spotify/basic-pitch)). Latest release v0.4.0 (2024-08-16); last commit 2025-11-13.
- **Training data:** GuitarSet, iKala, MAESTRO, MedleyDB-Pitch, Slakh (paper Table 1).
- **Benchmarks (paper, Fno = onset-only note F):**

  | Dataset | Fno | F (with offset) |
  |---|---|---|
  | Molina | .52 | – |
  | GuitarSet | .79 | – |
  | MAESTRO | .71 | – |
  | Slakh | .42 | – |
  | **PHENICX section stems** | **.49** | **.35** |

  - PHENICX uses 42 "section-grouped stems" such as violins and bassoons, with horn and trumpet sections present. It is the closest published proxy for a brass section stem.
  - Against specialist models: MAESTRO Fno 70.9 vs 95.2 for Onsets & Frames; Molina vocals 52.3 vs 64.2 for VOCANO; guitar solo 84.0 vs 76.3 for TENT.
  - Harmonica's common protocol: URMP-stem .687, Slakh-stem .394, MAESTRO .578. These are released-checkpoint numbers, and its training data overlaps the test sets.
- **Monophonic pitch accuracy:** pitch F1@50c on URMP is .798 in pitch-benchmark v2, second only to SwiftF0 on that corpus ([benchmark](https://github.com/lars76/pitch-benchmark)). Octave errors are 0.85 % up and 0.40 % down.
- **Apple Silicon:** **claimed.** The README ships TF, CoreML (`nmp.mlpackage`), TFLite and ONNX models, and says "CoreML will be installed on MacOS" ([README](https://github.com/spotify/basic-pitch)). The same README says "For Mac M1 hardware, we currently only support python version 3.10". Python 3.12 fails to resolve on macOS arm64 ([#203](https://github.com/spotify/basic-pitch/issues/203), [#204](https://github.com/spotify/basic-pitch/pull/204)).
  - A JS/TS port exists: [basic-pitch-ts](https://github.com/spotify/basic-pitch-ts), inactive since 2023.
  - NeuralNote v1 wrapped Basic Pitch in C++ (ONNX Runtime + RTNeural); v2 replaced it with MuScriptor ([NeuralNote](https://github.com/DamRsn/NeuralNote)).
- **Speed:** 392.7× real time on an RTX 4090 (Harmonica); 177× real time on CPU in pitch-benchmark.
- **Strengths:** permissive; tiny; the only instrument-agnostic note model with bends; exposes raw posteriorgrams, which are ideal for fusion; "works best on one instrument at a time" (README), which matches our per-stem design.
- **Weaknesses:** accuracy is clearly behind 2024–26 models, and the Harmonica authors report its harmonic stacking as the weakest aggregator. Its small receptive field can cause octave and harmonic errors on dense chords.

### 3.3 Harmonica (BandLab, arXiv 2609.04640, Sep 2026). Benchmark reference only
- **Architecture:** multi-depth harmonic "shift-and-aggregate" convolution with onset, sustain and offset heads. Sizes: nano 26.3K, small 137K, medium 679K, large 3.2M, x-large 15.1M ([HTML](https://arxiv.org/html/2609.04640)).
- **Training data:** MAESTRO, MAPS, GuitarSet, GAPS, EGDB, GOAT, URMP-stem and Slakh-stem (1,385.5 h), with temperature sampling.
- **Results:** x-large gets URMP-stem OnP .925 and Slakh-stem .918. Nano runs at 1,622.5× real time and beats Basic Pitch "by a wide margin on all test sets other than URMP". Fig. 3 shows per-family frame F1 on Slakh including a **Brass** family (synthesized), where x-large is strongest on every family.
- **Availability:** no code or weights. The paper says it is "deployed as the Audio-to-MIDI service in BandLab"; the project page is [oulongshen.xyz/amt](https://www.oulongshen.xyz/amt). **Not usable.**
- **Value for us:** the only table where many architectures are **retrained instrument-agnostic** on the same data. It shows that the frame-level architectures Transkun, HPPNet, TriAD and SFT-CRNN generalize well to stems **when retrained**. That points to a path of retraining one of them ourselves on brass data (see open questions).

### 3.4 MT3 / YourMT3+ (per-stem use)
These belong to the multi-instrument report; here is only the per-stem view.
- The released MT3 scores URMP-stem .829 and Slakh-stem .900, but it was trained on both, so the numbers are inflated ⚑ ([Harmonica](https://arxiv.org/html/2609.04640)). The MT3 repo is Apache-2.0 and still receives commits (2026-09-15) ([repo](https://github.com/magenta/mt3)).
- YourMT3+ is GPL-3.0 ([repo](https://github.com/mimbres/YourMT3)). Retrained by the Harmonica authors, it scores URMP-stem .926. It came second in the 2025 AMT Challenge (0.5938 F1) ([results](https://arxiv.org/html/2603.27528v1)).

### 3.5 Other instrument-agnostic and multipitch research models
- **Timbre-Trap** (Sony, ICASSP 2024; [arXiv 2309.15717](https://arxiv.org/abs/2309.15717), [repo](https://github.com/sony/timbre-trap), MIT; weights in an [HF Space](https://huggingface.co/spaces/cwitkowitz/timbre-trap)). A joint reconstruction and transcription U-Net over a complex CQT, trained on only 35 URMP pieces.
  - Frame-level MPE F1: Bach10 82.6 (Basic Pitch 82.9), Su 51.4 (Basic Pitch 48.9), GuitarSet 60.2 (Basic Pitch 76.2, but Basic Pitch trained on GuitarSet).
  - Interesting as a **low-resource recipe** for fine-tuning on a small brass-band set. It outputs frames only, no notes.
- **Slot-attention multi-instrument MPE** (Taenzer, MMSP 2026; [arXiv 2606.01460](https://arxiv.org/abs/2606.01460)). Hungarian-matched slots turn a CQT into per-source pitch maps; evaluated on URMP. The author states "stem-level prediction remains more challenging". No code found.
- **Note-level contrastive clustering** (Li & Zhu, TISMIR 2026; [arXiv 2509.12712](https://arxiv.org/abs/2509.12712)). A timbre-agnostic backbone plus a timbre encoder that clusters notes into instruments. It is conceptually relevant for splitting a brass-section stem into voices by timbre, but brass-band voices share one timbre, so this is unlikely to help. No code found.
- **Cheuk et al.:**
  - **ReconVAT** ([arXiv 2107.04954](https://arxiv.org/abs/2107.04954), [repo](https://github.com/KinWaiCheuk/ReconVAT), no license stated): semi-supervised, evaluated on MusicNet, which contains horn but not trumpet.
  - **Jointist** ([arXiv 2302.00286](https://arxiv.org/abs/2302.00286), [repo](https://github.com/KinWaiCheuk/Jointist)): joint transcription and separation on Slakh.
  - **DiffRoll** ([repo](https://github.com/sony/DiffRoll), MIT, last push 2023-12): piano only.
  - All three are research code with no brass evaluation.
- **Weak and unpaired supervision (2025–26):**
  - **CountEM** (ISMIR 2025; [arXiv 2511.14250](https://arxiv.org/abs/2511.14250)) trains from note histograms only.
  - **Cycle-consistent AMT with (almost) no supervision** ([arXiv 2605.24193](https://arxiv.org/abs/2605.24193), May 2026) reports that new instruments can be learned from unpaired audio plus scores.
  - Both are directly relevant to brass bands: lots of scores and recordings exist, but aligned pairs do not. No code or weights were found for either (a project page exists for CountEM).
- **Omnizart** ([repo](https://github.com/music-and-culture-technology-lab/omnizart), MIT, pushed 2026-05-31): an older toolkit with music, vocal, chord and drum models. No evidence it beats the models above.
- **Out of scope, clarified:**
  - **MIDI-VAE** is a symbolic style-transfer VAE, not an AMT model.
  - **NNLS-Chroma** (Mauch) produces chroma and chord features, not notes; it belongs in the harmony report.
  - "Timbre-agnostic MPE" in the brief is best matched by Timbre-Trap and Basic Pitch above.

---

## 4. Monophonic pitch trackers (brass/bass lines after separation)

### Why a pitch tracker plus segmentation instead of polyphonic AMT
- A single separated brass voice is a monophonic problem.
- f0 trackers give continuous pitch, which captures scoops, falls and vibrato.
- They make fewer octave errors than polyphonic AMT on monophonic input.
- They need a **note-segmentation** step to produce notes.

### 4.1 Pitch-benchmark v2
Source: [repo](https://github.com/lars76/pitch-benchmark), [BENCHMARK.md](https://github.com/lars76/pitch-benchmark/blob/main/BENCHMARK.md), MIT; dataset CC BY-NC-SA 4.0. It compares 19 trackers on 10 corpora under 8 degradations (scene noise, room, mic filtering). Speed was measured on a Ryzen 9 8945HS, one thread.

| Tracker | Overall pitch F1@50c | **URMP** (orchestral incl. brass) | Bach10-synth | Octave-up % | Octave-down % | Speed ×RT (CPU) |
|---|---|---|---|---|---|---|
| SwiftF0 | .778 | **.836** | .904 | 0.33 | 0.43 | 416.6 |
| RMVPE | .768 | .689 | .841 | 0.76 | 0.52 | 50.0 |
| FCPE | .728 | .763 | .859 | 0.73 | 1.02 | 49.6 |
| TorchCREPE | .691 | .737 | .870 | 0.97 | **0.18** | 2.2 |
| CREPE | .689 | .750 | .858 | 1.53 | 0.37 | 2.7 |
| PESTO | .680 | .747 | .832 | 3.39 | 0.80 | 33.2 |
| BasicPitch | .557 | .798 | .875 | 0.85 | 0.40 | 177.0 |
| pYIN | .506 | .671 | .779 | 0.54 | 1.79 | 10.5 |

**Caveats:**
- **Conflict of interest:** the benchmark is maintained by the SwiftF0 author, and SwiftF0 v0.3.0 is **trained on this benchmark's own train split**. The split holds out speaker and recording groups but uses the same corpora ([swift-f0-training](https://github.com/lars76/swift-f0-training)). Other trackers are out of domain here.
- The overall score is dominated by speech corpora. **The URMP column is the relevant one for us.**
- Only about 1.1 % of voiced frames fall in the "bass" band, so low-register accuracy is barely measured. That matters for Eb and BBb basses.

### 4.2 Per-tracker notes
- **SwiftF0**
  - Sources: [repo](https://github.com/lars76/swift-f0), MIT; [paper arXiv 2508.18440](https://arxiv.org/abs/2508.18440).
  - v0.3.0 was released 2026-09-25 with **14,386 params** (README). The paper version had 95,842 params. Numbers from each apply only to that version.
  - The only dependencies are numpy and onnxruntime, which run on CPU. It has a built-in `segment_notes()` and MIDI export.
  - **Range 46.875–2093.75 Hz (F♯1–C7).** This misses BBb and Eb bass pedal and low-register notes (e.g. Eb1 ≈ 38.9 Hz, E1 ≈ 41.2 Hz) and the bass guitar's low E.
  - Apple Silicon: platform-neutral ONNX, not explicitly documented for M-series → "claimed (generic)".
- **CREPE / torchcrepe**
  - Sources: [CREPE](https://github.com/marl/crepe), MIT, pushed 2024-08; [torchcrepe](https://github.com/maxrmorrison/torchcrepe), MIT, pushed 2025-05.
  - 360 bins at 20 cents, starting at 1997.38 cents re 10 Hz. That gives a range of **≈31.7–2006 Hz** ([core.py](https://github.com/marl/crepe/blob/master/crepe/core.py)).
  - torchcrepe defaults to **Viterbi decoding**, which suppresses octave jumps ([README](https://github.com/maxrmorrison/torchcrepe)). It has the lowest octave-down error rate in the benchmark.
  - Slow: 2–3× real time on one CPU thread. That does not matter for offline batch.
- **RMVPE**
  - Sources: [arXiv 2306.15412](https://arxiv.org/abs/2306.15412), Interspeech 2023; [Dream-High/RMVPE](https://github.com/Dream-High/RMVPE), Apache-2.0; [yxlllc/RMVPE](https://github.com/yxlllc/RMVPE), training fork with ONNX notes, no license.
  - A U-Net plus GRU designed for **vocal pitch within polyphonic mixes**, using CREPE's 360-bin grid (≈31.7 Hz floor; [constants.py](https://github.com/Dream-High/RMVPE/blob/main/src/constants.py)).
  - Strong on speech and vocals but weak on URMP (.689). It is vocal-trained and a poor fit for brass.
- **FCPE / torchfcpe**
  - Sources: [arXiv 2509.15140](https://arxiv.org/abs/2509.15140), Sep 2025; [repo](https://github.com/CNChTu/FCPE), MIT, pushed 2025-10.
  - Lynx-Net with depthwise convolutions. Its model class range defaults to **32.70–1975.5 Hz** ([models.py](https://github.com/CNChTu/FCPE/blob/main/torchfcpe/models.py)). The 80–880 Hz in the README is only a post-processing default.
  - Paper: MIR-1K RPA 96.79 %, RTF 0.0062 on an RTX 4090. URMP .763 in the benchmark.
- **PESTO (v1 ISMIR 2023, v2 2025)**
  - Sources: [arXiv 2309.02265](https://arxiv.org/abs/2309.02265), [arXiv 2508.01488](https://arxiv.org/abs/2508.01488), [repo](https://github.com/SonyCSLParis/pesto), **LGPL-3.0**.
  - A self-supervised, transposition-equivariant model with 130k params and a VQT starting at 27.5 Hz ([config.py](https://github.com/SonyCSLParis/pesto/blob/main/pesto/config.py)). It supports ONNX export.
  - It has the highest octave-up error rate (3.39 %) of the neural trackers. Its self-supervision makes it the easiest to **fine-tune on unlabelled brass-band audio**.
- **Note segmentation**
  - **CREPE Notes** (Riley & Dixon, [arXiv 2311.08884](https://arxiv.org/abs/2311.08884); [repo](https://github.com/xavriley/crepe_notes), **GPL-3.0**, pushed 2026-03) segments CREPE f0 plus confidence into notes. It was tested on unseen instrumental data:

    | Dataset | CREPE Notes F | Basic Pitch F | MT3 F | pYIN-notes F |
    |---|---|---|---|---|
    | FiloSax (tenor sax) | 82.3 | 75.5 | 43.0 | 58.3 |
    | ITM-Flute-99 | 66.6 | 59.6 | 25.5 | – |

    Sax and flute are the closest published proxies for monophonic wind or brass lines.
  - SwiftF0's `segment_notes()` is an MIT alternative, but no published note-level evaluation was found.
- **Bass-specific:** no maintained note-level bass transcriber was found. Abeßer's [walking_bass_transcription_dnn](https://github.com/jakobabesser/walking_bass_transcription_dnn) (2020) and [bassunet](https://github.com/jakobabesser/bassunet) (2021) are old research code. **FiloBass** ([arXiv 2311.02023](https://arxiv.org/abs/2311.02023), ISMIR 2023) is a 48-track jazz-bass dataset useful for evaluation.
  - Recommendation: treat a separated bass stem as monophonic and use CREPE, FCPE or RMVPE, whose ranges reach about 32 Hz, plus segmentation.
  - Guitar-specific models (GAPS, Riley et al. domain adaptation [arXiv 2402.15258](https://arxiv.org/abs/2402.15258), TART [arXiv 2609.11904](https://arxiv.org/abs/2609.11904)) are out of scope for a brass target.

---

## 5. Piano-trained models and generalization to other timbres

- **Kong et al. high-resolution** ([arXiv 2010.01815](https://arxiv.org/abs/2010.01815); [inference repo](https://github.com/qiuqiangkong/piano_transcription_inference), no LICENSE file; [bytedance/piano_transcription](https://github.com/bytedance/piano_transcription), **archived**; weights [Zenodo 4034264](https://zenodo.org/records/4034264), CC-BY-4.0).
  - A CRNN that regresses onset and offset times. MAESTRO onset F1 96.72 %, pedal onset F1 91.86 %.
  - **GiantMIDI-Piano** ([arXiv 2010.07061](https://arxiv.org/abs/2010.07061)) is a *dataset* of 10,855 piano works transcribed with this system, not a new model.
- **hFT-Transformer** (Sony, ISMIR 2023; [arXiv 2307.04305](https://arxiv.org/abs/2307.04305), [repo](https://github.com/sony/hFT-Transformer), MIT; checkpoint in a GitHub release).
  - MAESTRO v3 note F1 97.43 and note-with-offset 90.32.
  - Retrained instrument-agnostic by the Harmonica authors, it underperformed their 26K nano model (MAESTRO Frm .283; "slow convergence").
- **Transkun V2** ([repo](https://github.com/Yujia-Yan/Transkun), MIT, weights in pip). A neural semi-CRF piano model (NeurIPS 2021), with V2 scoring intervals using a non-hierarchical transformer ([ISMIR 2024, arXiv 2404.09466](https://arxiv.org/abs/2404.09466)); the shipped checkpoint has no pedal extension.
- **Onsets & Frames** ([arXiv 1710.11153](https://arxiv.org/abs/1710.11153)): the [magenta/magenta](https://github.com/magenta/magenta) repo is **archived**. A PyTorch re-implementation exists at [jongwook/onsets-and-frames](https://github.com/jongwook/onsets-and-frames) (MIT).
- **Generalization evidence:**
  1. Public piano checkpoints are trained on MAESTRO/MAPS only, and no paper evaluates them on brass. The Harmonica table shows that the *architectures* generalize **only when retrained** on multi-instrument stems.
  2. Riley et al. show piano → guitar transfer works **via fine-tuning** or domain adaptation, not zero-shot use of the piano checkpoint ([arXiv 2402.15258](https://arxiv.org/abs/2402.15258)).
  3. Piano models assume percussive onsets and decaying notes. Brass has soft, tongued or slurred attacks and sustained or swelling notes, so expect missed legato onsets and fragmented sustains. This is an inference, not measured.
  - **Recommendation:** do not use piano checkpoints on brass stems. Use them only for a genuine piano stem in the source.

---

## 6. Vocal melody → notes (for vocal-led sources)

- **GAME: Generative Adaptive MIDI Extractor** (openvpi; [repo](https://github.com/openvpi/GAME), MIT; created 2026-01, v1.0.3 on 2026-03-09, pushed 2026-08-29). The successor to [SOME](https://github.com/openvpi/SOME) (MIT, 706 stars).
  - Uses D3PM discrete-diffusion boundary extraction and "works on dirty or separated voice mixed with noise, reverb or even accompaniments".
  - Outputs float pitch and optionally aligns to word boundaries.
  - No published benchmark numbers were found beyond its [ALGORITHMS.md](https://github.com/openvpi/GAME/blob/main/ALGORITHMS.md) technical report.
- **ROSVOT** (ACL 2024; [arXiv 2405.09940](https://arxiv.org/abs/2405.09940), [repo](https://github.com/RickyL-2000/ROSVOT), MIT; weights on Google Drive, trained on M4Singer).

  | Method | COnPOff F (clean) | COnPOff F (noisy) |
  |---|---|---|
  | ROSVOT | 77.4 | 77.0 |
  | VOCANO | 50.2 | 43.4 |
  | MusicYOLO | 58.9 | 51.5 |

  It uses RMVPE internally.
- **VOCANO** ([repo](https://github.com/B05901022/VOCANO), MIT, inactive since 2021). Superseded.
- **Wang et al. ICASSP 2021 / MIR-ST500** ([repo](https://github.com/york135/singing_transcription_ICASSP2021), no license).
- **STARS** (2025; [arXiv 2507.06670](https://arxiv.org/abs/2507.06670), [repo](https://github.com/gwx314/STARS), MIT, pushed 2026-08). A unified framework for transcription, alignment and style annotation.
- **VocalParse** (May 2026; [arXiv 2605.04613](https://arxiv.org/abs/2605.04613)). A Qwen3-ASR-based model for lyrics plus notes; code status not found.

---

## 7. Fusion / ensembling of per-stem AMT output

### What the literature says
- **No dedicated paper on note-level ensembling of AMT models was found.** Searches for AMT ensembles, ROVER-style note fusion and posteriorgram averaging turned up nothing directly on topic.
- The 2025 AMT Challenge report documents no ensemble or fusion among the top systems ([arXiv 2603.27528](https://arxiv.org/html/2603.27528v1)).
- The closest work:
  - **Voting-based pitch estimation** (Koguchi & Koriyama, ICASSP 2026; [arXiv 2602.01727](https://arxiv.org/abs/2602.01727)). It ensembles SWIPE′, pYIN, DIO, REAPER, Harvest, Praat, CREPE and FCNF0++ in three steps:
    1. Pre-vote alignment corrects time and frequency bias between trackers. Time offset is chosen by maximizing RPA against a reference; frequency offset is the median cent deviation.
    2. Frame-wise **median** f0 is taken, with a majority vote for voicing.
    3. Trackers are chosen greedily by error correlation.

    The authors show median aggregation is robust to octave outliers and that the ensemble beats individual trackers in clean conditions. No code was found.
  - **Late fusion of OMR and AMT hypotheses in a lattice** ([arXiv 2204.03063](https://arxiv.org/abs/2204.03063)) is a template for merging symbolic hypotheses from different sources.
  - **ROVER** (from speech recognition: align the hypotheses, then vote) is the classical analogue, as summarized in [MOVER, arXiv 2508.05055](https://arxiv.org/abs/2508.05055).

### Proposed design (untested; for benchmarking)
1. **Frame-level fusion where posteriorgrams exist.** Basic Pitch exposes note, onset and contour posteriorgrams (`--save-model-outputs`). Resample every model's output (for MuScriptor and other token models, render notes to a piano roll) onto a common 10–12 ms grid and pitch axis, then take a weighted average. Per-model weights should be tuned on a small annotated brass set.
2. **Note-level match-and-vote.** Match notes across models with `mir_eval.transcription.match_notes` (50 ms onset, ±50 cents). A note survives if at least k of N models agree. Onset time is the median of the matched onsets; offset comes from the model with the best offset accuracy on the dev set.
3. **Octave arbitration.** For stems known to be monophonic, or per voice after voice separation, run a monophonic tracker. Prefer torchcrepe with Viterbi, which has the lowest octave-down rate, plus SwiftF0, and move polyphonic-model notes that sit exactly ±12 semitones from a confident f0 onto the tracker's octave.
4. **Musical priors.** Clamp each part to its instrument's range (cornet, horn, baritone, euphonium, Eb and BBb bass). Voice-leading and harmony consistency are left to the arrangement stage.
5. **Evaluation:** OnP / OnPOff F1 and the octave-error rate (per pitch-benchmark's definition) on a hand-annotated brass-band set.

---

## 8. Open questions only benchmarking can settle

1. Does MuScriptor transcribe better from the **separated brass stem** or from the **full mix with instrument conditioning** (`brass_section`, `trumpet`, `tuba`…)? Its training on mixes suggests the mix may win.
2. On a real brass-band recording with three cornet parts in close harmony, what fraction of simultaneous pitches does each model recover (MuScriptor, Basic Pitch, and a retrained Transkun/HPPNet if we train one)? Are unisons between parts collapsed?
3. Low brass: accuracy below 47 Hz (SwiftF0's floor) versus CREPE, FCPE and RMVPE on Eb and BBb bass parts, and the octave-error rate on tuba, which has a strong upper-partial spectrum.
4. Does Basic Pitch's 120 ms minimum note length drop fast cornet passages? What setting is best?
5. Slurred legato brass: onset recall of each approach (polyphonic AMT, f0 plus CREPE Notes, SwiftF0 `segment_notes`).
6. Does frame-level or note-level fusion beat the best single model, and by how much?
7. Is it worth **retraining** an open frame-level architecture (Transkun, MIT; or HPPNet/TriAD if code exists) instrument-agnostic on URMP and Slakh stems plus synthesized brass-band MIDI? Harmonica's table suggests this reaches about .92 OnP on URMP-stem, against .71 for the best public checkpoint without training overlap (MuScriptor; the released MT3 scores .829 but was trained on URMP).
8. Separation artefacts (bleed, phasing): which tracker degrades least on Demucs/BS-RoFormer brass stems?
9. MuScriptor on M5 Pro: MPS PyTorch versus the ggml/Metal port, and throughput for large.

---

## 9. References

**Models / repos**
- Basic Pitch: https://github.com/spotify/basic-pitch · paper https://arxiv.org/abs/2203.09893 · issues https://github.com/spotify/basic-pitch/issues/203, https://github.com/spotify/basic-pitch/pull/204 · TS port https://github.com/spotify/basic-pitch-ts
- MuScriptor: https://github.com/muscriptor/muscriptor · https://arxiv.org/abs/2607.08168 · https://huggingface.co/MuScriptor/muscriptor-medium · tokenizer https://github.com/muscriptor/muscriptor/blob/main/muscriptor/tokenizer/mt3.py
- NeuralNote (Basic Pitch v1 → MuScriptor v2, ggml/Metal): https://github.com/DamRsn/NeuralNote
- Harmonica: https://arxiv.org/abs/2609.04640 · https://arxiv.org/html/2609.04640
- MT3: https://github.com/magenta/mt3 · YourMT3: https://github.com/mimbres/YourMT3
- 2025 AMT Challenge: https://arxiv.org/html/2603.27528v1
- Kong high-res piano: https://arxiv.org/abs/2010.01815 · https://github.com/qiuqiangkong/piano_transcription_inference · https://github.com/bytedance/piano_transcription · https://zenodo.org/records/4034264 · GiantMIDI https://arxiv.org/abs/2010.07061
- hFT-Transformer: https://arxiv.org/abs/2307.04305 · https://github.com/sony/hFT-Transformer
- Transkun: https://github.com/Yujia-Yan/Transkun
- Onsets & Frames: https://arxiv.org/abs/1710.11153 · https://github.com/magenta/magenta · https://github.com/jongwook/onsets-and-frames
- Timbre-Trap: https://arxiv.org/abs/2309.15717 · https://github.com/sony/timbre-trap
- ReconVAT: https://arxiv.org/abs/2107.04954 · https://github.com/KinWaiCheuk/ReconVAT · Jointist https://arxiv.org/abs/2302.00286 · DiffRoll https://github.com/sony/DiffRoll
- Slot-attention MPE: https://arxiv.org/abs/2606.01460 · Contrastive clustering: https://arxiv.org/abs/2509.12712
- CountEM: https://arxiv.org/abs/2511.14250 · Almost-no-supervision AMT: https://arxiv.org/abs/2605.24193
- Omnizart: https://github.com/music-and-culture-technology-lab/omnizart
- SwiftF0: https://github.com/lars76/swift-f0 · https://arxiv.org/abs/2508.18440 · training https://github.com/lars76/swift-f0-training
- Pitch benchmark v2: https://github.com/lars76/pitch-benchmark · https://github.com/lars76/pitch-benchmark/blob/main/BENCHMARK.md
- CREPE: https://github.com/marl/crepe · torchcrepe: https://github.com/maxrmorrison/torchcrepe
- RMVPE: https://arxiv.org/abs/2306.15412 · https://github.com/Dream-High/RMVPE · https://github.com/yxlllc/RMVPE
- FCPE: https://arxiv.org/abs/2509.15140 · https://github.com/CNChTu/FCPE
- PESTO: https://arxiv.org/abs/2309.02265 · https://arxiv.org/abs/2508.01488 · https://github.com/SonyCSLParis/pesto
- CREPE Notes: https://arxiv.org/abs/2311.08884 · https://github.com/xavriley/crepe_notes
- GAME: https://github.com/openvpi/GAME · SOME: https://github.com/openvpi/SOME
- ROSVOT: https://arxiv.org/abs/2405.09940 · https://github.com/RickyL-2000/ROSVOT
- VOCANO: https://github.com/B05901022/VOCANO · MIR-ST500: https://github.com/york135/singing_transcription_ICASSP2021 · STARS: https://arxiv.org/abs/2507.06670, https://github.com/gwx314/STARS · VocalParse: https://arxiv.org/abs/2605.04613
- Bass: https://github.com/jakobabesser/walking_bass_transcription_dnn · https://github.com/jakobabesser/bassunet · FiloBass https://arxiv.org/abs/2311.02023
- Guitar DA: https://arxiv.org/abs/2402.15258 · TART: https://arxiv.org/abs/2609.11904

**Datasets / fusion**
- PHENICX-Anechoic: https://www.upf.edu/web/mtg/phenicx-anechoic
- Voting-based pitch estimation: https://arxiv.org/abs/2602.01727
- OMR+AMT late fusion: https://arxiv.org/abs/2204.03063
- MOVER / ROVER summary: https://arxiv.org/abs/2508.05055
