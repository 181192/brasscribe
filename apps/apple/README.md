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
pixi run fetch-sounds   # (repo root) the band SoundFonts into data/sounds/band: needs `gh auth login`
make project        # BrasscribePlay.xcodeproj from project.yml (not committed); stages the band sounds
make build          # macOS, iPhone simulator, iPad simulator
make test           # package tests, macOS app unit tests, then app unit and UI tests on the iPhone simulator
../../scripts/mac-vm.sh test-ui   # macOS UI tests (make test-mac-ui), only in the macOS VM or in CI
make size           # Release build for iOS devices, prints the .app size
make install-mac    # Release build into /Applications/Brasscribe Play.app (ad-hoc signed), launched and checked
scripts/run-fixture-mac.sh                                        # open the Old Hundredth fixture score on the Mac
scripts/run-fixture-sim.sh "iPhone 17" docs/screenshots/x.png     # same on a simulator, with a screenshot
scripts/screenshots.sh mac|iphone|ipad [screen …]                 # docs/screenshots, from the same fixture
```

The macOS UI tests run only in a headless macOS VM, never on your desktop: see [docs/dev/macos-vm.md](../../docs/dev/macos-vm.md).

UI tests, the app unit tests and the screenshots open `apps/fixtures/old-hundredth` (a public-domain
hymn arranged by the core, with review marks; regenerate with `apps/fixtures/make-old-hundredth.py`),
passed as `BRASSCRIBE_FIXTURES`. No build of the app carries a sample score or recording. The package
tests also check the parser and playback against the engine's golden output in the local `data/` folder
and skip themselves when it is missing.

## Layout

| Path | What |
|---|---|
| `project.yml` | XcodeGen spec: one multiplatform app target, unit tests, UI tests |
| `App/` | SwiftUI app: models (`AppModel`, `PracticeModel`, `Piece`), views, string catalogs (en, nb) |
| `Packages/BrasscribeKit` | `ScoreKit` (Composition, MusicXML parser, talking score, MIDI, CoreBridge), `TranscriptionKit` (companion client and fixture service), `PlaybackKit` (AVAudioEngine), `SVGRender` (native SVG drawing) |
| `Packages/NotationKit` | Verovio wrapper: engraving, part filtering, concert pitch, timemap |
| `../../capture` | `AudioCapture` package (Core Audio process tap), used by the macOS app and the CLI |
| `scripts/` | Verovio, core and sound-font builds, string catalog, fixture launchers, screenshots |
| `docs/notation-spike.md` | Native vs WKWebView measurements and the decision |

## Mac window

Every main window keeps a 900 × 600 minimum (`App/WindowMinimum.swift`), also for windows opened later
with New Window. Sheets are sized to their content and capped at the room between their top and the
bottom of the visible frame, so Settings never reaches under the Dock, and zooming a window keeps it clear
of the Dock. Controls drawn over the score (player bar, stand controls, video) come before the score in
accessibility order, so VoiceOver and the UI tests reach them. `AppTests/ResponsiveLayoutTests.swift` checks
these sizes off screen.

## Keyboard (macOS, and iPad with a keyboard)

| Key | Action |
|---|---|
| Space | Play / pause |
| ← / → | Previous / next bar |
| L | Loop the current bar (again to stop) |
| Shift-L | Loop the from–to bar range |
| , / . | Slower / faster (5 % steps, 25–150 %); comma and full stop sit on the same keys on English and Norwegian keyboards |
| C / M / A | Count-in / metronome / play along (mutes your part) |
| O | Original recording ↔ score, at the same place |
| ⌘+ / ⌘- | Zoom |
| ⇧⌘P / ⇧⌘T / ⇧⌘E | Parts and sound / talking score / export |
| F | Music stand (again to leave); View › Music Stand on the Mac. ⌃⌘F stays the window's own full screen |

The Playback menu lists the same keys.

In the music stand (`App/Views/MusicStandView.swift`, design/music-stand.md): → ↓ Page Down turn to the
next page and ← ↑ Page Up to the previous one (what Bluetooth page turners send; on the Mac Page Up, Page
Down, Home and End are key equivalents, because AppKit turns them into scrolling first), Home and End go to the first
and last page, Option-↓ ↑ move by bar, Space plays and pauses, and Esc or F leaves. Stand screenshots:
`docs/screenshots/*stand*`, taken by `MusicStandUITests.testScreenshots` (set `TEST_RUNNER_STAND_SHOTS` to
the folder and `TEST_RUNNER_NB=1` for Norwegian).

## Notes

- **Timing.** Score playback follows the MusicXML tempo marks. The original recording, "listen to
  this bar" and the synced video follow the Composition's beat times, so the two stay at the same
  bar even when the performance is not metronomic.
- **Uncertainty.** Uncertain notes are drawn in orange (Okabe–Ito palette) with an open diamond above
  them, so colour is never the only cue. The talking score says "uncertain". Confidence comes from the
  Composition's source voices, and arranged notes inherit it by onset and pitch class. The arranger's
  own flag (the red colour in the MusicXML) is kept too.
- **Bundled band sounds.** Each app bundle carries the band SoundFont in `Sounds/`, staged per platform
  by `scripts/stage-band-sounds.sh` (run by `make project`) from `data/sounds/band`: the Mac gets
  `brasscribe-band-16bit.sf2` (191 MB), iPhone and iPad `brasscribe-band-mobile.sf2` (68 MB: smaller, for
  phone memory and download size). `BandSounds.bandFiles` looks for the same file first on each
  platform; `make size` prints the iOS Release app's size with the phone build. Without
  the files (`pixi run fetch-sounds` was not run) the app builds, plays the basic tier and says the band
  sounds are missing. Release builds in CI fetch them first and stop if they cannot.
- **Sound.** With `BRASSCRIBE_SOUNDS` set to the repository root, each part plays its preset from the
  band SoundFont (`data/sounds/band/brasscribe-band-16bit.sf2`: bank MSB 0x79 + LSB = bank, drums
  0x78/0, gain `channel_gain_db`), placed at its audience-seat position from `sounds/seating.json` in an
  AVAudioEnvironmentNode. The room is a convolution of the OpenAIR central-hall IR (vDSP partitioned
  convolution in an AUAudioUnit), calibrated to +4.5 dB wet-to-direct at the audience seat (measured
  4.48 dB on the golden band recording). Without the room IR (the shipped app) "Concert hall sound" is the
  environment node's medium hall at −10.7 dB with a −4 dB low shelf at 250 Hz on the reverb return, so held
  bass notes don't bloom; turning it off adds 5 dB of make-up gain (`band.dry_room_gain_db`) so the band keeps
  its loudness. Without the band SoundFont the app falls back to MuseScore_General.sf2 (or the system DLS).
- **Output level.** The presets are level-matched to −24 LUFS, so the band goes through an output stage
  (`OutputStageAU`): +31.5 dB of make-up gain (`band.gain_db.apple` in `sounds/playback-levels.json`), then a memoryless tanh soft limiter above 0.8 with a 0.98
  ceiling, the same shape as the Windows player. The full-band test phrase peaks at about −1 dBFS and a
  solo cornet at about −11. The limiter has no attack or release, so it never pumps at the Stop fade,
  and below the threshold Mute and Only this keep the balance. The metronome and the original recording
  bypass it.
- **Offline solos.** On iPhone, iPad and Mac a solo is transcribed on the device (`OnDeviceKit`): SwiftF0
  and Basic Pitch (Core ML fp32, CPU/GPU) and Beat This small0 (fp16 on devices, fp32 in the simulator,
  whose Core ML returns zeros for the fp16 program), with the upstream frontends and decoders ported to
  Swift. The Rust core's solo-with-band path then writes the score. The models (about 6 MB) download on
  demand from the address in Settings, or come from `BRASSCRIBE_MODELS` (a `models/converted/` folder)
  during development. They are not in the app.
- **Band drafts.** A brass band recording is made on the device as a draft when the computer is not
  there (no computer paired, or Offline / needs pairing) or when Settings › On this device › "Make band
  drafts on this device" is on (`AppModel.maker(for:)`). `OnDeviceBandDraftService` runs Basic Pitch on
  the whole mix and Beat This small0 (`BandTranscriber`), then the core's song arranger
  (`arrangeSongWith`) with Basic Pitch in every slot: the engine's brass-band profile with
  `muscriptor=false`. A recording longer than the free memory allows (`OnDeviceBudget`) is refused before
  anything runs. It stays in the foreground on iPhone and iPad (the models use the GPU). The piece is
  marked as a draft and keeps its recording, and its score offers "Make the full score" on the computer.
  Parity with the engine's draft: `BandDraftTests` against `scripts/make-band-draft-reference.sh`.
- **Video.** The synced video plays in a player layer with picture in picture
  (AVPictureInPictureController) and a labelled start/stop button.
- **Capture on macOS.** This uses the Core Audio process tap. The release build is sandboxed. Whether
  the process tap works under App Sandbox is an open question. Debug builds run unsandboxed.
- **Exports.** MusicXML, MIDI, audio (offline render to AAC) and the talking score (text) are made on
  the device. PDF and BRF come from the engine.
- **On-device arranging.** The Rust core (`RustCoreBridge`) arranges a Composition for full or small
  band without a computer. It is used by Review → "Arrange again on this device" and by importing a
  `composition.json`.

## Test tiers

| Tier 1 (inner loop) | Tier 2 (before handoff) | Tier 3 (devices, UI) |
| --- | --- | --- |
| `make package-test-fast`; `make test-mac-unit` after `make build-for-testing-mac` | `make package-test test-mac-unit` | `make test-ios-unit` (headless simulator); `make test-mac-ui` only in the macOS VM |

See [docs/dev/verify.md](../../docs/dev/verify.md).
