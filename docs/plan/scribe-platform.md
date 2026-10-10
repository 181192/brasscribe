# One core, several apps: structure and plan

This repository holds more than one app on one transcription core. Brasscribe turns a recording into a brass-band score. Fretscribe turns a recording into tab for guitar, bass, ukulele and mandolin. More apps on the same core are expected. This plan says how the code is laid out so that a new app is a new thin product and nothing else has to move, and in which order the work is done.

It replaces the "split the core" and "open decisions" sections of `docs/fretscribe/plan/PLAN.md` and the single-product layout in `docs/plan/apps-plan.md` §3.

**Status (2026-10-10): started.** The decisions below are the owner's, made that day.

## Decisions

| Question | Decision |
|---|---|
| Name of the shared, instrument-free core | `scribe-core`. The family is "scribe". |
| Versions | Each app has its own version, tag and release. A change that does not reach an app does not build or release it. |
| Names on the wire (pairing link, network service) | Neutral, in the "scribe" family, shared by all apps. The old names are dropped in the same change. |
| Compatibility | None before 1.0.0. Every part targets the latest of every other part. No code that exists only to keep an older app, engine, file or name working. After 1.0.0 a breaking change needs a new major version. |
| Devices | The newest release of each operating system and the one before it. Nothing older. Code that exists only for an older system is removed. |
| How much the clients share | Logic is shared. Looks are not assumed to be. Each product owns its screens and can differ in layout, navigation and experience, not only in colour. |
| What Fretscribe is to become | Everything in `docs/fretscribe/plan/android-app.md`'s roadmap and `design/fretscribe/flows.md`, on each of its clients. This is the scope to reach, not a version number: Fretscribe is released early and often on the way there. |
| Clients of an app | Android, Mac, Windows, and an unsigned test build for iPhone and iPad (there is no Apple Developer account). Studio and Bandroom are not clients of one app: they serve all of them. |

## Layers

| Layer | Holds | Rule |
|---|---|---|
| Core (crate `scribe-core`) | Notes, rhythm, spelling, MusicXML primitives, transcription clean-up | Knows no instruments and no product |
| Targets (crates `target-brass`, `target-fretted`, later others) | What turns notes into one kind of output: arranging for a band, placing notes on strings | Depend on the core. Never on each other |
| Engine and Bandroom | Runs the heavy models on a computer and serves every app | One program for all apps. A profile belongs to a target |
| Client services, per platform | Pairing, the engine client, recording, sending, the library's storage, settings storage, playback engines | No screens. No product words |
| Client features, per platform | View models and logic of a feature: the score, the music stand, the tab, practice | Logic and state. Views only where two products truly show the same thing |
| Design system | A generator that makes each brand's tokens for every platform | A small set of neutral roles that any app needs. A brand adds its own roles beside them |
| Products | An app: name, icon, identifiers, words, navigation, screens, which features it uses | Thin in logic, free in looks |

Sharing a screen between two products is a choice made per screen, not the default. Two products may start from the same component and drift apart. When they do, the component is copied into each product rather than grown switches.

## Folder layout

The target, and where today's directories go. Directories move in mechanical pull requests of their own, each with every path that points at them. Renaming what the core builds (step 3) is a different thing and happens in one pull request.

```
core/
  scribe-core/            was core/brasscribe-core, without its brass modules
  targets/brass/          crate target-brass: was inside brasscribe-core
  targets/fretted/        crate target-fretted: was core/target-fretted
  ffi/  cli/              were core/brasscribe-ffi and core/brasscribe-cli
  bindings/  swift/  dotnet/  android/  conformance/  tools/  scripts/    stay where they are
engine/  music/  eval/    Python: a package per target beside the shared code
apps/
  android/
    services/             was the modules engine-client, core-bridge, audio, and the non-screen parts of app
    features/score/       was model, pitch, and the score logic in app
    features/tab/         was the tab logic in app's fretscribe source set
    products/brasscribe/  products/fretscribe/    the two apps: screens, words, navigation
  apple/                  the same three levels as Swift packages and app targets
  windows/                the same three levels as projects
  bandroom/{macos,windows}/
  fixtures/               stays; a folder per target inside it
studio/
design/
  tooling/                was design/tokens/build.py, the schema and the checks
  brands/brasscribe/      was design/{tokens,brand,pink,dist,mockups,system.md,music-stand.md}
  brands/fretscribe/      was design/fretscribe/
docs/
  shared/                 was docs/{dev,research,accessibility} and this plan
  brasscribe/             was the Brasscribe plans in docs/plan
  fretscribe/             stays
```

## Versions and releases

- Tags: `brasscribe-vX.Y.Z`, `fretscribe-vX.Y.Z`, `bandroom-vX.Y.Z`, `scribe-core-vX.Y.Z`. Each has its own changelog.
- The engine has no tag of its own: it ships inside Bandroom and takes Bandroom's version. `scribe-core` releases the command line tool for each system, as today.
- A release builds only that app's clients. Its notes list the changes that reach it: its own product code, plus the shared layers it is built from.
- CI on a pull request runs the checks of the layers the change touches and of the products built from them. A change in one product's screens runs that product only. This part does not wait for the tags (see the order below).
- App and engine must match. The engine's health answer carries one whole number, its interface version. An app is built for one number. When they differ, the app says in plain words which of the two to update, and does nothing else.
- Android: each app keeps its package name and its signing key for ever (`no.brasscribe.play` with Brasscribe's key, `no.fretscribe.play` with the prototypes key). Fretscribe's first release under its own tag takes a version name and version code above the last ones it had under the shared tag.
- iPhone and iPad: an unsigned `.ipa` for each app that has an Apple client. A tester signs it with their own Apple ID; a free signature lasts seven days.

## Devices

| Platform | Supported on 2026-10-10 |
|---|---|
| Android | 17 and 16 |
| iPhone, iPad, Mac | 27 and 26 |
| Windows | Windows 11 |

The floor moves up when a new system is released. Raising it is one pull request per platform that also removes the checks and fallbacks the older system needed.

## Order of work

Each step lands as small reviewed pull requests, and `main` stays releasable. Until step 11 everything is still released together under one `v*` tag, which is what lets steps 3 and 7 change the engine and every client at once.

A pull request that renames a library, a package or a file the release builds name must also pass a hand-started release build of each platform it touches: the release builds stage the core and shrink the apps differently from the test builds.

| # | Step | Needs |
|---|---|---|
| 1 | **Fretscribe for Android gets a release build**, signed with the prototypes key, without what only Brasscribe uses. | — |
| 2 | **Core split.** Brass code leaves the core for the crate `target-brass`. The compiler, not a test, keeps targets apart. No renames. Every conformance vector, golden and benchmark stays byte for byte the same. | — |
| 3 | **Core rename, in one pull request.** The crates and their folders, the library and the bindings the clients load, the command line tool and the core's environment variables take "scribe" names. No old name is kept. The name the core writes into its files changes too, so the goldens and fixtures that carry it are made again in the same pull request, and nothing else in them may differ. | 2 |
| 4 | **Design system for any brand on every platform.** Fretscribe's tokens are generated for Apple, Windows and the web. | — |
| 5 | **An unsigned iPhone and iPad build** in the release. | — |
| 6 | **Device floors raised** on every platform, with the old systems' code removed. | 1, 5 |
| 7 | **The engine and the wire, in one release of everything.** A target is a first-class thing in the engine: profiles belong to a target, and output file names come from the target instead of being written as `brass-band.*` in shared code. The Python packages and the command take "scribe" names. The pairing link and the network service take theirs. The interface version number is added. Every client changes in the same pull requests. After this release an older app has to be updated and paired again. | 3 |
| 8 | **Android restructure.** Services, features and products become modules. Fretscribe's code leaves the `no.brasscribe.play` package. Each product has its own complete words. The `Product` object with call sites all over shared code becomes what each product's module wires together. CI runs one product when only that product changed. | 1, 3, 6 |
| 9 | **Windows.** The same three levels, then Fretscribe for Windows. Windows already draws with alphaTab. | 4, 7 |
| 10 | **Apple.** The same three levels, then a decision on how tab is drawn (Apple has no tab renderer today), then Fretscribe for Mac, iPhone and iPad. | 4, 5, 7 |
| 11 | **Versions per app.** Tags, changelogs, release workflows and release notes per product. The same pull requests change everything the tag reaches: the `release` environment's tag rule (the owner's to change), the release workflow's tag pattern and its look-up of the previous tag, `scripts/release.sh`, how the phone's updater reads a version from a tag, and every download link on the site and in the READMEs, which today point at "the latest release" and would then point at whichever app released last. | 8, 9, 10 |
| 12 | **Studio** gets a tab view. Studio stays one program. | 7 |
| 13 | **Fretscribe's remaining features**, built once per feature across its clients: sharing and printing a tab, fixing a note, the tuning and capo sheet, the layers menu, count-in and metronome, the speed trainer, saved repeats, hiding the chrome, pedals, the screen reader reading beat by beat, the record preflight, left-handed views. | 8; then 9 and 10 as each client arrives |

Steps 1, 2, 4 and 5 run side by side. Step 3 touches what every client loads, so nothing else that touches a client's build lands while it is open.

## What is not shared

- Words. Each product has its own, complete, in every language it speaks.
- Navigation and the first run.
- The screens of a product's own idea (a music stand; a tab with a practice player).
- Brand: colours, type, icon, illustration.

## Open

- How tab is drawn on Apple: alphaTab in a web view, a native drawing of the core's tab data, or Verovio. Decided by a spike in step 10.
- The desktop program's name. It serves every app; "Bandroom" without a product's name in front is the working choice.
- When the repository itself takes a neutral name.
- With both apps on one phone before step 7, a pairing link offers a choice of the two. After step 7 the link names the family, and the question of which app opens it remains.
