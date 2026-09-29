# macOS UI tests in a virtual machine

**Rule: the macOS UI tests run only inside the macOS VM, never on a desktop someone is using.**
XCUITest on the Mac moves the real pointer and types real keys. On the host, one misplaced click
lands in another app. This covers Brasscribe Play's `AppUITests` (`make test-mac-ui`) and, once it
has them, Brasscribe Bandroom's UI tests. CI runners are VMs too, so the tests also run there.

The VM runs under [Tart](https://tart.run) (Apple Virtualization.framework) with `--no-graphics`.
It has no window on the host and no link to the host's mouse or keyboard. The tests drive the VM's
own virtual display, 1440 × 900 pt.

```sh
scripts/mac-vm.sh up                 # start or resume headless, wait for SSH (provisions the first time)
scripts/mac-vm.sh test-ui            # build on the host, run every Play macOS UI test over two VMs
scripts/mac-vm.sh test-ui WindowSizeUITests,PlayUITests/testKeyboardShortcuts   # only these
scripts/mac-vm.sh test-ui-bandroom   # Bandroom: its UI test scheme, or build + unit tests until it has one
scripts/mac-vm.sh ssh [command]      # a shell in the VM
scripts/mac-vm.sh down [--stop|--reset]  # suspend; --stop shuts down; --reset also deletes the clones
scripts/mac-vm.sh status             # VMs, disk use, state
```

## Install

```sh
brew install cirruslabs/cli/tart
```

If the Homebrew tap fails to load (in September 2026 it was stuck on 2.32.1 and newer Homebrew
rejects its `depends_on`), install the release by hand:

```sh
curl -sSLO https://github.com/cirruslabs/tart/releases/download/2.40.0/tart.tar.gz   # check the sha256 against the release
mkdir -p ~/.local/opt/tart ~/.local/bin && tar -xzf tart.tar.gz -C ~/.local/opt/tart
printf '#!/bin/sh\nexec "$HOME/.local/opt/tart/tart.app/Contents/MacOS/tart" "$@"\n' > ~/.local/bin/tart && chmod +x ~/.local/bin/tart
```

The script looks for `tart` on `PATH`, then in `~/.local/bin`.

## What gets built

Two VMs, both local to Tart (`~/.tart/vms`):

| VM | What |
|---|---|
| `brasscribe-ui-base` | `ghcr.io/cirruslabs/macos-tahoe-base:latest` plus the host's Xcode, set up once by `provision` (runs on the first `up`) |
| `brasscribe-ui` | an APFS clone of the base. The tests run here. `down --reset` throws it away, and the next `up` reclones it in seconds |

Provisioning is idempotent: `provision` picks up where a failed run stopped, and
`~/.tart/brasscribe-ui-base.provisioned` marks it finished. It:

- replaces the image's admin/admin SSH login with a key, `~/.tart/brasscribe-ui_ed25519`
- grows the disk to 72 GB
- streams the host's `/Applications/Xcode.app` in over SSH (`ditto -c … | ssh … ditto -x --hfsCompression`),
  which keeps it compressed as on the host (about 4 GB, about 10 minutes). A Tart shared folder
  (`--dir`) is slower and breaks the frameworks' symlinks
- copies the host's `xcodegen` in: the image's network cannot always reach ghcr.io for Homebrew,
  and this keeps the same version on both sides
- runs `xcodebuild -license accept`, `-runFirstLaunch`, `DevToolsSecurity -enable` and
  `automationmodetool enable-automationmode-without-authentication` (XCUITest then needs no password prompt)
- turns off sleep and the screensaver
- (on every `up`) switches the display to the configured size with `scripts/mac-vm-display.swift`. Without this
  every boot comes back in the image's saved 1024 × 768 mode, whatever `tart set --display` says
- (on every `up`) sets the Dock's icons to 36 pt (`MAC_VM_DOCK_TILE`). The image's Dock is as wide as
  the screen, so it shrank its icons, and its height, by a few points each time an app's icon came or
  went. The test runner reads the visible frame once and kept the old value, so a window the app had
  zoomed to its own, current visible frame measured 2 pt "under the Dock"

The image is `macos-tahoe-base`, not `macos-tahoe-xcode`, because of disk space. The Xcode 27
image is 62 GB compressed and about 76 GB on disk. On a Mac with about 90 GB free, that leaves
less than the 20 GB margin we keep. The base image is about 35 GB, and the host's Xcode adds about
4 GB. The VM therefore runs exactly the Xcode that builds the app locally (27.0 here).
`MAC_VM_XCODE=/Applications/Xcode-26.6.app scripts/mac-vm.sh provision` builds a base with
another Xcode.

Settings, all overridable in the environment: `MAC_VM_CPUS` (6), `MAC_VM_MEMORY_MB` (10240),
`MAC_VM_DISPLAY` (1440x900), `MAC_VM_DISK_GB` (72), `MAC_VM_IMAGE`, `MAC_VM_NAME`, `MAC_VM_BASE`.
To change the CPUs or memory, run `tart set brasscribe-ui --cpu … --memory …` while the VM is
stopped (and on `brasscribe-ui-base`, for later clones). The display size applies on the next `up`.
The 1024 × 768 of the image's default mode is worth one run too: `MAC_VM_DISPLAY=1024x768 scripts/mac-vm.sh test-ui`.

## Disk and memory

Measured on the first setup (September 2026):

| | |
|---|---|
| Download | 27 GB (the base image, about 25 minutes) |
| `brasscribe-ui-base` | 38 GB on the host's disk: 33 GB of image, 4 GB of Xcode, and the rest |
| Image cache (`~/.tart/cache/OCIs`) | shares its blocks with the base (APFS clone), so deleting it frees almost nothing. Delete it anyway with `tart delete ghcr.io/cirruslabs/macos-tahoe-base:latest`, so it doesn't grow on the next pull. A later `provision` of a missing base pulls again |
| `brasscribe-ui` | a clone: only what diverges from the base. That is the synced repo, the band sounds (0.5 GB) and DerivedData (about 2 GB). `down --reset` returns it |
| RAM while running | 10 GB + 6 GB for the two VMs (6 CPUs each), returned to the host at `down` (suspend) |

`up`, `test-ui` and `provision` refuse to start when the host has less than 15 GB free
(`MAC_VM_MIN_FREE_GB`). The guest's disk can grow into the host's.

A stopped VM uses no RAM or CPU. When the tests are done, run `scripts/mac-vm.sh down`.

## Where these tests sit

The VM click tests are **tier 3** ([verify.md](verify.md)). Run them before a release, and for
changes to window, input or navigation code (the window delegate, `WindowFit`, menus and keyboard
shortcuts, the split view, sheets, the stand's entry and exit).

Layout and resize regressions are covered earlier by the off-screen layout harness
(`AppTests/LayoutHarness.swift`, `ResponsiveLayoutTests.swift`). It runs with the app unit tests
in seconds, never touches the pointer, and runs on every change (tier 1 and 2). When a VM test
finds a layout bug, add the case to the harness too, so it is caught without the VM next time.

Run only the classes a change touches: `scripts/mac-vm.sh test-ui WindowSizeUITests`, or
`test-ui WindowSizeUITests/testZoomStaysInsideTheVisibleFrame,PlayUITests`.

What the VM tests found that the harness cannot see (September 2026), and how each was settled:

- **Controls over the score were not hittable.** The pointer clicked them fine, but SwiftUI's
  accessibility hit test on the Mac returns the first element in accessibility order whose frame
  holds the point, whatever is drawn on top. The score came first, and its frame (its scroll
  content runs on under the player band) covered Play, Next bar, the stand's controls and the video.
  VoiceOver's pointer and Switch Control found the score there too. The overlaid controls now sort
  before the score (`StackedAccessibility` in `ScoreScreen.swift`). The harness cannot check this:
  SwiftUI builds no accessibility tree without an assistive client.
- **The window's minimum is 900 × 600, the window itself.** SwiftUI gives the first window 900 × 600
  (548 pt of content under the 52 pt toolbar), but a window it opens later (File › New Window, or the
  first window at a background launch, which comes from the New Window action) gets 900 × 620 with
  the same layout. The app holds every main window at 900 × 600 (`WindowMinimum`); the harness checks
  that every screen lays out at 900 × 548 and that the minimum holds when SwiftUI sets 620 again.
- **Sheets end above the Dock.** A sheet hangs from below the toolbar, so 90 % of the visible
  height reached under the Dock. `sheetSize` caps a sheet at the room between its top and the
  visible frame's bottom. Settings is longer than any screen, so its sheet takes that room (or the
  window's height, which a sheet cannot pass) and scrolls; a sheet whose content fits keeps its size.
- **Page Up, Page Down, Home and End on the stand.** AppKit turns them into scroll commands before
  the focused view's `onKeyPress` sees them; on the Mac they are key equivalents on the stand.

## How a test run works

Nothing compiles in the VM, and the VMs stay up between runs. `test-ui`:

1. Builds on the host with `xcodebuild build-for-testing` into `apps/apple/build/DerivedData-vm`.
   This is incremental, and the host has the same Xcode as the VM. It needs the parts of the build
   that are not in git:
   - the Rust core `BrasscribeFFI.xcframework`: always this checkout's. It is built with
     `apps/apple/scripts/build-core.sh` when missing or older than the core's sources
   - Verovio (`apps/apple/Frameworks`): from this checkout, else from the main checkout when this is
     a worktree, else `make verovio`
   - the band sounds (`data/sounds/band`): linked from the main checkout in a worktree. Without
     them the app plays the basic tier
2. Splits the tests over the VMs (`MAC_VM_PARALLEL`, default 2). The longest go first, each to
   the VM with the least work, using the durations of earlier runs (`build/mac-vm/durations.json`,
   `scripts/mac-vm-plan.py`). Only two macOS guests can run at once: macOS's licence, enforced by
   Virtualization.framework.
3. Starts or resumes the VMs (`brasscribe-ui`, `brasscribe-ui-2`: a second clone with 6 GB).
4. Rsyncs, incrementally, the build products, `apps/fixtures` and `sounds/` into each VM.
5. Runs `xcodebuild test-without-building -xctestrun …` in each VM, in parallel, with
   `-only-testing` for its share. The fixture reaches the runner as
   `TEST_RUNNER_BRASSCRIBE_FIXTURES`.
6. Copies each `.xcresult` back to `build/mac-vm/play-<time>/<vm>/`. It then:
   - exports the attachments into `attachments/`. `manifest.json` there maps them to tests. Xcode 27
     keeps a screen recording of each failing test instead of a screenshot, and the script saves
     each recording's last frame as `<id>-last.png` (with ffmpeg)
   - writes `summary.json` and `tests.json`, and prints the failures. The xcodebuild log is
     `play-<time>/<vm>.log`

It prints the time of each step and exits non-zero when a test fails. `down` suspends the VMs
(they run `--suspendable`), and the next `up` or `test-ui` resumes them in seconds.

### Timings

Measured on September 29, 2026, on a host shared with other agents. All 30 tests (25 run, 5 skip themselves):

| Step | The first design: build and test in one VM | Now, warm | Now, two tests |
|---|---|---|---|
| VM boot or resume | 20–40 s boot | 1 s (running) or about 20 s (resumed after `down`) | 1 s |
| Sync | rsync of the repo, a few s | 5 s (products only) | 4 s |
| Build | in the VM, 1–7 min | 5 s on the host (incremental; about 75 s after a larger change) | 6 s |
| Tests | 13 min 20 s in one VM | about 5 min 30 s over two VMs | 30 s |
| Results | rsync of the whole bundle | a few s: exported in the VM, recordings stay there | 3 s |
| **Total** | **12–16 min** | **6 min** | **44 s** |

Almost all of a full run is the tests themselves. The longest is
`testMinimumWindowOnTheScoreAndEveryPart` at about 2.5 min: it resizes the window for each of the
18 parts. That bounds a full run even with the work split perfectly. So a change runs its classes
(`test-ui <Class>`), well under 3 minutes, and the full suite runs before a release.
`MAC_VM_FETCH_BUNDLE=1` also copies the whole `.xcresult` back, with the recordings. Otherwise it
stays in the VM at `~/results/`.

The first macOS alert a fresh build meets, "Allow BrasscribePlay to find devices on local
networks?", covers the window. `dismissLocalNetworkPrompt()` in `UITestSupport.swift` answers
Don't Allow by its position, because the runner cannot reach the alert's buttons through
accessibility.

The window size tests (`AppUITests/WindowSizeUITests.swift`):

- drag the window small, to a medium size and onto the Dock
- zoom it with the title bar, Option-click on the green button, and Window › Zoom, Fill, Center
  and the halves
- after each, check that the window lies inside the screen's visible frame
- check that home, "What is this?", "How should the score be?" and the Settings sheet keep their
  controls together in a taller window, rather than spreading them to full height
- resize the score back and forth across the sidebar's 1000 pt line, and zoom it with the title
  bar. After each, the score's column has to be laid out at once for the sidebar's state, with no
  stale column
- check that the window's minimum is 900 × 600 on the score, on the stand and with each of the
  18 parts shown

They skip themselves outside a virtual machine (`kern.hv_vmm_present`).

## For agents

- Never run `make test-mac-ui`, `xcodebuild test` on a UI test scheme, `screenshots.sh mac` or any
  other input automation on the host. Use `scripts/mac-vm.sh test-ui`, or `scripts/mac-vm.sh ssh …`
  for anything else that needs a Mac GUI.
- Never start the VM with a window or VNC (`tart run` without `--no-graphics`). The script never does.
- Building on the host (`make build`, `build-for-testing`) and the unit tests (`make test`) are fine.
  They do not touch the pointer.
- Most branches don't need the VM. Use the unit tests and the layout harness. Use the VM only
  to confirm a fix the harness can't see (hit-testing, clicks, keyboard, the window delegate), and
  then only the named tests: `test-ui <Class>/<test>[,…]`, at most two at a time.
- The full suite is run once, before a release, by whoever cuts it. The script refuses
  `test-ui` without a list unless `MAC_VM_FULL=1` is set.
- One VM user at a time: the script holds a host-wide lock (`~/.tart/brasscribe-ui.lock`), and other
  runs wait on it. Never kill another run.
- Read the results from `build/mac-vm/<run>/<vm>/`: `summary.json` for the failures,
  `attachments/*-last.png` for the screen at each failure.
- Run `scripts/mac-vm.sh down` when finished. It suspends the VMs, which frees their RAM.
- Screenshots for a review come from `build/mac-vm/<run>/…/attachments/`, not from the host's screen.

## Troubleshooting

- **No SSH after 3 minutes**: see `build/mac-vm/<vm>.log`. `tart list` shows whether it runs.
  Run `scripts/mac-vm.sh down && scripts/mac-vm.sh up`.
- **"Timed out while enabling automation mode"**: the base lost the automation-mode setting.
  Run `scripts/mac-vm.sh ssh sudo automationmodetool enable-automationmode-without-authentication`,
  or run `provision` again.
- **A strange state after many runs**: `scripts/mac-vm.sh down --reset`.
- **DHCP leases run out after many reclones**: see the Tart FAQ on shortening the lease time.
