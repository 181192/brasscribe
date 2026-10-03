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
tools/AxeScan/                       Axe.Windows accessibility scan
tools/CodeBehindCheck/               type-checks the app's C# without the XAML compiler
tools/check-macos.sh                 everything that builds off Windows
```

## Not on Windows yet

The music stand, the Appearance setting (dark, high contrast) and "What do you play?" are in the
Mac and Android apps but not in this one yet: they wait for a test run on a Windows machine. For the
same reason no release has a Windows download.

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

Accessibility scan on a built exe:

```powershell
dotnet run --project tools/AxeScan -c Release -- <path-to-exe> <output-dir> tests/Brasscribe.Play.Core.Tests/Fixtures/two-parts.musicxml
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

The full Windows build, the start-up smoke test, the Axe.Windows scan and the screenshots run in
[.github/workflows/windows.yml](../../.github/workflows/windows.yml), on a Windows runner. `ci.yml`
calls it on every pull request that touches `apps/windows/`, `core/`, the design tokens or what the
build links from `design/`, `sounds/`, `apps/fixtures/` or the score player's SoundFont (the list is
the `windows_play` filter in `ci.yml`'s `changes` job), and on every push to main. It is part of
`CI result`. The screenshots are an artefact (`windows-screenshots`), not compared with the merge base.

## Test tiers

| Tier 1 (inner loop) | Tier 2 (before handoff) | Tier 3 (devices, UI) |
| --- | --- | --- |
| `dotnet test tests/Brasscribe.Play.Core.Tests --filter 'Category!=Slow'` | `tools/check-macos.sh` | the app itself, on Windows (CI) |

See [docs/dev/verify.md](../../docs/dev/verify.md).
