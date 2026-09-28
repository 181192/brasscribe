# macOS UI tests in a virtual machine

**Rule: the macOS UI tests run only inside the macOS VM, never on a desktop someone is using.**
XCUITest on the Mac moves the real pointer and types real keys. On the host, one misplaced click
lands in another app. This covers Brasscribe Play's `AppUITests` (`make test-mac-ui`) and, once it
has them, Brasscribe Bandroom's UI tests. CI runners are VMs too, so the tests also run there.

The VM runs under [Tart](https://tart.run) (Apple Virtualization.framework) with `--no-graphics`.
It has no window on the host and no link to the host's mouse or keyboard. The tests drive the VM's
own virtual display, 1440 × 900 pt.

```sh
scripts/mac-vm.sh up                 # start headless, wait for SSH (provisions the first time)
scripts/mac-vm.sh test-ui            # sync, run the Play macOS UI tests, fetch the results
scripts/mac-vm.sh test-ui BrasscribePlayUITests_macOS/WindowSizeUITests   # one class (or one test)
scripts/mac-vm.sh test-ui-bandroom   # Bandroom: its UI test scheme, or build + unit tests until it has one
scripts/mac-vm.sh ssh [command]      # a shell in the VM
scripts/mac-vm.sh down [--reset]     # stop; --reset also reclones the VM from the provisioned base
scripts/mac-vm.sh status             # VMs, disk use, IP
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
| RAM while running | 10 GB for the VM (6 CPUs), returned to the host at `down` |

`up`, `test-ui` and `provision` refuse to start when the host has less than 15 GB free
(`MAC_VM_MIN_FREE_GB`). The guest's disk can grow into the host's.

A stopped VM uses no RAM or CPU. When the tests are done, run `scripts/mac-vm.sh down`.

## How a test run works

`test-ui`:

1. Starts the VM if it is not running and waits for SSH.
2. Gets the parts of the build that are not in git, on the host:
   - the Rust core `BrasscribeFFI.xcframework`: always this checkout's. It is built with
     `apps/apple/scripts/build-core.sh` when missing or older than the core's sources
   - Verovio (`apps/apple/Frameworks`): from this checkout, else from the main checkout when this is
     a worktree, else `make verovio`
   - the band sounds (`data/sounds/band`) and the optional MuseScore SoundFont: found the same way.
     Without them the app plays the basic tier
3. Rsyncs the repo into `~admin/brasscribe` in the VM. It leaves out `.git`, `.claude/`
   (worktrees), `node_modules`, `build/`, DerivedData, `core/target`, `data/` and `*.xcodeproj`, then
   adds the items above.
4. Runs `make test-mac-ui TEST_ARGS='-resultBundlePath …'` in `apps/apple` over SSH.
5. Copies the `.xcresult` back to `build/mac-vm/play-<time>/`. It then:
   - exports the attachments into `attachments/`. `manifest.json` there maps them to tests. Xcode 27
     keeps a screen recording of each failing test instead of a screenshot, and the script saves
     each recording's last frame as `<id>-last.png` (with ffmpeg)
   - writes `summary.json` and `tests.json`, and prints the failures

   The full log is `build/mac-vm/play-<time>.log`.

It exits non-zero when a test fails.

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
- One run at a time: the VM has one display. Other agents that need it wait, or use a second VM:
  `MAC_VM_NAME=brasscribe-ui-2 scripts/mac-vm.sh test-ui` clones another from the same base,
  with another 10 GB of RAM.
- Read the results from `build/mac-vm/…`: `summary.json` for the failures, `attachments/` for the
  screenshots.
- Run `scripts/mac-vm.sh down` when finished.

## Verify

This section stands in until a shared verify page exists. A change to the Mac app's windows,
layout or input is verified with `scripts/mac-vm.sh test-ui` (or `test-ui <class>`). Screenshots
for a review come from `build/mac-vm/<run>/attachments/`, not from the host's screen.

## Troubleshooting

- **No SSH after 3 minutes**: see `build/mac-vm/<vm>.log`. `tart list` shows whether it runs.
  Run `scripts/mac-vm.sh down && scripts/mac-vm.sh up`.
- **"Timed out while enabling automation mode"**: the base lost the automation-mode setting.
  Run `scripts/mac-vm.sh ssh sudo automationmodetool enable-automationmode-without-authentication`,
  or run `provision` again.
- **A strange state after many runs**: `scripts/mac-vm.sh down --reset`.
- **DHCP leases run out after many reclones**: see the Tart FAQ on shortening the lease time.
