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
| `models/converted/swift-f0/swift-f0-window.onnx` | `models/convert` | Bundled in every build: offline solo transcription. Without it, "On this phone" is disabled |
| `data/golden/mikkel-arranged-band/` | the golden output | Debug builds only: the built-in sample engine ("Open the Mikkel sample"). JVM tests that need it skip themselves when it is missing |
| `third_party/sfizz` | `scripts/fetch-sfizz.sh` (sfizz 1.2.3) | The realistic playback tier. Without it the native library builds a stub and the tier is shown as unavailable. You can also pass `-Pbrasscribe.sfizzDir=<checkout>` |

## Modules

| Module | Kind | What it holds |
|---|---|---|
| `model` | Kotlin/JVM | Composition JSON model (tolerant of new fields), tick map (bars and recording seconds, including the golden file's negative `first_downbeat`), spelling and brass-band transpositions, `PartView`, a monophonic MusicXML writer, a solo quantizer with key and tempo estimates, and the talking-score announcer. `CoreBridge` is the seam for the Rust core |
| `engine-client` | Kotlin/JVM | Ktor client for `engine/openapi.json` (pairing, upload, jobs, SSE progress, results), `ProgressTracker` for the time left, and `FixtureEngineApi` (the golden Mikkel output with timed stage events) |
| `pitch` | Kotlin/JVM | SwiftF0 on ONNX Runtime (the `ai.onnxruntime` API: the Android build in the app, the desktop build in tests), a port of `segment_notes`, the resampler, `SoloTranscriber` |
| `audio` | Android library with NDK | Decoding audio and video with MediaExtractor/MediaCodec, WAV, microphone capture through Oboe/AAudio, AudioPlaybackCapture, sfizz playback through an Oboe output stream |
| `app` | Android app | Compose UI, capture foreground service, alphaTab score, exports |

## Seams

- **CoreBridge** (`model/.../CoreBridge.kt`). `KotlinCoreBridge` implements it for now: decode and encode, solo quantize, key, MusicXML for app-made parts, and talking-score announcements. Once the Rust core ships its UniFFI Kotlin bindings and jniLibs, add a `UniffiCoreBridge` behind the same interface and switch it in `AppContainer.core`. The talking-score vectors test (`TalkingScoreVectorsTest`) can then run against both.
- **Engine client.** The client is hand-written. `openapi-generator` 7.25.0 (kotlin, jvm-ktor, kotlinx_serialization) produced code that does not compile for this spec: `additionalProperties: true` became `HashMap<String, Any>()()`, numbers became `@Contextual BigDecimal`, and the SSE stream was typed as a JSON body. `EngineContractTest` compares the client with the vendored `engine-client/openapi.json`: operationIds, every property, required fields and enums. Refresh the spec with `./gradlew :engine-client:syncOpenApi` once `engine/` is in the same checkout.
- **On-device models.** SwiftF0 runs on ONNX Runtime Mobile. LiteRT is not used because no TFLite export exists. Other models (Basic Pitch, Beat This!) can be added with the same session code once `models/convert` has parity reports for them.

## Features and where they live

- **Inputs** (`ui/HomeScreen.kt`, `capture/CaptureService.kt`, `audio/`):
  - file import through SAF
  - the share sheet (`ACTION_SEND`) and "Open with" (`ACTION_VIEW`)
  - video, whose first audio track is decoded
  - the microphone through Oboe
  - other apps' playback through AudioPlaybackCapture. Play shows an opt-out and DRM notice first, asks for MediaProjection consent, and runs a foreground service of type `mediaProjection` (type `microphone` for mic recording). After 5 s of silence it shows "Nothing is coming through…". Android offers no API that reports an app's opt-out, so silence is the signal.
- **"What is this?"** picks the engine profile: `solo`, `brass-band`, `orchestra-with-soloist` or `pop-rock`. For a solo it also asks where to transcribe: on the phone (offline) or on the companion engine.
- **Transcription** shows a plain-language step, percent, "step n of m", time left and Cancel. A cancel also cancels the engine job.
- **Review** colours uncertain notes with the tokens from `docs/accessibility/design-tokens.json` and gives each level a shape: an open ring when uncertain; brackets and a filled ring when very uncertain. Each note is one TalkBack item. It speaks the talking-score announcement and has these custom actions:
  - Listen to this bar: plays the original bar, then the score's bar, looped
  - Mark as checked
  - Next uncertain note
- **Output**: lineup, difficulty and key. The engine API (0.1.0) has no lineup or difficulty parameters, so the other difficulty levels are shown disabled with the reason. The key shift transposes playback and notation in alphaTab.
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

  Reduced motion (animator scale 0) turns off the animated cursor and scrolls by page. For screen readers, the notation view is one item. It announces the title, the part and "bar n of m", and has the custom actions Next/Previous bar, Next/Previous part and Play this bar. The Text tab is the talking score: one item per event, with Next/Previous bar, Read bar and Play this bar.
- **Realistic sound**: alphaTab's note events drive sfizz while alphaTab's own instruments are muted. Its metronome and count-in stay on. Each part loads `sounds/<instrument>/<instrument>-sus.sfz` from the app's external files. Copy the folders that `sounds/build.py` writes, for example with `adb push data/sounds/built/cornet-a /sdcard/Android/data/no.brasscribe.play/files/sounds/`. Parts without an installed instrument play a test tone.
- **Exports** go through the share sheet or "Save to Files":
  - MusicXML
  - PDF and MP3, from the engine
  - MIDI, generated by alphaTab from the loaded score
  - talking-score text, as HTML with a heading per part and bar
  - braille (BRF), listed but disabled, because the engine has no BRF output yet
- **Languages**: English and bokmål (`values-nb`), with per-app language through the generated locale config. Lint fails on a missing translation.

## Accessibility tests

`app/src/androidTest/.../PlayFlowA11yTest.kt` walks home, then "What is this?", transcription, review, output, score and export on the sample engine. Every action runs with `enableAccessibilityChecks()` (ATF). At the end, the Espresso `AccessibilityChecks` check the whole window, including the alphaTab View. The test asserts:
- headings
- the radio role and its collection position
- progress range info
- the announcement of an uncertain note, and its custom actions
- the score's custom actions, and moving to the next bar
- 48 dp targets

The first run found two real problems, both fixed: an unlabelled empty live region, and part names that alphaTab stores with no-break spaces.

The TalkBack acceptance script (`qa/screen-reader-scripts/talkback-android.md`) still needs a person with TalkBack on a device. Automated checks cannot hear speech.

## Known limits

- **Spelling.** Chromatic notes are spelled by a key-based rule in Kotlin. In a sharp key the review shows A♯ where the golden MusicXML has B♭. The ps13 speller in the Rust core replaces this.
- **Talking score on the full band.** In the Text tab it reads the transcribed layers (solo, bass and so on) from the Composition, not the 18 arranged parts. Per-part talking scores need the arrangement in the TalkingScore JSON (spec §6) from the core.
- **Realistic tier timing.** Note events come from alphaTab's `midiEventsPlayed` and follow its synth buffer (500 ms by default). Timing against the cursor has not been measured.
- **APK size.** ONNX Runtime's full Android build takes 33 MB of the 48.6 MB arm64 release APK. A reduced-operator ONNX Runtime build for SwiftF0 alone is the obvious cut. Its size is not measured.
- **alphaTab's `api.load(bytes)`** returns false on Android: `AndroidUiFacade.load` uses `when (data) { (data is ByteArray) -> … }`, which compares values rather than checking the type. The app parses with `ScoreLoader.loadScoreFromBytes` and calls `renderScore` itself.
