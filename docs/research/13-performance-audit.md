# 13 — Performance audit: memory, main thread, start-up, engine, network, core

**Status (2026-09-29):** the fixes marked fixed below are on `main` (the audit and app-side fix branches are merged). Items marked open in the ranked list are still open.

**Why.** An Android video upload read the whole file into memory, copied it again, and crashed at the 512 MB heap (fixed in 0c8b98b by streaming the upload and extracting the audio on the device). This audit looks for the same class of problem everywhere else: the engine (`engine/`, `music/`, `ml/adapters`), the Rust core, Studio, Play on Apple, Android and Windows, and Bandroom on macOS and Windows. Date: 2026-09-28, on `main` at a485bef.

**Short answer.**
- **Worst measured problem (fixed): Studio's band sound.** alphaTab held about **7× the SoundFont** per player in the browser. Opening one score cost +0.52 GB with the 77 MB SoundFont that every shipped build serves, and +1.3 GB with the 195 MB one. Compare opened two players (3.9 GB for the browser with the 195 MB file), and files over Chrome's cache-entry limit were downloaded again for every score. Fixed (2a9c9e4, 8103324): one synth per page, the SoundFont loaded once and kept in IndexedDB. One score now costs +0.31 GB (77 MB) and +0.80 GB (195 MB) over General MIDI; Compare with the 195 MB file 3,871 → 2,012 MB; a revisit is one 304.
- **Worst engine problem (fixed): event streams starved the API.** Forty open job event streams took every thread of the engine's request pool. `GET /v1/health` then waited 13 s, or timed out. Fixed: 120 streams, 6 ms.
- **Worst Android problem (fixed): the event stream broke every 10 s.** OkHttp's 10 s read timeout is shorter than the engine's 15 s keepalive, so every quiet stretch cost a reconnect (measured). By the reconnect logic, six in a row end the job with "event stream lost", which a stage silent for about a minute would do (read from the code, not seen running).
- **Worst core problem (partly fixed): the band arrangement with stems peaked at 1.10 GB** for Mikkel's four 43.5 MB stems through the C ABI Windows Play uses. Three copies are removed: the CLI goes from 750 to 575 MB, and the C ABI from 1.10 to 0.83 GB, with byte-identical output (the C ABI now borrows the caller's stems and contour instead of copying them). What remains is decoding every stem to float32 when only an envelope is needed.
- On `perf/audit`, seven commits fix seven items, each with a test (table below). Two more add the probes and this document. On `perf/apps`, nine more fix the app-side items #3 (partly), #5, #8, #9, #11, #13, #14, #18 and the Bandroom Windows start-up check (section 1, second table). Everything else is in the ranked list with its size.
- **Worst Android problem found on `perf/apps` (fixed): the view model kept the last score's synth.** With the band SoundFont bundled, three opens of a score from Home peaked at 547 MB of the 576 MB large heap, and ScoreRenderTest's repeated opens ran alphaTab's SoundFont load out of memory (**M**). Now: 150–190 MB with no SoundFont, and a score left behind keeps under 40 MB.

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
| 2a9c9e4 perf(studio): one synthesizer and SoundFont per page | Studio | Every opened score built its own alphaTab synth worker and loaded the SoundFont into it; Compare ran two. The page now keeps one worker synth (`lib/sharedsynth.ts`) with the SoundFont loaded once, handed to the score that plays (Compare: the one whose Play is pressed). The bytes are fetched once per page and transferred to the worker, not copied. Leaving a score gives the synth back and destroys its api; a load that finishes after the element left builds nothing. | Mikkel, median of 3, browser RSS: 77 MB file, one score 1,656 → 1,445 MB, Compare 2,497 → 1,858 MB; 195 MB file 2,444 → 1,932 and 3,871 → 2,012 MB. Synths per session 5 → 1. Moving the player in Compare: ready in 15 ms (**M**, M1) | `tests/sharedsynth.test.ts`; `browser/soundfont.spec.ts` (one synth and one download across re-open, navigation and two scores; the moved synth plays the other score's MIDI) |
| 8103324 perf(studio): keep the band SoundFont across visits | Studio | Chromium never disk-caches the 195 MB file. Studio keeps the SoundFont in IndexedDB (works over LAN http, unlike the Cache API) and revalidates it with the ETag; offline, the kept copy plays. `build.mjs` copies the SoundFont with its own mtime, so ETag and Last-Modified survive rebuilds. | 195 MB file: downloads per session 5 × 195 MB → 1; after a reload, one 304 with no body (**M**) | `tests/soundfontstore.test.ts`; `browser/soundfont.spec.ts` (reload → 304) |
| 81d05e9 perf(engine): list jobs from cached manifest summaries | Engine | `GET /v1/jobs` parsed every manifest, read every `events.jsonl` and walked every `outputs/` per call. Finished runs are kept per run, keyed by the manifest's mtime and size, with their output list; the list never reads events. | 49 runs, warm: 52 → 3.3 ms; first call after start 91 → 66 ms (**M**) | `engine/tests/test_job_list.py`: a second list parses nothing, a changed manifest is parsed again |
| 091217a feat(engine): record GPU queue wait apart from stage run time | Engine / Studio | Stage seconds included the wait for the GPU mutex. Manifests, stage events and job stage states now carry `queue_wait_s` and `run_s` beside `seconds` (still the wall clock). "waiting for GPU mutex" is logged only when the mutex is held; it is polled every 1 s instead of 5 s. Studio shows "ran … · waited …" in the stage graph, stage details and manifest table. | A stage behind a held mutex: 0.8 s wait recorded as `queue_wait_s`, not run time (**M**, test) | `engine/tests/test_gpu_wait.py`, `studio/tests/stagetime.test.ts` |
| 8745559 feat(engine): optional bounded stage parallelism | Engine | `BRASSCRIBE_STAGE_PARALLELISM` (default 1: unchanged) runs up to that many stages whose inputs are done; at most one GPU stage per job at a time, and the GPU mutex still orders jobs. Events are serialised, the manifest keeps pipeline order, and the file-hash index now saves under a lock (two stages saving at once raced on its temporary file). | 30 s solo take, all stages forced: 22.3 → 19.2 s (−14 %); brass band on Mikkel: 95.6 → 92.2 s (−4 %) (**M**) | `engine/tests/test_stage_parallelism.py`: CPU and GPU stages overlap with 2, GPU stages never do, nothing overlaps with 1 |
| ad1bdc2 fix(studio): piano roll and beat summary without argument spreading | Studio | `Math.max(...list)` over every note or beat; V8 throws RangeError at about 110,000 arguments. | Precaution. Mikkel has 20,758 MIDI events. (**M**: limit measured) | `studio/tests/extent.test.ts` |

### On `perf/apps`: app-side fixes

| Commit | Platform | What | Before → after | Test |
|---|---|---|---|---|
| 71cde17 perf(android): parse the composition once per score for humanization | Android (#14) | `RustCoreBridge` keeps the last composition's `Performance` and reuses it for every part; a new composition replaces and closes it. `humanize` is synchronized with the cache. | One parse per part (18 for a band) → one per score. Host, Mikkel golden, 7 parts: 64 → 27 ms (**M**). | `RustCoreBridgeTest.aScoreParsesItsCompositionOnceForAllParts`: one build for 7 parts, output equal to a fresh `Performance` per part |
| c7920d6 perf(android): load the band SoundFont when it is needed and let it go with the score | Android (#3, partly) | The SoundFont loads once a score has shown for 1.5 s, or at the first Play before that (the Play waits for it). The export screen keeps only the score's MIDI source (`ScoreMidi`), not the controller, whose synth held the SoundFont until the next score replaced it. | Three opens from Home: peak 547 → 150–190 MB of heap. A played score left behind: 244 → under 40 MB kept. Play after a moment's reading: 15 ms; Play right after opening: about 0.4 s (**M**, M10) | `ScoreMemoryTest` (heap sampled every 10 ms); `SoundFontMemoryTest` and `OutputStageInstallTest` play first |
| 269c24f perf(android): parse the score off the main thread | Android (#13) | `ScoreController.load` is a suspend function. The MusicXML parse and the playback plan run on `Dispatchers.Default` and return plain values; the controller applies them and renders on the main thread. A load cancelled while it parses leaves the controller unloaded. | The whole parse moved off the main thread (**C**; not timed) | `ScoreLoadTest`: parse thread, cancelled load; `ScoreRenderTest` passes |
| b5071b8 perf(android): recordings stream to disk, with a stated length limit | Android (#5) | `TakeSink` writes each buffer to the take's WAV as it arrives and keeps samples in memory only up to the import budget (`AudioDecoder.maxSamplesInMemory`, about 8 minutes on a 576 MB heap). Takes stop at 3 hours; the record screen says so, and says when a take has become too long to score on the phone. | 11.5 MB of heap per minute plus a full copy at stop → flat past the budget (20 minutes of samples: under 16 MB heap growth) (**M**, JVM) | `TakeSinkTest`; `MicTakeTest` records from the emulator's microphone |
| 354172a perf(windows): stop a recording without blocking the UI thread | Windows Play (#9) | `StopAsync` awaits `StopWait.WithinAsync` (the 2 s cap kept as a timeout) instead of blocking in `Task.Wait`. A second stop during the wait returns the first one's result. | The UI thread no longer waits (**C**; not timed on Windows) | `StopWaitTests`: on a stand-in UI thread whose "stopped" callback is posted to it, the await ends quickly; the old `Wait` runs to the timeout |
| e33c2da perf(windows): read the dev brass SoundFonts one at a time, in the background | Windows Play (#8) | `Load` only lists the 11 files; `ApplyTo` reads, patches in place and releases one file at a time in the background. Byte-identical output. | macOS managed heap on the dev set: `Load` allocated 566 MB and held 283 MB → 0 and 0; heap after `ApplyTo` 474 → 191 MB (**M**) | `BrassSoundSetTests` (SHA-256 of the old clone-based output, no copy, `Load` with the files locked) |
| eb9dfa3 perf(windows): read cached layer stems off the UI thread | Windows Play (#11) | Both reads of the layer cache folder run in `Task.Run`; the contour `.npz` is read from disk without a second in-memory copy. | Cache hit no longer reads stems on the UI thread (**C**) | `LayerInputsTests`: a FIFO stem proves `LoadAsync` returns before reading; fails on the old code |
| df143dd perf(bandroom): check setup off the UI thread and remember when it is complete | Bandroom Windows (start-up row) | `pixi.lock` is hashed once per check, streamed, and cached while its size and time do not change; a true result is remembered. The start-up check and `FinishSetup` await `IsCompleteAsync`. | Each check read the 1.2 MB lock twice and walked the workspace on the UI thread → once, streamed, off the UI thread (**C**). The flyout is still built at start-up. | `BootstrapTests`: old markers still count; a complete setup answers with `pixi.lock` locked |
| 5f91627 perf(bandroom): verify model checksums off the main actor | Bandroom macOS (#18) | `verify` hashes in 4 MiB chunks in a detached task, reports a "Checking the download · N%" progress (at most 4 per second), and is cancelled by Pause (the `.part` file is kept). Network progress hops to the main actor are throttled to 4 per second. | Main actor blocked 0.38–0.40 s per GB (about 0.55 s for a 1.4 GB model) → longest main-actor gap 6 ms, same 2.7–2.8 GB/s (**M**, harness copy of the loop, warm cache) | `ChecksumTests`, `ThrottleTests` (`make test`: 87 tests) |

Bandroom Windows model downloads were checked for the same hashing pattern: they already hash off the UI thread (`ModelDownloader.cs:156` runs the download in `Task.Run`, `Sha256Hex` streams, `GitBlobId` hashes in 1 MiB chunks). The one gap: Pause during the hash of a 1.4 GB file waits for the hash to end.

The same branch carries two score-screen fixes that are not from this audit: every bottom sheet opens fully and keeps clear of the navigation bar (edbaa33), and the landscape control row has no More chip of its own; what does not fit is in the top bar's ⋯ sheet (82b864d).

`main` fixed the same Studio stack overflow on open (c3dc2ad, alphaTab's self-referencing `loadedMidiInfo`). This audit found it independently: the Studio e2e "the Mikkel run" failed before that commit.

## 2. Findings, ranked by user impact

Crash or out of memory first, then jank, slow, waste. Size: S (hours), M (a day or two), L (more).

### Crash / out of memory

| # | Platform | Where | Evidence | Proposed fix | Size |
|---|---|---|---|---|---|
| 1 | Studio | `studio/src/components/score.ts:244` `this.api?.destroy()` then `:271` `new alphaTab.AlphaTabApi(...)` with `soundFont` URL `:261`; Compare `views/compare.ts:194-195` two `bs-score`, `:228` both loaded | **M**: browser RSS after one score was 1,125 MB with General MIDI, 1,661 MB with the 77 MB SoundFont and 2,448 MB with the 195 MB one. Compare after that: 1,614, 2,497 and 3,891 MB. alphaTab cost about 7× the file per player. **Fixed** (2a9c9e4, 8103324): 1,445 and 1,932 MB after one score, 1,858 and 2,012 MB in Compare. What is left is alphaTab's own copy: the sample chunk plus the decoded samples, 228 MB for the 77 MB file (M1). | Done: one synth per page, handed between scores. Not done: start the synth on first Play. | — |
| 2 | Rust core / Windows Play (partly fixed) | `energy.rs:52-59` decodes each stem to f32; `LayerInputs.cs:50` `File.ReadAllBytes` of each stem | **M**: C ABI call on Mikkel 0.92 GB peak after the two fixes above, for 174 MB of WAV. **Fixed:** `c_api.rs` copied each stem (`to_vec`); the C ABI now borrows the caller's MIDI, stems and contour for the call (`bc_arrange_layers_band_contour` takes the contour as four `double` arrays, not JSON). Peak RSS 923 → 834 MB, heap peak 830 → 664 MB (M7). The stems are only used for envelopes and the separation check. | Done: borrow the caller's buffers. Open: decode straight to a mono envelope in blocks, never a full f32 stem (M). Windows: pass file paths, or memory-map (M–L). | M |
| 3 | Android (partly fixed, c7920d6) | `AndroidManifest.xml:24` `android:largeHeap="true"`; `ScoreController.kt:310` `sf.readBytes()` | **M**: emulator heap growth limit is 192 MB normally and 576 MB with `largeHeap`. **C/M**: 0c8b98b measured about 220 MB of heap for the SoundFont (the steady state is about 3× the file). The app does not work without `largeHeap`, and a device with a smaller large-heap limit has little room left. | Short term: keep `largeHeap` and budget the other buffers (#5). Long term: stream samples from disk (sfizz already does), or a smaller mobile SoundFont. **Done:** the SoundFont loads only after 1.5 s on the score or at the first Play, and goes with the score (M10). `largeHeap` stays: playing still peaks at about 340 MB. | L |
| 4 | Apple Play | `NotationKit/ScoreRenderer.swift:252` `sounding(atBeat:)` reads `timemap` without the lock; `:140-143` `apply()` rewrites `timemap` and `measureIDs` under the lock from `Task.detached` (`PracticeModel.swift:158`); called at 20 Hz from `PracticeModel.swift:324` | **C**: an unsynchronised read and write of a Swift Array during playback can crash. | Build the arrays in locals and publish them under the lock; read under the lock or from a snapshot. | S |
| 5 | Android (fixed, b5071b8) | `audio/.../Recorders.kt:44` `FloatBuilder()`, `:57`/`:124` `pcm.addAll`, `:83`/`:143` `pcm.toArray()` | **C**: recording grows without a cap (11.5 MB per minute at 48 kHz), plus a full copy at the end. **R**: can coexist with an imported take, the solo WAV and the decoded score MP3 (`PlayViewModel.kt`) and the SoundFont. | Write samples to the WAV as they arrive (`WavWriter` exists); cap in memory like `AudioDecoder.maxSamplesInMemory`. | M |
| 6 | Apple Play (macOS) | `PlaybackKit/SoundBank.swift:88-93` `kMusicDeviceProperty_StreamFromDisk` off, macOS only | **C** for the switch. **R**: `docs/research/12-band-sound.md` estimates 270–535 MB for all presets in memory. On iOS the samplers stream from disk (there is no switch), so that estimate is macOS-only. Two or three engines can be alive at once (score, Review, export), which multiplies it (**R**). | Measure first (recipe in section 5). Release the engine when leaving the score; share one engine per piece. | M |
| 7 | Studio | `components/audio.ts:15` `const cache = new Map<string, Promise<AudioBuffer>>()` | **C** for the module-level map. **R**: decoded audio (about 92 MB per 4-minute stereo stem at 48 kHz) is never evicted; the Stems tab preloads 8. | LRU of about 3 buffers, clear on leaving a run. | S |
| 8 | Windows Play (dev builds; fixed, e33c2da) | `BrassSoundSet.cs:53` `File.ReadAllBytes(file)` for 11 files, `:82` `(byte[])sf2.Clone()`; called from `App.xaml.cs:246` before the first frame | **C**: 270 MB read and copied (about 540 MB peak) on the UI thread. Only when the band SoundFont is not bundled. | Patch presets in place, drop the arrays after `ApplyTo`, run in the background. | S |

### Jank (main or UI thread)

| # | Platform | Where | Evidence | Proposed fix | Size |
|---|---|---|---|---|---|
| 9 | Windows Play (fixed, 354172a) | `WasapiCaptureService.cs:154` `done.Task.Wait(TimeSpan.FromSeconds(2), ct)` in a synchronous `StopAsync`, awaited from `StartViewModel.cs:149` | **C** for the blocking wait on the UI thread. **R**: NAudio posts `RecordingStopped` to the captured UI context, so the wait always runs the full 2 s. | Make `StopAsync` truly async (`await done.Task.WaitAsync(...)`). | S |
| 10 | Windows Play | `AlphaTabScorePlayer.cs:133` `lock (Gate) _synth.LoadSoundFont(...)` | **C**: the whole SoundFont parse holds the audio lock. The UI takes the same lock (`IsReady`, `LoadScore`, volume), so Play right after launch blocks until the parse ends. | Parse outside the lock, swap under it; or have UI calls skip the lock until loaded. | M |
| 11 | Windows Play (fixed, eb9dfa3) | `EngineLayerSource.cs:16` `LayerInputs.FromDirectory(dir)` on a cache hit, before the first await, from `OutputOptionsViewModel` on the UI thread | **C**: all stems read with `File.ReadAllBytes` on the UI thread (about 42 MB per minute of audio). | Wrap the cache-hit path in `Task.Run`. | S |
| 12 | Windows Play | `ScoreViewModel.Load` (talking score, `Player.Load` → alphaTab parse and MIDI), `CorrectPitch` → native re-arrange | **R**: all synchronous on the UI thread per score open and per pitch edit. | Parse on the alphaTab worker; FFI in `Task.Run`. | M |
| 13 | Android (fixed, 269c24f) | `ui/ScoreScreen.kt:136-138` `LaunchedEffect(controller) { controller.load(r.musicXml.toByteArray()) ... }`; `score/ScoreController.kt:228` `fun load(...)` is not a suspend function and switches no dispatcher | **C**: the whole MusicXML parse and `prepareSound` run on the main thread. | Parse on `Dispatchers.Default`, render on main. | M |
| 13a | Windows Play | `NativeCoreBridge.cs:219-220` `JsonNode.Parse(compositionJson)` then `bc_humanize_json(request.ToJsonString(), ...)` per part | **C**: the 1.3 MB composition is parsed in C#, serialised again and parsed again in Rust for each of up to 18 parts. | A `Performance` handle in the C ABI (as UniFFI has), or one call for all parts. | M |
| 14 | Android (fixed, 71cde17) | `core-bridge/.../RustCoreBridge.kt:143` `val perf = compositionJson?.let { Performance(it) }` per `humanize` call; loop at `HumanizedPlayer.kt:57` | **C**: the 1.3 MB composition is parsed once per part (18 for a band), on the main thread when the realistic tier loads. | Build `Performance` once per score and pass it to every part. | S |
| 15 | Android | `PlayViewModel.kt:172` and `:177` `scoreLibrary.list()` | **C**: every saved score (MusicXML, composition, evidence) read twice at start-up, and again on every Keep. | Read the index only; load a score on open; save on `Dispatchers.IO`. | S (the double call) / M |
| 16 | Apple Play | `App/Views/ScoreScreen.swift:18` `.task { loadModel() }`, `PracticeModel` is `@MainActor` (`PracticeModel.swift:11`); samplers load per part (`SoundBank.swift:103`) | **C** for main-actor isolation. **R**: MusicXML parse, composition decode and one `loadSoundBankInstrument` per part all on the main thread when a score opens. | Parse and build the engine off the main actor, publish when ready; show the score first. | M |
| 17 | Apple Play | 20 Hz timer sets `position`, which redraws every visible page and rebuilds accessibility labels (`NotationView.swift`) | **R**. | Draw the cursor in an overlay; cache per-layout lookups; stop the timer while stopped. | M |
| 18 | Bandroom macOS (fixed, 5f91627) | `ModelDownloader.swift:24` `@MainActor`, `:223` `try verify(part, as: f)` hashes the whole file; `:214` a main-actor task per network chunk | **C**: SHA-256 of 0.7–1.4 GB model files on the main actor. | `Task.detached` for `verify`; throttle progress to 4 per second. | S |
| 19 | Studio | `views/run.ts:165` `renderHeader(...)` on every SSE event, log lines included | **C** for the call; **R** for its cost. | Re-render on `job`/`stage` events only. | S |
| 20 | Studio | MusicXML parsed up to four times per open (`score.ts` `parseMusicXml`, `buildTalkingScore`, alphaTab, `run.ts` again) | **R**. | Parse once and pass the result on. | S |

### Slow

| # | Platform | Where | Evidence | Proposed fix | Size |
|---|---|---|---|---|---|
| 21 | Studio | Band SoundFont over the network | **M**: a 195 MB file is never taken from Chrome's disk cache, with or without `Cache-Control` (over the per-entry limit). It is downloaded again for every score opened, and twice for Compare. A 77 MB file is cached with or without the header. **C**: every shipped surface serves the 77 MB file (`studio/build.mjs:34`, `apps/bandroom/macos/scripts/stage-band-sounds.sh:11`, `Brasscribe.Bandroom.csproj:89-90`); only a dev engine with `BRASSCRIBE_BAND_SOUNDS_DIR=data/sounds/band` serves the 293 MB 24-bit file. | Keep serving the 77 MB file to Studio. **Fixed** (2a9c9e4: one fetch per page; 8103324: kept in IndexedDB, revalidated with the ETag, a revisit is a 304 with no body). | — |
| 22 | Engine | `dag.py` stages ran one after another; each adapter is a new process (`adapters.py`) | **M**: fixed cost per adapter call, warm: MuScriptor 2.1 s, Basic Pitch 2.2 s, SwiftF0 0.3 s; cold (first call after idle) 8.6–10.8 s. Stage parallelism is done (8745559, off by default): a 30 s solo take 22.3 → 19.2 s, a brass-band run 95.6 → 92.2 s (M5). Warm adapter workers would save at most 30 % of a solo take run in order and about 20 % with parallelism on, and 6 % of a band run (M6), for 1–2 GB held per idle GPU worker: not built, design in M6. | Turn parallelism on by default after a week of use; warm workers only if short solo takes become the main load. | — (parallelism done) / M (workers) |
| 23 | Engine | `adapters.py` logged "waiting for GPU mutex" before every heavy stage, whether or not it waited; polled every 5 s; stage seconds included the wait | **M**: a solo run shows `beats` 375.9 s on a 3 s input (`20260926-005002-solo-8a82c3`, from before the split), almost certainly queueing. Fixed (091217a): `queue_wait_s` and `run_s` per stage in manifests and events, shown in Studio as waited and ran; logged only when blocked; polled every 1 s. Five fresh runs here recorded 0.0 s waits. | Done. | S |
| 24 | Engine | `jobs.py` `list()` parsed every manifest and `events.jsonl` on disk per call, and `api.py` walked every `outputs/` | **M**: `GET /v1/jobs` 52 ms warm for 49 runs, linear in runs; two thirds of it was the `outputs/` walk. Fixed (81d05e9): 3.3 ms warm, only a `stat` per run while nothing changes. | Done. | S |
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
| Bandroom, Windows (hashing fixed, df143dd) | `_bootstrap.IsComplete(_cuda)` on the UI thread (`App.xaml.cs:192`, again at `:208`) hashes `pixi.lock` with `SHA256.HashData(File.ReadAllBytes(...))` (`Bootstrap.cs:96`) and walks the whole bundled workspace (`:89`). `EngineReady` repeats it on progress callbacks (`App.xaml.cs:219`). The flyout window is built even for a background start. | **C** for the calls, **R** for their cost | Compute the hashes once and cache them; build the flyout on first open. | S / M |
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
3. **Done: three stem copies out of the band arrangement** (5f07ff1, 4152f83, and the borrowing C ABI). 175 MB less each on the CLI path and the C ABI for Mikkel, byte-identical output; the C ABI then borrows the caller's stems (#2), another 166 MB of heap.
4. **Open, S: Apple `ScoreRenderer` race (#4).** Publish `timemap`/`measureIDs` under the lock. A crash in playback on zoom or part change.
5. **Done on `perf/apps`: Windows recording stop (#9)** (354172a). Stop awaits the device with the 2 s cap as a timeout; still to be timed on Windows.

Next in line, all S: Android start-up library read once (#15). Done on `perf/apps`: Android `Performance` once per score (#14), Bandroom macOS hash verification off the main actor (#18), Windows layer cache hit off the UI thread (#11). Also done, smaller: Windows SoundFont read off the first frame (a2ff100), `Cache-Control` (5d3805a).

Studio's one-SoundFont-per-page (#1), the largest measured memory cost in the project, is done (2a9c9e4, 8103324).

## 4. Measurements

Scripts are in `qa/perf/` and `studio/perf/`. Machine: Apple M-series Mac, macOS 26, Chromium headless shell from Playwright, engine on loopback.

### M1. Studio: memory and SoundFont traffic per score

```sh
pixi run studio --no-browser --port 8799        # or any engine serving Studio
cd studio && STUDIO_URL=http://127.0.0.1:8799/ RUNS=<run-a>,<run-b> node perf/soundfont-probe.mjs
cd studio && STUDIO_URL=http://127.0.0.1:8799/ RUN=<run-a> node perf/worker-heap.mjs   # what the synth worker keeps
```

Each run starts from an empty profile, opens run A, run B and run A again (hash change, as the Runs view does), then Compare with both, then moves the player to Compare's second score, then reloads the page and opens run A. "Browser RSS" sums the browser process and all its children. Runs: Mikkel (`20260927-224906-orchestra-with-soloist-b03895`, 18 parts, 132 bars) and a brass-band run (`20260926-190056-brass-band-9c0e22`).

Median of 3 runs, MB. Before: the audit's run plus two on a485bef + 81de8c3; after: on 8103324.

| SoundFont served at `/assets/band/` | | Studio open | 1st score | 2nd score | 1st again | Compare | Player to B | Reload, 1st | SoundFont requests |
|---|---|---|---|---|---|---|---|---|---|
| none (sonivox, 1.35 MB) | before | 415 | 1,131 | 1,165 | 1,463 | 1,614 | — | — | — |
| | after | 415 | 1,133 | 1,167 | 1,373 | 1,502 | 1,504 | 1,483 | 1, then 304 |
| mobile, 77 MB | before | 416 | 1,656 | 1,823 | 1,854 | 2,497 | — | — | network once, then disk cache |
| | after | 414 | **1,445** | 1,513 | 1,745 | **1,858** | 1,859 | 1,925 | 1 per page; reload: 304, 0 bytes |
| 16-bit, 195 MB | before | 414 | 2,444 | 2,560 | 2,248 | 3,871 | — | — | **network every time** (5 × 195 MB) |
| | after | 414 | **1,932** | 1,995 | 1,902 | **2,012** | 2,016 | 2,201 | 1 per page; reload: 304, 0 bytes |

Synths created per session: 5 before (one per score, two in Compare), 1 after. Time to a ready player: 0.9–1.3 s for the first score, 0.2–0.6 s for later ones (MIDI only), 15 ms to move the player in Compare. Over Wi-Fi (an estimate at 30 MB/s), the 195 MB download used to add about 6.5 s per score; now once per page, and not again on a revisit.

**What alphaTab keeps.** `perf/worker-heap.mjs` forces a GC in every worker and reads its ArrayBuffer backing stores: the synth worker holds **228 MB** for the 77 MB file and **576 MB** for the 195 MB one (the sample chunk plus the decoded float32 samples; Mikkel uses almost every preset). That is the floor while alphaTab decodes whole samples.

**Target: RSS within about 1.3× of idle plus one SoundFont's decoded size**, with "idle" the General MIDI run at the same step (rendering Mikkel alone costs about 700 MB) and "decoded" the worker's 228 / 576 MB:

| | One score | Compare |
|---|---|---|
| 77 MB, before | 1,656 / (1,131 + 228) = 1.22 | 2,497 / (1,614 + 228) = 1.36 |
| 77 MB, after | 1,445 / (1,133 + 228) = **1.06** | 1,858 / (1,502 + 228) = **1.07** |
| 195 MB, before | 2,444 / (1,131 + 576) = 1.43 | 3,871 / (1,614 + 576) = 1.77 |
| 195 MB, after | 1,932 / (1,133 + 576) = **1.13** | 2,012 / (1,502 + 576) = **0.97** |

All four pass. Counting only what the SoundFont adds over General MIDI, the stricter reading: one score 312 MB for the 77 MB file (1.37× decoded, was 2.3×) and 799 MB for the 195 MB file (1.39×, was 2.3×); Compare 356 MB (1.56×, was 3.9×) and 510 MB (0.89×, was 3.9×). The rest above "decoded" is the transferred download not yet returned to the OS and run-to-run spread (±150 MB on Compare).

To vary the file, point `BRASSCRIBE_BAND_SOUNDS_DIR` at a folder with `mapping.json` and the SoundFont as `brasscribe-band.sf2`. A symlinked file is refused by `StaticFiles`; use a copy or `cp -c`. For "none", move `static/assets/band` aside.

### M2. Cache-Control A/B

Same probe, engine with and without the header. The 195 MB file was downloaded on every open either way. The 77 MB file came from the disk cache on the second open either way (heuristic freshness from Last-Modified). Conditional requests work without the header: `curl -H 'If-None-Match: <etag>'` → 304, 0 bytes, 1 ms. The header is kept for Studio's own files (see section 1). Since 8103324 Studio keeps the SoundFont itself (IndexedDB) and sends `If-None-Match` with `cache: no-store`; the build keeps the file's mtime, so the ETag no longer changes with every `build.mjs` run.

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

`run_stages.py` also prints the median and largest `queue_wait_s` for manifests that record it (from 091217a on), so queueing is no longer mistaken for a slow stage.

**Stage parallelism (8745559).** Two typical jobs in a fresh data directory (models from the main checkout), every stage forced with `--cold all`, alternating the setting:

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
cd core && cargo test -p brasscribe-ffi --release --test layers_band_c_api -- --ignored c_abi_heap_peak --nocapture
```

- All 405 cases in 9.5 s (best of three each). Everything except Mikkel takes under 35 ms and under 25 MB.
- The 14 Mikkel layer cases take 350–530 ms each. Peak RSS was 731–761 MB before 5f07ff1 and 557–588 MB after, with byte-identical outputs (`diff -r` of all 14 output folders).
- C ABI `bc_arrange_layers_band`, a process making only that call (the inputs are held by the caller, as in C#): 1,098 MB before 4152f83 and 923 MB after (3 runs each, ±1 MB). With the C ABI borrowing the caller's buffers instead of copying them: 834 MB (3 runs, ±1 MB; the old binary alternated with it read 922–924 MB). The heap peak, counted by `--ignored c_abi_heap_peak` (run alone), goes from 830 to 664 MB with 166 MB of inputs held by the caller: exactly the four stems. RSS falls by less (89 MB): it also counts pages the allocator has not given back, so its peak is not only live heap. Same output: `c_abi_with_stems_matches_uniffi` and `c_abi_contour_arrays_match_uniffi_and_json`.
- 16 `solo-beats/*/layers` cases exit 101 here because the full suite synthesises their inputs first; they are not timed.

### M8. Engine requests

- Upload: `curl --limit-rate 20M -F file=@data/mikkel/mikkel.wav .../v1/audio`, sampling `ps -o rss=` every 0.1 s: 51.6 → 71.0 MB while receiving 71 MB.
- `GET /v1/jobs` with 49 runs on disk: 262 ms cold, 50 ms warm (audit). Re-measured on the same 49 runs with `curl -w "%{time_total}"`, 12 calls against a fresh `brasscribe serve`: before 81d05e9 first call 91 ms, then median 52 ms; after, first call 66 ms, then median 3.3 ms. In process (TestClient, 15 calls, 3 starts each): warm median 50–52 → 2.2–2.6 ms.

### M9. V8 argument limit

`node -e 'Math.max(...new Array(n).fill(1))'`: 100,000 is fine and 120,000 throws RangeError.

### M10. Android: heap while scores open and play

```sh
cd apps/android && ANDROID_SERIAL=emulator-5554 ./gradlew :app:connectedDebugAndroidTest \
  -Pandroid.testInstrumentationRunnerArguments.class=no.brasscribe.play.ScoreMemoryTest
adb -s emulator-5554 logcat -d | grep ScoreMemoryTest:
```

Needs the phone SoundFont bundled (`data/sounds/band/brasscribe-band-mobile.sf2` at build time, 73 MB). The score is Old Hundredth repeated 16 times in every part (1.4 MB MusicXML, about Mikkel's size). A thread samples `Runtime` heap in use (garbage not yet collected included) and `Debug.getNativeHeapAllocatedSize` every 10 ms. Emulator heap limit 576 MB (`largeHeap`).

| Step | Before c7920d6 | After |
|---|---|---|
| Open from Home three times | peak 547 MB heap (SoundFont loaded on every open) | 150–190 MB, no SoundFont |
| Leave a played score, GC | 244 MB kept | 24–39 MB kept |
| First Play | 22 ms (SoundFont already in) | 15 ms after 1.5 s on the score; 0.38–0.55 s right after opening |
| Play with the SoundFont in | peak about 340 MB | the same |

Without the leak fix, a second score played after the first peaked at 562 MB. alphaTab's load of the file takes 40–100 ms; the rest of the first-Play delay is alphaTab readying its synth after a new SoundFont.

## 5. Not measured, and how to measure

- **iOS / iPadOS memory with the band.** Doc 12 estimates 270–535 MB. On iOS the samplers stream from disk (`SoundBank.swift:88-93` only switches streaming off on macOS), so the iOS number may be much lower. Measure on a headless simulator you create for it, or better, a device. Open the full-band golden score, then Review, then export audio, and record `footprint <pid>` or Instruments' Allocations and VM Tracker at each step. Do the same on macOS for #6.
- **Windows Play.** Time `OnLaunched` to the first frame with and without a2ff100 (ETW or a `Stopwatch` log). Take a `dotnet-counters` or `dotnet-gcdump` snapshot after start-up and after playing a band score, to find out whether alphaTab keeps the 195 MB array and decodes it to float32. Time #9 (stop recording) with the fix (354172a).
- **Android on a device.** `ScoreMemoryTest` (M10) records the peaks on the emulator. Run it on a phone with a smaller large-heap limit to see whether playing (about 340 MB) fits there.
- **Engine throughput with overlapping stages (#22).** Build a profile with SwiftF0 and Basic Pitch running beside MuScriptor, and compare wall time on a cold cache.
