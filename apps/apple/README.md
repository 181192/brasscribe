# Brasscribe Play for macOS, iOS and iPadOS

One SwiftUI app for macOS, iOS and iPadOS. It covers import, recording, transcription through the companion engine,
review, the score, practice and export.

## Build

```sh
export DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer
brew install xcodegen cmake
make verovio        # Frameworks/Verovio.xcframework (LGPL-3.0, unmodified, dynamic) + font subset
scripts/build-core.sh   # core/swift/BrasscribeCore/BrasscribeFFI.xcframework (Rust core, UniFFI)
make soundfont      # data/soundfonts/MuseScore_General.sf2 (MIT, 206 MB, not committed)
make project        # BrasscribePlay.xcodeproj from project.yml (not committed)
make build          # macOS, iPhone simulator, iPad simulator
make test           # package tests, then app unit and UI tests on macOS and the iPhone simulator
make size           # Release build for iOS devices, prints the .app size
scripts/run-demo-mac.sh                                           # open the golden Mikkel score on the Mac
scripts/run-demo-sim.sh "iPhone 17" docs/screenshots/x.png        # same on a simulator, with a screenshot
```

Tests locate the golden output through the `data/` link or `BRASSCRIBE_FIXTURES`.

## Layout

| Path | What |
|---|---|
| `project.yml` | XcodeGen spec: one multiplatform app target, unit tests, UI tests |
| `App/` | SwiftUI app: models (`AppModel`, `PracticeModel`, `Piece`), views, string catalogs (en, nb) |
| `Packages/BrasscribeKit` | `ScoreKit` (Composition, MusicXML parser, talking score, MIDI, CoreBridge), `TranscriptionKit` (companion client and fixture service), `PlaybackKit` (AVAudioEngine), `SVGRender` (native SVG drawing) |
| `Packages/NotationKit` | Verovio wrapper: engraving, part filtering, concert pitch, timemap |
| `../../capture` | `AudioCapture` package (Core Audio process tap), used by the macOS app and the CLI |
| `scripts/` | Verovio, core and sound-font builds, string catalog, demo launchers |
| `docs/notation-spike.md` | Native vs WKWebView measurements and the decision |

## Keyboard (macOS, and iPad with a keyboard)

| Key | Action |
|---|---|
| Space | Play / pause |
| ← / → | Previous / next bar |
| L | Loop the current bar (again to stop) |
| Shift-L | Loop the from–to bar range |
| [ / ] | Slower / faster (5 % steps, 25–150 %) |
| C / M / A | Count-in / metronome / play along (mutes your part) |
| O | Original recording ↔ score, at the same place |
| ⌘+ / ⌘- | Zoom |
| ⇧⌘P / ⇧⌘T / ⇧⌘E | Parts and sound / talking score / export |

The Playback menu lists the same keys.

## Notes

- **Timing.** Score playback follows the MusicXML tempo marks. The original recording, "listen to
  this bar" and the synced video follow the Composition's beat times, so the two stay at the same
  bar even when the performance is not metronomic.
- **Uncertainty.** Uncertain notes are drawn in orange (Okabe–Ito palette) with an open diamond above
  them, so colour is never the only cue. The talking score says "uncertain". Confidence comes from the
  Composition's source voices, and arranged notes inherit it by onset and pitch class. The arranger's
  own flag (the red colour in the MusicXML) is kept too.
- **Sound.** With `BRASSCRIBE_SOUNDS` set to the repository root, each part plays its preset from the
  band SoundFont (`data/sounds/band/brasscribe-band-16bit.sf2`: bank MSB 0x79 + LSB = bank, drums
  0x78/0, gain `channel_gain_db`), placed at its audience-seat position from `sounds/seating.json` in an
  AVAudioEnvironmentNode. The room is a convolution of the OpenAIR central-hall IR (vDSP partitioned
  convolution in an AUAudioUnit), calibrated to +4.5 dB wet-to-direct at the audience seat (measured
  4.48 dB on Mikkel). Without those files the app falls back to MuseScore_General.sf2 (or the system
  DLS) and the environment node's hall reverb. The app does not bundle any sounds.
- **Offline solos.** On iPhone, iPad and Mac a solo is transcribed on the device (`OnDeviceKit`): SwiftF0
  and Basic Pitch (Core ML fp32, CPU/GPU) and Beat This small0 (fp16 on devices, fp32 in the simulator,
  whose Core ML returns zeros for the fp16 program), with the upstream frontends and decoders ported to
  Swift. The Rust core's solo-with-band path then writes the score. The models (about 40 MB) download on
  demand from the address in Settings, or come from `BRASSCRIBE_MODELS` (a `models/converted/` folder)
  during development. They are not in the app.
- **Video.** The synced video plays in a player layer with picture in picture
  (AVPictureInPictureController) and a labelled start/stop button.
- **Capture on macOS.** This uses the Core Audio process tap. The release build is sandboxed. Whether
  the process tap works under App Sandbox is an open question. Debug builds run unsandboxed.
- **Exports.** MusicXML, MIDI, audio (offline render to AAC) and the talking score (text) are made on
  the device. PDF and BRF come from the engine or the demo folder.
- **On-device arranging.** The Rust core (`RustCoreBridge`) arranges a Composition for full or small
  band without a computer. It is used by Review → "Arrange again on this device" and by importing a
  `composition.json`.
