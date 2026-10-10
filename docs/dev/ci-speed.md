# How long CI takes, and why it is laid out as it is

What a pull request waits for, where the minutes go, and which changes are done or still open. The numbers
are measurements with their date; when the workflows change, measure again (`gh run view <id> --json jobs`
has every job's and step's times) instead of trusting this page.

## Measurements (2026-10-10)

From the last 100 `ci` runs that day (64 on pull requests, 36 on pushes to `main`), their jobs and step
timings. It was a day with many branches in flight, so the durations per job are typical and the totals
(macOS minutes, queue lengths) are higher than on a quiet day. All times are minutes.

### Per job, on pull requests

| Job | Runner | Median | p90 | Queue median | Queue p90 |
|---|---|---|---|---|---|
| Apple / Play (packages, macOS app, iPhone simulator app) | macos-26 | 22.6 | 33.4 | 5.9 | 34.0 |
| Windows / Play (test, build and scan) | windows-2025 | 16.4 | 16.6 | 0 | 0 |
| Apple / Play for Mac screen catalogue | macos-26 | 12.6 | 14.5 | 8.4 | 28.0 |
| Android unit and screen tests | ubuntu-24.04 | 10.8 | 12.1 | 0 | 0 |
| Apple / Bandroom for Mac | macos-26 | 8.8 | 10.2 | 0.2 | 1.4 |
| Windows / Bandroom | windows-2025 | 8.5 | 12.0 | 0 | 0 |
| Rust core and .NET core logic | ubuntu-24.04 | 6.6 | 6.7 | 0 | 0 |
| Android screen catalogue, each app | ubuntu-24.04 | 5.8 to 6.2 | 7.1 | 0 | 0 |
| Studio | ubuntu-24.04 | 5.2 | 6.5 | 0 | 0.1 |
| Engine tests and benchmark gate | ubuntu-24.04 | 3.5 | 4.9 | 0 | 0 |

A whole pull request run, from created to its last job done: **median 16.9, p90 53.4**. The p90 was waiting
for a macOS runner, not building.

### What was slow

- **Waiting for macOS.** A public repository on a personal account gets 5 macOS jobs at a time (20 jobs in
  all). Of 95 macOS jobs, 26 waited more than 3 minutes, each time with 5 or more already running. Of the
  1,133 macOS minutes that day, 457 were pushes to `main`, and 132 of those were jobs cancelled before they
  finished.
- **Pushes to `main` were cancelled by the next merge**: 27 of 36. So the caches saved "from main only", at
  the end of a job, were mostly not saved, and `main` was rarely checked as a whole.
- **The iPhone simulator UI tests**: 10.6 of the Apple Play job's 22.6, after a 3.7 minute build of the same
  sources for the simulator.
- **Taking the base's screenshots again** for the comparison with `main`: Play for Windows 5.0, Play for Mac
  4.0, Bandroom for Mac 2.7, Android 2.35 for each app, Studio 1.4, on every push to every pull request.
- **A label added or removed** started every platform again to read one label: 8 runs, 349 job-minutes.
- **Release pull requests** (a version line in six build files, and the changelog) ran every platform: about
  105 job-minutes each. An edit to `ci.yml` did the same (97).
- **The Rust core is built once in every job that needs it**, in the release profile: three times on an
  Android pull request (0.7 each), twice on an Apple one (2.0, and 2.2 to 2.9 in the Mac catalogue job, which
  had no cache), once on Windows (1.1), three times in the core job.
- **Gradle is configured and the app compiled in three jobs** (the unit tests and the two catalogues), each
  restoring 1.2 to 1.4 GB of nearly the same cache.

Checked and not a problem: Verovio (cached), a branch running twice (it runs once, through its pull request),
release builds (only on tags), CodeQL (already per language).

### Where one median run's minutes went

| Job | Minutes | Parts |
|---|---|---|
| Apple / Play | 22.6 | setup 0.6; core for three targets 2.0; four Swift packages 1.5; macOS app build 1.1 and unit tests 2.2; iPhone simulator build 3.7, unit tests 0.4, UI tests 10.6 |
| Windows / Play | 16.4 | setup, NuGet, Rust 1.3; core 1.1; tests and build 1.2; catalogue 12.3 (base 4.9, head 5.3, Axe and Tab scan, verdict and compare 1.6) |
| Play for Mac catalogue | 12.6 | setup 0.6; core 2.2; base 4.0; head and compare 4.8 |
| Android unit tests | 10.8 | setup and core 1.0; compile 2.2; tests 4.3; lint and the debug builds 3.0 |
| Bandroom for Mac | 8.8 | setup 0.3; package tests 1.5; base 2.7; head 2.2; comparison and cleanup 1.7 |
| Bandroom for Windows | 8.5 | setup 0.6; tests and build 0.9; smoke test 0.2; engine install and start 1.2; catalogue 5.3 (the base was not needed) |
| Android catalogue, each app | 5.8 to 6.2 | setup and core 1.5; base 2.35; head 1.75 |
| Studio | 5.2 | npm, unit tests, build, browser tests 0.9; base 1.4; head 2.8 |
| Rust core and .NET | 6.6 | `cargo test --release` 3.6; the FFI library 0.55; bindings check 1.2; four `dotnet test` projects 0.9 |

### After the first changes (2026-10-10, one run each)

| Job | Before | After | What changed |
|---|---|---|---|
| Apple / Play, on a pull request | 22.6 | 9.5 | the iPhone simulator app and its tests are built (1.0) and not run; the rest is the core 2.4 (its cache was not there), the packages and the macOS app's tests 5.5 |
| The iPhone simulator tests, at night | in the job above | 15.3 | a job of their own: core 2.6, build and tests 12.1 |
| Play for Mac catalogue, the core's build | 2.2 to 2.9 | 1.4 | the Mac's slice alone, still without a cache; with the Play job's cache from `main` only the workspace's own crates are compiled |
| An edit to `ci.yml`, for the platforms nothing else in the pull request reaches | every platform (about 97 job-minutes) | 0.5 | `what changed` and actionlint; that pull request also changed `apple.yml`, so the Apple jobs ran and the others did not |

## The floor per platform

For a pull request that touches only that platform, on the hosted runners, with warm caches, a core that is
not built again and no base screenshots. Estimates from the parts above, not measurements.

| Platform | Measured (2026-10-10) | Floor | 1 to 3 minutes? |
|---|---|---|---|
| Android, one app | 10.8 beside 5.8 to 6.2 | 3 to 4 | about 3, with the unit tests in two or three shards; Gradle, the compile and Robolectric are over a minute before the first test |
| Studio | 5.2 | 2.5 to 3.5 | yes, with the catalogue in two shards |
| Rust core | 6.6 | 2 to 3 | probably, with the tests in the `fast` profile and one build instead of three |
| Engine | 3.5 | 3 | already there |
| Play for Mac and iOS | 22.6 beside 12.6, plus 6 to 8 of queue | 5 to 6, no queue | no, on a 3-core hosted Mac |
| Bandroom for Mac | 8.8 | 4 | no |
| Play for Windows | 16.4 | 5 to 6 | no |
| Bandroom for Windows | 8.5 | 4 | no |

So 1 to 3 minutes is within reach on the Linux jobs and not on hosted Windows or macOS, where 4 to 6 is. The
larger gain is the queue: it goes away when macOS use falls by more than half.

## Two tiers

**What a pull request waits for:** the compile and unit tests of the products the change reaches, and each
product's screen catalogue with its checks.

**What it does not wait for:**

- after merge, on `main`: every job, for every product. Runs there are not cancelled; merges that land while
  one is running are checked together by the next;
- every night, and by hand before a release: the iPhone simulator app's unit and UI tests (`nightly.yml`);
- the release run on a tag: every check again, then the release builds.

What each move costs:

| Move | Risk |
|---|---|
| iPhone simulator tests at night | a fault that only shows on iOS (a sheet, a flow, the accessibility audit there) reaches `main` and is found within a day; the nightly issue has to be looked at. The app and its tests are still compiled for iOS on every pull request |
| `main` not cancelled | a merge waits for the run before it, so its result comes later; of several waiting, only the newest runs |
| a release pull request starts no platform job | none found: the lines it may change are checked one by one, and the tag's run checks everything before anything is built |
| `ci.yml` in no filter | an edit that breaks one platform's job shows on the next pull request that reaches that platform, or in a hand-started run |

## The list, by minutes saved for the work

Effort: S under a day, M a few days.

| # | Change | Saves | Effort | State |
|---|---|---|---|---|
| 1 | The iPhone simulator unit and UI tests leave pull requests for a nightly run; the simulator build stays | 11 of the Apple Play job's 22.6 | S | done |
| 2 | Runs on `main` are queued, not cancelled | most of the 132 macOS minutes a day spent on cancelled jobs; the caches from `main` get saved | S | done |
| 3 | A label event runs again only the jobs that read the label | a whole run each time the label was set (349 job-minutes that day) | S | done |
| 4 | Version-only pull requests and edits to `ci.yml` start no platform job | about 105 job-minutes for each release, about 97 for each workflow edit | S | done |
| 5 | The Mac catalogue job builds the core for the Mac only, and reads the Play job's Rust cache | 1.5 to 2 of its 2.2 to 2.9 | S | done |
| 6 | The Android catalogue jobs read the unit test job's Rust cache | two caches fewer; no time | S | done |
| 7 | No comparison of screenshots with `main` on pull requests | Play for Windows 5.3, Play for Mac 4.6, Bandroom for Mac 4.6, Android and Studio about 1.0 each | S | open |
| 8 | Android as one job graph: one Gradle cache; lint and the debug builds after merge; unit tests in two shards; only the app whose sources changed | 3.0 (lint) and about 2 (shards) of 10.8; 2.7 GB of cache; one catalogue instead of two on single-app changes | M | open |
| 9 | One macOS job for Play: build for testing once, run the unit tests and the catalogue from it | one of two macOS slots for each Apple pull request, about 3 runner-minutes | M | open |
| 10 | The Rust core built once for a pull request and handed to the jobs that need it; its tests in the `fast` profile | 0.7 ×3 on Android, about 4 on Apple, 1.1 on Windows, about 3 in the core job | M | open |
| 11 | The Windows catalogue's four runs on two runners, and one Axe pass instead of two | wall time of the catalogue about halved; more Windows minutes in all | M | open |

Looked at and left out: paid or larger runners (make the cuts first; larger hosted runners need an
organisation), a self-hosted Mac (a public repository's pull requests would run code on it), a hosted
screenshot review service (5,000 to 7,000 free screenshots a month would last about a day), a remote Gradle
build cache (the local one already travels in the Actions cache), sccache (it does not cache the `cdylib` the
core is), Bazel (no rules for WinUI), a larger Actions cache (merging the Gradle caches removes the need).

## Things to know when changing the workflows

- Nothing is a required status check; `CI result` is the one to wait for.
- A hosted Linux or Windows runner has 4 cores and 16 GB, a macOS one 3 cores and 7 GB.
- The Actions cache holds 10 GB for the repository, and entries not read for 7 days go. It was full on the
  day measured; the three Gradle caches are about 4 GB of it.
- `release.yml` calls `ci.yml`, `apple.yml` and `windows.yml`, and a called workflow gets no more permissions
  than its caller gives. A job in one of those three that asks for more stops every release at its start.
- A new workflow file can be started by hand or by its schedule only once it is on `main`.
