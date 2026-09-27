# Brasscribe Bandroom for Windows

Brasscribe on this computer: installs the engine, keeps it running and lives in the corner of the taskbar.
The design is [`design/server-app.md`](../../../design/server-app.md) (states §6, flyout §7, copy deck §10);
mockups are `design/mockups/png/server-win-flyout-*`, `server-pair-*`.

| Project | What |
|---|---|
| `src/Brasscribe.Bandroom.Core` | No WinUI, builds and tests anywhere: engine supervisor, first-run bootstrap, admin credential, `/v1/*` client, status polling, health words, state rules and tray badges, flyout / devices / pairing view models, the QR |
| `src/Brasscribe.Bandroom` | WinUI 3 app: notification-area icon, flyout, "Brasscribe on this PC" window, Pair a phone, Allow window, Windows services (job object, DXGI, run at sign-in, host readings) |
| `tests/Brasscribe.Bandroom.Core.Tests` | xUnit tests of Core, on the app's own string tables |
| `tools/AxeScan`, `tools/Screenshots` | CI: Axe.Windows scan and screenshots of every view (`--show`) |
| `tools/Strings/gen_resw.py` | Writes both `Resources.resw` from the copy deck |

## Build and run

```powershell
dotnet test tests/Brasscribe.Bandroom.Core.Tests
dotnet build src/Brasscribe.Bandroom -p:Platform=x64 -p:RuntimeIdentifier=win-x64 -p:BandroomBundleWorkspace=true
# A development run against this checkout, with pixi on PATH:
$env:BRASSCRIBE_BANDROOM_WORKSPACE = "C:\src\brasscribe"; .\src\Brasscribe.Bandroom\bin\x64\Debug\...\BrasscribeBandroom.exe
```

On macOS: `tools/check-macos.sh` runs the Core tests and type-checks the app's C# (the XAML compiler only runs
on Windows; CI builds it: `.github/workflows/windows.yml`, job `bandroom`).

Command line: `--background` (the sign-in start: no window), `--demo` / `--show flyout|devices|confirm-stop|window|pair|allow`
(sample content, no engine), `--state running|busy|attention|stopped|error|setup|starting`, `--theme light|dark`, `--lang en|nb`.

## How it runs

- **Data** in `%LOCALAPPDATA%\Brasscribe` (§5.2): `envs` (the pixi workspace, copied from the app's
  `workspace\` on first run), `cache\pixi`, `models`, `logs\engine.log` (rolls at 5 MB), `bandroom\` (admin
  credential, setup markers) and `engine.json` (port, pid, server id, version: for Play on the same PC).
- **First run** installs, in order, `default` (the engine, so it can start early), `swift-f0`,
  `basic-pitch`, then the torch adapters. With an NVIDIA card (DXGI vendor 0x10DE) and a driver of 525 or
  newer they are the `-cuda` builds and the engine gets `BRASSCRIBE_CUDA=1`; otherwise the CPU builds.
  A marker per environment holds the lockfile hash, so a stopped setup resumes and an update reinstalls only
  when `pixi.lock` changed.
- **The engine** is `pixi run --manifest-path <envs>\pixi.toml --frozen -e default brasscribe serve --lan
  --port N` on the first free port from 8765, in a job object (Stop, Restart and Bandroom exiting end the
  whole tree). It is Running once `/v1/health` answers. An unexpected exit restarts it after 2, 4, 8 … 30 s;
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

## Not done yet

- The four-step first-run window (§3.2: check this computer, the Hugging Face licence step, download progress
  with Pause, Ready) and the model downloads after the licence step. Today setup installs the environments in the
  background and the flyout shows **Setting up** / **Finish setting up**.
- Settings page, Check for updates and About (the More menu has Open Studio, Start when I log in, Remove, Quit).
- Needs-attention detection for Windows Firewall blocking and a Public network (strings and fixes are in place).
- The lockout line in Pair a phone: the engine answers wrong codes to the phone, not to the computer, so the
  computer can't know. It needs a field in `GET /v1/pairing` (for example `locked_until`).
- Actionable toast for a pair request while the Pair window is closed: an always-on-top Allow window is shown instead.
- The GPU half of Work load (CPU only today).
