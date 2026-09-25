# 06 — Arrangement generation, macOS audio capture, MusicXML export

Desk research, 2026-09-25. Target: M5 Pro / 48 GB / macOS 26.6. Scope: (1) symbolic arrangement/orchestration models and constraint solvers, (2) system/app audio capture on macOS 26, (3) MusicXML generation and tooling. Every claim links to a source. "not found" means I could not verify it.

---

## Executive summary

| Area | PRIMARY | BACKUP |
|---|---|---|
| 1. Arrangement | **A hybrid built in-house.** A rule/CP-SAT arranger (OR-Tools CP-SAT) allocates melody, bass and harmony notes to the ~10 brass-band parts under hard range, voice-leading and doubling constraints. The **Anticipatory Music Transformer (AMT)** fills gaps where material is missing, such as inner parts, countermelodies and fills, with range constraints enforced by logit masking. | **REMI-z band arranger** (Ou et al., NeurIPS 2025): any-to-any re-instrumentation, weights apparently on HF (`LongshenOu/m2m_arranger`), but the model card is blank and has no license. **METEOR** (IJCAI-25) is an alternative for melody-preserving re-orchestration (Apache-2.0 weights, no code license). |
| 2. Capture | **A Swift helper CLI on a Core Audio process tap** (macOS 14.2+). On macOS 26 it taps by **`bundleIDs`** with `isProcessRestoreEnabled`, records native float32 at the device rate, and writes WAV/CAF. The Go orchestrator runs it as a subprocess. Metadata: **Spotify AppleScript** via `osascript`. | **audiotee** (MIT), used unchanged: PCM on stdout, PID include/exclude. Also **BlackHole** (GPL-3.0 source) routed through a Multi-Output Device. Metadata fallback: **media-control / mediaremote-adapter** (a Perl-trampoline workaround for the MediaRemote lockdown in 15.4+). |
| 3. MusicXML | **Python music21** (BSD-3) plus an **lxml post-pass**. Build the score at sounding pitch with custom brass-band `Instrument` subclasses. The post-pass adds `<instrument-sound>`, brackets and score order. Validate with `xmllint` against the **MusicXML 4.0 XSD (v4.0 tag)**, then render PDF and parts with the **MuseScore 4 CLI**. | **Verovio** for fast SVG previews and a second-opinion import. For a Go-native writer later, `go-muse/go-musicxml` (MIT, v0.1.0, 0 stars, marked as heavily AI-assisted): not production-ready. |

**Biggest risks**
1. No published model is trained on or evaluated for brass band. All generative candidates see only General MIDI brass (trumpet, trombone, tuba, French horn, brass section). Cornet, flugel, tenor horn, baritone and euphonium must be proxied, and idiom will be off. A deterministic arranger must own the output. Generative models can only propose material.
2. Among the generative models, only AMT (and probably REMI-z, since it has per-track instrument tokens) exposes a token structure where hard range limits can be enforced during decoding. ABC-based LLMs (NotaGen, ChatMusician, general LLMs) can only be repaired after generation. ComposerX reports out-of-range notes from GPT-4 ([arXiv 2404.18081](https://arxiv.org/html/2404.18081v1)).
3. Capture: Spotify through a process tap is **reported working**. It is not DRM-blocked in practice, but Spotify spawns new audio clients mid-session and a PID-snapshot tap then goes silent ([FineTune #373](https://github.com/ronitsingh10/FineTune/issues/373)). FairPlay content (Apple Music, Safari) is probably blocked. Needs a 10-second smoke test on this machine.
4. music21 has **no Cornet, Flugelhorn, Tenor/Alto Horn or Euphonium classes** and **does not write `<instrument-sound>`** (a TODO in the exporter), so MuseScore may import parts as generic instruments unless the post-pass fixes this.

---

## Part 1 — Symbolic arrangement / orchestration

### 1.1 Comparison table

| Model | Task fit | Released / last commit | Code lic. | Weights lic. | Weights | Range-constraint hook | Apple Silicon | Brass |
|---|---|---|---|---|---|---|---|---|
| **Anticipatory Music Transformer** ([arXiv 2306.08620](https://arxiv.org/abs/2306.08620), TMLR) | Infilling and accompaniment given fixed control events: "give me parts X,Y given melody+bass" | 2023; last main-branch commit 2024-03-18 ([repo](https://github.com/jthickstun/anticipation)) | Apache-2.0 | Apache-2.0 ([HF music-large-800k](https://huggingface.co/stanford-crfm/music-large-800k), [medium](https://huggingface.co/stanford-crfm/music-medium-800k)) | HF | **Yes.** Each note token is `instr*128+pitch` ([ops.py](https://github.com/jthickstun/anticipation/blob/main/anticipation/ops.py)). `sample.py` already masks logits per instrument (`instr_logits`, [sample.py](https://github.com/jthickstun/anticipation/blob/main/anticipation/sample.py)), so pitch-range masks per instrument are a small patch. | unknown (HF transformers GPT-2-style model, so MPS is plausible; not verified) | GM programs only (Lakh MIDI) |
| **REMI-z unified arranger** ([arXiv 2408.15176](https://arxiv.org/abs/2408.15176), NeurIPS 2025) | Any-to-any re-instrumentation ("band arrangement"), piano reduction, drum infill | Paper v5 Nov 2025; tokenizer repo 2026-09-18 ([Sonata165/REMI-z](https://github.com/Sonata165/REMI-z)) | MIT (tokenizer). The full training/inference code is linked from the [demo page](https://www.oulongshen.xyz/automatic_arrangement), but I found no public arranger repo: **not found** | **not stated** (blank HF card) | Probably [`LongshenOu/m2m_arranger`](https://huggingface.co/LongshenOu/m2m_arranger) and `m2m_pt` (same author; the link to the paper is **unconfirmed**) | Probably yes: per-track instrument tokens with bar-level instrument control. Not verified in code. | unknown | Fine-tuned on Slakh2100 (34 pitched instruments); pretrained on the Los Angeles MIDI dataset (405K files); 80M params ([paper §4.1](https://arxiv.org/pdf/2408.15176)) |
| **METEOR** ([arXiv 2409.11753](https://arxiv.org/abs/2409.11753), IJCAI-25) | Melody-preserving, texture-controllable re-orchestration (Transformer-VAE) | Last commit 2025-06-30 ([repo](https://github.com/dinhviettoanle/meteor)) | **none in repo** | Apache-2.0 ([HF](https://huggingface.co/dinhviettoanle/meteor)) | HF (`step_306000-model.pt`, vocab `symphonynet_full_multitrack...`) | Bar- and track-level texture control; no range hook found | CPU/CUDA switch in config; MPS unknown | Orchestral vocabulary (SymphonyNet-derived, inferred from the vocab filename). Training dataset: not found. |
| **AccoMontage-3 / Structured Arrangement** ([NeurIPS 2024 repo](https://github.com/zhaojw1998/Structured-Arrangement-Code)) | Lead sheet → piano accompaniment → multi-track orchestration with style prior | Last commit 2026-01-17 | MIT | not stated (Google Drive) | [Google Drive](https://drive.google.com/file/d/1mk24C2uKcjmQ-jZQ0CxiFQm0lm3czSwC/view?usp=sharing) | Instrument choice per track; no range hook found | **CPU-only as pinned.** It requires PyTorch 1.10.1 on Python ≤3.9, and MPS first shipped in PyTorch 1.12 ([PyTorch blog](https://pytorch.org/blog/introducing-accelerated-pytorch-training-on-mac/)). | Trained on LMD + Slakh2100 |
| **Q&A** ([arXiv 2306.01635](https://arxiv.org/abs/2306.01635), IJCAI 2023) | Re-instrumentation and orchestration via content/style queries (predecessor of AccoMontage-3's orchestrator) | 2023 | not found | not found | not found | — | unknown | Slakh-style GM |
| **SymphonyGen** ([arXiv 2604.25498](https://arxiv.org/abs/2604.25498), ISMIR 2026) | Orchestral generation from a harmony skeleton / short score ("outline control") | Apr 2026, rev. Aug 2026 | **not found** | **not found** | not found | Harmony-skeleton conditioning; instrumentation control not described | unknown | Orchestral |
| **UOT-IR** ([arXiv 2608.00576](https://arxiv.org/abs/2608.00576), ISMIR 2026) | Routing high-polyphony scores into a **fixed slot budget** with orchestration-compatibility and playability terms | Aug 2026 | not found | not found | not found | Explicitly a constrained allocation problem. Conceptually the closest paper to "reduce to 10 brass parts" | n/a | not reported |
| **NotaGen / NotaGen-X** ([arXiv 2502.18008](https://arxiv.org/abs/2502.18008), IJCAI-25) | Prompted classical score generation ("period-composer-instrumentation"). **Not an arranger**: no lead-sheet conditioning | Last commit 2025-04-21 ([repo](https://github.com/ElectricAlexis/NotaGen)) | MIT | MIT ([HF](https://huggingface.co/ElectricAlexis/NotaGen)) | HF, 110M/244M/516M | Post-hoc only (ABC patches). NotaGen-X dropped key augmentation for "more reasonable instrument range" ([README](https://github.com/ElectricAlexis/NotaGen)) | Reported working with a fix: MPS memory leak without `torch.no_grad()` ([#45](https://github.com/ElectricAlexis/NotaGen/issues/45)). Large needs ≥24 GB. | The paper admits orchestral output "still lags behind" ([arXiv](https://arxiv.org/html/2502.18008v5)) |
| **ChatMusician** ([arXiv 2402.16153](http://arxiv.org/abs/2402.16153)) | LLaMA2-7B continued-pretrained on ABC; chord/melody-conditioned generation | Last commit 2024-03-29 ([repo](https://github.com/hf-lin/ChatMusician)) | none in repo | Card says MIT ([HF](https://huggingface.co/m-a-p/ChatMusician)), but it is **LLaMA2-derived**, so the Llama 2 licence may also apply | HF | Post-hoc only | unknown | The card warns that training data is largely Irish-style ABC |
| **MuseCoco** ([microsoft/muzic](https://github.com/microsoft/muzic/tree/main/musecoco)) | Text/attributes → multitrack MIDI; "instrument" and "pitch range" are attributes | muzic repo pushed 2026-08-05 | MIT (muzic) | not stated | HF (per README) | Attribute-level (soft), not per-note | unknown | GM |
| **MusicLang predict** ([repo](https://github.com/MusicLang/musiclang_predict)) | Chord-conditioned multitrack generation | Last push 2024-03-25 | GPL-3.0 | GPL-3.0 ([musiclang-4k](https://huggingface.co/musiclang/musiclang-4k)) | HF | — | unknown | GM |
| **Composer's Assistant 2** ([repo](https://github.com/m-malandro/composers-assistant-REAPER)) | Multitrack infilling inside REAPER | Last push 2025-06-16 | MIT | not checked | — | — | unknown | GM |
| **DeepBach** ([repo](https://github.com/Ghadjeres/DeepBach)) / **Coconet** ([arXiv 1903.07227](https://arxiv.org/abs/1903.07227), [repo](https://github.com/czhuang/coconet)) | 4-voice chorale infilling (Gibbs sampling) with positional constraints | DeepBach last push 2022 | MIT / — | trained on Bach chorales | — | DeepBach is "steerable"; per-voice ranges are implicit | CPU is fine (small) | SATB only; could inform horn/baritone inner-voice filling |
| **Live Orchestral Piano** ([arXiv 1609.01203](https://arxiv.org/abs/1609.01203)) + **Projective Orchestral Database** ([arXiv 1810.08611](https://arxiv.org/abs/1810.08611)) | Piano → orchestra (cRBM), with a paired piano/orchestra dataset | 2016–2017 | — | — | — | — | — | Historical; POD is the only piano↔orchestra parallel corpus found |
| **General LLMs (Claude/GPT) with ABC/MusicXML/LilyPond** | Planning, section-level texture decisions, explanation | — | — | — | API | None. Range violations are documented ([ComposerX](https://arxiv.org/html/2404.18081v1)). LilyBench finds "executable LilyPond generation is achievable in zero-shot" but structural understanding is weak ([arXiv 2606.08722](https://arxiv.org/abs/2606.08722)). Libretto proposes an LLM-native grammar with onset slots and voices ([arXiv 2606.22708](https://arxiv.org/abs/2606.22708)). | n/a | none |

Benchmark comparability: REMI-z reports Note F1 / Notei F1 / I-IoU / VER / Mel-F1 on the Slakh2100 test split ([paper Table 1](https://arxiv.org/pdf/2408.15176)). METEOR, AccoMontage-3 and Q&A use different datasets and mostly subjective listening tests, so **no cross-paper numbers are comparable**. No paper evaluates brass band.

### 1.1a Per-candidate detail (serious candidates)

**Anticipatory Music Transformer (AMT)**
- Architecture: decoder-only causal Transformer (GPT-2-style via HF transformers) over an "arrival-time" event encoding. Each event is (time, duration, note) with note = `instr*128+pitch`. Controls are interleaved ahead of events ("anticipation") ([arXiv](https://arxiv.org/abs/2306.08620), [vocab.py](https://github.com/jthickstun/anticipation/blob/main/anticipation/vocab.py)).
- Release: Jun 2023 (TMLR). Last main-branch commit 2024-03-18; repo pushed 2026-07-19 ([repo](https://github.com/jthickstun/anticipation)).
- Code Apache-2.0; weights Apache-2.0. Sizes: `music-large-800k` has 780,139,520 params (HF safetensors metadata); small and medium sizes not found in metadata ([HF](https://huggingface.co/stanford-crfm/music-large-800k)).
- Training data: Lakh MIDI. Benchmarks: human evaluation reports accompaniments with musicality "similar" to human-composed music over 20-second clips ([arXiv](https://arxiv.org/abs/2306.08620)). No per-instrument or brass numbers.
- Hardware / VRAM / inference speed: not found. Apple Silicon: unknown (plain PyTorch/transformers, so MPS is plausible).
- Strengths: true infilling with fixed controls; permissive licences; token layout allows exact per-instrument pitch masks.
- Weaknesses: GM-only instruments; performance-MIDI timing (needs quantisation downstream); no section or texture control; unmaintained since 2024.
- Brass suitability: can generate trumpet/trombone/tuba/horn proxies under hard range masks. Brass-band idiom not learned.

**REMI-z unified arranger (Ou et al.)**
- Architecture: 80M-parameter decoder-only Transformer (768 hidden, 12 layers, 16 heads, 2048 context). Pre-trained with next-token prediction, then fine-tuned on segment-level reconstruction with separate instrument, content and history streams. REMI-z tokenization keeps each track contiguous within a bar ([paper §3–4.1](https://arxiv.org/pdf/2408.15176)).
- Release: arXiv Aug 2024, NeurIPS 2025 camera-ready Nov 2025. Tokenizer repo updated 2026-09-18 ([Sonata165/REMI-z](https://github.com/Sonata165/REMI-z), MIT).
- Weights: [`LongshenOu/m2m_arranger`](https://huggingface.co/LongshenOu/m2m_arranger) (uploaded 2024-08-14, 13 days before arXiv v1, which supports the attribution) plus `m2m_pt`, `m2m_pianist`, `m2m_drummer`. The card is an empty template with **no licence**.
- Training data: Los Angeles MIDI dataset (405K files) for pre-training; Slakh2100 (1,289 train / 270 val / 151 test) for fine-tuning.
- Benchmarks, band arrangement on the Slakh2100 test split ([paper Table 1](https://arxiv.org/pdf/2408.15176)). I-IoU↑ / VER↓ / Note F1↑ / Notei F1↑ / Mel F1↑:

  | Model | I-IoU | VER | Note F1 | Notei F1 | Mel F1 |
  |---|---|---|---|---|---|
  | Transformer-VAE | 97.5 | 35.0 | 49.5 | 40.0 | 24.7 |
  | Transformer w/ REMI+ | 95.0 | 18.2 | 94.4 | 76.0 | 68.8 |
  | Transformer w/ REMI-z | 99.5 | 9.9 | 97.8 | 77.5 | 77.8 |
  | + pre-training (ours) | 99.8 | 7.6 | 97.5 | 87.0 | 84.5 |

  Column mapping reconstructed from the PDF text extraction; verify against the PDF.
- Hardware: trained on 4× RTX A5000 and fine-tuned on 1× A40. At 80M params, inference should be trivial on M5 Pro, but speed and MPS are not reported.
- Strengths: any-to-any instrumentation at inference, conditioned on content, which is exactly "re-voice this multitrack for these instruments"; strong objective results.
- Weaknesses: licence unknown; undocumented weights; 1-bar segments, so long-range coherence depends on the history stream; GM-only.
- Brass suitability: can target trumpet/trombone/tuba/horn tracks; brass not evaluated separately.

**METEOR**
- Architecture: Transformer-VAE (builds on MuseMorphose) with bar- and track-level texture attributes and melody conditioning ([arXiv](https://arxiv.org/abs/2409.11753), [repo](https://github.com/dinhviettoanle/meteor)).
- Release: Sep 2024; IJCAI-25. Last commit 2025-06-30.
- Code licence: **none**. Weights: Apache-2.0 ([HF](https://huggingface.co/dinhviettoanle/meteor)).
- Training data: not found in README. The vocab filename suggests SymphonyNet-derived data.
- Benchmarks: paper reports subjective and objective gains over style-transfer baselines. Numbers not extracted; not comparable to REMI-z.
- Hardware: CPU or CUDA via config; Python 3.9.2. Speed and VRAM not found. Apple Silicon unknown.
- Strengths: explicit melody fidelity; per-bar and per-track texture control (useful for "cornets sustain, horns after-beats").
- Weaknesses: no code licence; homophonic-texture assumption; orchestral, not band, vocabulary.
- Brass suitability: orchestral brass tracks only; no brass-band instruments.

### 1.2 Brass-band specifics
- No brass-band-specific generative model or dataset was found. A search for brass-band arrangement ML returned only generic arrangement work ([search trace: AccoMontage2](https://arxiv.org/pdf/2209.00353), [Q&A](https://arxiv.org/pdf/2306.01635)).
- **GM proxy mapping** for any model with GM instrument tokens. The table uses 1-based GM program numbers. AMT's `instr` is the 0-based MIDI `program_change` value, with drums (channel 9) encoded as 128 ([convert.py](https://github.com/jthickstun/anticipation/blob/main/anticipation/convert.py)), so trumpet = 56. Enforce the range of the **real** instrument (table in §3.4), not the proxy's.
- **Slakh2100 (the fine-tune/eval set for REMI-z and AccoMontage-3):** "Brass" is a GM *class* (programs 56–63: trumpet, trombone, tuba, muted trumpet, French horn, brass section, synth brass 1/2), and per-stem metadata keeps `program_num`, so individual brass instruments are distinguishable ([slakh-utils GM table](https://github.com/ethman/slakh-utils/blob/master/midi_inst_values/general_midi_inst_0based.txt), [metadata README](https://github.com/ethman/slakh-utils)). No cornet, flugel, tenor horn or euphonium exists anywhere in GM.

  | Brass-band part | GM proxy (program) |
  |---|---|
  | Eb soprano cornet, Bb cornets (solo/repiano/2nd/3rd) | Trumpet (57) |
  | Flugelhorn | Trumpet (57), or Brass Section (62) if the model has no flugel concept |
  | Eb tenor horns (solo/1st/2nd) | French Horn (61) |
  | Baritones, euphoniums | Trombone (58) |
  | Tenor trombones, bass trombone | Trombone (58) |
  | Eb/Bb basses | Tuba (59) |

- Brass-band texture is closer to **4–5-part choral writing duplicated across sections** (cornets / horns+flugel+baritones as an "alto choir" / trombones+euphs / basses). The Music Company's scoring guide describes flugel, tenor horns and baritones as forming "a large alto" section, and notes the modern pairing of flugel with solo horn ([scoring guide extract](https://www.themusiccompanyshop.com/wp-content/uploads/2016/12/Scoring-Sample-book-extract.pdf), p. ~8–9). This favours a rule-based voice allocator over an end-to-end model.

### 1.3 Constraint-based voice leading
- There is a long line of constraint-programming harmonisation work (a survey: [Musical Harmonization with Constraints](https://www.researchgate.net/publication/220202301_Musical_Harmonization_with_Constraints_A_Survey); a 2021 ISMIR LBD four-part harmoniser: [ISMIR 2021 LBD](https://archives.ismir.net/ismir2021/latebreaking/000018.pdf)). **No maintained open-source MiniZinc/CP-SAT harmoniser was found** on GitHub. The only hit, [Voice-Leading-Solver](https://github.com/ReasonMaster44/Voice-Leading-Solver), has 0 stars.
- **OR-Tools CP-SAT** (Apache-2.0, v9.15, 2026-01-12, [repo](https://github.com/google/or-tools)) has Python bindings and **Go bindings** (`ortools/sat/go/cpmodel`, [tree](https://github.com/google/or-tools/tree/main/ortools/sat/go/cpmodel)). The Go path needs cgo and a native OR-Tools build (Bazel-based), so Python is the cheaper home.
- Formulation sketch: one integer pitch variable per (part, chord-slot). Hard constraints: written range per part; chord-tone membership (from the chord/harmony stage); melody pinned to its designated part(s); no voice crossing within a section; spacing ≤ an octave between adjacent upper voices; bass part = the detected bass line (octave-displaced to fit Eb/Bb bass). Soft constraints (objective): minimise voice movement, penalise parallel 5ths/8ves between outer voices, prefer completing the triad (3rd before 5th), and prefer tessitura sweet spots (the amateur range, inside the professional range).

### 1.4 Recommended hybrid
1. **Plan (LLM, optional).** Given the analysis JSON (sections, melody, bass, chords, countermelodies from earlier stages), Claude produces a *structured plan*: per section, which part carries the melody, texture type (chorale / melody+accomp / tutti), dynamics and doubling. The LLM emits only JSON, never notes, so range errors cannot originate here.
2. **Allocate (deterministic).** Map the plan to parts. Melody goes to its part (for example solo cornet, with octave shifts to fit the range). Bass goes to Eb/Bb bass with octave doubling. Detected countermelodies go to euphonium or solo horn.
3. **Harmonise (CP-SAT).** Fill inner voices from the chord track under the constraints in §1.3.
4. **Embellish (AMT, optional).** For bars flagged "sparse", run AMT infilling with melody+bass+CP-SAT voices as fixed controls, and **mask logits** to the allowed `(instr, pitch)` set per proxy instrument.
5. **Repair and validate.** Re-check ranges and part limits. Any violation is repaired by octave displacement or re-solved by CP-SAT with the generated notes as soft targets.
6. REMI-z / METEOR remain experimental alternatives for step 4, pending licence and card clarification (REMI-z) or a code licence (METEOR).

---

## Part 2 — macOS audio capture (macOS 26, Apple Silicon)

### 2.1 Comparison table

| Option | Min macOS | Permission (TCC) | Per-app | Format | Licence | Last activity | Notes |
|---|---|---|---|---|---|---|---|
| **Core Audio process tap** (`AudioHardwareCreateProcessTap` + `CATapDescription` + aggregate device) | 14.2 ([API doc](https://developer.apple.com/documentation/coreaudio/audiohardwarecreateprocesstap(_:_:))) | "System Audio Recording Only". Needs `NSAudioCaptureUsageDescription`; prompt on first record ([Apple sample](https://developer.apple.com/documentation/coreaudio/capturing-system-audio-with-core-audio-taps)) | Yes: `processes`, global-minus-excluded, and on **macOS 26 `bundleIDs` + `isProcessRestoreEnabled`** ([CATapDescription](https://developer.apple.com/documentation/coreaudio/catapdescription), [bundleIDs](https://developer.apple.com/documentation/coreaudio/catapdescription/bundleids), [isProcessRestoreEnabled](https://developer.apple.com/documentation/coreaudio/catapdescription/isprocessrestoreenabled)) | Read `kAudioTapPropertyFormat`; mono/stereo mixdown options; optional mute-when-tapped ([Apple sample](https://developer.apple.com/documentation/coreaudio/capturing-system-audio-with-core-audio-taps)) | Apple API | — | **Preferred.** Narrower permission than screen recording. |
| **ScreenCaptureKit** (`SCStreamConfiguration.capturesAudio`, `excludesCurrentProcessAudio`, `SCContentFilter` with included apps) | 13.0 ([capturesAudio](https://developer.apple.com/documentation/screencapturekit/scstreamconfiguration/capturesaudio), [excludesCurrentProcessAudio](https://developer.apple.com/documentation/screencapturekit/scstreamconfiguration/excludescurrentprocessaudio)) | "Screen & System Audio Recording". Sequoia added periodic (monthly) re-confirmation prompts ([9to5Mac](https://9to5mac.com/2024/08/14/macos-sequoia-screen-recording-prompt-monthly/), [Apple forum](https://developer.apple.com/forums/thread/761443)) | Yes (app filter, but tied to a display filter) | Sample rate **only 8/16/24/48 kHz**, default 48k ([sampleRate](https://developer.apple.com/documentation/screencapturekit/scstreamconfiguration/samplerate)); 1 or 2 channels ([channelCount](https://developer.apple.com/documentation/screencapturekit/scstreamconfiguration/channelcount)) | Apple API | — | Secondary report: all-zero audio buffers when screen-recording permission is missing ([ModelPiper blog](https://modelpiper.com/blog/capture-app-audio-mac-no-drivers), not primary). Granting only "System Audio Recording Only" does **not** make SCK audio capture work. OBS maintainers explain SCK always performs a screen recording, and apps cannot request the audio-only permission through SCK ([obs-studio #10401](https://github.com/obsproject/obs-studio/issues/10401), closed). |
| **AudioCap** (sample app) | 14.4 | Same as tap; uses a **private TCC API** to pre-check/request (optional) ([README](https://github.com/insidegui/AudioCap)) | PID | Tap format → `AVAudioFile` | BSD-2-Clause | last commit 2025-08-07 | Best reference code for the permission probe ([AudioRecordingPermission.swift](https://github.com/insidegui/AudioCap/blob/main/AudioCap/ProcessTap/AudioRecordingPermission.swift)) |
| **audiotee** (CLI) | 14.2 | Same. **Permission is attributed to the terminal**; iTerm may not prompt, so pre-grant ([README §Permissions](https://github.com/makeusabrew/audiotee)) | `--include-processes/--exclude-processes` (PIDs), `--mute` | Raw PCM to stdout; default **mono float32 at device rate**; `--stereo`; `--sample-rate` resamples **to 16-bit int** | MIT | last commit 2026-03-31; no releases | "Only supports default output device"; including a PID that is not playing "will probably fail" |
| **BlackHole** (virtual device) | — | Microphone permission for the reading app | No (device-level; route with a Multi-Output Device) | Up to 2/16/64 ch, device rate | Source **GPL-3.0**; official binaries all-rights-reserved ([LICENSE](https://github.com/ExistentialAudio/BlackHole/blob/master/LICENSE)) | pushed 2026-09-22 | Kernel-less HAL driver install; robust fallback if taps break |

### 2.2 Is Spotify capture DRM-blocked?
**Conclusion: not in practice for the Spotify desktop app. Reported working; not tested here.**
- **Evidence for working (primary):** FineTune (9.4k-star per-app volume/EQ app built on process taps, GPL-3.0, [repo](https://github.com/ronitsingh10/FineTune)) processes Spotify's audio through a muted-when-tapped tap and re-renders it. That only works if the tap receives Spotify PCM. Its issue [#373](https://github.com/ronitsingh10/FineTune/issues/373) shows silence *only* when Spotify switches to a video variant and "spin[s] up a new CoreAudio audio client after the tap was created". That is a PID-snapshot problem, not DRM. (Routing Spotify through BlackHole is also a commonly *proposed* workflow, e.g. [contrapunk #102](https://github.com/contrapunk-audio/contrapunk/issues/102), but that is a feature proposal, not evidence.)
- **Evidence for blocking (secondary only):** a vendor blog claims "Core Audio Taps respect DRM… Apple Music or Netflix [are] not available" and extends this to Spotify ([ModelPiper](https://modelpiper.com/blog/capture-app-audio-mac-no-drivers)). There is no primary source for the Spotify part.
- **FairPlay content:** in an Apple developer-forum thread, a developer reports that audio of FairPlay-protected content in Safari/Mac cannot be recorded, while on iOS it can ([thread 816464](https://developer.apple.com/forums/thread/816464)). Apple's older QA1970 says FairPlay Streaming protects only the *video* portion ([QA1970](https://developer.apple.com/library/archive/qa/qa1970/_index.html)). Apple Music behaviour is therefore **uncertain, probably blocked**. Test it.
- **Mitigation for respawning clients:** on macOS 26, create the tap with `bundleIDs = ["com.spotify.client"]` ("each String holds the bundle ID of a process to tap or exclude") and `isProcessRestoreEnabled = true` ("save tapped processes by bundle ID when they exit, and restore them to the tap when they start up again"). Both are new in macOS 26.0 ([bundleIDs](https://developer.apple.com/documentation/coreaudio/catapdescription/bundleids), [isProcessRestoreEnabled](https://developer.apple.com/documentation/coreaudio/catapdescription/isprocessrestoreenabled)). The docs cover process exit and restart; whether they also cover a *new audio client inside a running process* (the FineTune #373 case) is untested. On 14.x/15.x, watch `kAudioHardwarePropertyProcessObjectList` and rebuild the tap.
- Terms of service: capturing Spotify output for personal analysis is a ToS question, not a technical one. Out of scope, but worth noting.

### 2.3 Sample rate / format
- Taps deliver the **output device's** format (`kAudioTapPropertyFormat`), float32. Spotify's stream sample rate: **not found** in a primary source (commonly assumed 44.1 kHz). If the source rate differs from the output device's nominal rate, **CoreAudio has already resampled** before the tap. For fidelity, set the output device to 44.1 kHz in Audio MIDI Setup during capture, or accept 48 kHz. Avoid audiotee's `--sample-rate`, which drops to 16-bit. Avoid ScreenCaptureKit, which cannot do 44.1 kHz.
- Record native float32 WAV/CAF and resample offline in the Python analysis stage if a model wants 16/22.05/44.1 kHz.

### 2.4 Go integration
- `progrium/darwinkit` (MIT) has `coreaudio`/`avfoundation` packages, but its last push was 2025-03-08 ([repo](https://github.com/progrium/darwinkit)), and I found no process-tap or ScreenCaptureKit coverage. **Recommendation:** a small **Swift CLI** (`brasscribe-capture --bundle-id com.spotify.client --out x.caf --max-seconds N`), modelled on AudioCap and audiotee and invoked from Go. Keep cgo out of the orchestrator.
- TCC attribution: a bare CLI's prompt is attributed to the responsible process, which is the terminal ([audiotee README](https://github.com/makeusabrew/audiotee)). For a stable grant independent of the terminal, ship the helper inside a minimal `.app` bundle with `NSAudioCaptureUsageDescription` and launch it via `open -W`, or embed an Info.plist (`-sectcreate __TEXT __info_plist`). **Whether the embedded-plist route satisfies TCC for audio capture is unverified.**

### 2.5 Now-playing metadata
- **Spotify AppleScript** (`osascript -e 'tell application "Spotify" to …'`): `name/artist/album/duration of current track` (duration in ms), `player position` (seconds), `player state` ([example](https://willcodefor.beer/posts/asdur), [simonbs Spotify.applescript](https://github.com/simonbs/spotify-controls-api/blob/master/Spotify.applescript)). Needs Automation (Apple Events) permission. `player position` at capture start plus track id gives alignment and naming.
- **MediaRemote:** since macOS 15.4, `mediaremoted` checks entitlements, so unentitled apps get nothing ([LyricFever #94](https://github.com/aviwad/LyricFever/issues/94)). **mediaremote-adapter** (BSD-3) works around this by loading a helper framework into `/usr/bin/perl`, which is allowed. Tested up to macOS 27.0 beta as of 2026-09-04 ([README](https://github.com/ungive/mediaremote-adapter)). CLI: `media-control stream` ([ungive/media-control](https://github.com/ungive/media-control)). It is a fragile workaround that Apple could close, so it's a fallback only.

---

## Part 3 — MusicXML / notation tooling

### 3.1 Comparison table

| Tool | Role | Licence | Latest | Transposing-instrument support | Notes |
|---|---|---|---|---|---|
| **music21** ([repo](https://github.com/cuthbertLab/music21)) | Build score → MusicXML | BSD-3-Clause | v10.5.0, 2026-06-17 | Writes `<transpose>` (diatonic/chromatic/octave-change) from `Instrument.transposition` ([m21ToXml.py `intervalToXmlTranspose`/`setTranspose`](https://github.com/cuthbertLab/music21/blob/master/music21/musicxml/m21ToXml.py)). On export it calls `toWrittenPitch(inPlace=True)` on each part. | **Gaps:** no Cornet/Flugelhorn/TenorHorn/Euphonium classes (`BrassInstrument` subclasses are only Horn, Trumpet, Trombone, Tuba, [instrument.py](https://github.com/cuthbertLab/music21/blob/master/music21/instrument.py)). `<instrument-sound>` not written ("TODO: instrument-sound" in m21ToXml.py). |
| **partitura** ([repo](https://github.com/CPJKU/partitura)) | Analysis-oriented I/O | Apache-2.0 | v1.9.0, 2026-05-25 | **Imports** `<transpose>` ([importmusicxml.py](https://github.com/CPJKU/partitura/blob/main/partitura/io/importmusicxml.py)); the exporter has no transpose handling ([exportmusicxml.py](https://github.com/CPJKU/partitura/blob/main/partitura/io/exportmusicxml.py)) | Not suited for writing transposed brass parts |
| **MuseScore Studio 4 CLI** ([handbook](https://handbook.musescore.org/appendix/command-line-usage)) | Render PDF/PNG/SVG/MIDI/audio, extract parts, import sanity check | GPL-3.0 ([LICENSE.txt](https://github.com/musescore/MuseScore/blob/master/LICENSE.txt)) | v4.7.5, 2026-09-08 | Full | `-o out.pdf`; `-P/--export-score-parts` appends parts to the PDF; `--score-parts` writes per-part mscz; `-j job.json` batch; `-f` force. Converter mode runs without a GUI. The macOS binary is `/Applications/MuseScore 4.app/Contents/MacOS/mscore` (standard bundle path; not verified on this machine). Built-in **Brass Band score order** (below). |
| **Verovio** ([repo](https://github.com/rism-digital/verovio)) | Fast MusicXML/MEI → SVG engraving; Python and JS toolkits | LGPL-3.0 | 6.3.0, 2026-08-19 | Imports MusicXML | Good for web previews and CI snapshots |
| **go-muse/go-musicxml** ([repo](https://github.com/go-muse/go-musicxml)) | Typed Go MusicXML 4.0 read/write/validate, MXL | MIT | v0.1.0; last commit 2026-08-15; 0 stars | Types generated from the official 4.0 XSD | README: "developed with substantial AI assistance… pre-1.0" |
| jonasrichard/go-musicxml ([repo](https://github.com/jonasrichard/go-musicxml)) | Go MusicXML 4.0 | Apache-2.0 | 2026-05-05; 0 stars | unknown | — |
| alda-lang/go-musicxml ([repo](https://github.com/alda-lang/go-musicxml)) | Go MusicXML | EPL-2.0 | 2021 | unknown | Stale |

### 3.2 MusicXML 4.0 transposition model
- `<attributes><transpose>` "represents what must be added to a written pitch to get a correct sounding pitch": `<diatonic>`, `<chromatic>`, optional `<octave-change>`, `<double>`, and a `number` attribute for per-staff transposition ([musicxml.xsd](https://github.com/w3c-cg/musicxml/blob/gh-pages/schema/musicxml.xsd)).
- New in 4.0: `<concert-score/>` in `<defaults>` plus `<for-part>` lets a single file hold a concert-pitch score with transposed-part instructions (same XSD).
- **Schema versions:** the only release is **v4.0** (2021-06-03, [releases](https://github.com/w3c-cg/musicxml/releases)). The `gh-pages` branch XSD is labelled "Version 4.1 Draft". **Validate against the v4.0 tag.**
- Standard sound IDs exist for `brass.cornet`, `brass.cornet.soprano`, `brass.flugelhorn`, `brass.alto-horn` (use this for the Eb tenor horn), `brass.baritone-horn`, `brass.euphonium`, `brass.trombone.tenor`, `brass.trombone.bass`, `brass.tuba` ([sounds.xml](https://github.com/w3c-cg/musicxml/blob/gh-pages/schema/sounds.xml)).

### 3.3 Brass-band score order and clefs
- Standard instrumentation: 1 Eb soprano cornet; solo (×4, including principal), repiano, 2nd (×2) and 3rd (×2) Bb cornets; 1 flugel; 3 Eb tenor horns (solo/1st/2nd); 2 baritones; 2 euphoniums; 2 tenor trombones plus bass trombone; 2 Eb and 2 Bb basses; percussion ([US Open Brass](https://www.usopenbrass.org/bbinfo.php)).
- Score order used by **MuseScore's built-in "Brass Band" order**: cornets → flugelhorn + alto (tenor) horns → baritones → trombones → euphoniums → tubas (basses) → percussion ([orders.xml `brass-band`](https://github.com/musescore/MuseScore/blob/main/share/instruments/orders.xml)). Some published sources place euphoniums before trombones ([US Open Brass](https://www.usopenbrass.org/bbinfo.php)), so make it configurable. Default to MuseScore's order.
- "Modern day brass band parts from the soprano cornet through to the Bb bass (with the exception of the bass trombone) are all written out in transposed treble clef" ([The Music Company scoring guide](https://www.themusiccompanyshop.com/wp-content/uploads/2016/12/Scoring-Sample-book-extract.pdf), text p. ~5).

### 3.4 Transpositions and ranges (MuseScore `instruments.xml`, one primary source)
Values from [instruments.xml](https://github.com/musescore/MuseScore/blob/main/share/instruments/instruments.xml). `aP` is the amateur range and `pP` the professional range, as MIDI numbers. **They are concert (sounding) pitch.** Evidence from the data itself: `baritone-horn` (F clef, no transposition) and `baritone-horn-treble` (−14) have identical ranges, as do the euphonium and trombone clef variants. Converting to written pitch, Bb cornet 52–79, Eb soprano 57–84 and Eb alto horn 45–72 all come out as written F#3–A5 (amateur), and the pro ranges as written F#3–C6. So the CP-SAT model and AMT logit masks, which both work in sounding MIDI pitch, can use these numbers directly. `diat/chrom` go straight into `<transpose>`.

| Part | MuseScore id | diat / chrom | Clef | aP | pP | Sound id |
|---|---|---|---|---|---|---|
| Eb soprano cornet | `eb-cornet` | +2 / +3 | G | 57–84 | 57–87 | brass.cornet.soprano |
| Bb cornet (solo/rep/2/3) | `bb-cornet` | −1 / −2 | G | 52–79 | 52–82 | brass.cornet |
| Flugelhorn | `flugelhorn` | −1 / −2 | G | 52–79 | 52–82 | brass.flugelhorn |
| Eb tenor horn | `eb-alto-horn` | −5 / −9 | G | 45–72 | 45–75 | brass.alto-horn |
| Baritone (treble) | `baritone-horn-treble` | −8 / −14 | G | 40–67 | 40–70 | brass.baritone-horn |
| Euphonium (treble) | `euphonium-treble` | −8 / −14 | G | 40–70 | 34–74 | brass.euphonium |
| Tenor trombone (treble) | `trombone-treble` | −8 / −14 | G | 40–71 | 36–74 | brass.trombone |
| Bass trombone | `bass-trombone` | 0 / 0 | F | 32–65 | 21–77 | brass.trombone.bass |
| Eb bass (treble) | `eb-tuba-treble` | −12 / −21 | G | 26–64 | 24–72 | brass.tuba |
| Bb bass (treble) | `bb-tuba-treble` | −15 / −26 | G | 28–58 | 22–72 | brass.tuba |

Use `aP` as a soft preference and `pP` as the hard limit in the CP-SAT model. Spot-check against a brass-band arranging text before relying on it; MuseScore's generic tuba ranges may not reflect brass-band practice.

### 3.5 Where MusicXML generation should live
**Python (music21 + lxml).** Reasons:
- music21 already handles measures, ties, beaming, voices, key/time signatures and `<transpose>` written-pitch conversion. The Go libraries are v0.1.0 with no users.
- The arrangement stage (CP-SAT via Python OR-Tools, AMT) is Python anyway, so generating MusicXML in the same process avoids a second score model.
- Go stays the orchestrator. It calls `python -m brasscribe.export`, then `XML_CATALOG_FILES=schema/catalog.xml xmllint --noout --nonet --schema schema/musicxml.xsd out.musicxml`, then `mscore -o score.pdf -P`. The XSD imports `xml.xsd` and `xlink.xsd` by **absolute URL** (`http://www.musicxml.org/xsd/...`, lines 40–41). The bundled `catalog.xml` in the [schema dir](https://github.com/w3c-cg/musicxml/tree/v4.0/schema) maps those URLs to local copies, so offline validation needs the catalog.

Implementation rules:
1. Build every part at **sounding pitch**, set `score.atSoundingPitch = True` explicitly, and attach custom `Instrument` subclasses (`BbCornet(transposition=Interval('M-2'))`, `EbSopranoCornet(Interval('m3'))`, `EbTenorHorn(Interval('M-6'))`, `Baritone/Euphonium/TromboneTreble(Interval('M-9'))`, `EbBass(Interval('M-13'))`, `BbBass(Interval('M-16'))`, i.e. Bb two octaves plus a whole tone). music21 transposes to written pitch exactly once on export.
2. lxml post-pass: insert `<instrument-sound>` per `<score-instrument>`; add `<part-group>` brackets per section; order parts; set part names and abbreviations ("Sop. Cnt.", "Solo Cnt.", "Rep.", …); optionally add `<concert-score/>`.
3. **Round-trip test in CI:** export → re-import with music21 → `toSoundingPitch()` must equal the original. Also run MuseScore `-o x.musicxml` re-export and diff sounding pitches, since MuseScore is the real consumer.

---

## Open questions (only benchmarking can settle)
1. Does AMT with range-masked decoding produce idiomatic inner parts for cornet/horn-proxy textures, or does CP-SAT alone sound better? Blind A/B on 5–10 songs.
2. Are the REMI-z HF weights (`m2m_arranger`) the paper's band-arrangement model, and what licence applies? Ask the author ([oulongshen@u.nus.edu](https://www.oulongshen.xyz/automatic_arrangement)).
3. METEOR's training data and code licence (the repo has none). Does it run on MPS?
4. Capture smoke test on macOS 26.6: tap by `bundleIDs` on Spotify for 10 s, including a track change and a video-variant switch. Is the audio non-silent and gapless? Repeat with Apple Music to confirm the FairPlay behaviour.
5. Does a helper `.app` or embedded-Info.plist CLI obtain a persistent "System Audio Recording Only" grant independent of the launching terminal?
6. Output device at 44.1 vs 48 kHz: measurable effect on downstream transcription accuracy?
7. MuseScore import of music21-generated MusicXML: are brass-band instruments recognised from `<instrument-sound>` alone, or do part names and MIDI programs also matter?
8. Do MuseScore's `instruments.xml` ranges match brass-band practice, especially the soprano cornet top and the Eb/Bb bass pedal range? (They are concert pitch, see §3.4.)

---

## References
- Anticipatory Music Transformer: https://arxiv.org/abs/2306.08620 · https://github.com/jthickstun/anticipation · https://huggingface.co/stanford-crfm/music-large-800k
- REMI-z / unified arrangement: https://arxiv.org/abs/2408.15176 · https://www.oulongshen.xyz/automatic_arrangement · https://github.com/Sonata165/REMI-z · https://huggingface.co/LongshenOu/m2m_arranger
- METEOR: https://arxiv.org/abs/2409.11753 · https://github.com/dinhviettoanle/meteor · https://huggingface.co/dinhviettoanle/meteor
- AccoMontage-3 / Structured Arrangement: https://github.com/zhaojw1998/Structured-Arrangement-Code
- Q&A: https://arxiv.org/abs/2306.01635
- SymphonyGen: https://arxiv.org/abs/2604.25498
- UOT-IR: https://arxiv.org/abs/2608.00576
- NotaGen: https://arxiv.org/abs/2502.18008 · https://github.com/ElectricAlexis/NotaGen · https://huggingface.co/ElectricAlexis/NotaGen · https://github.com/ElectricAlexis/NotaGen/issues/45
- ChatMusician: http://arxiv.org/abs/2402.16153 · https://huggingface.co/m-a-p/ChatMusician · https://github.com/hf-lin/ChatMusician
- MuseCoco: https://github.com/microsoft/muzic/tree/main/musecoco
- MusicLang: https://github.com/MusicLang/musiclang_predict · https://huggingface.co/musiclang/musiclang-4k
- Composer's Assistant: https://github.com/m-malandro/composers-assistant-REAPER
- DeepBach: https://github.com/Ghadjeres/DeepBach · Coconet: https://arxiv.org/abs/1903.07227
- LOP: https://arxiv.org/abs/1609.01203 · POD: https://arxiv.org/abs/1810.08611
- ComposerX: https://arxiv.org/html/2404.18081v1 · LilyBench: https://arxiv.org/abs/2606.08722 · Libretto: https://arxiv.org/abs/2606.22708
- Versatile music-for-music (ISMIR 2025): https://arxiv.org/abs/2506.15548
- OR-Tools: https://github.com/google/or-tools
- PyTorch MPS (1.12): https://pytorch.org/blog/introducing-accelerated-pytorch-training-on-mac/
- Apple: https://developer.apple.com/documentation/coreaudio/capturing-system-audio-with-core-audio-taps · https://developer.apple.com/documentation/coreaudio/audiohardwarecreateprocesstap(_:_:) · https://developer.apple.com/documentation/coreaudio/catapdescription · https://developer.apple.com/documentation/screencapturekit/scstreamconfiguration/samplerate
- AudioCap: https://github.com/insidegui/AudioCap · audiotee: https://github.com/makeusabrew/audiotee · BlackHole: https://github.com/ExistentialAudio/BlackHole
- FineTune: https://github.com/ronitsingh10/FineTune · https://github.com/ronitsingh10/FineTune/issues/373
- OBS system-audio-only permission: https://github.com/obsproject/obs-studio/issues/10401
- ModelPiper (secondary): https://modelpiper.com/blog/capture-app-audio-mac-no-drivers
- mediaremote-adapter: https://github.com/ungive/mediaremote-adapter · LyricFever #94: https://github.com/aviwad/LyricFever/issues/94
- MusicXML: https://github.com/w3c-cg/musicxml · music21: https://github.com/cuthbertLab/music21 · partitura: https://github.com/CPJKU/partitura · Verovio: https://github.com/rism-digital/verovio · MuseScore CLI: https://handbook.musescore.org/appendix/command-line-usage · MuseScore orders/instruments: https://github.com/musescore/MuseScore/tree/main/share/instruments
- Go MusicXML: https://github.com/go-muse/go-musicxml · https://github.com/jonasrichard/go-musicxml · https://github.com/alda-lang/go-musicxml
- Brass band: https://www.usopenbrass.org/bbinfo.php · https://www.themusiccompanyshop.com/wp-content/uploads/2016/12/Scoring-Sample-book-extract.pdf
