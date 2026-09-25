# 00 — Research summary and architecture decision (draft)

Date: 2026-09-25. Target machine: Apple M5 Pro, 48 GB, macOS 26.6.
Detail and citations are in the area reports:

| # | Area | Report |
|---|---|---|
| 01 | Source separation | [01-source-separation.md](01-source-separation.md) |
| 02 | Multi-instrument AMT, instrument recognition | [02-amt-multi-instrument.md](02-amt-multi-instrument.md) |
| 03 | Per-stem polyphonic AMT, monophonic pitch, fusion | [03-amt-polyphonic-stem.md](03-amt-polyphonic-stem.md) |
| 04 | Beat/downbeat/meter, quantization, structure | [04-rhythm-meter-quantization.md](04-rhythm-meter-quantization.md) |
| 05 | Key, chords, melody, spelling, verification embeddings | [05-harmony-melody-embeddings.md](05-harmony-melody-embeddings.md) |
| 06 | Arrangement/orchestration, macOS capture, MusicXML | [06-arrangement-capture-export.md](06-arrangement-capture-export.md) |

All of this is desk research. No model has been installed or run yet. Every pick below is a *hypothesis for the benchmark*. It is not yet a decision.

---

## 1. Headline findings

1. **The multi-instrument AMT landscape changed in mid-2026.**
   - **MuScriptor** (Kyutai + Mirelo, ISMIR 2026, [arXiv 2607.08168](https://arxiv.org/abs/2607.08168)) is the first open-weight transcriber trained at scale on *real* mixes: about 11k hours, then RL post-training.
   - On its authors' real-music test set it roughly doubles YourMT3+ in multi-instrument F1 (48.2 vs 21.9). On orchestral PHENICX it scores 25.7 vs 12.2.
   - MT3 is obsolete as a candidate. Its released checkpoint reproduces about 26 of the paper's 55 Slakh Multi F1.
2. **No model knows brass-band instruments.**
   - Every AMT and separation vocabulary stops at General MIDI brass: trumpet, trombone, tuba, French horn and "brass section".
   - Cornet, flugelhorn, tenor horn, baritone and euphonium are absent everywhere.
3. **No model separates same-timbre voices.**
   - Three cornets in close harmony become one stream, in separation (no such model exists) and in AMT. MT3-style tokens cannot even represent a unison on one instrument.
   - **Voice separation, and assigning notes to brass-band parts, must be a symbolic stage we build ourselves.**
4. **The evidence that separation improves transcription is thin.**
   - For mixture-trained transcribers the gain is about 1–6 F1 points (YourMT3+ ablation).
   - MuScriptor is *worse-matched* to separated stems than to mixes: it scores only 2–6 points above Basic Pitch on URMP/Slakh stems.
   - On an all-brass recording, separation has almost nothing to separate.
   - Pipelines A vs B must be decided by measurement.
5. **Nothing reports accuracy on real brass audio.**
   - Brass-band ground truth does not exist publicly. The closest resources are ChoraleBricks (real isolated brass chorales, CC-BY 4.0), URMP, PHENICX-Anechoic, CocoChorales and Slakh brass (synthetic).
   - We will have to build the evaluation set. It is the critical path.
6. **Audio-LLMs cannot transcribe.**
   - Frontier audio-LLMs fail at pitch (PitchBench), and a MERT front end did worse than a mel spectrogram inside MuScriptor.
   - Do not route notes through an LLM. An LLM is at most a planner for arrangement decisions (section textures, doubling strategy), never a source of notes.
7. **Capture is feasible without Spotify APIs.**
   - A Core Audio process tap (macOS 14.2+; on 26, tap by bundle ID) is reported to capture Spotify fine; the DRM claim traces only to a vendor blog.
   - FairPlay sources (Apple Music, Safari) are probably blocked.
   - This needs a 10-second smoke test on this machine.

---

## 2. Picks per area

| Area | PRIMARY | BACKUP | Code / weights licence (primary) | Apple Silicon (primary) |
|---|---|---|---|---|
| Source separation, stage 1 | BS-RoFormer SW (6-stem) via python-audio-separator / MSST | HT-Demucs v4 `htdemucs_ft` / `_6s` | MIT / **undocumented** | claimed (MPS); MLX port lists SW |
| Source separation, brass sub-stems | MVSep Mega-53 v1 (ckpt in MSST release v1.0.21, 1.37 GB; SW ckpt in audio-separator `model-configs` release — both verified 2026-09-25) (brass, trumpet, trombone, horn, tuba) | SAM-Audio text prompts (experimental; generative, can invent notes) | MIT / **not stated** | unknown (author asks ≥16 GB VRAM) |
| Multi-instrument AMT | **MuScriptor** medium/large | YourMT3+ (YPTF.MoE+Multi) | MIT / **CC BY-NC 4.0, gated** | claimed (MPS) |
| Instrument-agnostic stem AMT | MuScriptor (instrument-conditioned) + Basic Pitch, fused | — | Basic Pitch Apache-2.0 | Basic Pitch: CoreML default. **Pin Py 3.10** (arm64+3.12 install broken, #203) |
| Monophonic f0 (lead / single line) | SwiftF0 → note segmentation | torchcrepe (Viterbi) + CREPE Notes | MIT | ONNX, fine |
| Bass-register f0 | torchcrepe / RMVPE (reach ~32 Hz) | Basic Pitch (27.5 Hz) | MIT | fine |
| Vocals → notes | GAME (openvpi 2026) | ROSVOT | MIT | unknown |
| Instrument recognition | User-supplied instrument list (brass-band input) + MuScriptor conditioning; Essentia `mtg_jamendo_instrument` tagger for unknown pop/rock input | PANNs (AudioSet) frame-wise SED | Essentia model CC BY-NC-SA | TF; unknown |
| Beats / downbeats / tempo | **Beat This!** (no DBN) | allin1 | MIT / MIT | reported working (MPS) |
| Meter | Derived from downbeat spacing, per bar, with user override | madmom DBN `beats_per_bar` | — | — |
| Quantization | Our own beat-grid DP/HMM quantizer (24 ticks/beat) → music21/partitura for ties/tuplets | MuseScore 4 `mscore` MIDI import on a beat-locked tempo map; PM2S with injected beats | — | — |
| Structure / sections | allin1 | SongFormer (weights non-commercial through MuQ), MSAF | MIT | open PR #39 (reported working on M5) |
| Global key | S-KEY | madmom CNN key (git master) | MIT / MIT (in repo) | claimed (MPS) |
| Local key, Roman numerals | AnalysisGNN / RNHybrid (symbolic) | AugmentedNet | MIT | CPU fine |
| Chords | consonance-ACE (reports inversions) | music-x-lab ISMIR2019 CNN-LSTM | MIT / MIT | unknown |
| Pitch spelling | partitura `ps13s1` in concert pitch, **before** transposition | PKSpell | Apache-2.0 | pure Python |
| Melody f0 | Deep Salience `melody2` | MSNet melody | MIT | unknown |
| Countermelody | **No audio model exists.** Symbolic melodic-line ranking over transcribed voices | — | — | — |
| Verification loop | Chroma/CENS + MrMsDTW (synctoolbox); same-AMT diff (source vs render); score-informed NMF residual | MuQ early layers, CLEWS | MIT | fine |
| Audio/music embeddings | MuQ early layers (frame-level) | CLEWS segment embeddings; MERT | MuQ weights CC BY-NC | unknown |
| Arrangement | In-house: OR-Tools CP-SAT allocation with hard range/transposition constraints; Anticipatory Music Transformer for infill with per-instrument logit masking | REMI-z arranger (licence blank), METEOR | Apache-2.0 / Apache-2.0 | plausible (HF GPT-2); unverified |
| Capture | Swift CLI on a Core Audio process tap, called from Go | audiotee (MIT), BlackHole | ours | native |
| Metadata | Spotify AppleScript (`osascript`) | media-control / mediaremote-adapter | — | — |
| MusicXML | music21 (custom brass-band Instrument classes) + lxml post-pass (`<instrument-sound>`, score order, brackets); xmllint against the MusicXML 4.0 XSD; MuseScore 4 CLI for PDF/parts | Verovio previews | BSD-3 | fine |

Repo activity and licences were spot-checked on 2026-09-25 with `gh api`. The check covered beat_this, skey, consonance-ACE, demucs, python-audio-separator, sam-audio, anticipation, swift-f0, basic-pitch, YourMT3, audiotee, mlx-audio-separator and muscriptor. Plus the MuScriptor HF card: `cc-by-nc-4.0`, gated. Findings:
- YourMT3's GitHub licence is GPL-3.0; the HF card says Apache.
- SAM-Audio uses a custom SAM licence.
- audiotee states MIT in its README only, with no LICENSE file.

---

## 3. Licence risk (personal use is fine; recorded for the future)

| Licence situation | Components |
|---|---|
| Permissive code + weights | Beat This!, S-KEY, consonance-ACE, Basic Pitch, SwiftF0, Anticipatory MT, allin1, Deep Salience, music21, partitura, HT-Demucs (code) |
| Non-commercial weights | MuScriptor (CC BY-NC 4.0), madmom models, MERT, MuQ (and therefore SongFormer), Banquet |
| Undocumented / ambiguous | BS-RoFormer SW, Mega-53, YourMT3+ (GPL vs Apache), REMI-z arranger, MT3 checkpoint |
| Custom | SAM-Audio (SAM License, gated) |
| Copyleft | Essentia (AGPL), CREPE Notes (GPL-3.0), BlackHole (GPL-3.0), MusicLang (GPL-3.0) |

Mitigation: pin model files locally under `models/` with a checksum and a source URL. Several of these download links have already rotted: the SW Hugging Face link and the madmom PyPI package.

## 4. Apple Silicon risk

| Risk | Components |
|---|---|
| Low (native / claimed + reported) | Basic Pitch (CoreML), SwiftF0 (ONNX), Beat This! (MPS, reported), HT-Demucs (MPS + MLX port), capture, music21 |
| Medium (claimed, no Mac reports) | MuScriptor (MPS claimed; no Mac timings. The large model runs >4× real-time on an RTX 4090), S-KEY, BS-RoFormer SW |
| High / unknown | Mega-53 (memory), YourMT3+, consonance-ACE, allin1 (open PR only), SAM-Audio (MPS workaround) |

48 GB of unified memory is ample for everything listed. The real risk is operators missing from PyTorch's MPS backend and falling back to the CPU. Speed only matters once quality is established (spec §20).

## 5. Environment / architecture finding

The candidate models pull in incompatible dependencies:
- **numpy:** YourMT3+ pins numpy 1.26; MuScriptor needs numpy ≥2.
- **Python version:** Basic Pitch needs Python 3.10 on arm64; madmom/BeatNet need Python <3.10 or git builds.
- **Framework:** MT3 would need JAX, TF and t5x from git HEAD.

**Decision: one isolated `uv` environment per model adapter, invoked as a subprocess** with a file-based contract: WAV in, JSON/MIDI plus a sidecar out. This confirms spec §19's Go → Python subprocess option. gRPC is not needed.
- System Python is 3.14. Most stacks don't support it yet, so per-adapter venvs pin 3.10–3.12.
- The Go orchestrator owns job graphs, the cache (content-hashed artefacts on disk) and capture.
- The arrangement engine and MusicXML export live in Python, because music21 and partitura have no Go equivalent (§6 of report 06).

## 6. Where the spec should change (§30)

1. **Voice separation becomes an explicit stage.**
   - The spec assumes AMT recovers "simultaneous brass voices". No model does.
   - Add a symbolic *voice separation / part assignment* stage between reconciliation and the canonical score. It works on pitch range, voice-leading cost and harmonic role.
   - It is the single most important piece of in-house algorithmic work.
2. **Instrument labels are hints, not facts.**
   - `instrumentProbability` should be over *families and roles* (brass, low brass, melody, bass), not brass-band instrument ids.
   - Brass-band instruments exist only on the arrangement side.
3. **Separation is conditional, not a fixed stage.**
   - For all-brass input, skip it or use it only to peel off percussion.
   - For pop/rock it feeds melody, bass and chord analysis.
   - The benchmark decides per downstream task, not globally.
4. **The consensus engine is novel work.**
   - No published note-level AMT fusion exists.
   - Design: time-tolerant note matching (mir_eval-style 50 ms onset window, pitch equality modulo octave-error handling), per-model calibrated weights learned on the eval set, and unresolved conflicts kept as alternatives in the canonical model (spec §7).
5. **Meter comes from downbeats plus a human check.** No open model outputs a time signature.
6. **Key and chords are cross-checked in both directions.**
   - Audio-domain key and chord models are pop-trained.
   - Re-derive harmony symbolically from the transcription and flag disagreements rather than trusting either side.
7. **Evaluation data is the critical path.** Build the eval set (§7) before tuning anything.
8. **MIDI stays an adapter format, as the spec says.** MuScriptor and Basic Pitch emit MIDI or note lists. Adapters convert to the canonical note model immediately and keep confidence and provenance.

## 7. Evaluation plan

**Datasets (ground truth available):**

| Set | Content | Use |
|---|---|---|
| ChoraleBricks v1.1.0 ([Zenodo](https://zenodo.org/records/20849469), [TISMIR](https://transactions.ismir.net/articles/10.5334/tismir.252)) | Real, isolated SATB chorales, 13 wind instruments incl. trumpet, baritone, trombone, tuba; CC-BY 4.0; MusicXML/MIDI + note-level onset/offset CSV + f0 + audio-score alignment (verified 2026-09-25) | Closest thing to brass-band texture; close-voiced same-family polyphony; **primary brass benchmark** |
| URMP | Real chamber recordings, per-instrument stems incl. trumpet/horn/trombone/tuba | Per-stem vs mixture AMT; f0 trackers |
| PHENICX-Anechoic | Orchestral sections incl. horn and trumpet sections | Section polyphony, orchestral |
| CocoChorales | 350 h synthetic brass quartets | Large-scale synthetic; fine-tuning candidate |
| Slakh2100 (brass subset) | Synthetic pop/rock multitrack | Pop-context brass, separation+AMT |
| **Own synthetic brass band** | Public-domain brass-band / hymn / march MusicXML rendered with good brass samples, varied reverb/tempo/balance (spec §24) | Only source of full-band ground truth |
| **Own real recordings** | A few real brass-band recordings with hand-corrected scores | Final sanity check; small but real |

**Metrics (mir_eval unless noted):**
- note P/R/F1 (onset), onset+offset F1, multi-instrument F1 (onset+pitch+program)
- octave-error rate
- per-voice F1 after part assignment
- beat F-measure and downbeat F-measure (mir_eval.beat)
- chord MIREX scores incl. inversions (mir_eval.chord)
- key weighted score
- melody OA/RPA (mir_eval.melody)
- MV2H or MUSTER for score-level rhythm/voice correctness
- runtime (secondary).

## 8. Pipelines for the key experiment (§27), with real models

| Pipeline | Concrete chain |
|---|---|
| **A** direct | mix → MuScriptor-large (and separately YourMT3+) |
| **B** separate → per-stem | mix → BS-RoFormer SW (+ Mega-53 on "other") → per stem: MuScriptor (instrument-conditioned) / Basic Pitch / SwiftF0 (mono lines) / GAME (vocals) |
| **C** consensus on mix | mix → {MuScriptor-large, MuScriptor-medium, YourMT3+, Basic Pitch} → consensus engine |
| **D** separate → consensus | B's stems → {MuScriptor, Basic Pitch, (+ SwiftF0/CREPE for mono)} → consensus engine |

Common downstream for all four: Beat This! grid → quantizer → spelling (ps13s1) → canonical score → MusicXML. Downstream stays fixed so the pipelines differ only in note recovery.

## 9. Questions only the benchmark can settle

1. MuScriptor on the mix vs on separated stems: which gives better brass notes (A vs B)?
2. Does consensus (C/D) beat the best single model once model outputs are calibrated? How much does it help to keep alternatives?
3. Does Mega-53's brass stem help at all, or does its bleed (2.7–7.2 SDR) hurt?
4. MuScriptor medium vs large on the M5 Pro: accuracy vs runtime. Does quality degrade on songs longer than 5–8 minutes (chunking strategy)?
5. SwiftF0 vs torchcrepe on real cornet/euphonium lines; octave errors in the bass register.
6. Beat This! downbeat accuracy on marches (6/8), hymns (slow; DBN tempo floor) and test pieces with meter changes.
7. Own quantizer vs MuseScore import vs PM2S on MUSTER/MV2H.
8. consonance-ACE vs symbolic chord re-derivation on brass audio.
9. Which verification signal (chroma-DTW cost, same-AMT diff, NMF residual) actually localizes known injected transcription errors?
10. Does the process tap on macOS 26.6 capture Spotify cleanly, including across track changes?

## 10. Next steps (in order)

1. **Capture smoke test.** A tiny Swift process-tap CLI → `captured.wav` from Spotify (Milestone 1).
2. **Eval harness skeleton.** Python: canonical note model, mir_eval metrics, dataset loaders for ChoraleBricks and URMP.
3. **Adapters.** MuScriptor, YourMT3+, Basic Pitch, SwiftF0, Beat This!, each in its own uv venv behind a common CLI contract.
4. **Run Pipeline A vs B on ChoraleBricks + URMP** (Milestones 2, 4, 5), and write `docs/research/10-benchmark-results.md`.
5. **Synthetic brass-band set.** Starts in parallel with steps 3–4.
6. Consensus engine → voice separation / part assignment → minimal arranger (Milestones 6–7).

Watch list:
- ISMIR 2026 (8–12 Nov): Explore This!, masked-diffusion beat tracker weights, TUTTI weights.
- MIREX 2026 results (~15 Oct).
- Harmonica weights, if BandLab releases them.
