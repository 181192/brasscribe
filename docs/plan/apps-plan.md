# brasscribe apps: build plan

Two applications on one shared engine:

- **Studio**: a technical workbench. Inspect every pipeline stage, compare models, run benchmarks, and debug scores.
- **Play**: a musician app. Recording in, brass-band score out, then read, listen, practise and play along.

This plan is written so a team can start in a fresh session. Read it together with:

| Doc | What it holds |
|---|---|
| `docs/research/00-summary.md` §0 | Current architecture decision: which models, which pipeline, and why |
| `docs/research/10-benchmark-results.md` | All measured results; the regression baseline |
| `docs/songs/mikkel.md` | The end-to-end target song and the layered solo-with-band approach |
| `docs/plan/research-app-stack.md` | Shells, packaging, notation libraries, capture limits, accessibility law (sources inline) |
| `docs/plan/research-sound-and-mobile-ml.md` | Sample libraries, neural synthesis, room sound, mobile ML, licences (sources inline) |

---

## 1. Where the project stands

What exists today, all in this repo and committed:

- **Capture:** `capture/`, a Swift Core Audio process-tap CLI for macOS. Records any app or system audio and has passed a loopback test.
- **Model adapters:** `ml/adapters/*`, one uv environment each, all behind the same `run.sh <in> <out>` contract. They cover:
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
  - instrument knowledge for the full brass band with transpositions and ranges
  - deterministic arrangers: minimal band, and layered solo-with-band
  - MusicXML export with transposing parts, `<instrument-sound>` IDs and percussion
- **Evaluation:** `eval/brasscribe_eval/`, with builders for ChoraleBricks, URMP and Slakh and benchmarks for:
  - transcription
  - consensus
  - rhythm
  - melody
  - solo vote
  - arrangement
  - a MuseScore round-trip gate
- **End-to-end:** Mikkel audio → 18-part brass-band MusicXML, PDF and MP3, verified through MuseScore.

Known engine gaps. These are engine work that runs in parallel with the apps (see §8):
- The free-time (rubato) intro is forced onto a beat grid.
- Sustained notes are shortened.
- Bar lines drift when beats are inserted or dropped.
- The melody-as-inner-voice case is not handled.
- There are no articulations or dynamics.
- The key is ambiguous (Mikkel: C major or F lydian).

---

## 2. Decisions this plan rests on

| Topic | Decision | Reason |
|---|---|---|
| Shell, both apps | **Tauri 2** with a TypeScript web UI | The notation and playback layer (alphaTab) is web. The webview gives native screen-reader support (VoiceOver, Narrator/NVDA, TalkBack). One codebase covers desktop and mobile. Electron is the fallback if Linux screen-reader support (WebKitGTK/Orca) fails its test. |
| Engine | Stays **Python**, run as a local service (FastAPI on localhost or stdio) | All models and the music library are Python. The spec suggested Go for orchestration, but nothing so far needs it, so it is dropped until a measured need appears. |
| Engine packaging | **pixi workspace**: one lockfile, one environment per adapter (Python 3.10 for Basic Pitch, 3.12 elsewhere), platforms `osx-arm64` (MPS), `linux-64`/`win-64` with CUDA 12, plus CPU fallbacks | uv workspaces can't mix Python versions. Docker Desktop has no Metal GPU, so Docker is for Linux CI and benchmark runners only. |
| Installer strategy | Small installer. On first run it installs the environment (pixi-pack) and downloads model weights into a cache | Weights total about 3–4 GB. Never embed them in the installer. |
| Score view and playback | **alphaTab** (MPL-2.0) | Built-in synth, cursor, loop, speed, per-part mute/solo and part selection. It shows written pitch for B♭/E♭ parts while sounding at concert pitch, and can follow the original recording. It cannot handle transposition changes mid-piece, which we don't generate. |
| Accessible score | A **talking score**: a structured text view navigable bar by bar and part by part, plus **braille music (BRF)** via music21 | No SVG notation library is screen-reader navigable. |
| Accessibility target | **WCAG 2.2 AA** plus EN 301 549 | Norwegian law today requires WCAG 2.0 AA for private businesses and 2.1 AA for the public sector. 2.2 is where the law is heading, so build to it now. |
| Mobile | Tauri 2 mobile UI with native audio modules. **Transcription stays on desktop**; see §5.6–5.7 for what runs on the phone | The models plus PyTorch don't run on phones without ports, and some weights can't legally be shipped (§7). |
| Contract between stages | `Composition` JSON (concert pitch, ticks, voices with role and layer, per-note confidence and source models) plus content-addressed artifacts | Already implemented and tested; every UI reads the same thing. |

---

## 3. Target architecture

```
                     ┌──────────────────────── Studio (Tauri) ───────────────────────┐
                     │ pipeline graph · stage inspector · A/B · benchmarks · logs     │
                     └───────────────┬───────────────────────────────────────────────┘
                                     │ HTTP/JSON (OpenAPI) + server-sent events
┌──────────── Play (Tauri, desktop + mobile UI) ─────────┐        │
│ import · record · score · parts · play-along · a11y    │────────┤
└────────────────────────────────────────────────────────┘        │
                                     ┌───────────────▼───────────────────────────────┐
                                     │ engine service (Python, FastAPI)              │
                                     │  job runner: DAG of stages, per-stage cache    │
                                     │  stages call adapters (pixi envs, subprocess)  │
                                     │  artifacts: content-hashed files + SQLite index│
                                     └───────┬──────────────┬──────────────┬──────────┘
                                             │              │              │
                                   ml/adapters/*   music (brasscribe_music)   capture helpers
                                   (per-env)       (Composition, arranger,    (macOS tap, WASAPI,
                                                    MusicXML)                  PipeWire)
```

- **Shared UI package** (`ui/`, TypeScript):
  - score view (alphaTab wrapper): part selection, written/concert toggle, confidence overlay, cursor sync with the original audio
  - waveform and piano roll with a confidence layer
  - talking-score component
  - accessible transport controls
  Both apps consume it.
- **Engine API**:
  - `POST /jobs` with source and profile; `GET /jobs/{id}` for status; `GET /jobs/{id}/events` as SSE
  - `GET /artifacts/{hash}`
  - `GET /compositions/{id}`; `POST /arrange` with a composition and lineup
  - `POST /benchmarks/{suite}`
  - OpenAPI is the contract, and the TypeScript client is generated from it.
- **Profiles:**
  - `licence-clean`: HT-Demucs, Basic Pitch, SwiftF0, Beat This!
  - `best-quality`: adds MuScriptor, BS-RoFormer SW and Mega-53. Personal use only (§7).
  - `fast`: mobile/companion subset.
  A profile is data (YAML), not code.
- **Reproducibility.** Every job writes a run manifest: adapter versions, model hashes, profile, parameters, git SHA. Studio can re-run any manifest.

Target repo layout (additive; existing folders stay):

```
engine/          FastAPI service, job runner, stage definitions, profiles/*.yaml
music/           (exists) brasscribe_music core
ml/adapters/     (exists) → migrated into pixi environments
eval/            (exists) benchmarks become engine "benchmark suites"
capture/         (exists, macOS) + capture-win/ (WASAPI loopback) + capture-linux/ (PipeWire)
ui/              shared TS components (score, waveform, talking score, transport)
apps/studio/     Tauri app
apps/play/       Tauri app (desktop + iOS + Android targets)
sounds/          SFZ instrument mappings, IR metadata (audio assets downloaded, not committed)
pixi.toml        workspace
```

---

## 4. Studio (technical workbench)

**Who it's for:** Kalli and contributors. Accuracy and insight over polish.

### Features

1. **Run a pipeline** on any source (file, capture, dataset item) with a chosen profile. The live stage graph shows timings, device (CUDA/MPS/CPU) and cache hits.
2. **Stage inspector:** for each stage, the artifact viewer that fits it:
   - audio: waveform plus spectrogram, playable, with A/B against the original
   - stems: solo, mute, per-stem energy over time
   - notes: piano roll coloured by source model and confidence
   - beats and downbeats over the waveform, including the detected metrical level
   - Composition: voices by role and layer
   - arrangement: score view plus range and crossing validator warnings
   - MusicXML: score view, MuseScore round-trip status
3. **Compare runs:** diff two runs note by note (added, removed, moved, octave), score overlay, metric deltas.
4. **Benchmarks:** run any suite on a GPU or CPU backend.
   - Suites: transcription, consensus, rhythm, melody, solo vote, arrangement, MuseScore gate.
   - Results are stored with manifests. There is a trend view per suite and a regression gate against the numbers in `10-benchmark-results.md`.
5. **Datasets:** registry of ChoraleBricks, URMP and Slakh with download helpers. Datasets are never bundled; each has its licence noted.
6. **Model manager:** installed models, sizes, licences, hashes; download and verify; GPU/CPU per adapter.
7. **Logs and reproducibility:** per-job logs, run manifest export and re-run.

### Packaging and GPU

- pixi environments per adapter.
  - Backends: CUDA 12 on Windows/Linux, MPS on macOS arm64, and a CPU fallback everywhere.
  - Device selection is automatic, and can be overridden per adapter in the UI.
- Headless mode: `brasscribe bench <suite>` CLI in the same package, for CI.
- Linux Docker image with the NVIDIA runtime for dedicated benchmark runners. It is optional and not the desktop path.
- **Isolation.** Adapters run as subprocesses in their own environments; the engine never imports model code. The app keeps its data in one directory: models, cache, datasets, runs.

### Done means

- It installs on a clean macOS arm64, Windows 11 and Ubuntu 24.04 machine.
- A first-run download sets up the environments and models.
- One Mikkel run and the full chorale benchmark complete with GPU where available.
- Numbers match `10-benchmark-results.md` within ±0.01 F1 (or ±1 percentage point for accuracy figures).

---

## 5. Play (musician app)

**Who it's for:** brass-band musicians and arrangers. Speed, clarity, accessibility.

### 5.1 Inputs

| Input | macOS | Windows | Linux | iOS | Android |
|---|---|---|---|---|---|
| Audio file (wav, mp3, flac, m4a) | ✓ | ✓ | ✓ | ✓ | ✓ |
| Video file (mp4, mov, mkv): audio extracted | ✓ ffmpeg | ✓ ffmpeg | ✓ ffmpeg | ✓ AVFoundation | ✓ MediaExtractor |
| Microphone | ✓ | ✓ | ✓ | ✓ | ✓ |
| Sound playing on the device | ✓ process tap (exists) | ✓ WASAPI loopback (per-app from build 20348) | ✓ PipeWire monitor | ✗ only a user-started screen broadcast, never DRM content | ◐ AudioPlaybackCapture, apps may opt out |
| Link (YouTube etc.) | Not planned: platform terms. Users record playback or import files | | | | |

DRM-protected playback (Apple Music, most browser DRM) is blocked on every platform. The app says so plainly instead of recording silence. The capture helpers already detect silence.

### 5.2 From source to score

1. **One button:** import or record, then Transcribe.
   - The first screen of the flow asks what kind of source it is: solo instrument, brass band, orchestra with soloist, or pop/rock. The answer picks a profile, which keeps the pipeline from guessing.
   - Advanced options are hidden behind "More".
2. **Progress:** readable stages ("Separating instruments… Finding the beat… Writing parts…") with an estimated time. Cancel is always available.
3. **Result:** the score opens with the source audio aligned.
4. **Review:**
   - Uncertain notes are marked with colour **and** a shape or pattern, since colour must never be the only signal.
   - "Listen to this bar": the original against the score, looped.
   - Free-time passages are labelled *ad lib*, never forced onto a grid (engine backlog, §8).
5. **Choose output:**
   - lineup: full band, minimal band, or solo plus piano reduction later
   - difficulty: faithful, standard, easier; the architecture already allows modes
   - key
6. **Export:** MusicXML (full score plus parts), PDF, MIDI, MP3, talking-score text and braille (BRF).

### 5.3 Score, parts and practice

- **Show all / show one:** full score, or one part. Parts are in written pitch, with a concert-pitch toggle.
- **Playback:** mute/solo per part, speed from 25 to 150% without pitch change, loop a bar range, count-in, metronome, transpose.
- **Play along:** mute your own part and play with the band.
  - Later: follow the player's tempo from the microphone (score following using SwiftF0 plus Beat This!, both small enough to run live).
  - Later: an intonation and rhythm feedback overlay.
- **Original vs score:** switch between the source recording and the synthesized score at the same position. The two are synced; alphaTab supports following external audio.
- **Video:** when the source was a video, it plays in a picture-in-picture window synced to the score.

### 5.4 Sound: making playback realistic

MIDI plus General MIDI sounds is not enough, and there is **no free, redistributable sample library with cornet, tenor horn, baritone or euphonium**. So we build up in layers, and each layer ships on its own:

| Tier | What | Licence status |
|---|---|---|
| Baseline | MuseScore MS Basic SF3 via alphaTab's built-in synth. The same file already drives our MP3 renders | MIT, bundle freely |
| Realistic sections | SFZ instruments via **sfizz**. Sources: VSCO 2 CE (CC0) and University of Iowa MIS (unrestricted), covering trumpet, horn, trombone and tuba. Brass-band parts are mapped to the nearest instrument with timbre EQ (cornet → darker trumpet; tenor horn/flugel → horn; baritone/euphonium → trombone/tuba). Velocity layers come from our dynamics | Bundle freely |
| Room | Convolution reverb with a concert-hall or band-room impulse response (OpenAIR, CC BY 4.0), plus seating-based stereo/HRTF placement per section (cornets left, basses centre-back…) | Bundle with attribution |
| Humanization | Timing, dynamic and articulation variation taken from the *transcribed performance* (we have onset offsets and velocities), not random jitter | Ours |
| Own brass-band samples | Record an SFZ set with real players: cornet, flugel, tenor horn, baritone, euphonium, E♭/B♭ bass; 3 dynamics; sustain plus staccato. About a day per instrument | We own it |
| Apple extra | Host AUv3 instruments the user already owns (e.g. SWAM Euphonium/Flugelhorn) on macOS and iOS | No redistribution |
| Research | DDSP timbre models (Apache-2.0, real-time on CPU) trained on our own recorded stems | Ours, experimental |

Desktop runs sfizz natively. The web and mobile playback path uses alphaTab's synth for SF2, SpessaSynth for the web, and TinySoundFont (MIT) for native mobile. **Avoid FluidSynth on iOS**: LGPL and App Store distribution conflict.

### 5.5 Accessibility (WCAG 2.2 AA, universell utforming)

Requirements, tested on every release:
- Every action works with the keyboard alone. Focus is always visible, the order is logical, and there are no keyboard traps. Transport controls have documented shortcuts (space, loop, speed, next/previous bar).
- Screen readers: VoiceOver (macOS/iOS), NVDA and Narrator (Windows), TalkBack (Android), Orca (Linux). Scripted manual test runs for each release. Keep native window decorations, because NVDA goes silent in frameless Tauri windows.
- **Talking score:** navigable by part, bar and beat. It announces pitch (written or concert), duration, dynamics and confidence ("bar 12, beat 1: E-flat 5, quarter note, uncertain"). It can also play the current bar.
- **Braille music:** BRF export from music21.
- Visual:
  - contrast ≥ 4.5:1 for text and 3:1 for UI and notation
  - notation zoom to 400% without horizontal scrolling of controls
  - high-contrast theme; honour reduced motion (no animated cursor)
  - uncertain notes use shape plus colour
  - a colour-blind-safe palette
- Media: video import keeps any captions. All app audio cues have visual equivalents, and vice versa.
- Plain language. Norwegian and English UI from the start (i18n keys, no hard-coded strings).
- Automated checks: axe-core in UI tests; Lighthouse accessibility ≥ 95 on every screen.

### 5.6 Offline

| Platform | Transcription | Score, playback, practice |
|---|---|---|
| Desktop | **Fully offline** after a one-time model download (about 3–4 GB for `best-quality`, well under 1 GB for `licence-clean`) | Offline |
| Mobile | Offline for **simple sources**: one instrument recorded with the microphone, using SwiftF0 (135 kB), Basic Pitch and Beat This! small (8 MB). Full-band transcription runs on the user's own desktop over the local network ("companion"), with no cloud needed | Offline |
| Cloud | Not required. It could be added later as an opt-in; it would need the licence-clean profile | — |

### 5.7 Mobile specifics

- Tauri 2 mobile targets for iOS and Android share the UI package.
- Tauri's shell cannot spawn processes on mobile, so audio and ML go through native plugins:
  - iOS: AVAudioEngine, Core ML
  - Android: Oboe, ONNX Runtime Mobile
- On-device models:
  - SwiftF0 (ONNX)
  - Basic Pitch (Core ML/TFLite shipped upstream)
  - Beat This! small, converted to Core ML/ONNX in a spike with measured latency and memory; no published phone numbers exist
  - HT-Demucs as an optional download
- **Companion mode:** the phone discovers the desktop engine via mDNS, sends audio and receives the Composition and MusicXML. It is pairing-code protected and stays on the local network.
- Store limits: use on-demand model downloads (Apple hosted asset packs; Play AI packs) instead of bundling.

---

## 6. Build order and acceptance criteria

The work is listed in dependency order. Each milestone ends with something runnable, and every milestone keeps the benchmarks green.

### Engine as a service
- Migrate `ml/adapters/*`, `music/` and `eval/` into a pixi workspace. Keep one environment per adapter; the `run.sh` contract stays for compatibility.
- Build the FastAPI engine:
  - job DAG with stages: capture/import, separate, transcribe per layer, vote, beats, quantize, spell, compose, arrange, export
  - content-hashed artifact cache, SQLite index, SSE progress, run manifests, profiles
- Port the benchmarks to engine suites, plus the `brasscribe bench` CLI.
- **Done when:**
  - `brasscribe run mikkel.wav --profile best-quality` reproduces the golden output in `data/golden/mikkel-arranged-band/`. That output comes from `eval/brasscribe_eval/song_pipeline.py`; compare per-part note counts and pitch sequences.
  - `brasscribe bench chorales` reproduces the table in `10-benchmark-results.md`.
  - The benchmark suites also report a `licence-clean` column.
  - CI runs the CPU suites on Linux.

### Shared UI package
- alphaTab score view:
  - part selection and written/concert toggle
  - confidence overlay (shape plus colour)
  - cursor synced to external audio
- Waveform and piano roll; talking-score component; transport with keyboard shortcuts; i18n (nb/en).
- **Done when:** a Storybook of each component passes axe-core with no violations, and the talking score reads the Mikkel score correctly with VoiceOver and NVDA.

### Studio first release
- Tauri app: run a pipeline, see the stage graph, inspect artifacts, compare runs, run benchmarks with a device choice, manage models.
- First-run installer: environment plus model download with checksum verification.
- **Done when:** the Studio "done means" in §4 passes on all three desktop OSes, and the GPU is used on CUDA and MPS machines (verified in the run manifest).

### Play desktop first release
- Import audio or video, microphone, device-sound capture on all three desktop OSes (Windows and Linux helpers are new).
- Source-type question → profile → one-button transcription.
- Score with parts and practice features (§5.3); baseline plus room sound; exports including BRF and talking-score text.
- **Done when:** a musician can go from a Spotify-captured track or a video file to a playable full-band score offline, and the WCAG 2.2 AA checklist passes with screen-reader test scripts on macOS and Windows.

### Realistic sound
- sfizz integration, SFZ mappings (VSCO 2 / Iowa) with brass-band timbre adaptation, section placement, humanization from the performance.
- Recording plan and SFZ build pipeline for our own brass-band samples, if we go ahead (§9).
- **Done when:** a blind A/B listening test (5 listeners, 5 excerpts) prefers the realistic tier over the baseline at least 80% of the time.

### Play mobile
- Tauri mobile shells for iOS and Android. Native audio plugins. On-device SwiftF0/Basic Pitch/Beat This! with measured latency and memory. Companion mode. On-demand model download.
- **Done when:** a solo line recorded on the phone becomes a readable part offline; a full-band transcription through the companion desktop works; TalkBack and VoiceOver test scripts pass.

### Engine quality (continuous, alongside everything above)
See §8. Each item lands with a benchmark and must not regress existing numbers.

---

## 7. Licences and distribution

| Component | Licence | Consequence |
|---|---|---|
| MuScriptor weights | CC BY-NC 4.0, gated on Hugging Face | Personal and non-commercial use only. The user must accept the licence on Hugging Face; the app downloads with the user's token and never redistributes the weights. Not allowed in any commercial offering, server-side included. |
| BS-RoFormer SW, Mega-53 weights | Licence unknown or undocumented | Personal use only; downloaded by the user. Excluded from `licence-clean`. |
| HT-Demucs, Basic Pitch, SwiftF0, Beat This! | MIT / Apache-2.0 | Fine to bundle. This set is the `licence-clean` profile. |
| alphaTab | MPL-2.0 | Fine. Changes to alphaTab files themselves must be shared. |
| MuseScore CLI (PDF/MP3 render in Studio) | GPL-3.0 | Called as an external program installed by the user. Never bundled in Play. |
| Verovio | LGPL | Not used; alphaTab covers the need. |
| FluidSynth | LGPL | Not on iOS. |
| VSCO 2 CE / Iowa MIS / MS Basic / OpenAIR IRs | CC0 / unrestricted / MIT / CC BY 4.0 | Bundle, with attribution where required. |
| Datasets (ChoraleBricks CC BY, URMP, Slakh) | Various | Downloaded by the user in Studio; never bundled. |

**Rule:** `licence-clean` is the only profile that may ever be shipped preinstalled or run for anyone other than the user themselves.

**What `licence-clean` cannot do today:**
- It can't isolate a solo instrument from a band or orchestra (no Mega-53). HT-Demucs gives only vocals/drums/bass/other.
- It has no drum transcription (only MuScriptor transcribes drums), so no percussion part.
- Its multi-instrument transcription quality is unmeasured. Basic Pitch alone scored 0.47–0.73 onset F1, against MuScriptor's 0.56–0.88.

It currently works for brass-only sources and single-line recordings, not for the Mikkel-style flagship flow. Its benchmark column is part of the "Engine as a service" acceptance criteria, and decision 1 in §9 depends on those numbers.

---

## 8. Engine backlog (quality)

Ordered by impact on Mikkel and on musicians:

1. **Free-time detection.**
   - When beat intervals are wildly irregular (the intro gaps are 1–6 s), stop imposing a grid.
   - Mark the passage *ad lib* and notate proportionally, or ask for a tempo.
   - Benchmark against rubato passages in URMP and ChoraleBricks (fermatas).
2. **Durations from audio.** Use SwiftF0 contour offsets and MuScriptor offsets so sustained notes are written long. Add articulation inference: staccato when the performed length is under half the written length.
3. **Bar-line robustness.** Downbeat-constrained beat cleanup, handling of inserted or deleted beats, and a UI to confirm meter and pickup.
4. **Key and harmony cross-check.** Audio key (S-KEY) and chords (consonance-ACE) against the symbolic estimate. Support modes (lydian) and key changes.
5. **Melody when it's an inner voice.** Needs test material; the benchmark currently favours the top line.
6. **Dynamics** from loudness per layer, and phrase marks.
7. **Arranger idiom.**
   - rhythmic figuration from the source (not one chord per beat)
   - countermelody selection
   - soprano cornet use
   - difficulty modes
   - the full voice-leading solver (CP-SAT) where the greedy voicer fails
8. **Separation failure detection.** Flag when the solo stem doesn't contain the soloist (two chorales failed silently).

---

## 9. Decisions only Kalli can make

1. **Commercial intent.** If any future version is sold or offered to others, only the `licence-clean` profile qualifies, and MuScriptor is out. That affects how much effort goes into making the clean profile good.
2. **Own sample recordings.** Record a brass band (about a day per instrument) to get real cornet, tenor horn, baritone and euphonium sounds we own. It is the only route to authentic brass-band playback.
3. **Mobile priority.** Build mobile after Play desktop, as this plan orders it, or sooner?
4. **App names.** "Studio" and "Play" are working names.
5. **What "native mobile" means.** This plan packages the mobile apps with Tauri: a shared web UI in the system webview, with native Swift/Kotlin plugins for audio and ML. Fully native Swift/Kotlin UIs would mean a separate UI per platform and couldn't reuse the web notation library (alphaTab). Confirm the Tauri route is acceptable.

---

## 10. Starting the work in a new session

### Team shape

Each role owns folders, which keeps parallel work conflict-free (use git worktrees):

| Role | Owns |
|---|---|
| Engine | `engine/`, `pixi.toml`, `ml/adapters/`, `eval/` → suites |
| Music core | `music/` (quantizer, spelling, arranger, export, engine backlog items) |
| UI components | `ui/` (score view, talking score, transport, a11y) |
| Studio app | `apps/studio/` |
| Play app | `apps/play/`, `capture-win/`, `capture-linux/` |
| Sound | `sounds/`, sfizz integration, room and placement |
| Mobile | mobile targets of `apps/play/`, native plugins, model conversion |
| Accessibility and QA | Cross-cutting reviewer: axe-core, screen-reader scripts, WCAG checklist sign-off |

Start with **Engine**, **UI components** and the **Accessibility and QA** reviewer in parallel. Both depend only on what exists today. Studio and Play start when the engine API and the score view are usable.

### Working rules

- Conventional commits, ending with the model `Co-Authored-By` trailer.
- **Docs, commit messages and code comments describe what the code does.** No agent names, task numbers or phase labels.
- Every engine change runs the benchmark suites. Numbers go into `docs/research/10-benchmark-results.md` only when measured, with the command that produced them.
- Never commit audio, models or datasets (`data/`, `models/` are gitignored). Record where to download them.
- The MuseScore round-trip gate must pass for any change to MusicXML export.
- The MuseScore 4.7 CLI aborts during shutdown *after* writing its output, so check for the file, not the exit code.
- Unverified claims go in docs as open questions, not facts.

### Kickoff prompt (paste into the new session)

> Read `docs/plan/apps-plan.md`, `docs/research/00-summary.md` §0 and `docs/research/10-benchmark-results.md`. Build the "Engine as a service" and "Shared UI package" milestones in parallel with three teammates: Engine, UI components, and Accessibility and QA (roles in §10), each in its own git worktree, owning the listed folders. Keep the existing benchmarks green; reproduce `data/golden/mikkel-arranged-band/` through the new engine as the acceptance test (`eval/brasscribe_eval/song_pipeline.py` is the current reference implementation). Report back with what runs, the measured numbers, and any decision from §9 you need from me.
