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
| `Tests/` | The screen catalogue: unit tests hosted in a Debug build of the app ([Testing](#testing)) |
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
- **Bass tabs.** The engine's `bass-tab` profile runs the Rust core's command line, `brasscribe-core`.
  The build copies it from `core/target/release` into `Contents/Resources/bin`
  (`scripts/stage-core-cli.sh`), and Bandroom passes it to the engine it installed as
  `BRASSCRIBE_CORE_CLI`. An engine run from a checkout uses the checkout's own build instead.
- **Pairing.** Pair a phone shows a QR code and a code to type; the phones list removes paired devices.

Data lives in `~/Library/Application Support/Brasscribe` (`BRASSCRIBE_DATA` overrides it), logs in
`~/Library/Logs/Brasscribe` (`BRASSCRIBE_LOGS`).

## Build and run

Needs Xcode 16+ and `xcodegen` (`brew install xcodegen`). The band SoundFont comes from
`pixi run fetch-sounds`; without it a Debug build leaves the band sounds out and a Release build stops.
The same goes for `brasscribe-core`: `scripts/worktree-setup.sh` at the repository root installs it
(or `cargo build --release --locked -p brasscribe-cli` in `core/`).

```sh
make project      # generate BrasscribeBandroom.xcodeproj
make build        # Debug build into build/DerivedData
make test         # BandroomKit unit tests (scripts/test-kit.sh)
make screens      # the screen catalogue, off screen (scripts/screenshots.sh record)
make run          # build, then run against this checkout (CHECKOUT=/path/to/brasscribe to change it)
make strings      # rebuild App/Localizable.xcstrings (en + nb) from the last build
```

Against a checkout (`BRASSCRIBE_CHECKOUT`, or the `engineCheckout` setting), Bandroom runs the engine
with `pixi run` in that checkout instead of installing its own copy; the checkout needs `pixi install`
first. `scripts/run-dev.sh` launches the built app the way Finder does, with options for the data
folder (its own under `build/dev` by default, so it never shares the installed Bandroom's), appearance, language
and canned demo states for screenshots.

`scripts/check.sh fast bandroom-mac` runs the unit tests, `full bandroom-mac` also builds the app and runs the
screen catalogue, compared with the merge base.
Release builds are made by hand: [docs/dev/release.md](../../../docs/dev/release.md) §4.

## Testing

BandroomKit's unit tests (`make test`) cover the engine supervisor, setup, downloads, pairing and polling. The
screens are checked by the **screen catalogue** (`Tests/BandroomScreensTests.swift`): unit tests hosted in a Debug
build of the app, which draws every screen off screen, without a window on the screen or an item in the menu bar,
so it runs on a Mac in use and on CI's macOS runner.

- **The test host.** When the app hosts the tests it starts as `UnitTestHost` (`App/AppEntry.swift`), not as
  `BandroomApp`: no `MenuBarExtra`, no window, never activated. Its models run in demo mode (`DemoEngine`, canned
  engine answers; the demo never starts, installs or downloads anything), with their own data and logs folders under
  the temporary folder and a settings store of their own; `AppModel` stops the run if any of the three is missing, so
  a test can never stop an installed Bandroom's engine or change its settings.
- **Screens and variants.** Each `Screen` (the panel busy, ready, with a phone asking, setting up; the phones list;
  Pair a phone; the four setup steps; Settings) in light, dark, increased contrast (light and dark) and Bandroom's
  largest text size, and in bokmål (`xcodebuild -testLanguage nb`) in light and the largest text size. A screenshot
  of each, at 2 pixels a point, and its accessibility tree beside it (`<name>.ax.txt`).
- **The checks**, on the accessibility tree SwiftUI builds in the process: every control has a name; Bandroom's own
  buttons, menus and links are at least 24 × 24 pt, and the system's standard controls (switches, checkboxes, radio
  buttons, fields) keep their sizes under WCAG 2.5.8's spacing exception; no text of one line is cut off, and nothing
  lies outside the window; the controls come in reading order in the order VoiceOver and the keyboard go through
  them (`accessibilityChildrenInNavigationOrder`). `CatalogueChecksTests` shows each check failing on a view made to
  fail it. `BandroomScreensTests.known` lists findings not yet fixed, each with its issue.
- **Two undocumented hooks**, in the tests only: `AXEnhancedUserInterface` on `NSApp` makes SwiftUI build its
  accessibility tree without an assistive app running, and the environment key `_colorSchemeContrast` sets increased
  contrast. Each is checked on every run (`Hooks`): a tree without controls, a contrast probe drawn as standard
  contrast, or English strings under `-testLanguage nb` fail the run, so an Xcode or macOS update that changes them
  is noticed instead of passing quietly.

What it does not check: a real Tab walk (SwiftUI moves focus only in a key window on a screen, with keyboard
navigation turned on in System Settings), a text of several lines cut at its last line (the tree gives a text's
frame, not the width it was wrapped at), the colour contrast of each text (the design tokens' pairs are checked in
CI), the menu-bar item and its popover window, notifications, the keychain, the login item and the engine itself.
`scripts/desktop-screenshots.sh` takes the real popover from the menu bar; run it in the macOS VM
([docs/dev/macos-vm.md](../../../docs/dev/macos-vm.md)).

**Screenshots** are not kept in git. `scripts/screenshots.sh compare` takes the catalogue's screenshots at the merge
base with `origin/main` and then on the branch, on the same machine, and writes `build/reports/screenshots/`
(`index.html` with before, the difference and after for each changed screen; `summary.md`). It exits 1 when a screen
changed, appeared or went away, 2 when the catalogue's own checks failed, and 3 when the screenshots could not be
taken at the base (nothing was compared). CI does the same on every pull request that reaches Bandroom
(`apple.yml`): a changed screen fails the `Bandroom for Mac screenshots` job and its images are in the
`bandroom-mac-screenshots` artefact; when the change is meant, the label `screenshots-changed` on the pull request
lets it through. The label is read when the job runs, in a job that runs none of the pull request's code, and never
lets a failed check or a failed base through.

A new screen or state gets a `Screen` in the catalogue; a found problem the change does not fix is an issue, and an
entry in `known` only with that issue named.
