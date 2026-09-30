# Brasscribe Bandroom for Mac

A menu-bar app that installs the [engine](../../../engine/README.md) on this Mac, keeps it running and
pairs phones and tablets with it, so Play can make full-band scores. The design is
[`design/server-app.md`](../../../design/server-app.md); the Windows version is
[`apps/bandroom/windows`](../windows/README.md).

| Path | What |
|---|---|
| `App/` | SwiftUI app: menu-bar status panel, first-run setup, Pair a phone, phones list, settings |
| `Packages/BandroomKit/` | Everything testable without the UI: engine supervisor, first-run install, model downloads, pairing, status polling, uninstall |
| `project.yml` | XcodeGen spec (the `.xcodeproj` is generated, not committed) |
| `scripts/` | Build phases, test and screenshot helpers, string catalog |

## What it does

- **First run.** The app carries the engine workspace (`pixi.toml`, `pixi.lock`, the `engine`, `music`
  and `eval` packages and `ml/adapters`, staged by `scripts/stage-workspace.sh`) and a `pixi` binary.
  It copies the workspace to `~/Library/Application Support/Brasscribe` and runs `pixi install` there.
  After an app update it swaps in the new workspace and installs again only when `pixi.lock` changed.
- **Models.** It downloads the three models a full-band score needs from their makers' release pages
  (`ModelCatalog.swift`). The band writer is gated on Hugging Face: the user accepts its licence with
  their own account and pastes their key, which Bandroom keeps in the keychain. Setup shows the model's
  terms, and Continue waits for the user to tick the box under them (`LicenceStep.swift`).
- **Engine.** It starts `brasscribe serve --lan` on the first free port of 8765–8775, restarts it if it
  stops, and shows its state in the menu bar. The band sounds Studio plays are bundled
  (`scripts/stage-band-sounds.sh`).
- **Pairing.** Pair a phone shows a QR code and a code to type; the phones list removes paired devices.

Data lives in `~/Library/Application Support/Brasscribe` (`BRASSCRIBE_DATA` overrides it), logs in
`~/Library/Logs/Brasscribe` (`BRASSCRIBE_LOGS`).

## Build and run

Needs Xcode 16+ and `xcodegen` (`brew install xcodegen`). The band SoundFont comes from
`pixi run fetch-sounds`; without it a Debug build leaves the band sounds out and a Release build stops.

```sh
make project      # generate BrasscribeBandroom.xcodeproj
make build        # Debug build into build/DerivedData
make test         # BandroomKit unit tests (scripts/test-kit.sh)
make run          # build, then run against this checkout (CHECKOUT=/path/to/brasscribe to change it)
make strings      # rebuild App/Localizable.xcstrings (en + nb) from the last build
```

Against a checkout (`BRASSCRIBE_CHECKOUT`, or the `engineCheckout` setting), Bandroom runs the engine
with `pixi run` in that checkout instead of installing its own copy; the checkout needs `pixi install`
first. `scripts/run-dev.sh` launches the built app the way Finder does, with options for the data
folder (its own under `build/dev` by default, so it never shares the installed Bandroom's), appearance, language
and canned demo states for screenshots.

`scripts/check.sh fast bandroom-mac` runs the unit tests, `full bandroom-mac` also builds the app.
Release builds are made by hand: [docs/dev/release.md](../../../docs/dev/release.md) §4.
