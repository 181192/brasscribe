# Brasscribe Play for Windows

WinUI 3 app on .NET 10, unpackaged, x64. It reads the same `composition.json`
as the other Play apps, renders and plays the score, and talks to the engine
over the OpenAPI contract. The symbolic logic comes from the Rust core through
a C ABI (`brasscribe_ffi.dll`).

```
src/Brasscribe.Play/                 WinUI 3 app (XAML, services, composition root)
src/Brasscribe.Play.Core/            Composition model, talking score, the core bridge
src/Brasscribe.Play.Audio.Windows/   WASAPI loopback capture
src/Brasscribe.Play.Controls/        score and transport controls
tests/Brasscribe.Play.Core.Tests/    xunit
tests/Brasscribe.Play.Catalogue/     screen catalogue: the app as its own test host (MSTest), every screen and its checks
tools/ScreenCheck/                   the catalogues' tool: Axe.Windows and Tab from outside, Bandroom's catalogue, the verdict
tools/ScreenCheck.Core/              its checks on pictures and the findings (any OS; tests in tools/ScreenCheck.Tests)
tools/Screenshots/catalogue.ps1      runs the catalogue with its checks
tools/CodeBehindCheck/               type-checks the app's C# without the XAML compiler
tools/check-macos.sh                 everything that builds off Windows
```

## Not on Windows yet

The music stand and "What do you play?" are in the Mac and Android apps but not in this one yet: they
wait for a test run on a Windows machine. For the same reason no release has a Windows download.
Settings › Appearance (Match system, Light, Dark, and a Windows contrast theme winning over the choice) is
checked on every pull request by the screen catalogue below.

## Prerequisites

- .NET 10 SDK (`global.json` pins `10.0.100`, `rollForward: latestFeature`)
- Windows 10 21H2 (10.0.19041) or newer to run; Windows SDK 10.0.20348 to build
- Rust stable, to build `brasscribe_ffi.dll`

## Build

The app build copies the native core next to the exe, so build that first.

```powershell
cd core
cargo build --release --locked -p brasscribe-ffi
$dll = Resolve-Path target/release/brasscribe_ffi.dll

cd ../apps/windows
dotnet restore Brasscribe.Play.slnx -p:Platform=x64
dotnet build src/Brasscribe.Play -c Release -p:Platform=x64 -p:RuntimeIdentifier=win-x64 "-p:BrasscribeFfiDll=$dll"
```

The exe lands in `src/Brasscribe.Play/bin/Release/net10.0-windows10.0.20348.0/win-x64/BrasscribePlay.exe`,
with `brasscribe_ffi.dll` beside it — the app will not start without it.

The band sounds are bundled as `SoundFonts\brasscribe-band.sf2` (the 16-bit build, 191 MB with `sounds-2026.09.30`) when
`data/sounds/band/brasscribe-band-16bit.sf2` is there: run `pixi run fetch-sounds` at the repository root once
(the pack pinned in `sounds/band-sounds.json`; needs `gh auth login`). Without it the app says the band sounds
are missing. Release builds in CI fetch it first and stop if they cannot.

## Run

```powershell
src/Brasscribe.Play/bin/Release/net10.0-windows10.0.20348.0/win-x64/BrasscribePlay.exe
```

Open a MusicXML score (for example `apps/fixtures/old-hundredth/brass-band.musicxml`, a
public-domain hymn used for screenshots), or point the app at a
running engine: start `pixi run serve --lan` in the repo root and enter the
pairing code the engine prints.

## Test

```powershell
dotnet test tests/Brasscribe.Play.Core.Tests -c Release
```

Set `BRASSCRIBE_FFI_PATH` to the built DLL to include the native-core tests
(the talking-score vectors through the C ABI). Tests that need `data/` or
`models/` skip when those are absent.

Axe.Windows and the walk with Tab on every screen of a built exe (one start per screen):

```powershell
dotnet run --project tools/ScreenCheck -c Release -- play --exe <path-to-exe> --score ../fixtures/old-hundredth/brass-band.musicxml --out <output-dir>
```

## On macOS or Linux

The XAML compile, PRI generation and the app itself need Windows. Everything
else builds anywhere:

```sh
tools/check-macos.sh
```

It runs the core tests, builds the audio and controls libraries, and
type-checks the app's C# through `tools/CodeBehindCheck`. Set `DOTNET_ROOT` if
your SDK is not at `/opt/homebrew/opt/dotnet/libexec`.

The full Windows build, the start-up smoke test and the screen catalogue (screenshots, Axe.Windows, Tab) run in
[.github/workflows/windows.yml](../../.github/workflows/windows.yml), on a Windows runner. `ci.yml`
calls it on every pull request that touches `apps/windows/`, `core/`, the design tokens or what the
build links from `design/`, `sounds/`, `apps/fixtures/` or the score player's SoundFont (the list is
the `windows_play` filter in `ci.yml`'s `changes` job: of `core/` the crates behind `brasscribe_ffi.dll` and
its C header, of `apps/fixtures/` the two scores the tests open), and on every push to main that starts
`ci.yml`, which a push of only Markdown, the site or screenshots does not. A release tag does not run these
checks: `release.yml` calls `windows.yml` for the release builds. It is part of
`CI result`. The screen catalogue takes every screen in Light, Dark, Pink, bokmål, a contrast theme and 200 % text
with its checks; its screenshots are the artefact `windows-screenshots`, to look at:
[tests/Brasscribe.Play.Catalogue/README.md](tests/Brasscribe.Play.Catalogue/README.md).

## Test tiers

| Tier 1 (inner loop) | Tier 2 (before handoff) | Tier 3 (devices, UI) |
| --- | --- | --- |
| `dotnet test tests/Brasscribe.Play.Core.Tests --filter 'Category!=Slow'` | `tools/check-macos.sh` | the app itself, on Windows (CI) |

See [docs/dev/verify.md](../../docs/dev/verify.md).
