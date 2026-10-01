# Verifying a change

Three tiers. Run tier 1 while you work, tier 2 before you hand a branch off, and tier 3 only when the
change touches a device or the UI.

| Tier | When | Command | Budget (warm) |
|---|---|---|---|
| 1 inner loop | after every edit | `make check-fast` | under 60 s per area |
| 2 handoff | before a branch is pushed for review | `make check` | minutes (conformance ~20 min) |
| 3 device and UI | device, audio or UI changes | see [Tier 3](#tier-3-devices-and-ui) | as long as it takes |

`make check-fast` and `make check` run the areas the branch touches (against the merge base with
`origin/main`, plus uncommitted and untracked files). `AREAS="engine core"` picks areas, and
`make check-all` runs tier 2 everywhere. Both print a timing table at the end. Areas: `engine`,
`core`, `conformance`, `studio`, `apple`, `android`, `windows`, `core-dotnet`, `bandroom-mac`.
Changes under `music/` or `eval/` count as `engine` (and `conformance`), `core/brasscribe-ffi/` and
`core/bindings/` as `core` and `core-dotnet`, `capture/` as `apple`, and
`apps/bandroom/macos/` as `bandroom-mac`. `scripts/check.sh fast|full [area...]` is the same without make.

## A new worktree

Once per checkout or worktree:

```sh
eval "$(scripts/worktree-setup.sh)"      # later shells: source .brasscribe-env
```

The script is idempotent. `--print-env` only prints the environment, `--no-core` skips the prebuilt
core, and `--core host,apple` limits it to those components. It does four things:

- Links `data/`, `models/` and `apps/apple/Frameworks` (Verovio) from the main checkout. It finds
  the main checkout through `git worktree list` (`BRASSCRIBE_MAIN` overrides it). `BRASSCRIBE_REPO`
  is set to the worktree itself, since the tests also look up tracked files through it.
- Copies in the prebuilt Rust core with `scripts/core-artifacts.sh ensure`:
  - the host library in `core/target/release` and `core/dist/macos`
  - the command line `core/target/release/brasscribe-core`, which the engine's `bass-tab` profile and
    its tests need
  - `BrasscribeFFI.xcframework`
  - the Android `jniLibs`
- Clones `studio/node_modules` from the main checkout when the lock files match.
- Prints the environment, and writes it to `.brasscribe-env`: `BRASSCRIBE_REPO`, `BRASSCRIBE_FFI_PATH`,
  `BRASSCRIBE_CORE_CLI`, `BRASSCRIBE_REQUIRE_DATA`, `ANDROID_HOME`, `ANDROID_NDK_HOME`, `DEVELOPER_DIR`, `DOTNET_ROOT`, and
  `PATH` with rustup and the Android tools.

### The core artifact cache

`scripts/core-artifacts.sh` keys each component (`host`, `apple`, `android`) by a hash of:

- the core sources, tracked and untracked (tests excluded)
- `Cargo.lock` and the script itself
- `rustc -vV`
- the component's toolchain (Xcode, NDK, cargo-ndk)

The first `ensure` after a core change builds the component into `~/.cache/brasscribe/core-artifacts`,
through one shared `CARGO_TARGET_DIR` under a lock. Every other checkout then gets an APFS clone in
about a second. `apps/apple/scripts/build-core.sh` and `apps/android/scripts/build-core.sh` use the
cache locally. CI, or `BRASSCRIBE_NO_ARTIFACT_CACHE=1`, builds in `core/target` as before.
`scripts/core-artifacts.sh status` shows what is cached and installed; `prune [days]` drops old entries.

The artifacts are for the apps. `cargo test` in `core/` still builds in the worktree's own
`core/target`: see [Why not a shared target dir](#why-not-a-shared-cargo-target-dir-or-sccache).

## Tier 1: inner loop

| Area | Command | What it leaves out |
|---|---|---|
| engine | `pixi run test-fast` | tests marked `@pytest.mark.slow` |
| engine, affected only | `pixi run test-affected` | tests the change cannot reach (pytest-testmon; the first run records `.testmondata`) |
| core | `cd core && cargo test --profile fast` | nothing. The `fast` profile is release without LTO, with parallel and incremental codegen, in `target/fast` |
| conformance | `scripts/check.sh fast conformance` | every case but Mikkel. With reference outputs from an earlier run in `core/target/conformance` made from the same Python sources (`music/src`, `eval/brasscribe_eval`, the conformance runner; a hash in `.python-reference-stamp`), it also skips the Python side and the extras (`--skip-python --no-extras`) |
| studio | `cd studio && npx vitest run` | the browser tests |
| apple | `make -C apps/apple package-test-fast` | the suites in `APPLE_SLOW` (tagged `.slow`), and the app tests |
| apple app | `make -C apps/apple build-for-testing-mac`, then `make -C apps/apple test-mac-unit` (repeatable) | UI tests |
| android | `./gradlew testDebugUnitTest -Pbrasscribe.fast` | JUnit category `Slow`, release unit tests, instrumented tests |
| windows | `dotnet test tests/Brasscribe.Play.Core.Tests --filter 'Category!=Slow'` | `[Trait("Category", "Slow")]` |
| core .NET | `cd core/dotnet/Brasscribe.Core.Tests && dotnet test` | nothing (seconds) |
| bandroom-mac | `cd apps/bandroom/macos && scripts/test-kit.sh [filter]` | the app build (tier 2 adds `make build`) |

A test that takes seconds gets the slow marker of its framework:

- pytest: `@pytest.mark.slow`
- Swift Testing: `.tags(.slow)`, plus its suite name in `APPLE_SLOW` in `apps/apple/Makefile`
  (`swift test` has no tag filter)
- JUnit 4: `@Category(Slow::class)`, where each module with slow tests has its own
  `no.brasscribe.play.test.Slow`
- xUnit: `[Trait("Category", "Slow")]`

`test-without-building` runs whatever `build-for-testing` last built. After an edit to the app,
build for testing again.

## Tier 2: before handoff

`make check` runs the full suites the way CI does:

- `pixi run test`
- `cargo test --release`
- conformance on every case
- vitest and the Playwright browser tests
- the Swift packages (BrasscribeKit, NotationKit, `capture`) and the macOS app unit tests
- `./gradlew testDebugUnitTest lint assembleDebug` (tests and lint for the Brasscribe app; the debug build is
  both apps, Brasscribe and Fretscribe)
- `apps/windows/tools/check-macos.sh`
- the core .NET tests
- Bandroom for macOS: the BandroomKit tests and `make -C apps/bandroom/macos build`

Things that differ from running the suites by hand:

- Conformance writes to `core/target/conformance` in the worktree (`--work`), not to `data/runs`,
  which all worktrees share through the link.
- The Studio browser tests get a free port (`STUDIO_STATIC_PORT`), not the fixed 8798.

### Golden tests never pass silently

When data, models, SoundFonts or the native core are missing, a test that needs them is reported as
skipped, with a reason that says what is missing and how to get it:

- pytest: `skipif`
- Swift: `.enabled(if:)`
- JUnit: `assumeTrue`
- xUnit: `[SkippableFact]` with `Skip.If`
- Rust: a `SKIPPED` line on stderr

If the counts show skips you did not expect, run `scripts/worktree-setup.sh`. With
`BRASSCRIBE_REQUIRE_DATA=1`, which the setup exports when the data is there, the Rust golden tests
fail instead of skipping.

## Tier 3: devices and UI

- **Android emulators.** Each checkout or shell gets its own emulator from the pool:

  ```sh
  serial=$(apps/android/scripts/emulator-pool.sh acquire)   # headless; about 6 s once the pool AVD exists
  ANDROID_SERIAL=$serial ./gradlew connectedDebugAndroidTest
  apps/android/scripts/emulator-pool.sh release "$serial"
  ```

  - Pool emulators run `-read-only` copies of the AVD (`bc36-pool`) on even ports from 5556. The
    copy's first boot saves a quick-boot snapshot, once.
  - `acquire` returns your existing lease when you already hold one. `list` shows the leases.
  - Leases expire after `--ttl` minutes (default 120) and are reaped by the next `acquire`.
  - At most four run at once (`BRASSCRIBE_EMULATORS_MAX`).
  - `emulator-5554` is the interactive one. The pool never starts, stops or hands it out.
- **The phone (Galaxy S25, adb serial in `BRASSCRIBE_PHONE_SERIAL`).** It may be used for device tests when it is connected.
  - `emulator-pool.sh acquire --phone` leases it when it is attached and free.
  - Afterwards, install the current debug build again (`./gradlew installDebug`).
  - Never uninstall the app: that deletes the user's scores.
- **iOS simulators.** Headless only. Use `make -C apps/apple test-ios-unit` for the app unit tests.
- **macOS UI tests** move the real pointer and keyboard. Run them only in the macOS VM
  ([macos-vm.md](macos-vm.md)), never on a Mac someone is using.
  - Most branches don't need them. The full suite runs once, before a release (`MAC_VM_FULL=1`).
    A branch may run only the named tests that confirm a fix the layout harness can't see
    (hit-testing, clicks, keyboard, the window delegate).
  - Layout and resize regressions are covered earlier, in tiers 1 and 2, by the off-screen layout
    harness in the macOS app unit tests (`AppTests/LayoutHarness.swift`).
  - Run the classes a change touches: `scripts/mac-vm.sh test-ui WindowSizeUITests[,PlayUITests/testKeyboardShortcuts]`.
    That takes under a minute warm. The full suite (`MAC_VM_FULL=1 scripts/mac-vm.sh test-ui`) takes about 6 minutes over two VMs.
    Runs from different worktrees queue on a host-wide lock.
  - Bandroom has its own entry point: `scripts/mac-vm.sh test-ui-bandroom`.
  - `scripts/mac-vm.sh down` suspends the VMs when you're done.

## Measurements

Measured on an 18-core M-series Mac with 48 GB, shared with other parallel builds (load average 15 to 40).
Treat the numbers as rough.

- **Cold** is a fresh worktree: nothing local to the worktree, but the global caches warm (`~/.gradle`,
  `~/.cargo/registry`, npm, pixi, NuGet, Playwright).
- **Warm** is the same command run again right away.
- "before" means the core built by hand in the worktree and the links made by hand.
- "after" means `scripts/worktree-setup.sh` with the artifact cache warm.

All times are in seconds.

| Suite | Before cold | Before warm | After cold | After warm | Tier 1 cold, then warm |
|---|---|---|---|---|---|
| setup: links and core builds (host, xcframework, jniLibs) | 136 | | 8.5 | 1 | |
| `pixi run test` | 103 | 52 | 39¹ | 39 | `test-fast` 107², then 21; `test-affected` 12 |
| `cargo test --release` | 108 | 5 | 99 | 6 | `--profile fast` 62, then 11; after an edit to core 8 |
| conformance, all cases | 1258 | 1366 | not rerun | | Mikkel, Rust side only: 18 (first run 251) |
| `npm ci` | 12 | | 0 (cloned) | | |
| vitest | 13 | 15 | 11 | 15 | 12, then 17 |
| `test:browser` | 7 | 7 | 7 | 11 | |
| `swift test`, BrasscribeKit | 100 | 64 | 65 | 74 | `package-test-fast`, both packages: 115, then 30 |
| `swift test`, NotationKit | 29 | 10 | 13 | 10 | |
| macOS app unit tests | 100 | 15 | 22¹ | 14 | `build-for-testing` plus `test-mac-unit`: 69, then 9 |
| `./gradlew test` | 23 | 4 | 24 | 3 | `testDebugUnitTest -Pbrasscribe.fast`: 14, then 4 |
| `./gradlew assembleDebug` | 19 | 1 | 30 | 2 | |
| Windows `dotnet test` | 56 | 59 | 59 | 50 | `Category!=Slow`: 48, then 24 |
| `check-macos.sh` | 54 | 59 | 63 | 54 | |
| core .NET | 6 | 5 | 3 | 3 | 6, then 3 |

¹ Run after tier 1 in the same worktree, so partly warm.

² Most of it is the first open of the new pixi environment's files. See
[Cold starts and on-access scanning](#cold-starts-and-on-access-scanning).

Conformance is tier 2 only. Its time is the Python reference and the extras. The fast tier reuses
the reference outputs of an earlier run in the same worktree.

The slow tests found and marked:

| Suite | Tests marked slow |
|---|---|
| engine | discovery service info, 7 s; golden lines fit the page, 4 s; two processes save one index, 3 s; stages in order, 2 s |
| Swift | `ArrangementLevelTests`, 12 s; `RecordingLevelTests`, 3 × 11 s; `DynamicsLevelTests`, 8 s |
| Android | `EventStreamTimeoutTest`, 12 s; `OnDeviceSoloTest`, 3 s; `BeatThisParityTest`, 3 s |
| Windows | the golden AlphaTab render, 11 s; golden playback level, 3 s; golden previews, 3 s |

The FFI check that the C ABI matches UniFFI takes 2.3 s in release, so it is not marked.

### Why not a shared cargo target dir or sccache

Three `cargo test --release --no-run` builds were started at once in three fresh worktrees, with the
registry warm:

| Strategy | Wall time | Notes |
|---|---|---|
| Own `core/target` each (today) | 160 s | |
| One shared `CARGO_TARGET_DIR` | 105 s; a fourth worktree then 0.6 s | serialised on the lock, then everything counts as fresh |
| sccache, own targets, empty cache | 246 s | |
| sccache, new targets, warm cache | 253 s | 0 hits in 648 compiles: the arguments carry each target's paths |
| Own targets seeded from an APFS clone of a built one | 2.4 s | same "fresh" as the shared dir |

The shared and seeded targets are fast because they are wrong:

- Cargo decides freshness from mtimes. It keeps the absolute source paths of the first worktree in
  the dep-info, and does not re-check the `CARGO_MANIFEST_DIR` those paths came from.
- The test binaries embed `env!("CARGO_MANIFEST_DIR")`. So in the second worktree they read the first
  worktree's fixtures and `data/`.
- A worktree whose files are older than the last build reuses another branch's code without a
  rebuild.

So `cargo test` keeps a target dir per worktree. There are two wins instead:

- The artifact cache: the apps, bindings and FFI tests of other languages never build the core.
- The `fast` profile: after an edit to brasscribe-core, `cargo test --profile fast` takes 8 s, against
  47 s for `--release`.

`cargo nextest` does not help here. The whole suite runs in about 2 s, and nextest's per-process
start-up made the warm run slower (7 s against 3.6 s).

### Cold starts and on-access scanning

A fresh worktree opens thousands of new files: the pixi environment, `node_modules`, and build
outputs. The first open of each one appears to be slowed by the endpoint scanner on this Mac.

Collecting the engine tests takes 48 s the first time and 2 s after. Nearly all of the first run is
spent in `open_code`, about 6 ms per file, while the CPU is almost idle.

Excluding `~/.cache/brasscribe` and the worktree root from on-access scanning would probably remove
most of the remaining cold cost. That is an IT policy decision.
