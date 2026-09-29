# brasscribe

Local-first audio → brass-band score (MusicXML).

Research and prototype pipeline are in place. Start at [docs/research/00-summary.md](docs/research/00-summary.md) (architecture decision) and [docs/plan/apps-plan.md](docs/plan/apps-plan.md) (Studio and Play apps).

## What runs where

| Component | Language | Build | Start | Port |
| --- | --- | --- | --- | --- |
| [engine](engine/) | Python (FastAPI) | `pixi install` | `pixi run studio` | 8765 |
| [studio](studio/README.md) | TypeScript | `npm ci && npm run build` | served by the engine at `/` | 8765 |
| [core](core/README.md) | Rust | `cargo build --release` | `brasscribe-core <cmd>` (CLI) | — |
| [capture](capture/README.md) | Swift (macOS) | `make` | `bin/brasscribe-capture --out f.wav` | — |
| [apps/apple](apps/apple/README.md) | Swift (macOS, iOS, iPadOS) | `make build` | `scripts/run-fixture-mac.sh` | — |
| [apps/android](apps/android/README.md) | Kotlin | `./gradlew assembleDebug` | `adb install` | — |
| [apps/windows](apps/windows/README.md) | C# (WinUI 3) | `dotnet build` | `BrasscribePlay.exe` | — |
| [apps/bandroom/macos](apps/bandroom/macos/Makefile) | Swift (macOS menu-bar app that runs the engine) | `make build` | `make run` | first free of 8765–8775 |
| [apps/bandroom/windows](apps/bandroom/windows/README.md) | C# (WinUI 3 tray app that runs the engine) | `dotnet build` | `BrasscribeBandroom.exe` | first free of 8765–8775 |

The Python library ([music](music/README.md)), the benchmarks ([eval](eval/README.md)), the model conversion ([convert](convert/README.md)) and the sound tier ([sounds](sounds/README.md)) are tools, not services; their own READMEs cover them.

## Prerequisites

Everything Python goes through [pixi](https://pixi.sh); it pins the numeric stack the golden output was built with.

```sh
curl -fsSL https://pixi.sh/install.sh | sh    # or: brew install pixi
pixi install                                  # default environment: engine + music + eval + test
```

Per component, only when you build that component:

| Component | Also needs |
| --- | --- |
| studio | Node 20+ (`npm`) |
| core | Rust stable (`rustup`), `uv` for the conformance runner, `cargo-ndk` for the Android target |
| capture, apps/apple | Xcode 16+, `brew install xcodegen cmake` |
| apps/android | Android SDK 37, build-tools 36, NDK 28.2, CMake 3.31.6, `ANDROID_HOME` |
| apps/windows | .NET 10 SDK, Windows 10 21H2 or newer |

Audio decoding outside the container needs `ffmpeg` (`brew install ffmpeg`).

## Verifying a change

New worktree: `eval "$(scripts/worktree-setup.sh)"` (links data/, models/ and Verovio, copies in the prebuilt core). Then [docs/dev/verify.md](docs/dev/verify.md):

| Tier 1: after every edit | Tier 2: before handoff | Tier 3: devices and UI |
| --- | --- | --- |
| `make check-fast` | `make check` | `apps/android/scripts/emulator-pool.sh acquire`, the iOS simulator, the macOS VM |

## End-to-end verification

Run these in order. Each step stands on its own; the app builds all talk to the engine from step 1.

### 1. Engine and Studio

```sh
pixi run test                 # engine + music unit tests, and the OpenAPI spec is up to date
pixi run brasscribe profiles  # the four transcription profiles
pixi run studio               # serves Studio on http://127.0.0.1:8765/ and opens a browser
```

`pixi run studio --no-browser --port 8799` leaves the browser alone. `pixi run serve --lan` binds `0.0.0.0`, prints a LAN URL and a 6-digit pairing code for phones on the same network, and advertises the engine over Bonjour/mDNS as `_brasscribe._tcp` so the Play apps list it in Settings (`--no-advertise` turns that off). Without a browser:

```sh
curl -s http://127.0.0.1:8765/v1/health
```

Drop an audio file on the Runs view, or transcribe one from the command line:

```sh
pixi run brasscribe run data/mikkel/captured.wav --profile orchestra-with-soloist --out data/runs/verify
```

The run streams stage events and writes `composition.json`, MusicXML, PDF, MIDI and MP3 to the output folder. Check it against the committed reference and the regression suites:

```sh
pixi run brasscribe run data/mikkel/captured.wav --check-golden data/golden/mikkel-arranged-band
pixi run brasscribe bench cpu
```

The Studio bundle in `engine/src/brasscribe_engine/static/` is committed, so the engine runs without Node. Rebuild it only when `studio/src/` changes:

```sh
cd studio && npm ci && npm run gen:api && npm run build && npm test
npx playwright install chromium && npm run e2e   # starts its own engine on port 8799
```

### 2. Engine in Docker

```sh
docker build -f engine/Dockerfile --target cpu -t brasscribe:cpu .   # --target cuda for NVIDIA
docker run --rm -v "$PWD/data:/data" -p 8765:8765 brasscribe:cpu
```

### 3. Rust core

```sh
cd core
cargo test --release
scripts/bindings.sh     # Swift, Kotlin and C bindings the native apps link against
cd conformance && uv run python -m brasscribe_conformance.run --only mikkel
```

Conformance proves the port produces the same Composition, MusicXML, humanization and talking score as the Python reference. [core/README.md](core/README.md) has the CLI and the full case list.

### 4. Native apps

```sh
# The band sounds every app bundles (not in git; once per checkout, needs gh auth login)
pixi run fetch-sounds

# macOS, iOS, iPadOS
cd apps/apple && make verovio soundfont project build test && scripts/run-fixture-mac.sh

# Android
cd apps/android && ./gradlew assembleDebug testDebugUnitTest lint

# Windows (PowerShell)
cd apps/windows
dotnet test tests/Brasscribe.Play.Core.Tests -c Release
dotnet build src/Brasscribe.Play -c Release -p:Platform=x64 -p:RuntimeIdentifier=win-x64
```

To point an app at a LAN engine, start it with `pixi run serve --lan`, pick it from the list in the app's settings (or type the printed address) and enter the pairing code. Guest and corporate Wi-Fi often block mDNS between devices; typing the address still works there. Set `BRASSCRIBE_TOKEN` to keep apps paired across engine restarts.

## CI/CD

Each native component has its own GitHub Actions workflow; every run uploads its build as a downloadable artifact. The hosted runners are currently not starting (the account's Actions billing blocks them), so run [the check tiers](docs/dev/verify.md) locally before merging and don't rely on a green workflow.

| Workflow | Builds and tests | Artifact |
| --- | --- | --- |
| [ci](.github/workflows/ci.yml) | Engine + music unit tests, OpenAPI spec check, CPU benchmark gate | `bench-ci` (benchmark JSON) |
| [core](.github/workflows/core.yml) | Rust workspace tests, `brasscribe-core` CLI (Linux, macOS, Windows) | `brasscribe-core-<platform>` |
| [android](.github/workflows/android.yml) | Unit tests, lint, debug + unsigned release APKs | `android-apks` |
| [apple](.github/workflows/apple.yml) | Package + app tests (macOS, iOS Simulator), macOS app build | `apple-macos-app` |
| [windows](.github/workflows/windows.yml) | Core tests, WinUI 3 app build, Axe.Windows accessibility scan | `windows-app` |
| [pages](.github/workflows/pages.yml) | Deploys `site/` to GitHub Pages | — |

Download an artifact from a run: open the workflow's page above, pick a run, and its **Artifacts** section at the bottom lists the files (GitHub Actions → the workflow → a run → Artifacts). Artifacts expire after 90 days.

The public site is served from the `gh-pages` branch, not from the pages workflow: build it with `site/build.sh` and publish `site/_site` there.

### Releases

Releases (v0.1.0, v0.2.0) are built by hand on a Mac and published with `gh release create`: signed Android APKs, the Mac apps, the `brasscribe-core` CLI and `SHA256SUMS`. [docs/dev/release.md](docs/dev/release.md) has the steps. The [release](.github/workflows/release.yml) workflow still runs on a `v*` tag push, but only when Actions runners are available.

## Configuration

| Variable | Default | Purpose |
| --- | --- | --- |
| `BRASSCRIBE_DATA` | `<repo>/data` | Cache, runs, uploads |
| `BRASSCRIBE_MODELS` | `<data>/models`, then `<repo>/models` | Model weights |
| `BRASSCRIBE_ADAPTERS` | `<repo>/ml/adapters` | Adapter `run.sh` scripts |
| `BRASSCRIBE_TOKEN` | generated per start | Bearer token for LAN clients |
| `BRASSCRIBE_GPU_LOCK` | `/tmp/brasscribe-gpu.lock` | Machine-wide mutex for heavy models |
