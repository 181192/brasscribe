# One core, several apps: structure and plan

This repository holds more than one app on one transcription core. Brasscribe turns a recording into a brass-band score. Fretscribe turns a recording into tab for guitar, bass, ukulele and mandolin. More apps on the same core are expected. This plan says how the code is laid out so that a new app is a new thin product and nothing else has to move, and in which order the work is done.

It replaces the "split the core" section of `docs/fretscribe/plan/PLAN.md` and the single-product layout in `docs/plan/apps-plan.md` §3 where they disagree.

**Status (2026-10-10): started.** Decisions below are the owner's, made that day.

## Decisions

| Question | Decision |
|---|---|
| Name of the shared, instrument-free core | `scribe-core`. The family is "scribe". |
| Versions | Each app has its own version, tag and release. A change that does not reach an app does not build or release it. |
| Names on the wire (pairing link, network service) | Neutral, in the "scribe" family, shared by all apps. The old names are dropped in the same change. |
| Compatibility | None before 1.0.0. Every part targets the latest of every other part. No code that exists only to keep an older app, engine, file or name working. After 1.0.0 a breaking change needs a new major version. |
| How much the clients share | Logic is shared. Looks are not assumed to be. Each product owns its screens and can differ in layout, navigation and experience, not only in colour. |
| Devices | The newest release of each operating system and the one before it. Nothing older. Code that exists only for an older system is removed. |
| Fretscribe's first version | Everything in `docs/fretscribe/plan/android-app.md`'s roadmap and `design/fretscribe/flows.md`, as complete as possible, on every client. |
| Clients | Android, Mac and Windows downloads for each app, and an unsigned test build for iPhone and iPad (there is no Apple Developer account). |

## Layers

| Layer | Holds | Rule |
|---|---|---|
| Core (`scribe-core`) | Notes, rhythm, spelling, MusicXML primitives, transcription clean-up | Knows no instruments and no product |
| Targets (`target-brass`, `target-fretted`, later others) | What turns notes into one kind of output: arranging for a band, placing notes on strings | Depend on the core. Never on each other |
| Engine and Bandroom | Runs the heavy models on a computer and serves every app | One program for all apps. A profile belongs to a target |
| Client services, per platform | Pairing, the engine client, recording, sending, the library's storage, settings storage, playback engines | No screens. No product words |
| Client features, per platform | View models and logic of a feature: the score, the music stand, the tab, practice | Logic and state. Views only where two products truly show the same thing |
| Design system | A generator that makes each brand's tokens for every platform | Neutral role names. A brand may add its own roles |
| Products | An app: name, icon, identifiers, words, navigation, screens, which features it uses | Thin in logic, free in looks |

Sharing a screen between two products is a choice made per screen, not the default. Two products may start from the same component and drift apart. When they do, the component is copied into each product rather than grown switches.

## Folder layout

The layout below is the target. Directories move one mechanical pull request at a time, each with every path that points at them.

```
core/
  scribe-core/            instrument-free
  targets/brass/          was inside brasscribe-core
  targets/fretted/        was core/target-fretted
  ffi/  cli/  bindings/   one library for all apps; each target behind its own functions
engine/  music/  eval/    Python: the same split, a package per target
apps/
  android/
    services/             pairing, engine client, capture, storage
    features/score/       features/tab/
    products/brasscribe/  products/fretscribe/
  apple/                  the same three levels as Swift packages and app targets
  windows/                the same three levels as projects
  bandroom/{macos,windows}/
studio/
design/
  system/                 generator, schema, checks
  brands/brasscribe/      brands/fretscribe/     tokens, brand, dist
docs/
  shared/  brasscribe/  fretscribe/
```

## Versions and releases

- Tags: `brasscribe-vX.Y.Z`, `fretscribe-vX.Y.Z`, `bandroom-vX.Y.Z`, `scribe-core-vX.Y.Z`. Each has its own changelog.
- A release builds only that app's clients. Its notes list the changes that reach it: its own product code, plus the shared layers it is built from.
- CI on a pull request runs the checks of the layers the change touches and of the products built from them. A change in one product's screens runs that product only.
- Bandroom and the engine are released on their own. Before 1.0.0 an app works with the latest engine only; when the two do not match, the app says in plain words which one to update, and nothing more.
- Android: each app keeps its package name and its signing key for ever (`no.brasscribe.play` with Brasscribe's key, `no.fretscribe.play` with the prototypes key). Both are registered in the Android Developer Console.
- iPhone and iPad: an unsigned `.ipa` per app. A tester signs it with their own Apple ID; a free signature lasts seven days.

## Order of work

Each step lands as small reviewed pull requests. `main` stays releasable. A step that moves code must leave every conformance vector, golden and benchmark byte for byte the same.

1. **Fretscribe for Android gets a release build**, signed with the prototypes key.
2. **Core split.** Brass code leaves the core for `target-brass`. The compiler, not a test, keeps targets apart. Then everything takes its new name in one go: the crates (`scribe-core`, `targets/…`), the library and bindings the clients load, the command line tool and the environment variables. No old name is kept as an alias.
3. **Design system for any brand on every platform**, with neutral role names. Fretscribe's tokens are generated for Apple, Windows and the web.
4. **An unsigned iPhone and iPad build** in each release.
5. **Android restructure.** Services, features and products become modules. Fretscribe's code leaves the `no.brasscribe.play` package. Product words stop overriding each other: each product has its own complete strings. The `Product` object with call sites all over shared code becomes what each product's own module wires together.
6. **Engine and Python.** A target is a first-class thing: profiles belong to a target, and output file names come from the target instead of being written as `brass-band.*` in shared code. Benchmarks gate per target.
7. **Versions per app.** Tags, changelogs, release workflows and CI path filters per product, as above.
8. **Neutral names on the wire.** The pairing link and the network service take their new names in the engine and in every client in the same release. An app from before the change has to be updated, and paired again.
9. **Windows.** The same three levels, then Fretscribe for Windows. Windows already draws with alphaTab.
10. **Apple.** The same three levels, then a decision on how tab is drawn (Apple has no tab renderer today; `design/fretscribe/system.md` says alphaTab on every platform), then Fretscribe for Mac, iPhone and iPad.
11. **Studio** gets a tab view. Studio stays one program.
12. **Fretscribe's remaining features**, built once per feature across all its clients: sharing and printing a tab, fixing a note, the tuning and capo sheet, the layers menu, count-in and metronome, the speed trainer, saved repeats, hiding the chrome, pedals, the screen reader reading beat by beat, the record preflight, left-handed views.

Steps 2, 3 and 4 do not touch each other and run side by side. Step 5 waits for step 1. Steps 9 and 10 wait for 3 and are easier after 5 has shown the shape.

## Devices

| Platform | Supported on 2026-10-10 |
|---|---|
| Android | 17 and 16 |
| iPhone, iPad, Mac | 27 and 26 |
| Windows | the current Windows 11 release and the one before |

The floor moves up when a new system is released. Raising it is one pull request per platform that also removes the checks and fallbacks the older system needed.

## What is not shared

- Words. Each product has its own, complete, in every language it speaks.
- Navigation and the first run.
- The screens of a product's own idea (a music stand; a tab with a practice player).
- Brand: colours, type, icon, illustration.

## Open

- How tab is drawn on Apple: alphaTab in a web view, a native drawing of the core's tab data, or Verovio. Decided by a spike in step 10.
- The desktop program's name. It serves every app; "Bandroom" without a product's name in front is the working choice.
- When the repository itself takes a neutral name.
