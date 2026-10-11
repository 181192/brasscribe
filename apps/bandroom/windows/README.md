# Brasscribe Bandroom for Windows

Brasscribe on this computer: installs the engine, keeps it running and lives in the corner of the taskbar.
The design is [`design/server-app.md`](../../../design/server-app.md) (states §6, flyout §7, copy deck §10);
mockups are `design/mockups/png/server-win-flyout-*`, `server-pair-*`.

| Project | What |
|---|---|
| `src/Brasscribe.Bandroom.Core` | No WinUI, builds and tests anywhere: engine supervisor, first-run bootstrap, admin credential, `/v1/*` client, status polling, health words, state rules and tray badges, flyout / devices / pairing view models, the QR |
| `src/Brasscribe.Bandroom` | WinUI 3 app: notification-area icon, flyout, "Brasscribe on this PC" window, Pair a phone, Allow window, Windows services (job object, DXGI, run at sign-in, host readings) |
| `tests/Brasscribe.Bandroom.Core.Tests` | xUnit tests of Core, on the app's own string tables |
| `tools/Screenshots` | CI: the screen catalogue of every view (`--show`), with Axe.Windows and Tab |
| `tools/Strings/gen_resw.py` | Writes both `Resources.resw` from the copy deck |

## Build and run

```powershell
dotnet test tests/Brasscribe.Bandroom.Core.Tests
dotnet build src/Brasscribe.Bandroom -p:Platform=x64 -p:RuntimeIdentifier=win-x64 -p:BandroomBundleWorkspace=true
# A development run against this checkout, with pixi on PATH (installs from the workspace\ the build put next to it):
.\src\Brasscribe.Bandroom\bin\x64\Debug\...\BrasscribeBandroom.exe
```

`-p:BandroomBundleWorkspace=true` copies the pixi workspace from this checkout next to the exe (`workspace\`: the
same files a release bundles), and Bandroom installs from there. `BRASSCRIBE_BANDROOM_WORKSPACE` points it at
another folder laid out the same way. Never point it at the checkout itself: Bandroom copies and hashes the whole
folder, `.git`, `.pixi` and `data` included.

The build puts the band sounds Studio plays under `band\` next to the exe (`brasscribe-band.sf2`, the phone
build, with `mapping.json` and `NOTICE.txt`), from `data/sounds/band`: run `pixi run fetch-sounds` at the
repository root once (needs `gh auth login`). Bandroom passes the folder to the engine as
`BRASSCRIBE_BAND_SOUNDS_DIR`, which serves it to Studio at `/assets/band/`; without it `engine.log` says the band
sounds are missing and Studio plays General MIDI sounds. The SoundFont adds 68 MB to the install (the
`sounds-2026.09.30` phone build). The engine's MP3 export does not use it: that is MuseScore's own sounds, levelled
to the band's loudness with `playback-levels.json`, which Bandroom stages next to it.

The engine's `bass-tab` profile runs the Rust core's command line. When `core\target\release\scribe-core.exe`
exists (`cargo build --release --locked -p scribe-cli` in `core\`), the build copies it to `core\` next to the
exe, and Bandroom passes it to the engine as `SCRIBE_CORE_CLI`; the release build in `windows.yml` builds it
first, with the C runtime linked in (`RUSTFLAGS=-C target-feature=+crt-static`), so it needs no Visual C++ runtime
on the PC. Without the exe `engine.log` says it is missing, and the engine refuses `bass-tab` jobs: a
`SCRIBE_CORE_CLI` set for the user is not passed on, so the engine only ever runs the bundled one.

On macOS: `tools/check-macos.sh` runs the Core tests and type-checks the app's C# (the XAML compiler only runs
on Windows; CI builds it: `.github/workflows/windows.yml`, job `bandroom`).

Command line: `--background` (the sign-in start: no window), `--demo` / `--show flyout|devices|confirm-stop|window|pair|allow`
(sample content, no engine), `--state running|busy|attention|stopped|error|setup|starting`, `--theme light|dark`, `--lang en|nb`.

## How it runs

- **Data** in `%LOCALAPPDATA%\Brasscribe` (§5.2): `envs` (the pixi workspace, copied from the app's
  `workspace\` on first run), `cache\pixi`, `models`, `logs\engine.log` (rolls at 5 MB), `bandroom\` (admin
  credential, setup markers) and `engine.json` (port, pid, server id, version: for Play on the same PC).
- **After an app update** the copy's stamp (`envs\.brasscribe-workspace.json`: a hash of the files, and the
  commit) differs from the app's. Bandroom shows Updating, stops the engine, swaps the code folders in (staged
  in `envs\.bandroom-update`, stamp last) and reinstalls environments only when `pixi.lock` changed. `.pixi`,
  models, runs and paired devices stay. If the engine environment won't install, the old copy goes back, its
  engine starts, and a Needs-attention problem offers Try again.
- **First run** installs, in order, `default` (the engine, so it can start early), `swift-f0`,
  `basic-pitch`, then the torch adapters. With an NVIDIA card (DXGI vendor 0x10DE) and a driver of 525 or
  newer they are the `-cuda` builds and the engine gets `BRASSCRIBE_CUDA=1`; otherwise the CPU builds.
  A marker per environment holds the lockfile hash, so a stopped setup resumes and an update reinstalls only
  when `pixi.lock` changed.
- **The engine** is `pixi run --manifest-path <envs>\pixi.toml --frozen -e default brasscribe serve --lan
  --port N` on the first free port from 8765, in a job object (Stop, Restart and Bandroom exiting end the
  whole tree). It is Running once `/v1/health` answers, and is asked again every 30 s: four unanswered in a row
  count as stuck, and it is ended and restarted like an exit. An unexpected exit restarts it after 2, 4, 8 … 30 s;
  three in five minutes is **Stopped unexpectedly**.
- **Admin credential**: 256 random bits in `bandroom\admin-token`, with an ACL that allows only the current
  user (inheritance removed). Passed as `BRASSCRIBE_ADMIN_TOKEN`; sent as `Authorization: Bearer` on every
  call. Never written to `engine.json`, logs or diagnostics.
- **Polling**: `/v1/status` every 5 s while the flyout or window is open, every 30 s otherwise; the running
  job from `/v1/jobs`; pair requests every 5 s always (a request lapses after 2 minutes). Engines without
  `/v1/status` are read from health, devices and jobs.
- **Health** (work load, memory, free space) comes from Windows, not the engine.

## MSIX packaging

The default build is unpackaged (`WindowsPackageType=None`), so CI can run the exe. The shipped build is MSIX
(§5.3): per user, no administrator prompt, signed, installed with App Installer (`.appinstaller`
auto-update) or winget; not the Microsoft Store.

```powershell
dotnet publish src/Brasscribe.Bandroom -c Release -p:Platform=x64 -r win-x64 `
  -p:WindowsPackageType=MSIX -p:GenerateAppxPackageOnBuild=true -p:AppxPackageSigningEnabled=true `
  -p:PackageCertificateThumbprint=<thumbprint> -p:BandroomBundleWorkspace=true -p:BandroomPixiExe=C:\tools\pixi.exe
```

`src/Brasscribe.Bandroom/Package.appxmanifest`:

- `runFullTrust` (the engine is a child process), `internetClient` and `privateNetworkClientServer`.
- **Start at sign-in**: `uap5:StartupTask TaskId="BrasscribeBandroom" Enabled="true"`. The app reads and
  changes it through `Windows.ApplicationModel.StartupTask` (**Start when I log in** in the More menu). When the
  user turns it off in Task Manager › Startup apps the state is `DisabledByUser`, and the switch is shown off and
  unavailable, because only the user can turn it back on there. A start by the task is recognised by its
  activation kind and opens no window. Unpackaged builds use `HKCU\…\CurrentVersion\Run` with `--background`
  and honour Task Manager's `StartupApproved` switch.
- **Data**: MSIX redirects `%LOCALAPPDATA%` writes into the package's own store, which is deleted on uninstall
  (what we want for ~10 GB). The engine runs inside the package context, so it sees the same folder.
  Play on the same PC must read `engine.json` through the package's redirected path: verify before shipping.
- Assets come from `design/dist/icons/windows/Assets` (linked by the project, never copied).

## What CI checks (`windows.yml`, job `bandroom`)

It runs on pull requests that touch `apps/bandroom/windows/`, the design tokens, `sounds/`, the pixi workspace
or the engine sources it bundles (the `windows_bandroom` filter in `ci.yml`'s `changes` job; `music/README.md`
and `eval/README.md` are in it, since the bundle copies them), and on the pushes to main that start `ci.yml`. A
push of only Markdown does not start it, so a change to one of those two READMEs is checked on its pull request
and not again on main. It is part of `CI result`. The engine test's packages are kept from main's runs
(pixi's package cache, for the same `pixi.lock`), so a pull request installs the engine from them.

Core tests; the WinUI build with the bundled workspace; a start without pixi (window, notification-area icon,
admin credential ACL); a start with pixi, where the first run installs the `default` environment from
`pixi.lock`, the engine reaches Running, `engine.json` is written without the credential, health, devices and an
open-until-closed pairing window answer with the bearer, and the engine's process tree ends with Bandroom; the
screen catalogue (`tools/Screenshots/catalogue.ps1`: every view in Light, Dark,
bokmål, a contrast theme and 200 % text, with the contrast of its text, Axe.Windows and a walk with Tab; its
screenshots are the artefact `bandroom-windows-screenshots`, to look at). How it works and what its answers
mean: [apps/windows/tests/Brasscribe.Play.Catalogue/README.md](../../windows/tests/Brasscribe.Play.Catalogue/README.md#bandroom-for-windows).

## Not done yet

- The MSIX build itself: the manifest and StartupTask path are written but not yet built or installed in CI.

- The four-step first-run window (§3.2: check this computer, the Hugging Face licence step, download progress
  with Pause, Ready). Today setup installs the environments in the background, then fetches the model weights
  (the separators into `models\`, the band writer into the Hugging Face hub cache) from their upstream URLs:
  progress shows in the flyout's **Ready to make scores** row, Pause and Resume are in the icon's menu, and the
  Hugging Face key (HF_TOKEN, or the one saved in Settings in Credential Manager) is asked for through a
  Needs-attention problem. The Settings card where the key is saved shows the band writer's terms, and Save waits
  for the box under them to be ticked.
- Check for updates and About (the More menu has Open Studio, Start when I log in, Remove, Quit).
- Needs-attention detection for Windows Firewall blocking and a Public network (strings and fixes are in place).
- Actionable toast for a pair request while the Pair window is closed: an always-on-top Allow window is shown instead.
- The GPU half of Work load (CPU only today).
