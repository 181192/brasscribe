# 13 — Performance audit: memory, main thread, start-up, engine, network, core

**Why.** An Android video upload read the whole file into memory, copied it again, and crashed at the 512 MB heap (fixed in 0c8b98b by streaming the upload and extracting the audio on the device). This audit looks for the same class of problem everywhere else: the engine (`engine/`, `music/`, `ml/adapters`), the Rust core, Studio, Play on Apple, Android and Windows, and Bandroom on macOS and Windows. Date: 2026-09-28, on `main` at a485bef.

**Short answer.**
- **Worst measured problem: Studio's band sound.** alphaTab holds about **7× the SoundFont** in the browser. Opening one score costs +0.54 GB with the 77 MB SoundFont that every shipped build serves, and +1.3 GB with the 195 MB one. Compare opens two players (3.9 GB for the browser with the 195 MB file). Opening another score builds a new synth. With files over Chrome's cache-entry limit, it also downloads the SoundFont again.
- **Worst engine problem (fixed): event streams starved the API.** Forty open job event streams took every thread of the engine's request pool. `GET /v1/health` then waited 13 s, or timed out. Fixed: 120 streams, 6 ms.
- **Worst Android problem (fixed): the event stream broke every 10 s.** OkHttp's 10 s read timeout is shorter than the engine's 15 s keepalive, so every quiet stretch cost a reconnect (measured). By the reconnect logic, six in a row end the job with "event stream lost", which a stage silent for about a minute would do (read from the code, not seen running).
- **Worst core problem (partly fixed): the band arrangement with stems peaked at 1.10 GB** for Mikkel's four 43.5 MB stems through the C ABI Windows Play uses. Two copies are removed: the CLI goes from 750 to 575 MB, and the C ABI from 1.10 to 0.92 GB, with byte-identical output. What remains is decoding every stem to float32 when only an envelope is needed.
- On `perf/audit`, seven commits fix seven items, each with a test (table below). Two more add the probes and this document. Everything else is in the ranked list with its size.

**Evidence labels in the tables.**

| Label | Meaning |
|---|---|
| **M** | Measured in this audit. The Measurements section says how. |
| **C** | Code proof. The quoted line was re-checked at the cited file:line on a485bef. |
| **R** | Code reading or estimate. Plausible, not measured and not re-checked line by line. Confirm before acting. |

## 1. Fixed on this branch

| Commit | Platform | What | Before → after | Test |
|---|---|---|---|---|
| 0696ca8 fix(engine): event streams wait in their own threads | Engine | `stream_events` was a sync generator. Each open stream held one of Starlette's 40 pool threads for up to 15 s per wait. Streams now wait through their own `anyio.CapacityLimiter(256)`. | 41 streams: `/v1/health` 13,023 ms; 60 streams: timeout after 20 s → 120 streams: 6 ms (**M**) | `engine/tests/test_event_streams.py`: 45 streams, `GET /v1/jobs/{id}` under 2 s; fails without the fix |
| 8148c8e fix(android): the job event stream outlasts a quiet stage | Android | Ktor's OkHttp engine keeps OkHttp's 10 s read timeout, and the engine sends a keepalive every 15 s (`api.py` `HEARTBEAT_S`). The event request now has a 60 s socket timeout; other requests keep the default. | 12 s quiet gap: 2 connections → 1 (**M**) | `EventStreamTimeoutTest` (real OkHttp, local socket); fails without the fix |
| 5f07ff1 perf(core): separation check without copies of the stems | Rust core | `separation()` copied the solo stem twice and built an interleaved mix, only to down-mix to mono. It now sums per frame in the same order. | `arrange-layers` on Mikkel: peak 750 → 575 MB, time unchanged (≈0.45 s), all 14 Mikkel cases byte-identical (**M**) | `pipeline::tests::separation_without_copies_matches_mixing_first` (1, 2 and 3 channels, uneven lengths) |
| 4152f83 perf(ffi): move the stems into the band arrangement instead of cloning them | Rust FFI (Windows Play) | `bc_arrange_layers_band` cloned the six MIDI files and four WAV stems inside an `FnOnce` closure. They are moved now. | C ABI only process: 1.10 → 0.92 GB (**M**) | `brasscribe-ffi/tests/layers_band_c_api.rs`: C ABI = UniFFI output on Mikkel; `--ignored c_abi_alone` for the measurement |
| a2ff100 perf(windows): read the band SoundFont in the background | Windows Play | `BandSoundFont.Load` did `File.ReadAllBytes` of the 195 MB SoundFont on the UI thread in `OnLaunched`, before `_window.Activate()` (`App.xaml.cs:79,130,245`). Load keeps the path; `ApplyTo` reads inside its `Task.Run`. The object no longer holds the bytes. | 195 MB read moved off the first frame (**C**; not timed on Windows) | `Load_leaves_reading_the_soundfont_to_ApplyTo` (file locked during Load) |
| 5d3805a feat(engine): Cache-Control on Studio files and band sounds | Engine / Studio | No `Cache-Control`, so browsers guessed a lifetime from Last-Modified. Studio's static files: `no-cache` (revalidate, 304 in ~1 ms). This includes the SoundFont Studio's build bundles in its own `assets/band/`. The `BRASSCRIBE_BAND_SOUNDS_DIR` mount (Bandroom): `public, max-age=86400`. | No change for the SoundFont (see M2). The gain is that an unhashed `studio.js` can no longer run stale after an update. | `test_static_files_say_how_long_to_cache` |
| 3335aa6 perf(engine): list jobs from cached manifest summaries | Engine | `GET /v1/jobs` parsed every manifest, read every `events.jsonl` and walked every `outputs/` per call. Finished runs are kept per run, keyed by the manifest's mtime and size, with their output list; the list never reads events. | 49 runs, warm: 52 → 3.3 ms; first call after start 91 → 66 ms (**M**) | `engine/tests/test_job_list.py`: a second list parses nothing, a changed manifest is parsed again |
| ec3875a feat(engine): record GPU queue wait apart from stage run time | Engine / Studio | Stage seconds included the wait for the GPU mutex. Manifests, stage events and job stage states now carry `queue_wait_s` and `run_s` beside `seconds` (still the wall clock). "waiting for GPU mutex" is logged only when the mutex is held; it is polled every 1 s instead of 5 s. Studio shows "ran … · waited …" in the stage graph, stage details and manifest table. | A stage behind a held mutex: 0.8 s wait recorded as `queue_wait_s`, not run time (**M**, test) | `engine/tests/test_gpu_wait.py`, `studio/tests/stagetime.test.ts` |
| 3a1ac5b feat(engine): optional bounded stage parallelism | Engine | `BRASSCRIBE_STAGE_PARALLELISM` (default 1: unchanged) runs up to that many stages whose inputs are done; at most one GPU stage per job at a time, and the GPU mutex still orders jobs. Events are serialised, the manifest keeps pipeline order, and the file-hash index now saves under a lock (two stages saving at once raced on its temporary file). | 30 s solo take, all stages forced: 22.3 → 19.2 s (−14 %); brass band on Mikkel: 95.6 → 92.2 s (−4 %) (**M**) | `engine/tests/test_stage_parallelism.py`: CPU and GPU stages overlap with 2, GPU stages never do, nothing overlaps with 1 |
| ad1bdc2 fix(studio): piano roll and beat summary without argument spreading | Studio | `Math.max(...list)` over every note or beat; V8 throws RangeError at about 110,000 arguments. | Precaution. Mikkel has 20,758 MIDI events. (**M**: limit measured) | `studio/tests/extent.test.ts` |

`main` fixed the same Studio stack overflow on open (c3dc2ad, alphaTab's self-referencing `loadedMidiInfo`). This audit found it independently: the Studio e2e "the Mikkel run" failed before that commit.

## 2. Findings, ranked by user impact

Crash or out of memory first, then jank, slow, waste. Size: S (hours), M (a day or two), L (more).

### Crash / out of memory

| # | Platform | Where | Evidence | Proposed fix | Size |
|---|---|---|---|---|---|
| 1 | Studio | `studio/src/components/score.ts:244` `this.api?.destroy()` then `:271` `new alphaTab.AlphaTabApi(...)` with `soundFont` URL `:261`; Compare `views/compare.ts:194-195` two `bs-score`, `:228` both loaded | **M**: browser RSS after one score is 1,125 MB with General MIDI, 1,661 MB with the 77 MB SoundFont and 2,448 MB with the 195 MB one. Compare after that: 1,614, 2,497 and 3,891 MB. alphaTab costs about 7× the file per player. | One SoundFont per page: fetch the bytes once and give each player `api.loadSoundFont(bytes)`, or keep one player and swap scores. Start the synth on first Play (`playerMode` off until then). Compare: one player. | M |
| 2 | Rust core / Windows Play | `core/brasscribe-ffi/src/c_api.rs:308` `from_raw_parts(...).to_vec()` of each stem; `energy.rs:52-59` decodes each stem to f32; `LayerInputs.cs:50` `File.ReadAllBytes` of each stem | **M**: C ABI call on Mikkel 0.92 GB peak after the two fixes above, for 174 MB of WAV. The stems are only used for envelopes and the separation check. | Borrow the caller's buffers instead of `to_vec` (S–M). Decode straight to a mono envelope in blocks, never a full f32 stem (M). Windows: pass file paths, or memory-map (M–L). | M |
| 3 | Android | `AndroidManifest.xml:24` `android:largeHeap="true"`; `ScoreController.kt:310` `sf.readBytes()` | **M**: emulator heap growth limit is 192 MB normally and 576 MB with `largeHeap`. **C/M**: 0c8b98b measured about 220 MB of heap for the SoundFont (the steady state is about 3× the file). The app does not work without `largeHeap`, and a device with a smaller large-heap limit has little room left. | Short term: keep `largeHeap` and budget the other buffers (#5). Long term: stream samples from disk (sfizz already does), or a smaller mobile SoundFont. | L |
| 4 | Apple Play | `NotationKit/ScoreRenderer.swift:252` `sounding(atBeat:)` reads `timemap` without the lock; `:140-143` `apply()` rewrites `timemap` and `measureIDs` under the lock from `Task.detached` (`PracticeModel.swift:158`); called at 20 Hz from `PracticeModel.swift:324` | **C**: an unsynchronised read and write of a Swift Array during playback can crash. | Build the arrays in locals and publish them under the lock; read under the lock or from a snapshot. | S |
| 5 | Android | `audio/.../Recorders.kt:44` `FloatBuilder()`, `:57`/`:124` `pcm.addAll`, `:83`/`:143` `pcm.toArray()` | **C**: recording grows without a cap (11.5 MB per minute at 48 kHz), plus a full copy at the end. **R**: can coexist with an imported take, the solo WAV and the decoded score MP3 (`PlayViewModel.kt`) and the SoundFont. | Write samples to the WAV as they arrive (`WavWriter` exists); cap in memory like `AudioDecoder.maxSamplesInMemory`. | M |
| 6 | Apple Play (macOS) | `PlaybackKit/SoundBank.swift:88-93` `kMusicDeviceProperty_StreamFromDisk` off, macOS only | **C** for the switch. **R**: `docs/research/12-band-sound.md` estimates 270–535 MB for all presets in memory. On iOS the samplers stream from disk (there is no switch), so that estimate is macOS-only. Two or three engines can be alive at once (score, Review, export), which multiplies it (**R**). | Measure first (recipe in section 5). Release the engine when leaving the score; share one engine per piece. | M |
| 7 | Studio | `components/audio.ts:15` `const cache = new Map<string, Promise<AudioBuffer>>()` | **C** for the module-level map. **R**: decoded audio (about 92 MB per 4-minute stereo stem at 48 kHz) is never evicted; the Stems tab preloads 8. | LRU of about 3 buffers, clear on leaving a run. | S |
| 8 | Windows Play (dev builds) | `BrassSoundSet.cs:53` `File.ReadAllBytes(file)` for 11 files, `:82` `(byte[])sf2.Clone()`; called from `App.xaml.cs:246` before the first frame | **C**: 270 MB read and copied (about 540 MB peak) on the UI thread. Only when the band SoundFont is not bundled. | Patch presets in place, drop the arrays after `ApplyTo`, run in the background. | S |

### Jank (main or UI thread)

| # | Platform | Where | Evidence | Proposed fix | Size |
|---|---|---|---|---|---|
| 9 | Windows Play | `WasapiCaptureService.cs:154` `done.Task.Wait(TimeSpan.FromSeconds(2), ct)` in a synchronous `StopAsync`, awaited from `StartViewModel.cs:149` | **C** for the blocking wait on the UI thread. **R**: NAudio posts `RecordingStopped` to the captured UI context, so the wait always runs the full 2 s. | Make `StopAsync` truly async (`await done.Task.WaitAsync(...)`). | S |
| 10 | Windows Play | `AlphaTabScorePlayer.cs:133` `lock (Gate) _synth.LoadSoundFont(...)` | **C**: the whole SoundFont parse holds the audio lock. The UI takes the same lock (`IsReady`, `LoadScore`, volume), so Play right after launch blocks until the parse ends. | Parse outside the lock, swap under it; or have UI calls skip the lock until loaded. | M |
| 11 | Windows Play | `EngineLayerSource.cs:16` `LayerInputs.FromDirectory(dir)` on a cache hit, before the first await, from `OutputOptionsViewModel` on the UI thread | **C**: all stems read with `File.ReadAllBytes` on the UI thread (about 42 MB per minute of audio). | Wrap the cache-hit path in `Task.Run`. | S |
| 12 | Windows Play | `ScoreViewModel.Load` (talking score, `Player.Load` → alphaTab parse and MIDI), `CorrectPitch` → native re-arrange | **R**: all synchronous on the UI thread per score open and per pitch edit. | Parse on the alphaTab worker; FFI in `Task.Run`. | M |
| 13 | Android | `ui/ScoreScreen.kt:136-138` `LaunchedEffect(controller) { controller.load(r.musicXml.toByteArray()) ... }`; `score/ScoreController.kt:228` `fun load(...)` is not a suspend function and switches no dispatcher | **C**: the whole MusicXML parse and `prepareSound` run on the main thread. | Parse on `Dispatchers.Default`, render on main. | M |
| 13a | Windows Play | `NativeCoreBridge.cs:219-220` `JsonNode.Parse(compositionJson)` then `bc_humanize_json(request.ToJsonString(), ...)` per part | **C**: the 1.3 MB composition is parsed in C#, serialised again and parsed again in Rust for each of up to 18 parts. | A `Performance` handle in the C ABI (as UniFFI has), or one call for all parts. | M |
| 14 | Android | `core-bridge/.../RustCoreBridge.kt:143` `val perf = compositionJson?.let { Performance(it) }` per `humanize` call; loop at `HumanizedPlayer.kt:57` | **C**: the 1.3 MB composition is parsed once per part (18 for a band), on the main thread when the realistic tier loads. | Build `Performance` once per score and pass it to every part. | S |
| 15 | Android | `PlayViewModel.kt:172` and `:177` `scoreLibrary.list()` | **C**: every saved score (MusicXML, composition, evidence) read twice at start-up, and again on every Keep. | Read the index only; load a score on open; save on `Dispatchers.IO`. | S (the double call) / M |
| 16 | Apple Play | `App/Views/ScoreScreen.swift:18` `.task { loadModel() }`, `PracticeModel` is `@MainActor` (`PracticeModel.swift:11`); samplers load per part (`SoundBank.swift:103`) | **C** for main-actor isolation. **R**: MusicXML parse, composition decode and one `loadSoundBankInstrument` per part all on the main thread when a score opens. | Parse and build the engine off the main actor, publish when ready; show the score first. | M |
| 17 | Apple Play | 20 Hz timer sets `position`, which redraws every visible page and rebuilds accessibility labels (`NotationView.swift`) | **R**. | Draw the cursor in an overlay; cache per-layout lookups; stop the timer while stopped. | M |
| 18 | Bandroom macOS | `ModelDownloader.swift:24` `@MainActor`, `:223` `try verify(part, as: f)` hashes the whole file; `:214` a main-actor task per network chunk | **C**: SHA-256 of 0.7–1.4 GB model files on the main actor. | `Task.detached` for `verify`; throttle progress to 4 per second. | S |
| 19 | Studio | `views/run.ts:165` `renderHeader(...)` on every SSE event, log lines included | **C** for the call; **R** for its cost. | Re-render on `job`/`stage` events only. | S |
| 20 | Studio | MusicXML parsed up to four times per open (`score.ts` `parseMusicXml`, `buildTalkingScore`, alphaTab, `run.ts` again) | **R**. | Parse once and pass the result on. | S |

### Slow

| # | Platform | Where | Evidence | Proposed fix | Size |
|---|---|---|---|---|---|
| 21 | Studio | Band SoundFont over the network | **M**: a 195 MB file is never taken from Chrome's disk cache, with or without `Cache-Control` (over the per-entry limit). It is downloaded again for every score opened, and twice for Compare. A 77 MB file is cached with or without the header. **C**: every shipped surface serves the 77 MB file (`studio/build.mjs:34`, `apps/bandroom/macos/scripts/stage-band-sounds.sh:11`, `Brasscribe.Bandroom.csproj:89-90`); only a dev engine with `BRASSCRIBE_BAND_SOUNDS_DIR=data/sounds/band` serves the 293 MB 24-bit file. | Keep serving the 77 MB file to Studio. Finding #1's fix (one fetch per page) also removes the re-downloads. For persistence across visits over LAN http, IndexedDB (the Cache API needs a secure context). | — (with #1) |
| 22 | Engine | `dag.py` stages ran one after another; each adapter is a new process (`adapters.py`) | **M**: fixed cost per adapter call, warm: MuScriptor 2.1 s, Basic Pitch 2.2 s, SwiftF0 0.3 s; cold (first call after idle) 8.6–10.8 s. Stage parallelism is done (3a1ac5b, off by default): a 30 s solo take 22.3 → 19.2 s, a brass-band run 95.6 → 92.2 s (M5). Warm adapter workers would save at most 30 % of a solo take run in order and about 20 % with parallelism on, and 6 % of a band run (M6), for 1–2 GB held per idle GPU worker: not built, design in M6. | Turn parallelism on by default after a week of use; warm workers only if short solo takes become the main load. | — (parallelism done) / M (workers) |
| 23 | Engine | `adapters.py` logged "waiting for GPU mutex" before every heavy stage, whether or not it waited; polled every 5 s; stage seconds included the wait | **M**: a solo run shows `beats` 375.9 s on a 3 s input (`20260926-005002-solo-8a82c3`, from before the split), almost certainly queueing. Fixed (ec3875a): `queue_wait_s` and `run_s` per stage in manifests and events, shown in Studio as waited and ran; logged only when blocked; polled every 1 s. Five fresh runs here recorded 0.0 s waits. | Done. | S |
| 24 | Engine | `jobs.py` `list()` parsed every manifest and `events.jsonl` on disk per call, and `api.py` walked every `outputs/` | **M**: `GET /v1/jobs` 52 ms warm for 49 runs, linear in runs; two thirds of it was the `outputs/` walk. Fixed (3335aa6): 3.3 ms warm, only a `stat` per run while nothing changes. | Done. | S |
| 25 | Rust core | `arranger.rs:80` phrase end recomputed per note (O(n²)); `harmony.rs:21` every note per beat (O(beats × notes)) | **M**: the whole Mikkel arrangement takes 0.35–0.5 s, so not hot today. **C** for the loops. | Running maximum; sweep line. Keep output byte-identical (conformance). | S / M |
| 26 | Engine | Upload | **M**: streamed and hashed in 1 MB chunks; engine RSS +19.5 MB while receiving 71 MB at 20 MB/s. **R**: written twice (Starlette spools, then `store_upload` copies). | Acceptable. Optionally stream the multipart body straight to the upload file. | S |
| 26a | Apple Play | `TranscriptionKit/CompanionService.swift:272-288` builds the multipart body in a temp file with `FileHandle.write(_:)`, sends it with `upload(for:fromFile:)` (`:294`); progress stays at `fraction: 0` (`:308`) | **C**: streamed from a file (good), but a full extra copy on disk, no upload progress and no retry. **R**: `FileHandle.write(_:)` raises an Objective-C exception, not a Swift error, when the disk is full, which crashes the app. | `write(contentsOf:)` (throws); progress from the task delegate's `didSendBodyData`; one retry on network errors. | S |
| 26b | Windows Play | `App.xaml.cs:104` `Timeout = Timeout.InfiniteTimeSpan` for the engine client | **C**: the upload streams from the file (`StreamContent`), but has no overall or idle timeout and no progress. **R**: it uploads the decoded 16-bit WAV, often about 10× the original compressed file. | A progress-reporting stream with an idle timeout, as the Bandroom downloader has. Uploading the original file needs the engine to accept it. | S / L |
| 26c | Android | `KtorEngineApi.kt:198` `bodyAsBytes()` for PDF, MIDI, audio and artifacts, `:112` braille | **C**: downloads land in memory before being written to a file. Small today (MP3s of a few MB). | `bodyAsChannel().copyTo(file)`. | S |

### Waste

| # | Platform | Where | Evidence | Proposed fix | Size |
|---|---|---|---|---|---|
| 27 | Android | `score/BandSoundFontFile.kt:35-41` copies the 77 MB asset to `filesDir` | **C**: second 77 MB on disk; slow first open. The asset is stored uncompressed. | Read through `assets.openFd(...)`. | S |
| 28 | Android | ONNX sessions built per transcription (`AppContainer.kt`) | **R**: a few hundred ms per run. | Cache the sessions. | S |
| 29 | Windows Play | `Microsoft.ML.OnnxRuntime.DirectML` shipped, no app code creates a session | **R**: install size. | Drop until used. | S |
| 30 | Studio | `index.html:19` `<script src="assets/alphatab/alphaTab.min.js">` parser-blocking (1.1 MB) | **C**. | `defer`, or load with the first score view. | S |
| 31 | Bandroom (both) | Polling every 3–5 s while idle, re-publishing unchanged state | **R**. | Compare before assigning; poll pairing only with the panel open. | S |
| 32 | Docs | `12-band-sound.md:305` says both Bandroom apps bundle the 16-bit 195 MB SoundFont | **C**: both bundle the 77 MB mobile file (see #21). | Correct the doc. | S |

### Start-up: what runs before the first frame

| App | Before the first frame | Evidence | Fix | Size |
|---|---|---|---|---|
| Studio | `alphaTab.min.js` (1.1 MB) blocks parsing (`index.html:19`); every view is bundled into one 276 KB `studio.js`. No SoundFont until a score opens. | **C** | `defer`; load alphaTab with the first score view. | S |
| Play, Apple | `Piece.loadAll()` twice, decoding every `piece.json` (`App/AppModel.swift:31` and `:33`). Nothing heavy loads: SoundFont and Core ML models wait for a score or an on-device job. | **C** | `:33` from `pieces`. | S |
| Play, Android | `RustCoreBridge.load()` on the main thread (`AppContainer.kt:133`), `SoundPack` `mkdirs` per instrument (`:127`), the saved-score library read twice (#15). No SoundFont, models or WebView. | **C** | `core` lazy or warmed off the main thread; library index only. | S |
| Play, Windows | Before a2ff100 the 195 MB SoundFont read. Still: the WASAPI output device opened at launch and kept open (`App.xaml.cs:80`, `WasapiSynthOutput.cs:18`, 80 ms latency, wakes for the app's lifetime), Media Foundation start-up (`:109`), the credential vault probe (`:96`), the score library index. | **C** for the calls, **R** for their cost | Open the audio device on first Play; construct the decoder lazily. | S–M |
| Bandroom, Windows | `_bootstrap.IsComplete(_cuda)` on the UI thread (`App.xaml.cs:192`, again at `:208`) hashes `pixi.lock` with `SHA256.HashData(File.ReadAllBytes(...))` (`Bootstrap.cs:96`) and walks the whole bundled workspace (`:89`). `EngineReady` repeats it on progress callbacks (`App.xaml.cs:219`). The flyout window is built even for a background start. | **C** for the calls, **R** for their cost | Compute the hashes once and cache them; build the flyout on first open. | S / M |
| Bandroom, macOS | After a crash, `reapStrayEngine()` (`App/AppModel.swift:149`) can wait up to 5 s on the main actor (`ProcessLauncher.swift:97`, 50 × `usleep(100_000)`). | **C** | Reap in `Task.detached` before starting the supervisor. | S |

### Rust core and FFI payloads

What crosses the boundary per call, for Mikkel: the composition JSON is 1.3 MB, the score MusicXML 2.0 MB, the talking-score JSON 5.4 MB, and the 18 part scores 2.1 MB together (`outputs/` of a Mikkel run). One arrangement moves each of these once, which is fine. The costs come from repeating a call:
- Humanize takes the whole composition per part: Android builds a `Performance` from it per part (#14), and Windows parses and re-serialises it per part through `bc_humanize_json` (#13a).
- Windows builds the talking score in Rust, gets 5.4 MB of JSON back and parses it in C#, then parses the MusicXML again in managed code (**R**; once per score).
- `bc_arrange_layers_band` returns one JSON string embedding the score, all 18 parts and the composition as strings, which C# then parses (**R**). The copies of the stems going in were the large part (fixed, see section 1).

Not a problem (checked): the engine's upload is streamed and deduplicated by content hash (`store_upload`); artifacts are served with `FileResponse` (streamed, ETag, ranges); run directories hardlink or clone the cache (APFS clones make `du` over-count); Windows Play's upload uses `StreamContent` from a file; the Bandroom Windows downloader streams to a `.part` file with a 1 MiB buffer, resumes with Range and has a 60 s idle timeout; Android's music stand reuses the score's alphaTab view (no second SoundFont load), and alphaTab recycles off-screen bitmaps at any zoom; Core ML models load lazily on the first on-device job and are cached for the app's lifetime.

## 3. Top 5 quick wins

Ranked by user impact for their size. Three are done on this branch.

1. **Done: engine event streams in their own threads** (0696ca8). Any client that opens many streams (several Studio tabs, several phones, reconnect loops) could freeze the whole API.
2. **Done: Android event stream socket timeout** (8148c8e). Long quiet stages no longer break the stream or end the job with "event stream lost".
3. **Done: two stem copies out of the band arrangement** (5f07ff1, 4152f83). 175 MB less each on the CLI path and the C ABI for Mikkel, byte-identical output.
4. **Open, S: Apple `ScoreRenderer` race (#4).** Publish `timemap`/`measureIDs` under the lock. A crash in playback on zoom or part change.
5. **Open, S: Windows recording stop (#9).** A 2 s freeze on every stop, if the NAudio context analysis holds. Verify on Windows first.

Next in line, all S: Android `Performance` once per score (#14), Bandroom macOS hash verification off the main actor (#18), Windows layer cache hit off the UI thread (#11), Android start-up library read once (#15). Also done, smaller: Windows SoundFont read off the first frame (a2ff100), `Cache-Control` (5d3805a).

The biggest remaining item is not a quick win: **Studio's one-SoundFont-per-page (#1, M)**. It is the largest measured memory cost in the project.

## 4. Measurements

Scripts are in `qa/perf/` and `studio/perf/`. Machine: Apple M-series Mac, macOS 26, Chromium headless shell from Playwright, engine on loopback.

### M1. Studio: memory and SoundFont traffic per score

```sh
pixi run studio --no-browser --port 8799        # or any engine serving Studio
cd studio && STUDIO_URL=http://127.0.0.1:8799/ RUNS=<run-a>,<run-b> node perf/soundfont-probe.mjs
```

Each run starts from an empty profile, opens run A, run B and run A again (hash change, as the Runs view does), then Compare with both. "Browser RSS" sums the browser process and all its children. Runs: Mikkel (orchestra-with-soloist, 18 parts, 132 bars) and a brass-band run.

| SoundFont served at `/assets/band/` | Studio open | 1st score | 2nd score | 1st again | Compare | SoundFont requests |
|---|---|---|---|---|---|---|
| none (sonivox, 1.35 MB) | 415 MB | 1,125 MB | 1,160 MB | 1,463 MB | 1,614 MB | — |
| mobile, 77 MB | 416 MB | 1,661 MB | 1,837 MB | 1,854 MB | 2,497 MB | network once, then disk cache |
| 16-bit, 195 MB | 414 MB | 2,448 MB | 2,563 MB | 2,248 MB | 3,891 MB | **network every time** (5 × 195 MB) |

Time to a ready player on loopback: 0.8–1.9 s. Over Wi-Fi (an estimate at 30 MB/s), a 195 MB download adds about 6.5 s per score.

To vary the file, point `BRASSCRIBE_BAND_SOUNDS_DIR` at a folder with `mapping.json` and the SoundFont as `brasscribe-band.sf2`. A symlinked file is refused by `StaticFiles`; use a copy or `cp -c`.

### M2. Cache-Control A/B

Same probe, engine with and without the header. The 195 MB file was downloaded on every open either way. The 77 MB file came from the disk cache on the second open either way (heuristic freshness from Last-Modified). Conditional requests work without the header: `curl -H 'If-None-Match: <etag>'` → 304, 0 bytes, 1 ms. The header is kept for Studio's own files (see section 1).

### M3. Event streams against the request pool

```sh
pixi run python qa/perf/sse_starve.py 10 39 41 60
```

| Open streams | Before 0696ca8 | After |
|---|---|---|
| 10 | 9 ms | — |
| 39 | 5 ms | — |
| 41 | 13,023 ms | 10 ms |
| 45 | — | 6 ms |
| 60 | timeout (20 s) | 11 ms |
| 120 | — | 6 ms |

### M4. Android event stream read timeout

`cd apps/android && ./gradlew :engine-client:test --tests '*EventStreamTimeoutTest'`. A local server sends one event, stays quiet 12 s, then ends the job. Before 8148c8e the client made 2 connections (the first cut at 10 s by OkHttp's read timeout); after, 1. That the job then fails after six such cuts in a row comes from reading `KtorEngineApi.events` (`MAX_RECONNECTS = 5`; `failures` resets only on a real event), not from a run.

Heap limits on the emulator: `adb -s emulator-5554 shell getprop dalvik.vm.heapgrowthlimit` → 192m, `dalvik.vm.heapsize` → 576m.

### M5. Engine stage timings from run manifests

```sh
pixi run python qa/perf/run_stages.py data/runs
```

49 manifests. Median / max seconds when a stage actually ran:

| Stage | n | Median | Max |
|---|---|---|---|
| stems (MEGA-53) | 2 | 72.2 | 74.7 |
| transcribe.mix.muscriptor | 4 | 31.1 | 91.2 |
| transcribe.mix.basic-pitch | 4 | 15.4 | 67.9 |
| arrange (music21 reference) | 35 | 13.3 | 110.8 |
| export (MusicXML, PDF, MP3, parts, braille) | 30 | 8.9 | 28.5 |
| beats | 6 | 8.7 | 375.9 (GPU mutex wait, #23) |
| layers | 5 | 1.6 | 2.9 |

A re-run with all model stages cached takes 13–45 s, all of it arrange and export. Full pop-rock runs: 168–174 s.

`run_stages.py` also prints the median and largest `queue_wait_s` for manifests that record it (from ec3875a on), so queueing is no longer mistaken for a slow stage.

**Stage parallelism (3a1ac5b).** Two typical jobs in a fresh data directory (models from the main checkout), every stage forced with `--cold all`, alternating the setting:

```sh
BRASSCRIBE_STAGE_PARALLELISM=1 pixi run brasscribe run --profile solo --cold all take30.wav   # then =3
BRASSCRIBE_STAGE_PARALLELISM=1 pixi run brasscribe run --profile brass-band --cold all data/mikkel/mikkel.wav
```

| Job | Parallelism 1 | Parallelism 3 |
|---|---|---|
| Solo take, 30 s of Mikkel (beats, SwiftF0, Basic Pitch, MuScriptor, contour, arrange, export) | 23.2, 21.4 s | 19.8, 18.7 s |
| Brass band, all of Mikkel (247 s; beats, MuScriptor, Basic Pitch, arrange, export) | 95.6 s | 92.2 s |

The first run of each profile, with a cold file cache and nothing cached, took 44.2 s (solo) and 107.6 s (band). The gain is small because the two GPU stages still run one after the other and arrange and export wait for all of them; in the band job MuScriptor alone is 75 s. No GPU waits were recorded in these runs. The setting stays off by default: parallel stages add their peak memory together (MuScriptor and Basic Pitch on a long mix).

### M6. Adapter start-up cost

```sh
PYTHON="pixi run python" qa/perf/adapter_overhead.sh data/mikkel/mikkel.wav swift-f0 basic-pitch muscriptor
```

| Adapter | 2 s clip (cold) | 2 s clip (warm) | 60 s clip (warm) |
|---|---|---|---|
| swift-f0 | 1.0 s | 0.3 s | 0.3 s |
| basic-pitch (CoreML) | 10.8 s | 2.2 s | 1.8 s |
| muscriptor (MPS) | 8.6 s | 2.1 s | 15.1 s |

**Warm adapter workers: the ceiling, and why they are not built.** In the solo job above, the five adapter calls took beats 1.8 s, SwiftF0 0.3 s, Basic Pitch 2.5 s, MuScriptor 9.1 s and contour 0.3 s. Counting all of beats and the warm fixed costs of the others as start-up (0.3 + 2.2 + 2.1 + 0.3 s) gives at most 6.7 s of 22.3 s, 30 %, with stages in order; with parallelism on, SwiftF0, Basic Pitch and the contour already run beside the GPU stages, so at most beats and MuScriptor's 3.9 s of 19.2 s, 20 %. The band job has three calls: at most 6 s of 95 s, 6 %. The first job after the machine has been idle pays 9–11 s per adapter, which a worker would save only if it had stayed alive through the idle time. Below the 30 % bar on a typical job, so this is the design, not code:

- **Protocol.** `run_adapter.py --serve <adapter>` in the adapter's own environment (uv project or pixi environment, as today) loads the model once, then reads one JSON request per line on stdin (`{"id", "src", "dst", "params"}`) and answers one line on stdout (`{"id", "ok", "error", "seconds"}`); logs go to stderr. One request at a time per worker. Each adapter's entry point splits into `load()` and `run(src, dst, params)`.
- **Per-request settings.** Today some settings are environment variables of the call (`BEAT_THIS_MODEL=small0` for the solo profile). They become request parameters; a setting that changes the loaded model keys the worker, so (adapter, model) has its own worker.
- **Lifecycle.** Started on the first call, stopped after an idle timeout (`BRASSCRIBE_WARM_ADAPTERS=<seconds>`, 0 = off, the default), killed with the engine (own process group). A worker that exits or times out during a request is replaced, and the request is retried once as a one-shot process, as now. The GPU mutex is still taken per request, not per worker.
- **Memory.** An idle worker keeps its model resident: about 1–2 GB for MuScriptor medium on MPS and a few hundred MB for Beat This and Basic Pitch (**R**, not measured). The MPS allocation stays with the process while it is idle, which competes with other GPU users (Bandroom, a second engine), so heavy workers need a short timeout.
- **Invalidation.** A worker is keyed by the adapter fingerprint the cache already uses (`adapters.py` `fingerprint`: scripts, `run_adapter.py`, environment) plus the model file hashes; when any changes, the old worker is stopped and the next call starts a new one.

### M7. Rust core per conformance case, and the band arrangement's memory

```sh
cd core && cargo build --release -p brasscribe-cli && cd ..
PYTHONPATH=core/conformance pixi run python qa/perf/core_times.py core/target/release/brasscribe-core
cd core && cargo test -p brasscribe-ffi --release --test layers_band_c_api -- --ignored c_abi_alone   # under /usr/bin/time -l
```

- All 405 cases in 9.5 s (best of three each). Everything except Mikkel takes under 35 ms and under 25 MB.
- The 14 Mikkel layer cases take 350–530 ms each. Peak RSS was 731–761 MB before 5f07ff1 and 557–588 MB after, with byte-identical outputs (`diff -r` of all 14 output folders).
- C ABI `bc_arrange_layers_band`, a process making only that call (the inputs are held by the caller, as in C#): 1,098 MB before 4152f83 and 923 MB after (3 runs each, ±1 MB).
- 16 `solo-beats/*/layers` cases exit 101 here because the full suite synthesises their inputs first; they are not timed.

### M8. Engine requests

- Upload: `curl --limit-rate 20M -F file=@data/mikkel/mikkel.wav .../v1/audio`, sampling `ps -o rss=` every 0.1 s: 51.6 → 71.0 MB while receiving 71 MB.
- `GET /v1/jobs` with 49 runs on disk: 262 ms cold, 50 ms warm (audit). Re-measured on the same 49 runs with `curl -w "%{time_total}"`, 12 calls against a fresh `brasscribe serve`: before 3335aa6 first call 91 ms, then median 52 ms; after, first call 66 ms, then median 3.3 ms. In process (TestClient, 15 calls, 3 starts each): warm median 50–52 → 2.2–2.6 ms.

### M9. V8 argument limit

`node -e 'Math.max(...new Array(n).fill(1))'`: 100,000 is fine and 120,000 throws RangeError.

## 5. Not measured, and how to measure

- **iOS / iPadOS memory with the band.** Doc 12 estimates 270–535 MB. On iOS the samplers stream from disk (`SoundBank.swift:88-93` only switches streaming off on macOS), so the iOS number may be much lower. Measure on a headless simulator you create for it, or better, a device. Open the full-band golden score, then Review, then export audio, and record `footprint <pid>` or Instruments' Allocations and VM Tracker at each step. Do the same on macOS for #6.
- **Windows Play.** Time `OnLaunched` to the first frame with and without a2ff100 (ETW or a `Stopwatch` log). Take a `dotnet-counters` or `dotnet-gcdump` snapshot after start-up and after playing a band score, to find out whether alphaTab keeps the 195 MB array and decodes it to float32. Time #9 (stop recording).
- **Android on a device.** `SoundFontMemoryTest` needs a sideloaded SoundFont and measures the steady state, not the peak during load. Add a test that records `Debug.getNativeHeapAllocatedSize` and `Runtime` peaks while opening the score screen twice.
- **Engine throughput with overlapping stages (#22).** Build a profile with SwiftF0 and Basic Pitch running beside MuScriptor, and compare wall time on a cold cache.
