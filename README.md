# Brasscribe

A score for your brass band, from any recording. Play something, record a rehearsal or open an audio
file, and Brasscribe writes out the parts for a brass band (MusicXML, PDF, MIDI), marks the notes it
wasn't sure about, and plays the score back with band sounds so you can practise along.

Everything runs on your own devices. A solo line is transcribed on the phone or tablet; a full band
needs the engine running on a computer on the same network.

Site and user guide: [kalli.no/brasscribe](https://kalli.no/brasscribe/) ·
How it works: [kalli.no/brasscribe/research](https://kalli.no/brasscribe/research/)

## The apps

| App | Platforms | What it does | Source |
|---|---|---|---|
| **Brasscribe Play** | Android, Mac, iPhone and iPad, Windows | Records or opens a take, shows and plays the score, your own part on a music stand | [apps/android](apps/android/README.md), [apps/apple](apps/apple/README.md), [apps/windows](apps/windows/README.md) |
| **Brasscribe Bandroom** | Mac, Windows | Installs and runs the engine in the background, so phones and tablets can make full-band scores | [apps/bandroom/macos](apps/bandroom/macos/README.md), [apps/bandroom/windows](apps/bandroom/windows/README.md) |
| **Studio** | Browser | The engine's own web interface: runs, scores, benchmarks, model and dataset views | [studio](studio/README.md) |
| **Engine** | Python | Transcription pipeline, arranger and the HTTP service the apps talk to | [engine](engine/README.md) |
| **Core** | Rust | The music rules the apps run on-device, ported from the Python reference and checked against it | [core](core/README.md) |

## Download

[Release v0.2.0](https://github.com/181192/brasscribe/releases/tag/v0.2.0) has:

- Play for Android (`brasscribe-play-android-arm64-v8a.apk` for most devices, `-universal.apk` for all).
- Play for Mac and Bandroom for Mac (Apple silicon). They are not notarised: the first time, open the
  app, then go to **System Settings › Privacy & Security** and choose **Open Anyway**.
- The `brasscribe-core` command-line tool for Mac, and `SHA256SUMS`.

Bandroom's first run downloads the engine and its models (about 10 GB). The band writer model is
licensed for non-commercial use only; Bandroom asks you to accept its licence with a free Hugging Face
account.

Windows has no release build yet: Play and Bandroom for Windows build from source, and Play still lacks
the music stand, the Appearance setting and "What do you play?". iPhone and iPad builds need an Apple
Developer account and are not distributed.

## Developing

Python goes through [pixi](https://pixi.sh), which pins the numeric stack; each app needs its own
toolchain (Xcode 16+ and `xcodegen`, the Android SDK, the .NET 10 SDK, Rust stable, Node 20+), listed
in its README.

```sh
eval "$(scripts/worktree-setup.sh)"   # once per checkout: prebuilt Rust core, environment in .brasscribe-env
pixi install                          # engine, music library, benchmarks, tests
pixi run test-fast                    # engine + music unit tests
pixi run studio                       # engine + Studio on http://127.0.0.1:8765/
pixi run serve --lan                  # engine for phones on the LAN, with a pairing code
```

Checks come in tiers ([docs/dev/verify.md](docs/dev/verify.md)):

| Tier | When | Command |
|---|---|---|
| 1 | after every edit | `make check-fast` (or `scripts/check.sh fast [area...]`) |
| 2 | before pushing a branch | `make check` (or `scripts/check.sh full [area...]`) |
| 3 | device, audio or UI changes | emulators, the iOS simulator, the macOS VM ([docs/dev/macos-vm.md](docs/dev/macos-vm.md)) |

Areas: `engine`, `core`, `conformance`, `studio`, `apple`, `android`, `windows`, `core-dotnet`,
`bandroom-mac`. Without areas, the ones the branch touches.

The band SoundFonts are not in git; `pixi run fetch-sounds` downloads the pinned pack (needs the GitHub
CLI, logged in). Some tests use recordings and reference output under `data/`, which is not in the
repository either; without it those tests are skipped.

Releases are built by hand on a Mac: [docs/dev/release.md](docs/dev/release.md).

## Repository layout

| Path | What |
|---|---|
| `engine/` | Engine: CLI, HTTP service, job DAG, profiles, the committed Studio bundle |
| `music/` | Python reference library: composition model, quantization, spelling, arranger, MusicXML |
| `eval/` | Benchmark suites and gated baselines |
| `ml/adapters/` | One isolated environment per model, behind a `run.sh <input> <output>` contract |
| `convert/` | Conversions of the small models to ONNX and Core ML, with parity reports |
| `core/` | Rust core, its CLI, the Swift/Kotlin/C bindings and the conformance runner |
| `studio/` | Studio web app (TypeScript) |
| `apps/` | Play for Apple, Android and Windows; Bandroom for Mac and Windows |
| `capture/` | macOS audio capture tool |
| `sounds/` | Band sound pack: sources, build, mapping and licences |
| `design/` | Design system, brand, tokens and mockups |
| `docs/` | Research, plans, accessibility specs, developer docs |
| `site/` | The public site |
| `qa/` | Readability, contrast and performance checks and reports |
| `scripts/` | Worktree setup, check tiers, core artifacts |

## Documentation

- Developer: [verify](docs/dev/verify.md), [release](docs/dev/release.md), [macOS VM](docs/dev/macos-vm.md)
- Design: [design/README.md](design/README.md), [system](design/system.md),
  [music stand](design/music-stand.md), [Bandroom](design/server-app.md)
- Research: [summary and architecture decision](docs/research/00-summary.md),
  [benchmark results](docs/research/10-benchmark-results.md), the rest of [docs/research](docs/research/)
- Plans: [docs/plan/apps-plan.md](docs/plan/apps-plan.md)
- Accessibility: [docs/accessibility](docs/accessibility/)

## Licence

Brasscribe is licensed under either of [Apache License 2.0](LICENSE-APACHE) or [MIT](LICENSE-MIT), at
your option ([LICENSE](LICENSE)). The libraries, fonts, band sounds and models it uses keep their own
licences; see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md). The model that writes full-band scores
is CC BY-NC 4.0, so full-band transcription is for non-commercial use only.
