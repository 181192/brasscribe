# brasscribe apps: build plan

Two applications on one shared engine:

- **Brasscribe Studio** ("Studio" below): a technical workbench. Inspect every pipeline stage, compare models, run benchmarks, and debug scores.
- **Brasscribe Play** ("Play" below): a musician app. Recording in, brass-band score out, then read, listen, practise and play along.

**Ground rules from the owner:**
- The project is **non-commercial**.
- The apps should use **as much of each native platform as possible and stay as slim as possible**. That means separate native apps (Swift, Kotlin, C#) rather than one cross-platform web shell.

This plan is written so a team can start in a fresh session. Read it together with:

| Doc | What it holds |
|---|---|
| `docs/research/00-summary.md` §0 | Current architecture decision: which models, which pipeline, and why |
| `docs/research/10-benchmark-results.md` | All measured results, how to reproduce each, and the regression baseline |
| `docs/songs/mikkel.md` | The end-to-end target song, the layered solo-with-band approach, and an external tool comparison |
| `docs/plan/research-app-stack.md` | Notation libraries, capture limits per OS, packaging, accessibility law (sources inline). Its shell recommendation (Tauri) is superseded by the native-first rule above |
| `docs/plan/research-sound-and-mobile-ml.md` | Sample libraries, neural synthesis, room sound, mobile ML, licences (sources inline) |

---

## 1. Where the project stands

What exists today, all in this repo and committed:

- **Capture:** `capture/`, a Swift Core Audio process-tap CLI for macOS. Records any app or system audio and has passed a loopback test.
- **Model adapters:** `ml/adapters/*`, one uv environment each, behind the same `run.sh <in> <out>` contract. They cover:
  - MuScriptor
  - Basic Pitch
  - SwiftF0
  - Beat This!
  - BS-RoFormer SW and HT-Demucs (via audio-separator)
  - Mega-53
  - PANNs
- **Core music library:** `music/src/brasscribe_music/`, 13 tests. It contains:
  - canonical `Composition` model (`score_model.py`), the JSON contract between transcription and arrangement
  - quantizer with metrical-level selection
  - ps13 pitch spelling and key estimation
  - harmony reduction
  - instrument knowledge for the full brass band (transpositions, ranges)
  - deterministic arrangers: minimal band, and layered solo-with-band
  - MusicXML export with transposing parts, `<instrument-sound>` IDs and percussion
- **Evaluation:** `eval/brasscribe_eval/`, with dataset builders (ChoraleBricks, URMP, Slakh) and benchmarks for:
  - transcription
  - consensus
  - rhythm
  - melody
  - solo vote
  - arrangement
  - a MuseScore round-trip gate
- **End to end:** `brasscribe_eval.song_pipeline`, which takes a recording to an 18-part brass-band MusicXML, PDF and MP3.
  - Reproducible: a fresh run matched the golden output in `data/golden/mikkel-arranged-band/` note for note.

**Known engine gaps.** Detail in §8; the first two are part of the kickoff:
1. **Free-time (rubato) passages are forced onto a beat grid.** In the Mikkel intro the detected "beats" are 1–6 s apart, so rhythm there is nonsense.
2. **Sustained notes are written short.** Durations should come from the audio: SwiftF0 knows when a note ends.
3. Bar lines drift when beats are inserted or dropped.
4. The key is ambiguous (Mikkel: C major or F lydian). There are no articulations or dynamics, and the melody-as-inner-voice case is not handled.

An external comparison (songscription, first 30 s of the Mikkel video, aligned to our capture) showed the same two weaknesses in that tool. Where it placed notes, its pitches were mostly right: 4 of 8 exact and 3 within a semitone. But:
- it wrote every note as a 32nd plus rests;
- it stacked impossible chords on a solo trumpet;
- it missed the phrase peak (B5–C6), which we have and two models confirm.

Nobody writes this intro readably yet. Fixing items 1 and 2 would put us ahead.

---

## 2. Decisions this plan rests on

| Topic | Decision | Reason |
|---|---|---|
| Play on Apple | **One SwiftUI codebase for macOS, iOS and iPadOS** | Native UI and accessibility (VoiceOver), and native audio: AVAudioEngine, AVAudioUnitSampler for SF2/DLS/EXS, AVAudioEnvironmentNode for 3D placement, convolution via AU, AUv3 hosting. Core ML and MLX run on the GPU/Neural Engine. The capture code already exists in Swift. |
| Play on Android | **Kotlin + Jetpack Compose** | Native UI and TalkBack. Audio via Oboe/AAudio. ML via LiteRT or ONNX Runtime Mobile (NNAPI/GPU). alphaTab ships a native Kotlin build (notation and synth). |
| Play on Windows | **C# / .NET, WinUI 3** | Native UI and Narrator/NVDA via UI Automation. WASAPI loopback capture. ONNX Runtime with DirectML (any GPU) or CUDA. alphaTab ships a .NET build. |
| Play on Linux | **Not planned.** Linux users use Studio's browser UI (it can open a score and play it) | Confirmed by the owner |
| Studio | **The engine serves its own web UI on localhost; open it in the system browser.** No desktop shell | Slimmest cross-platform option: nothing to install besides the engine, and the GPU is used wherever the engine runs. It's a technical tool, so a browser tab is fine. |
| Shared logic | **A Rust core library** (`core/`): Composition model, quantizer, spelling, harmony reduction, instrument knowledge, arrangers, MusicXML writer, confidence voting | One implementation for all native apps, bound to Swift and Kotlin with UniFFI and to C# with csbindgen or C ABI. The Python library stays the reference, and a **conformance suite** proves the Rust core produces identical Compositions and MusicXML on the golden set. |
| Model inference in Play | **Platform runtimes, not PyTorch.** Core ML or MLX on Apple, LiteRT/ONNX Runtime Mobile on Android, ONNX Runtime + DirectML on Windows. Models are converted per platform and verified against the Python outputs | Slim, uses each platform's accelerators, works offline. Conversion is real work (§6), so the engine service bridges the gap. |
| Engine (Python) | Stays as the reference implementation, the home of Studio, and a **companion service** that native apps can use on the local network while model conversions are pending | Everything works from day one; conversions replace it model by model. |
| Engine packaging | pixi workspace: one lockfile, one environment per adapter (Python 3.10 for Basic Pitch, 3.12 elsewhere), CUDA 12 on Windows/Linux, MPS on macOS, CPU fallback | uv workspaces can't mix Python versions. Docker is for Linux CI/benchmark runners only (no Metal GPU in Docker Desktop). |
| Accessibility | **WCAG 2.2 AA** (EN 301 549) on the native accessibility APIs, plus a talking score and braille music (BRF) | Norwegian law today requires WCAG 2.0 AA for private businesses and 2.1 AA for the public sector; build to where it's heading. Native apps get the best screen-reader behaviour. |
| Contract | `Composition` JSON and MusicXML | Already implemented and tested. Every app, runtime and language agrees on it. |

---

## 3. Target architecture

```
                 Studio (browser UI served by the engine)          Play: native apps
                 pipeline graph · inspector · benchmarks           ┌───────────────┬──────────────┬──────────────┐
                               │                                   │ Apple (Swift)  │ Android      │ Windows      │
                               │ HTTP/JSON + SSE                    │ macOS·iOS·iPad │ (Kotlin)     │ (C#/.NET)    │
                               ▼                                   └──────┬────────┴──────┬───────┴──────┬───────┘
 ┌──────────── engine (Python, reference + companion) ───────────┐        │ UniFFI / C ABI │              │
 │ job DAG · artifact cache · profiles · benchmark suites        │        ▼                ▼              ▼
 │ adapters (pixi envs): MuScriptor, Mega-53, SW, Basic Pitch,   │   ┌──────────────── core (Rust) ─────────────────┐
 │ SwiftF0, Beat This!                                           │   │ Composition · quantize · spell · harmony      │
 │ music (brasscribe_music) = reference implementation           │◄──│ instruments · arrange · MusicXML · voting      │
 └───────────────────────────────────────────────────────────────┘   │ conformance-tested against the Python library │
          ▲  companion mode (LAN, pairing code)                       └───────────────────────────────────────────────┘
          └──────────────── Play apps send audio, get Composition/MusicXML ────────────────┘
                              (until the on-device models land)

 On-device inference per platform:  Core ML / MLX (Apple) · LiteRT / ONNX Runtime Mobile (Android) · ONNX Runtime + DirectML (Windows)
```

Repo layout (additive):

```
core/            Rust crate: shared symbolic logic + UniFFI/C ABI bindings; conformance tests
engine/          Python FastAPI service, job runner, profiles, Studio web UI (served static)
music/ ml/ eval/ capture/   (exist) Python reference, adapters, benchmarks, macOS capture
models/convert/  per-model conversion scripts (Core ML, ONNX, LiteRT) + parity tests vs PyTorch
apps/apple/      SwiftUI app (macOS, iOS, iPadOS targets), Swift packages for audio/ML
apps/android/    Kotlin/Compose app
apps/windows/    C# WinUI 3 app
sounds/          SFZ/SF2 instrument mappings and IR metadata (audio downloaded, not committed)
pixi.toml        engine workspace
```

---

## 4. Studio (technical workbench)

**Who it's for:** Kalli and contributors. Insight over polish.

**Form:** `brasscribe studio` starts the engine and opens `http://localhost:…` in the default browser.
- There's no desktop shell. The UI is plain TypeScript and web components, built into the engine package.
- For viewing scores it uses alphaTab (web build, MPL-2.0).

### Features
1. **Run a pipeline** on a file, a capture, or a dataset item, with a chosen profile. The live stage graph shows timings, device (CUDA/MPS/CPU) and cache hits.
2. **Stage inspector:**
   - audio: waveform and spectrogram with A/B against the original
   - stems: solo, mute, energy over time
   - piano roll coloured by source model and confidence
   - beats and downbeats, including the chosen metrical level and free-time regions
   - Composition: voices by role and layer
   - arrangement: score plus validator warnings (range, crossing)
   - MusicXML: MuseScore round-trip status
3. **Compare runs:** note-level diff (added, removed, moved, octave), score overlay, metric deltas.
4. **Benchmarks:** run any suite on GPU or CPU. Results are stored with run manifests. There's a trend view and a regression gate against `10-benchmark-results.md` (±0.01 F1).
5. **Conversion parity:** for each converted model (Core ML, ONNX, LiteRT), compare its outputs with PyTorch on the eval sets. It reports note-level F1 against the PyTorch output and the latency per device. This is where on-device readiness is decided.
6. **Core conformance:** run the Rust core against the Python reference on the golden set and show any diff.
7. **Datasets and models:** download helpers, licences, sizes, hashes, device per adapter.
8. **Reproducibility:** every job writes a run manifest (adapter versions, model hashes, profile, parameters, git SHA). Any manifest can be re-run.

### Packaging and GPU
- pixi environments per adapter, installed on first run, with model weights downloaded into a cache. The installer itself is small.
- `brasscribe bench <suite>` works headless for CI. A Linux Docker image with the NVIDIA runtime is available for dedicated benchmark machines.
- **Isolation:** adapters run as subprocesses in their own environments. All data lives in one directory: models, cache, datasets, runs.

**Done means:**
- It installs on clean macOS arm64, Windows 11 and Ubuntu 24.04.
- `brasscribe run mikkel.wav` reproduces `data/golden/mikkel-arranged-band/` note for note.
- The chorale and URMP suites match `10-benchmark-results.md` within ±0.01 F1.
- The GPU is used on CUDA and MPS machines, confirmed in the run manifests.

---

## 5. Play (musician app, native per platform)

**Who it's for:** brass-band musicians and arrangers. Speed, clarity, accessibility.

### 5.1 Inputs

| Input | Apple (macOS) | Apple (iOS/iPadOS) | Android | Windows |
|---|---|---|---|---|
| Audio file | AVFoundation | AVFoundation | MediaExtractor/MediaCodec | Media Foundation |
| Video file → audio (+ synced video view) | AVFoundation | AVFoundation | MediaExtractor | Media Foundation |
| Microphone | AVAudioEngine | AVAudioEngine | Oboe/AAudio | WASAPI |
| Sound playing on the device | Core Audio process tap (exists in `capture/`) | ✗ only a user-started ReplayKit broadcast, never DRM content | ◐ AudioPlaybackCapture; apps may opt out | WASAPI loopback, per-app from build 20348 |
| Share sheet / "open with" | ✓ | ✓ | ✓ | ✓ |

DRM-protected playback is blocked on every platform, and the app says so instead of recording silence. Links (YouTube etc.) are not downloaded: platform terms. Users record the playback or import a file.

### 5.2 From source to score
1. **Import or record → "What is this?"** The options are solo instrument, brass band, orchestra with soloist, or pop/rock. The answer picks the pipeline profile; the app never guesses silently.
2. **Transcribe:**
   - progress in plain language, with an estimated time and cancel;
   - on-device where the models for that profile are converted;
   - otherwise via the companion engine on your own computer (LAN).
3. **Review:**
   - Uncertain notes carry colour **and** shape.
   - "Listen to this bar" plays the original and the score, looped.
   - Free-time passages are shown as *ad lib*.
4. **Choose output:** lineup (full band, minimal band), difficulty (faithful, standard, easier), key.
5. **Export:** MusicXML (score and parts), PDF, MIDI, audio, talking-score text, braille (BRF). Also share to MuseScore and Files.

### 5.3 Score, parts, practice
- **Show all / show one:** parts in written pitch, with a concert-pitch toggle.
- **Playback:** per-part mute and solo, speed from 25 to 150% without pitch change, loop a bar range, count-in, metronome, transpose.
- **Play along:** mute your part.
  - Later: follow the player's tempo from the microphone (SwiftF0 plus Beat This!, both small enough to run live), and intonation and rhythm feedback.
- **Original vs score:** switch at the same position. The video plays in picture-in-picture, synced.
- **Notation rendering:**
  - Android: alphaTab Kotlin (notation and synth, cursor, loop, speed, part selection).
  - Windows: alphaTab .NET.
  - Apple: there's no native alphaTab, so **Verovio** (C++, built as a dynamic framework, LGPL-compatible) renders SVG. Playback uses the Verovio timemap and AVAudioUnitSampler for cursor sync.
  - Spike first: Verovio SVG shown natively versus in a system WKWebView, compared on memory, speed and VoiceOver.

### 5.4 Sound: realistic playback

MIDI plus General MIDI sounds is not enough, and **no free library has cornet, tenor horn, baritone or euphonium**. Each tier ships on its own:

| Tier | What | Native implementation |
|---|---|---|
| Baseline | MuseScore MS Basic SF3 (MIT) | Apple: AVAudioUnitSampler. Android/Windows: alphaTab synth (TinySoundFont) |
| Realistic sections | VSCO 2 CE (CC0) and University of Iowa MIS (unrestricted) trumpet, horn, trombone and tuba. Brass-band parts mapped to the nearest instrument with timbre EQ (cornet → darker trumpet; tenor horn/flugel → horn; baritone/euphonium → trombone/tuba) | Apple: AVAudioUnitSampler (EXS/SF2 built from the samples). Android/Windows: sfizz (BSD, C++ via NDK/P/Invoke) |
| Room | Concert-hall or band-room impulse responses (OpenAIR, CC BY 4.0) plus seating placement per section | Apple: convolution AU plus AVAudioEnvironmentNode (HRTF). Android: Oboe with a convolution kernel. Windows: XAudio2/convolution |
| Humanization | Timing, dynamics and articulation from the transcribed performance | Rust core |
| Own brass-band samples | Record cornet, flugel, tenor horn, baritone, euphonium, E♭/B♭ bass: 3 dynamics, sustain plus staccato, about a day per instrument | All platforms |
| Apple extra | Host AUv3 instruments the user owns (e.g. SWAM Euphonium/Flugelhorn) | AVAudioUnit hosting |
| Research | DDSP timbre models (Apache-2.0, real-time on CPU) trained on our own stems | Core ML / ONNX |

**Avoid FluidSynth on iOS** (LGPL versus App Store).

### 5.5 Accessibility (WCAG 2.2 AA, universell utforming)
- **Native APIs:** SwiftUI accessibility (VoiceOver, Voice Control, Switch Control, Dynamic Type); Compose semantics (TalkBack, Switch Access, font scale); UI Automation (Narrator, NVDA). Custom rotors and actions for bar and part navigation.
- **Keyboard:** full keyboard operation on desktop. Visible focus, logical order, documented shortcuts (space, loop, speed, next/previous bar).
- **Talking score:** navigable by part, bar and beat. It announces pitch (written or concert), duration, dynamics and confidence ("bar 12, beat 1: E-flat 5, quarter note, uncertain") and can play the current bar.
- **Braille music:** BRF export (music21 via the engine now; a core port later).
- **Visual:**
  - contrast ≥ 4.5:1 for text and 3:1 for UI and notation
  - notation zoom to 400%
  - high-contrast theme; reduced motion (no animated cursor)
  - uncertainty shown by shape plus colour, with a colour-blind-safe palette
- **Media:** imported captions are kept. Audio cues have visual equivalents.
- **Language:** plain language. Norwegian and English from the start, using platform localisation.
- **Testing:** scripted screen-reader runs per platform on each release; Xcode Accessibility Inspector audits; Android Accessibility Scanner; Accessibility Insights for Windows.

### 5.6 Offline

| Platform | Transcription | Score, playback, practice |
|---|---|---|
| macOS | **Offline.** Via the local engine now; on-device Core ML/MLX as conversions land | Offline |
| Windows | **Offline.** Via the local engine now; ONNX Runtime + DirectML as conversions land | Offline |
| iOS/iPadOS, Android | **Offline for simple sources** (one instrument, microphone): SwiftF0 (135 kB), Basic Pitch, Beat This! small (8 MB). Full band via the companion on your own computer (LAN), then on-device where memory allows (iPad/high-end phones, after measurement) | Offline |

No cloud is required anywhere. Models download once, on demand: Apple hosted asset packs, Play asset/AI packs, or a direct download on desktop.

---

## 6. Build order and acceptance criteria

The work is listed in dependency order. Each milestone ends with something runnable and keeps the benchmarks green.

### Engine as a service, with the free-time and duration fixes
- Migrate `ml/adapters/*`, `music/` and `eval/` into a pixi workspace.
- FastAPI engine: job DAG, artifact cache, SSE progress, run manifests, profiles.
- Port the benchmarks to suites, with the `brasscribe bench` CLI.
- **Free-time detection:**
  - Detect passages where beat intervals are wildly irregular.
  - Mark them *ad lib* in the Composition and MusicXML.
  - Notate them proportionally from note lengths instead of a grid, or ask for a tempo.
  - Benchmark on the rubato and fermata material in URMP and ChoraleBricks, plus the Mikkel intro judged by ear.
- **Durations from audio:**
  - Use SwiftF0 contour offsets and MuScriptor offsets so sustained notes are written long.
  - Infer staccato when the performed length is under half the written length.
  - Benchmark: duration accuracy on URMP and chorales (currently 0.61 / 0.88).
- **Done when:**
  - `brasscribe run mikkel.wav` reproduces `data/golden/mikkel-arranged-band/`, updated deliberately when the two fixes change it; the diff is reviewed and the golden output re-saved.
  - Suites match within ±0.01 F1.
  - The Mikkel intro renders as readable sustained phrases marked *ad lib*.
  - CI runs the CPU suites on Linux.

### Studio
- Browser UI served by the engine: pipeline graph, inspector, compare, benchmarks, models, datasets.
- **Done when:** Studio's "done means" in §4 passes.

### Rust core with conformance
- Port the symbolic logic (Composition, quantize with metrical level, fill gaps, ps13 spelling, key, harmony reduction, instruments, both arrangers, voting, MusicXML writer with transposition, instrument sounds and percussion).
- UniFFI bindings for Swift and Kotlin, a C ABI for C#.
- **Done when:** on the golden set and every eval set, the Rust core produces Compositions and MusicXML identical to the Python reference, the MuseScore round trip passes, and it builds for macOS, iOS, Android and Windows.

### Play for Apple (macOS, iOS, iPadOS)
- SwiftUI app: import (audio, video, share sheet), microphone, device capture on macOS, companion transcription, review, parts, practice, exports.
- Verovio notation plus AVAudioUnitSampler playback with room and placement.
- Talking score and BRF. VoiceOver-first.
- **Done when:**
  - A musician goes from a captured track or a video file to a playable full-band score on a Mac offline.
  - On iPhone/iPad, from a recorded solo to a readable part offline.
  - VoiceOver test scripts pass.
  - The app size stays under an agreed budget: models are separate downloads, and the app binary target is under 50 MB.

### On-device models
- `models/convert/`: Core ML/MLX and ONNX/LiteRT exports with parity tests against PyTorch, run in Studio (§4.5).
- Order by value and difficulty:
  1. SwiftF0 (ONNX exists)
  2. Basic Pitch (Core ML/TFLite exist)
  3. Beat This! small
  4. HT-Demucs
  5. BS-RoFormer SW (ONNX export known, 336 MB fp16)
  6. Mega-53 (same architecture)
  7. MuScriptor: decoder with KV cache. Try MLX Swift on Apple and ONNX elsewhere; the hardest.
- **Done when (per model):** note-level F1 against PyTorch output ≥ 0.98 on the eval sets, with latency and memory recorded per device class. A model is switched on in Play only after this.

### Play for Android
- Kotlin/Compose app with the Apple feature set (minus device capture where apps opt out). alphaTab Kotlin notation and synth, sfizz via NDK, Oboe audio, LiteRT/ONNX Runtime Mobile.
- **Done when:** a solo recorded on the phone becomes a readable part offline, a full band works through the companion, and TalkBack scripts pass.

### Play for Windows
- WinUI 3 app: WASAPI loopback capture, alphaTab .NET, ONNX Runtime + DirectML, Narrator/NVDA.
- **Done when:** capture/file → full-band score offline on a Windows machine with and without an NVIDIA GPU, and Narrator/NVDA scripts pass.

### Realistic sound
- SFZ/EXS instruments from VSCO 2 and Iowa with brass-band timbre adaptation, IR rooms, seating placement, humanization. A recording plan for our own brass-band samples.
- **Done when:** a blind A/B test (5 listeners, 5 excerpts) prefers the realistic tier over the baseline at least 80% of the time.

### Engine quality (continuous)
See §8. Every item lands with a benchmark and no regressions.

---

## 7. Licences (non-commercial project)

| Component | Licence | What we do |
|---|---|---|
| MuScriptor weights | CC BY-NC 4.0, gated on Hugging Face | Allowed for this non-commercial project. The gate means each user accepts the licence with their own Hugging Face account, and the app downloads with the user's token. We don't redistribute the file. Attribution in the About screen. |
| BS-RoFormer SW, Mega-53 weights | No stated licence | Downloaded by the user from the original release URLs. Not re-hosted by us. Flagged in the model manager. |
| HT-Demucs, Basic Pitch, SwiftF0, Beat This! | MIT / Apache-2.0 | May be bundled. |
| alphaTab (Android, Windows, Studio) | MPL-2.0 | Fine. Changes to alphaTab's own files are shared. |
| Verovio (Apple) | LGPL-3.0 | Dynamic framework, unmodified or with published changes, so users can relink. |
| sfizz / TinySoundFont | BSD / MIT | Fine. |
| FluidSynth | LGPL | Not used on iOS. |
| MuseScore CLI | GPL-3.0 | Only as an optional external program for Studio renders; never bundled. |
| VSCO 2 CE / Iowa MIS / MS Basic / OpenAIR IRs | CC0 / unrestricted / MIT / CC BY 4.0 | Bundle or download, with attribution where required. |
| Datasets (ChoraleBricks, URMP, Slakh) | Various | Studio downloads them on request; never bundled. |

**If the project ever becomes commercial,** MuScriptor, BS-RoFormer SW and Mega-53 would have to go. The remaining licence-clean set can't isolate a soloist or transcribe drums today, so that would be a major step back.

---

## 8. Engine backlog (quality)

Ordered by impact on Mikkel and on musicians. **Items 1 and 2 are in the first milestone (§6).**

1. **Free-time detection.** When beat intervals are wildly irregular (Mikkel intro: 1–6 s), stop imposing a grid. Mark the passage *ad lib* and notate proportionally, or ask for a tempo.
2. **Durations from audio.** Sustained notes written long, from SwiftF0 and MuScriptor offsets; staccato inference.
3. **Bar-line robustness.** Downbeat-constrained beat cleanup, handling of inserted or deleted beats, meter and pickup confirmation in the UI.
4. **Key and harmony cross-check.** Audio key (S-KEY) and chords (consonance-ACE) against the symbolic estimate. Modes (lydian), key changes.
5. **Separation failure detection.** Flag when the solo stem doesn't contain the soloist; two chorales failed silently.
6. **Validate the non-solo layers.** Bass, orchestra residual and drums are transcribed with MuScriptor on separated or residual audio, which is untested given MuScriptor's collapse on separated solo stems.
7. **Melody when it's an inner voice.** Needs test material.
8. **Dynamics and phrasing** from loudness per layer.
9. **Arranger idiom.** Rhythmic figuration from the source, countermelody choice, soprano cornet use, difficulty modes, and a CP-SAT voice-leading solver where the greedy voicer fails.

---

## 9. Decisions

Settled:
- **Non-commercial.**
- **Native per platform** (Swift, Kotlin, C#).
- Studio runs in the browser, served by the engine. That also covers Linux users; there is no Linux Play app.
- **Names:** Brasscribe Play and Brasscribe Studio.

Still open, all for Kalli:
1. **Record our own brass-band samples** (about a day per instrument). It's the only route to authentic cornet, tenor horn, baritone and euphonium playback.
2. **Platform order after Apple:** Android or Windows next. The plan says Android, because mobile practice is the bigger musician need.


---

## 10. Starting the work in a new session

### Team shape

Each role owns folders, which keeps parallel work conflict-free (use git worktrees):

| Role | Owns |
|---|---|
| Engine | `engine/`, `pixi.toml`, `ml/adapters/`, `eval/` suites, the Studio web UI |
| Music core (Python) | `music/`: the free-time and duration fixes, then the rest of §8 |
| Rust core | `core/` and the conformance suite |
| Apple | `apps/apple/`, `capture/` |
| Android | `apps/android/` |
| Windows | `apps/windows/` |
| Models | `models/convert/`: conversions and parity tests |
| Sound | `sounds/`, instrument building, room and placement |
| Accessibility and QA | Cross-cutting reviewer: screen-reader scripts, WCAG checklist, platform audit tools |

**First wave:** Engine, Music core (Python) and Accessibility and QA. Rust core joins as soon as the free-time and duration fixes have settled the Composition format for rubato passages, so it ports the final logic once. Apple joins when the engine's companion API exists.

### Working rules
- Conventional commits, ending with the model `Co-Authored-By` trailer.
- **Docs, commit messages and code comments describe what the code does.** No agent names, task numbers or phase labels.
- Every engine or core change runs the benchmark suites. Numbers go into `docs/research/10-benchmark-results.md` only when measured, with the command that produced them.
- Changing the golden output (`data/golden/mikkel-arranged-band/`) is a deliberate, reviewed step. Record why in the commit message.
- Never commit audio, models or datasets (`data/`, `models/` are gitignored).
- The MuseScore round-trip gate must pass for any change to MusicXML output. The MuseScore 4.7 CLI aborts during shutdown *after* writing its output, so check for the file, not the exit code.
- Unverified claims go in docs as open questions, not facts.

### Kickoff prompt (paste into the new session)

> Read `docs/plan/apps-plan.md`, `docs/research/00-summary.md` §0, `docs/research/10-benchmark-results.md` and `docs/songs/mikkel.md`. Build the milestone "Engine as a service, with the free-time and duration fixes" using three teammates, each in its own git worktree owning the folders listed in §10:
> - **Engine** builds the pixi workspace, the FastAPI engine, and the benchmark suites and CLI.
> - **Music core (Python)** implements free-time detection and durations from audio (§8 items 1 and 2), each with a benchmark.
> - **Accessibility and QA** writes the WCAG 2.2 AA checklist and screen-reader test scripts for the three native platforms, and reviews output for readability.
>
> Acceptance:
> - `brasscribe run` on `data/mikkel/mikkel.wav` reproduces `data/golden/mikkel-arranged-band/` before the fixes.
> - After the fixes, the intro renders as readable *ad lib* sustained phrases. Review the diff against the golden output and re-save it deliberately.
> - All suites stay within ±0.01 F1 except where a fix is meant to improve them.
>
> Report what runs, the measured numbers, and any open decision from §9 you need.
