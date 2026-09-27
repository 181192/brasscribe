# Brasscribe Play for Android

Kotlin and Jetpack Compose. Android 10+ (min SDK 29, for AudioPlaybackCapture), target SDK 36, compile SDK 37 (Compose 1.12 requires it). Gradle Kotlin DSL with a version catalog (`gradle/libs.versions.toml`).

## Build and test

```
export ANDROID_HOME=/opt/homebrew/share/android-commandlinetools   # SDK: platform 37, build-tools 36, NDK 28.2, CMake 3.31.6
./gradlew assembleDebug testDebugUnitTest lint
./gradlew connectedDebugAndroidTest          # emulator or device
./gradlew assembleRelease                    # one APK per ABI plus a universal one
```

`testDebugUnitTest` also runs the tests of the plain Kotlin modules.

Some inputs come from outside git and are used only when present:

| Input | From | Used for |
|---|---|---|
| `models/converted/{swift-f0/swift-f0-window.onnx, basic-pitch/nmp-b1.onnx, beat-this/beat-this-small0.onnx}` | `convert/` (all MIT) | Bundled in every build: the offline solo (SwiftF0 spine, Basic Pitch confirmation, Beat This! small beats). Without SwiftF0, "On this phone" is disabled; without the other two, notes stay unconfirmed and the grid is a steady tempo |
| `core-bridge/src/main/jniLibs/` | `scripts/build-core.sh` (cargo-ndk, arm64-v8a + x86_64) | The Rust core. Without it `AppContainer.core` is the Kotlin fallback. The JVM tests of `core-bridge` load the host build (`cargo build --release -p brasscribe-ffi` in `core/`) and skip without it |
| `third_party/onnxruntime/onnxruntime-android-reduced.aar` | `scripts/ort/build-reduced-ort.sh <work dir>` (builds both ABIs, then merges them into the AAR) | Reduced-operator ONNX Runtime 1.30.0 (only the kernels of the three models, `scripts/ort/ops.config`). Without it the full Maven build is used |
| `data/golden/mikkel-arranged-band/` | the golden output | JVM tests only (never packaged). Tests that need it skip themselves when it is missing |
| `third_party/sfizz` | `scripts/fetch-sfizz.sh` (sfizz 1.2.3) | The realistic playback tier. Without it the native library builds a stub and the tier is shown as unavailable. You can also pass `-Pbrasscribe.sfizzDir=<checkout>` |

## Modules

| Module | Kind | What it holds |
|---|---|---|
| `model` | Kotlin/JVM | Composition JSON model (tolerant of new fields), tick map (bars and recording seconds, including the golden file's negative `first_downbeat`), spelling and brass-band transpositions, `PartView`, a monophonic MusicXML writer, a solo quantizer with key and tempo estimates, and the talking-score announcer. `CoreBridge` is the seam for the Rust core |
| `engine-client` | Kotlin/JVM | Ktor client for `engine/openapi.json` (pairing, upload, jobs, SSE progress, results), `ProgressTracker` for the time left, and `FixtureEngineApi` (replays a finished engine output folder with timed stage events, for tests) |
| `pitch` | Kotlin/JVM | SwiftF0, Basic Pitch and Beat This! small on ONNX Runtime (the `ai.onnxruntime` API: the Android build in the app, the desktop build in tests), with their host code ported (SwiftF0 windows and `segment_notes`; Basic Pitch windowing and note decoding; Beat This log-mel, chunking and minimal postprocessor), the resampler, and `SoloPipeline` |
| `core-bridge` | Android library | `RustCoreBridge`: the UniFFI Kotlin bindings from `core/android` plus `libbrasscribe_ffi.so`, behind `CoreBridge` |
| `audio` | Android library with NDK | Decoding audio and video with MediaExtractor/MediaCodec, WAV, microphone capture through Oboe/AAudio, AudioPlaybackCapture, sfizz playback through an Oboe output stream |
| `app` | Android app | Compose UI, capture foreground service, alphaTab score, exports |

## Seams

- **CoreBridge** (`model/.../CoreBridge.kt`). `RustCoreBridge` (core-bridge) is the default: ps13 spelling, the layered arranger for solo takes with lineup, difficulty, key and transposition, the announcer (all 25 talking-score vectors pass through it, EN and NB), the per-part talking score of arranged MusicXML, and humanization. `KotlinCoreBridge` is the fallback when the native library is missing; it has no arranger, per-part talking score or humanization.
- **Engine client.** The client is hand-written. `openapi-generator` 7.25.0 (kotlin, jvm-ktor, kotlinx_serialization) produced code that does not compile for this spec: `additionalProperties: true` became `HashMap<String, Any>()()`, numbers became `@Contextual BigDecimal`, and the SSE stream was typed as a JSON body. `EngineContractTest` compares the client with the vendored `engine-client/openapi.json`: operationIds, every property, required fields and enums. Refresh the spec with `./gradlew :engine-client:syncOpenApi` once `engine/` is in the same checkout.
- **On-device models.** SwiftF0, Basic Pitch and Beat This! small run on ONNX Runtime (one runtime for all three; Basic Pitch's TFLite would need LiteRT as a second runtime). Parity with upstream, JVM tests: SwiftF0 0.00 cents and 36/36 notes; Basic Pitch note F1 1.000 (synthetic and URMP March); Beat This beat/downbeat F1 1.000/1.000 on clicks and URMP, 1.000/0.986 on Mikkel 60–120 s.
- **The offline solo** (`pitch/SoloPipeline.kt`) is the engine's rule through the layered arranger with only a solo layer: SwiftF0 is the spine, Basic Pitch fills both confirmation slots (MuScriptor's too), the SwiftF0 contour gives written durations, Beat This the beats. Each layer's MIDI is written at its adapter's resolution (SwiftF0 480, Basic Pitch 220 ticks per beat at 120 bpm), so onsets round like the reference. On the URMP Entertainer trumpet clip (`data/runs/apple/entertainer-ref`, minimal lineup) it matches the reference note for note: 77 notes, 33 bars, F1 1.000 on pitch, start and duration (`OnDeviceSoloTest`).

## Design system

The app wears the Brasscribe design system (`design/`, generated into `design/dist/`):
- **Wiring** (`app/build.gradle.kts`): the Compose theme and icon enum compile straight from `design/dist/android/kotlin`; `syncDesignResources` syncs the `ic_bc_*` icons, Instrument Serif and the adaptive launcher icon (with its monochrome layer) from `design/dist/android/res` and `design/dist/icons/android/res` into one generated res folder, and the font licence goes to the assets. Nothing is hand-copied, so a token change is a rebuild.
- **Theme** (`ui/theme/Theme.kt`): `PlayTheme` is `BrasscribeTheme` with the display face. Primary is ink (paper in dark); the cursor purple, the uncertainty colours and the loop tint are for the score only. Instrument Serif is used only for `displaySmall` (36 sp screen titles) and the wordmark; everything else is Roboto, in sp, so it follows the font scale.
- **Components** (`ui/Common.kt`): one `PrimaryButton` per screen (52 dp, 12 dp corners, pinned above the navigation bar), tonal/outline/plain buttons, list-row groups with icon wells, practice chips (on = tonal fill, ink edge and a tick), the info note, the brand mark, and the "?" / boxed "?" mark.
- **Screens** follow `design/mockups/png/*phone*` in the Material idiom: first run, Home (one primary, the other ways in as rows), What is this? (choice cards, "where it runs" with Change), making the score (the steps, brass progress, a confirmed Cancel), Check N notes (one note at a time, Keep and Skip, Finish later with a confirm), How should the score be?, the score with its toolbar and a player that wraps and never clips, Share or print (Print as the primary), errors with a way forward, and Settings.
- **The score** colours each uncertain note (head, stem, flags, accidentals) from the tokens, and `score/NotationOverlay.kt` draws its mark from alphaTab's layout (`boundsLookup`, note bounds on) inside alphaTab's scrolling render wrapper: a "?" 1.6 staff spaces tall, and for a very uncertain note (MusicXML `enclosure="rectangle"`) the same "?" in a box with a stroke of at least 1.5 dp. alphaTab's own small text mark is blanked, so its text band still keeps the space. A second overlay under the notation draws the ad-lib tint behind the free-time bars ("ad lib." up to "a tempo"); the loop tint replaces it in a loop, and high contrast has no tints. Measured on the emulator: the mark is 1.6 staff spaces at 100 % (about 14.5 dp) and at 200 % zoom (about 30 dp).
- **Share or print** offers My part ("Solo Cornet (you)", the default, with PDF), Every part (one file per player) and the conductor's score, as on Windows. Part PDFs and braille come from the engine's `parts/NN-Name.*` files; a part's MusicXML is cut from the score and its talking score comes from the core. Print sends one print job per PDF. After a note is changed on the phone, the engine's PDF, braille and audio say "Made before your changes".
- **Check N notes** starts with the player's own part ("Check your part first"), very unsure notes first; Skip sends a note to the back of the queue. The accompaniment layers are folded under one chip. The note card shows the bar on a staff (`score/BarSnippet.kt`, alphaTab without a player) with the note ringed. Change note… offers a semitone, an octave and what each transcriber heard, and re-arranges the score through the core (the golden Composition re-arranges to the golden score, part for part: `RearrangeTest`).

## Features and where they live

- **Inputs** (`ui/HomeScreen.kt`, `capture/CaptureService.kt`, `audio/`):
  - file import through SAF
  - the share sheet (`ACTION_SEND`) and "Open with" (`ACTION_VIEW`)
  - video, whose first audio track is decoded
  - the microphone through Oboe
  - other apps' playback through AudioPlaybackCapture. Play shows an opt-out and DRM notice first, asks for MediaProjection consent, and runs a foreground service of type `mediaProjection` (type `microphone` for mic recording). After 5 s of silence it shows "Nothing is coming through…". Android offers no API that reports an app's opt-out, so silence is the signal.
- **"What is this?"** picks the engine profile: `solo`, `brass-band`, `orchestra-with-soloist` or `pop-rock`. For a solo it also asks where to transcribe: on the phone (offline) or on the companion engine.
- **Transcription** shows a plain-language step, percent, "step n of m", time left and Cancel. A cancel also cancels the engine job.
- **Review** (Check N notes) marks uncertain notes with the design tokens and a shape, as in the score: a "?" above an uncertain note and a boxed "?" above a very uncertain one. One note is checked at a time (Keep, go to next; Skip); Finish later asks first and the score keeps a "N notes marked ? · Check them" line to come back. Every note is also one TalkBack item that speaks the talking-score announcement, with these custom actions:
  - Listen to this bar: plays the original bar, then the score's bar, once. While it plays, the same button (and action) is Stop; it returns by itself when the bar ends, and leaving the note, the screen or the app stops it
  - Keep
  - Next uncertain note
- **Brasscribe on your computer** (Settings) pairs once. Scan the QR code on the computer (the system code scanner from Google Play services: no camera permission), open a `brasscribe://pair` link, type the code, or ask the computer to allow this phone and compare the four-digit match code. The credential is encrypted with an AES-GCM key held in the Android Keystore (StrongBox when there is one), kept per server id in the `credentials` preferences (excluded from backup), and never sent to another engine. A token stored in plain text by an earlier version moves there once and is deleted. Connect checks the credential it holds first and pairs only when there is none or the engine answers 401; the token is rotated when the engine says so.
- **Connection status** on Home and in Settings: connected, looking for (the heartbeat failed twice; it tries the last address, then the address mDNS advertises for the server id, backing off 2 to 30 s), not connected (nothing paired, or not found for 2 minutes), and pair again (only after a 401). The heartbeat is `GET /v1/devices/me` every 20 s while the app is in front (`/v1/health` for a trusted client with no credential, such as the emulator via 10.0.2.2).
- **Output**: lineup (full, minimal, solo part), difficulty (faithful, standard, easier) and key. On-device results are re-arranged by the core; engine results become a new engine job with `lineup`, `difficulty` and `transpose` (the cache reuses every model stage; the MP3 render is skipped for re-arrangements). Without either, only the display choices remain and the key shift is applied in alphaTab.
- **Score** uses alphaTab 1.8.4 (`net.alphatab:alphaTab`, MPL-2.0) with:
  - cursor
  - page layout
  - part selection, with one part (the solo cornet) shown first
  - mute and solo
  - speed from 25 to 150%
  - loop over a bar range typed as numbers, with no dragging
  - count-in and metronome
  - concert or written pitch
  - zoom from 50 to 400%
  - notation colours from the theme tokens (paper, ink, staff lines, cursor), so the score stays readable in dark and high contrast; alphaTab engraves in black on a transparent background by default
  - full screen for playing along and for the stand on stage: the score alone with play, the bar, a bar either way and the way out; no system bars, and the screen stays awake. Back leaves it, and it survives rotation

  Reduced motion (animator scale 0) turns off the animated cursor and scrolls by page. For screen readers, the notation view is one item. It announces the title, the part and "bar n of m", and has the custom actions Next/Previous bar, Next/Previous part and Play this bar. The Text tab is the talking score: one item per event, with Next/Previous bar, Read bar and Play this bar.
- **Band SoundFont**: every part gets its own MIDI channel (drums on channel 10; alphaTab's own two-channels-per-track numbering wraps past 16 and shares presets), its preset at (bank, program) and its `channel_gain_db` from `sounds/mapping.json` (bundled as an asset), and the importer's per-beat instrument and bank changes are removed. The SoundFont itself is read from the app's `sounds/` folder. The full `brasscribe-band.sf2` runs alphaTab out of Java heap (its synth keeps every sample as floats: OutOfMemoryError at the 576 MB large heap with the 149 MB 16-bit file), so `scripts/mobile_soundfont.py` makes `brasscribe-band-mobile.sf2`: the same presets and kit, sustain only, first layer, 22.05 kHz, 58.6 MB. It loads in about 0.1 s.
- **Realistic sound**: every pitched part plays an SFZ instrument through sfizz on its own channel with its band balance, humanized by the core (per player lag, timing and velocity, the soloist leading) and scheduled into the sfizz output sample-accurately (`score/HumanizedPlayer.kt`, 250 ms lookahead, following alphaTab's position and speed). Percussion stays on alphaTab's kit, as in the reference renderer. Each part loads `sounds/<instrument>/<instrument>-sus.sfz`; parts without one play a test tone.
- **Installing sounds**: the app creates `Android/data/no.brasscribe.play/files/sounds/<instrument>/samples` on first start. Files copied in with adb land readable only inside folders the app created, so copy into those, for example `adb push data/sounds/built/cornet-a/. /sdcard/Android/data/no.brasscribe.play/files/sounds/cornet-a/` and the SoundFont into `sounds/`.
- **Exports** go through the share sheet or "Save to Files":
  - MusicXML
  - PDF and MP3, from the engine
  - MIDI, generated by alphaTab from the loaded score
  - talking-score HTML from the core's talking score of the arranged score (every part)
  - braille (BRF) from the engine (`getBraille`); the core does not write braille
- **Languages**: English and bokmål (`values-nb`), with per-app language through the generated locale config. Lint fails on a missing translation.

## Accessibility tests

`app/src/androidTest/.../PlayFlowA11yTest.kt` walks home, then "What is this?", transcription, review, output, score and export on a fixture engine that serves "Old Hundredth" (`apps/fixtures/old-hundredth`, a public-domain hymn arranged by the core with a few uncertain notes; `apps/fixtures/make-old-hundredth.py` rebuilds it). The fixture is packaged in the test APK only, and the test opens it without the file picker. Every action runs with `enableAccessibilityChecks()` (ATF). At the end, the Espresso `AccessibilityChecks` check the whole window, including the alphaTab View. The test asserts:
- headings
- the radio role and its collection position
- progress range info
- the announcement of an uncertain note, and its custom actions
- the score's custom actions, and moving to the next bar
- 48 dp targets

The first run found two real problems, both fixed: an unlabelled empty live region, and part names that alphaTab stores with no-break spaces.

The export test shares MusicXML, MIDI and the talking-score HTML and checks them, plus the PDF and the braille file when the fixture has the engine's renders of them (it has none now; Listen to this bar also needs the engine's MP3, so that test is skipped without one); its talking-score check (every part, such as "Solo Horn") needs the Rust core, so build `core-bridge/src/main/jniLibs` first (`scripts/build-core.sh`). `audio/src/androidTest/.../RealisticSynthTest.kt` renders sfizz offline. For the SFZ case, pass `-Pandroid.testInstrumentationRunnerArguments.sfz=/data/local/tmp/sounds/cornet-a/cornet-a-sus.sfz` after pushing an instrument there.

Screenshots of the design (light, dark, bokmål and 200% text) are in `docs/screenshots/design/`; the ones from before the design system are in `docs/screenshots/before-design/`. Checked by hand on the emulator:
- the share sheet and "Open with" for WAV and MP4
- capture of the phone's own playback, with MediaProjection consent and the silence notice
- the microphone: starts and stops, but emulator input is silent
- 200% font scale
- bokmål
- dark theme
- the live engine over the LAN URL with the pairing code. With "Let the engine run heavy models" off, a new clip stops at the first heavy stage, and the app shows the engine's error.

The TalkBack acceptance script (`qa/screen-reader-scripts/talkback-android.md`) still needs a person with TalkBack on a device. Automated checks cannot hear speech.

## Known limits

- **Realistic tier sync.** The humanized schedule follows alphaTab's position events and a wall clock. The offset between the sfizz output and the cursor has not been measured.
- **alphaTab 1.8.4 on Android** has three more bugs worked around here: `api.loadSoundFont(ByteArray)` returns false for the same `when` reason as `load` (the app hands the bytes to `api.player` directly); registering on `api.midiLoaded` recurses forever in `AlphaSynthWebWorkerApi.loadedMidiInfo` (the app re-applies channel volumes on `postRenderFinished` instead); and it cannot hold the full band SoundFont (see above).
- **Beat grid of solo takes.** On the URMP clips Beat This marks most beats as downbeats, so both the engine and the phone write 1/4 bars; the engine's `arrange_solo` path and the phone agree on the notes (onset+pitch F1 0.963 on URMP March) but not on bar positions.
- **alphaTab's `api.load(bytes)`** returns false on Android: `AndroidUiFacade.load` uses `when (data) { (data is ByteArray) -> … }`, which compares values rather than checking the type. The app parses with `ScoreLoader.loadScoreFromBytes` and calls `renderScore` itself.
