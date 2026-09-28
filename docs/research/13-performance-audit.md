# 13 — Performance audit: memory, main thread, start-up, engine, network, core

**Why.** An Android video upload read the whole file into memory, copied it again, and crashed at the 512 MB heap (fixed in 0c8b98b by streaming the upload and extracting the audio on the device). This audit looks for the same class of problem everywhere else: the engine (`engine/`, `music/`, `ml/adapters`), the Rust core, Studio, Play on Apple, Android and Windows, and Bandroom on macOS and Windows. Date: 2026-09-28, on `main` at a485bef.

**Short answer.**
- **Worst measured problem: Studio's band sound.** alphaTab holds about **7× the SoundFont** in the browser. Opening one score costs +0.54 GB with the 77 MB SoundFont that every shipped build serves, and +1.3 GB with the 195 MB one. Compare opens two players (3.9 GB for the browser with the 195 MB file). Opening another score builds a new synth. With files over Chrome's cache-entry limit, it also downloads the SoundFont again.
- **Worst engine problem (fixed): event streams starved the API.** Forty open job event streams took every thread of the engine's request pool. `GET /v1/health` then waited 13 s, or timed out. Fixed: 120 streams, 6 ms.
- **Worst Android problem (fixed): the event stream broke every 10 s.** OkHttp's 10 s read timeout is shorter than the engine's 15 s keepalive. Every quiet stage cost a reconnect, and six in a row ended the job with "event stream lost".
- **Worst core problem (partly fixed): the band arrangement with stems peaked at 1.10 GB** for Mikkel's four 43.5 MB stems through the C ABI Windows Play uses. Two copies are removed: the CLI goes from 750 to 575 MB, and the C ABI from 1.10 to 0.92 GB, with byte-identical output. What remains is decoding every stem to float32 when only an envelope is needed.
- Nine commits on `perf/audit` fix seven items, each with a test (table below). Everything else is in the ranked list with its size.

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
| 5d3805a feat(engine): Cache-Control on Studio files and band sounds | Engine / Studio | No `Cache-Control`, so browsers guessed a lifetime from Last-Modified. Studio files: `no-cache` (revalidate, 304 in ~1 ms). Band sounds: `public, max-age=86400`. | No change for the SoundFont (see M2). The gain is that an unhashed `studio.js` can no longer run stale after an update. | `test_static_files_say_how_long_to_cache` |
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
| 13 | Android | `ui/ScoreScreen.kt:136-138` `LaunchedEffect(controller) { controller.load(r.musicXml.toByteArray()) ... }` | **C**: runs on the main dispatcher; the whole MusicXML parse and `prepareSound` run there. | Parse on `Dispatchers.Default`, render on main. | M |
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
| 22 | Engine | `dag.py:188` stages run one after another; each adapter is a new process (`adapters.py:197`) | **M**: fixed cost per adapter call, warm: MuScriptor 2.1 s, Basic Pitch 2.2 s, SwiftF0 0.3 s; cold (first call after idle) 8.6–10.8 s. Per job this is a few seconds against stems (72 s) and MuScriptor on a mix (31–91 s). | Run CPU stages (SwiftF0, Basic Pitch on CoreML) beside GPU stages; keep a warm worker per adapter only if many short jobs matter. | M–L |
| 23 | Engine | `adapters.py:203` logs "waiting for GPU mutex" before every heavy stage, whether or not it waits; `:165` polls every 5 s; stage seconds include the wait | **M**: a solo run shows `beats` 375.9 s on a 7 s input (`20260926-005002-solo-8a82c3`), almost certainly queueing. **C** for the unconditional log line. | Log only when the lock is held; record wait and run time separately in the manifest. | S |
| 24 | Engine | `jobs.py:112-117` `list()` parses every manifest and `events.jsonl` on disk per call | **M**: `GET /v1/jobs` 50 ms warm (262 ms cold) for 49 runs, linear in runs. | Keep a summary index; skip events for the list. | S–M |
| 25 | Rust core | `arranger.rs:80` phrase end recomputed per note (O(n²)); `harmony.rs:21` every note per beat (O(beats × notes)) | **M**: the whole Mikkel arrangement takes 0.35–0.5 s, so not hot today. **C** for the loops. | Running maximum; sweep line. Keep output byte-identical (conformance). | S / M |
| 26 | Engine | Upload | **M**: streamed and hashed in 1 MB chunks; engine RSS +19.5 MB while receiving 71 MB at 20 MB/s. **R**: written twice (Starlette spools, then `store_upload` copies). | Acceptable. Optionally stream the multipart body straight to the upload file. | S |

### Waste

| # | Platform | Where | Evidence | Proposed fix | Size |
|---|---|---|---|---|---|
| 27 | Android | `score/BandSoundFontFile.kt:35-41` copies the 77 MB asset to `filesDir` | **C**: second 77 MB on disk; slow first open. The asset is stored uncompressed. | Read through `assets.openFd(...)`. | S |
| 28 | Android | ONNX sessions built per transcription (`AppContainer.kt`) | **R**: a few hundred ms per run. | Cache the sessions. | S |
| 29 | Windows Play | `Microsoft.ML.OnnxRuntime.DirectML` shipped, no app code creates a session | **R**: install size. | Drop until used. | S |
| 30 | Studio | `index.html:19` `<script src="assets/alphatab/alphaTab.min.js">` parser-blocking (1.1 MB) | **C**. | `defer`, or load with the first score view. | S |
| 31 | Bandroom (both) | Polling every 3–5 s while idle, re-publishing unchanged state | **R**. | Compare before assigning; poll pairing only with the panel open. | S |
| 32 | Docs | `12-band-sound.md:305` says both Bandroom apps bundle the 16-bit 195 MB SoundFont | **C**: both bundle the 77 MB mobile file (see #21). | Correct the doc. | S |

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

### M6. Adapter start-up cost

```sh
PYTHON="pixi run python" qa/perf/adapter_overhead.sh data/mikkel/mikkel.wav swift-f0 basic-pitch muscriptor
```

| Adapter | 2 s clip (cold) | 2 s clip (warm) | 60 s clip (warm) |
|---|---|---|---|
| swift-f0 | 1.0 s | 0.3 s | 0.3 s |
| basic-pitch (CoreML) | 10.8 s | 2.2 s | 1.8 s |
| muscriptor (MPS) | 8.6 s | 2.1 s | 15.1 s |

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
- `GET /v1/jobs` with 49 runs on disk: 262 ms cold, 50 ms warm.

### M9. V8 argument limit

`node -e 'Math.max(...new Array(n).fill(1))'`: 100,000 is fine and 120,000 throws RangeError.

## 5. Not measured, and how to measure

- **iOS / iPadOS memory with the band.** Doc 12 estimates 270–535 MB. On iOS the samplers stream from disk (`SoundBank.swift:88-93` only switches streaming off on macOS), so the iOS number may be much lower. Measure on a headless simulator you create for it, or better, a device. Open the full-band golden score, then Review, then export audio, and record `footprint <pid>` or Instruments' Allocations and VM Tracker at each step. Do the same on macOS for #6.
- **Windows Play.** Time `OnLaunched` to the first frame with and without a2ff100 (ETW or a `Stopwatch` log). Take a `dotnet-counters` or `dotnet-gcdump` snapshot after start-up and after playing a band score, to find out whether alphaTab keeps the 195 MB array and decodes it to float32. Time #9 (stop recording).
- **Android on a device.** `SoundFontMemoryTest` needs a sideloaded SoundFont and measures the steady state, not the peak during load. Add a test that records `Debug.getNativeHeapAllocatedSize` and `Runtime` peaks while opening the score screen twice.
- **Engine throughput with overlapping stages (#22).** Build a profile with SwiftF0 and Basic Pitch running beside MuScriptor, and compare wall time on a cold cache.
