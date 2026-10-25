# One core, several apps: structure and plan

This repository holds more than one app on one transcription core. Brasscribe turns a recording into a brass-band score. Fretscribe turns a recording into tab for guitar, bass, ukulele and mandolin. More apps on the same core are expected. This plan says how the code is laid out so that a new app is a new thin product and nothing else has to move, and in which order the work is done.

It replaces the "split the core" and "open decisions" sections of `docs/fretscribe/plan/PLAN.md` and the single-product layout in `docs/brasscribe/plan/apps-plan.md` §3.

**Status (2026-10-10): started.** The decisions below are the owner's, made that day.

## Decisions

| Question | Decision |
|---|---|
| Name of the shared, instrument-free core | `scribe-core`. The family is "scribe". |
| Versions | Each app has its own version, tag and release. A change that does not reach an app does not build or release it. |
| Names on the wire (pairing link, network service) | Neutral, in the "scribe" family, shared by all apps. The old names are dropped in the same change. |
| Compatibility | None before 1.0.0. Every part targets the latest of every other part. No code that exists only to keep an older app, engine, file or name working. After 1.0.0 a breaking change needs a new major version. |
| Devices | The newest release of each operating system and the one before it; on Windows, Windows 11. Nothing older. Code that exists only for an older system is removed. |
| How much the clients share | Logic is shared. Looks are not assumed to be. Each product owns its screens and can differ in layout, navigation and experience, not only in colour. |
| What Fretscribe is to become | Everything in `docs/fretscribe/plan/android-app.md`'s roadmap and `design/brands/fretscribe/flows.md`, on each of its clients. This is the scope to reach, not a version number: Fretscribe is released early and often on the way there. |
| Package names and app ids | Everything sits under `no.kalli` (the owner's domain). The core is `no.kalli.scribe.core`. Shared client code is `no.kalli.scribe.*`. Each product is `no.kalli.brasscribe` or `no.kalli.fretscribe`, for its code and as its Android application id and Apple bundle id. On Windows it is `Kalli.Scribe.*` and `Kalli.Brasscribe.*` / `Kalli.Fretscribe.*`. The old ids (`no.brasscribe.play`, `no.fretscribe.play`) are dropped, with no migration: the new app installs beside the old one, and removing the old one deletes its scores. The new ids are registered in the Android Developer Console, with their signing keys, before the first release that carries them. Each client takes its names in its restructure (steps 8 to 10). |
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
engine/  music/  eval/    Python: stay at top level, a package per target beside the shared code (not yet split per target, see Open)
ml/  convert/  capture/  shared tools, stay: see "Where the rest goes"
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
studio/                   stays: serves every app
sounds/  qa/  site/       a folder per product beside a shared one: see below
scripts/                  stays: repository tooling
design/
  tooling/                was design/tokens/build.py, the schema and the checks
  brands/brasscribe/      was design/{tokens,brand,pink,dist,mockups,system.md,music-stand.md}
  brands/fretscribe/      was design/fretscribe/
  shared/                 was design/{server-app.md,reviews} that is not about one product
docs/
  shared/                 was docs/{dev,research,accessibility}, plus the plans in docs/plan that are about every app (this one)
  brasscribe/             was the Brasscribe plans in docs/plan, and docs/media
  fretscribe/             stays
  songs/                  stays
```

`docs/` moves in one pull request once step 3 is in, since step 3 changes many of the paths the documents name.

### Where the rest goes

The test for each folder: where would the sibling product's version of this go? Something that belongs to one product or one target sits under that product's or target's name. Something every product uses stays neutral, with the product folders beside it.

| Folder | Used by | Placement |
|---|---|---|
| `capture/` | Apple builds and CI (macOS process-tap recorder) | Shared. Records any audio; stays. Its tool is `scribe-capture`. |
| `convert/` | Model conversion to ONNX and Core ML, parity reports | Shared. A folder per model, so a model for another target is one more folder. Stays. |
| `ml/` | `ml/adapters/<model>`: one environment per model behind `run.sh`; `ml/pipelines` | Shared. Models are not products; a profile (per target) chooses which run. Stays. |
| `sounds/` | Android, Apple, Windows, Bandroom builds (the band SoundFont); `pixi fetch-sounds` | Mixed. The band pack (`band*.py`, `seating.json`, `mapping.json`, `band-sounds.json`, `LICENSES.md`, the band tests) is brass-specific. The SoundFont reader and writer, DSP, rendering, parity and `ab-test/` are not. Target: `sounds/common/` for the tools, `sounds/brass-band/` for the band pack, and a guitar set is `sounds/<set>/` beside it. The files that mix both are split file by file when this moves. |
| `qa/` | CI (contrast, readability tests), release checks | `qa/shared/` holds `perf`, `tools` (contrast, MusicXML readability) and the contrast reports on design tokens. The Mikkel readability reports and reviews and the screen-reader scripts are about Brasscribe Play and sit in `qa/brasscribe/`; Fretscribe gets `qa/fretscribe/`. |
| `site/` | `pages.yml`, `ci.yml`, `site/build.sh` | One build, one stylesheet and one language script in `site/shared/`. Content per product in `site/brasscribe/` (`index.html`, `guide/`, `research/`, `nb/`, `shots/`, and the screenshot list and script), served at the site root as before; `site/fretscribe/` when it has pages. |
| `scripts/` | Every workflow, `worktree-setup.sh`, the macOS VM | Shared repository tooling; stays. `release.sh` takes the product from the tag. |
| `design/claude/` | Publishes Brasscribe's design system as a Claude artifact; reads the Brasscribe sources | Brand-specific: `design/brands/brasscribe/claude/`. Fretscribe's would sit beside it. |
| `design/pink/` | Brasscribe screenshots of the pink theme, read by the Apple workflow's path filter | Brand-specific: `design/brands/brasscribe/pink/`. |
| `design/reviews/` | Written reviews with screenshots | `music-stand/` and the usability reviews of the Brasscribe mockups and Android screens: `design/brands/brasscribe/reviews/`. `studio-review.md` is about Studio, which serves every app: `design/shared/`. Likewise `design/server-app.md` (Bandroom). |
| `apps/android/design/{brasscribe,fretscribe}` | Gradle modules that wrap each brand's generated design system | Already a folder per brand; stays. A new brand adds its module here. |
| `apps/android/docs/screenshots/` | Android documentation and reviews | A folder per product: `brasscribe/` (`design`, `before-design`, `score-*`, `music-stand`, `my-instrument`) and `fretscribe/`. |

Neutral folders stay at the top level and do not carry a product name. A product's own files carry its name as a folder, not as a prefix in a file name.

### Adding a sibling product

For a product `<p>` on the same core:

1. Clients: on each of Android, Apple and Windows, `products/<p>/` (screens, words, navigation, identifiers) using the existing `services/` and `features/`. A feature only this product has goes in `features/` when a second product could use its logic, otherwise inside the product.
2. Design: `design/brands/<p>/` with its tokens, brand and mockups, generated by `design/tooling`; on Android a module in `apps/android/design/<p>`.
3. Docs: `docs/<p>/` for its plans and research; `qa/<p>/` for its screen-reader scripts and reports.
4. Output kind: if the product writes a new kind of output, a crate `core/targets/<kind>/` and a Python target package for it, and a profile in the engine. A product that reuses an existing kind needs neither.
5. Sounds, models: a sound set in `sounds/<set>/`; a model as one folder each in `ml/adapters/` and `convert/`.
6. Site: `site/<p>/` if it has public pages.
7. CI and release: path filters for its own folders in the per-client workflows, so a change to another product does not build it; a tag `<p>-vX.Y.Z` and a changelog.

## Versions and releases

- Tags: `brasscribe-vX.Y.Z`, `fretscribe-vX.Y.Z`, `bandroom-vX.Y.Z`, `scribe-core-vX.Y.Z`. Each has its own changelog.
- The engine has no tag of its own: it ships inside Bandroom and takes Bandroom's version. `scribe-core` releases the command line tool for each system, as today.
- A release builds only that app's clients. Its notes list the changes that reach it: its own product code, plus the shared layers it is built from.
- CI on a pull request runs the checks of the layers the change touches and of the products built from them. A change in one product's screens runs that product only. This part does not wait for the tags (see the order below).
- App and engine must match. The engine's health answer carries one whole number, its interface version. An app is built for one number. When they differ, the app says in plain words which of the two to update, and does nothing else.
- Android: each app keeps its application id and its signing key for ever (`no.kalli.brasscribe` with Brasscribe's key, `no.kalli.fretscribe` with the prototypes key). Fretscribe's first release under its own tag takes a version name and version code above the last ones it had under the shared tag.
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
| 2 | **Core split.** Brass code leaves the core for the crate `target-brass`. Where a module is part neutral and part brass (writing MusicXML, the talking score, the pipeline), the neutral part stays in the core behind a small interface that a target fills in: what an instrument is, and what a target does with the notes. The compiler, not a test, keeps targets apart. No renames. Every conformance vector, golden and benchmark stays byte for byte the same. It lands in three parts, 2a to 2c below. | — |
| 2a | **Done.** The brass modules (`instruments`, `arranger`, `difficulty`, the band score, `pipeline`) are the crate `target-brass`. The MusicXML writer stays in the core and takes a part's instrument facts as data (`InstrumentSpec`, the parts' MIDI banks). A test reads the manifests: the core depends on no target, targets do not depend on each other. | — |
| 2b | **Done.** The shared transcription is the core's `transcription`: `Beats`, `lead_sheet`, `composition_from_reference`, `quantize_reference`, and what `arrange_layers_song` and `arrange_song` did before they arranged (`transcribe_layers`, `transcribe_song`: transcriptions and beats in, a Composition out). Only arranging stays in `target-brass`, which tells the transcription what only the band knows: the range of the instrument that takes the tune, what a key change costs at a difficulty. A target must never be the only home of something another target needs. `InstrumentSpec`'s names are owned, so that a target whose instrument names come from data at run time can fill it in, and the writer's comments and names no longer speak of the band. | 2a |
| 2c | **Done.** The talking score's reading stays in the core. What parts and instruments are called in Norwegian is `target-brass`'s (`names`), handed to the core through `talking_score::Names`: a target supplies how its parts and instruments are named in each language. The core holds no instrument knowledge, and a test reads its code for instrument names in place of the one that kept its other modules from using `talking_score`. The announcers in the apps (Kotlin, C#, TypeScript, Swift) are separate implementations with their own copies of the names; they follow in the client steps (8 to 10 and 12). | 2a |
| 3 | **Core rename, in one pull request.** The crates and their folders, the library and the bindings the clients load, the command line tool and the core's environment variables take "scribe" names. No old name is kept. The name the core writes into its files changes too, so the goldens and fixtures that carry it are made again in the same pull request, and nothing else in them may differ. | 2a |
| 4 | **Design system for any brand on every platform.** Fretscribe's tokens are generated for Apple, Windows and the web. Then `design/` moves to the layout above, in a pull request of its own. | — |
| 5 | **An unsigned iPhone and iPad build** in the release. | — |
| 6 | **Device floors raised** on every platform, with the old systems' code removed. | 1, 5 |
| 7 | **The engine and the wire, in one release of everything.** A target is a first-class thing in the engine: profiles belong to a target, and output file names come from the target instead of being written as `brass-band.*` in shared code (done: 7b). The Python packages (`brasscribe_engine`, `brasscribe_music`, `brasscribe_eval`) and the engine's command (`brasscribe`) take "scribe" names. Benchmarks gate per target. The pairing link and the network service take theirs, and the interface version number is added (done: 7c). Every client changes in the same pull requests. After this release every app and Bandroom have to be updated together; an updated app keeps its pairing. What the core split left for this step (done: 7b), each changing what a client or a file sees: the bindings and the command line let a target choose its names for the talking score (today they always pass the band's, `BandNames`); the product name the core writes becomes something the target fills in (the MusicXML `<creator>arr. Brasscribe</creator>` in `notation/score.rs` and the message about the longest piece in `model.rs`), which changes the goldens; and the layer id `brass` in `composition.json` gets a name for what was heard. The Norwegian handling in `BandNames` that is not band knowledge (the lower-case first letter, " in C" to " i C") moves into the core's talking score when a second target needs it, which is not yet: the fretted target passes the score's own names. | 3 |
| 7a | **Done.** The Python side has "scribe" names: the packages `scribe_engine`, `scribe_music` and `scribe_eval` (distributions `scribe-engine`, `scribe-music`, `scribe-eval`, `scribe-sounds`), the engine's command `scribe`, the pixi workspace, and every environment variable the engine, the tools, the repository's scripts and Bandroom read (`SCRIBE_DATA`, `SCRIBE_MODELS`, `SCRIBE_REPO`, …), with the cache folder `~/.cache/scribe` and the workspace stamp `.scribe-workspace.json`. Both Bandrooms start the engine under the new command and replace an engine installed under the old names. No output changes. | 3 |
| 7b | **Done.** A target is a first-class thing in the engine (`scribe_engine/targets.py`): every profile belongs to `brass` or `fretted`, the target names its output files (`brass-band.*`, `tab.*`, unchanged for users) and its jobs' default titles, and no other engine code spells a score's file name (a test reads the code for it). `/v1/profiles` gives each profile's `target` and every job carries its own, and each app offers its own target's profiles and takes only its own target's jobs for its own. Benchmarks gate per target: every suite belongs to one, `eval/baselines.json` keeps the baselines under it, and `scribe bench` and the engine's answers give a verdict per target; no number changed. What the core split left is done too: the bindings and the command line take the target that wrote the score when they build a talking score (UniFFI `Target`, C `SC_TARGET_*`, `talking-score --target`), and the fretted target says the names the score gives; the core writes no product name (the score's `<creator>` is the target's, `ScoreSpec.creator`, which the band fills with what it wrote before; a tab names Fretscribe as the program that wrote it; and the message about the longest piece names no product); and the layer the orchestra's short chords are heard in is `hits` in `composition.json`, not `brass`. The Norwegian handling in `BandNames` that is not band knowledge stays there: the fretted target has no Norwegian names of its own yet, so nothing needs it from the core. | 3 |
| 7c | **Done.** The wire has the family's name and a number. The pairing link is `scribe://pair?…` and the network service `_scribe._tcp`, in the engine, both Bandrooms, Studio and every Play app (Android's two products, Apple, Windows); the old link and service are not read anywhere. The engine's health answer carries `interface_version`, which is `1`, and each client holds the one number it is built for next to its wire names (`wire.py`, `Wire.kt`, `Wire.swift`, `Wire.cs`, `wire.ts`). When the engine's number is higher the app says to update the app; when it is lower or missing, to update Bandroom on the computer. Until they match the app asks that engine for its health only: no pairing, no job, no score. Each client holds that in one place, its engine client, which refuses every other request before it is sent, asks the health first while it does not know the engine's number, and asks again after a request that did not get through. A paired device reads the number from its own heartbeat (`GET /v1/devices/me` carries it too). The pairing it had is kept. Raising the number is a breaking change for every client and is done in the pull request that breaks them. Every app and Bandroom are updated together: an updated app keeps its pairing, and an app or an engine left on the old version can neither find nor pair with the other. | 3 |
| 8 | **Done.** Services, features and products are modules (`apps/android/services`, `features`, `products`), in `no.kalli.scribe.*` and `no.kalli.brasscribe` / `no.kalli.fretscribe`, which are also the application ids. Fretscribe's code has left the old package. Each product declares its own complete words in English and bokmål, and a test fails when one leaves a shared string to the default. `Product` is an interface that each product module implements and hands in through its `Application`; shared code names no product. Settings, the navigation and the window colours are the product's own. Some capabilities are still read by shared code through the interface (`opensScores`, `phonePdf`, `keepsRecordings`, `timeLeft`, `keepOpenWhileWriting`, `arranges`, …); turning them into the product's own screens or slots is the next increment (they are flags the shared Home, Transcribing, Export and library code reads, each one wiring through a screen). The strings only Brasscribe's code reads are in `products/brasscribe` alone, and `features/play` and Fretscribe no longer carry them. CI on a pull request checks only the app whose module changed when nothing they share did. The Android build's and tests' environment variables are `SCRIBE_*`. | 1, 3, 6, 7 |
| 9 | **Done.** `apps/windows` has the three levels: `services` (`Kalli.Scribe.Services`, `Kalli.Scribe.Audio.Windows`, `Kalli.Scribe.WinUI`), `features` (`Kalli.Scribe.Score`, `Kalli.Scribe.Play`, `Kalli.Scribe.Controls`, `Kalli.Scribe.Tab`) and `products/brasscribe` and `products/fretscribe` (`Kalli.Brasscribe`, `Kalli.Fretscribe`, each with its screen catalogue and its own words in English and bokmål). Each product hands in its target, its data folder, its name in the credential vault, its single-instance key and, for Brasscribe, the hidden Pink palette; a test fails when shared code names a product or says "pink". The brass-only playback code (the band SoundFont, the brass sound set) sits in its own folder of the shared score feature, as on Android. Each Windows app has its own flow view model on the shared library, transcription, settings and error view models (Brasscribe's `MainViewModel`, Fretscribe's `TabFlowViewModel`); Android still has one shared flow, and may follow. Fretscribe for Windows draws tab with alphaTab, shares or prints it, keeps a failed take for 30 days, and is released as `fretscribe-windows-x64.zip` under the shared tag. CI on a pull request checks only the Windows app whose product folder changed when nothing they share did. The Windows build's and tests' environment variables are `SCRIBE_*`. | 4, 7 |
| 10 | **Done.** `apps/apple` has the three levels: `services` (the Swift package `ScribeServices`: the score model, the engine client, playback, on-device transcription), `features` (`score`: Verovio; `tab`: the tab and its practice logic; `play`: the screens every Play app shares, compiled into each app, which ask the app for what they need through `PlayHost`), `products/brasscribe` and `products/fretscribe`, and `testing` (the screen catalogues' checks and shared test code). The engine client takes the target from the app; the band's profiles and options are Brasscribe Play's. Shared screens' words name no product, and each product's catalog says them in its own words, with a test that fails when one is missing. The capture tool is `scribe-capture`, and the Apple builds' environment variables are `SCRIBE_*`. **Tab is drawn by alphaTab in a web view** (the spike: `apps/apple/docs/tab-spike.md`): the engraver of the other clients, from the app's own files with no network, its colours from the tokens, the cursor driven by the app's clock, and VoiceOver given native elements and a text alternative around a web view hidden from it. **Fretscribe for Mac, iPhone and iPad** (`no.kalli.fretscribe`) covers Fretscribe for Android's way through (Your instrument, What is this?, writing down the notes, Check the song, the tab with its marks, practice player and full-screen mode), and has its own Mac screen catalogue and CI job. Not yet there: writing a song down again from Check the song with another tuning, capo or octave, keeping a take without a tab in Your songs, being told when a tab is ready, and sharing a tab; a release has `fretscribe-macos-arm64.zip` and `fretscribe-ios-unsigned.ipa` under the shared tag. **A pairing link opened from outside** is the family's (`scribe:`), and both apps register it beside a scheme of their own (`brasscribe:`, `fretscribe:`): when the other app is installed, the app the system opened asks which app is to connect and hands the link over under the other's scheme. Brasscribe Play's own screens (Home, What is this?, the transcribing screen, Settings, problems) stay its own; sharing more of them is a choice per screen. The services name no product: the band's sound set is handed in by Brasscribe Play, and the prefix the engine puts before the computer's name is a wire constant. Some brass vocabulary is still in `services` (`ScoreKit`'s lineups and arranger bridge, `OnDeviceKit`'s band draft and its model folder): moving it into the product is the next increment. | 4, 5, 7 |
| 11 | **Versions per app.** Tags, changelogs, release workflows and release notes per product. The same pull requests change everything the tag reaches: the `release` environment's tag rule (the owner's to change), the release workflow's tag pattern and its look-up of the previous tag, `scripts/release.sh`, how the phone's updater reads a version from a tag, and every download link on the site and in the READMEs, which today point at "the latest release" and would then point at whichever app released last. | 8, 9, 10 |
| 12 | **Studio** gets a tab view. Studio stays one program. The score viewer already shows and plays a tab (tablature, or tablature under notation, as the file has it), a tab profile can be started from the run list, and a tab run links to the viewer. What remains is the run view for a tab run: the tab on the run's own page with its checks, the tab's own details (instrument, tuning, capo, how many notes were moved or left out), the playing instructions and the text tab among the downloads, Compare for two tab runs, and the talking score reading a tab by string and fret. | 7 |
| 13 | **Fretscribe's remaining features**, built once per feature across its clients: sharing and printing a tab, fixing a note, the tuning and capo sheet, the layers menu, count-in and metronome, the speed trainer, saved repeats, hiding the chrome, pedals, the screen reader reading beat by beat, the record preflight, left-handed views. | 8; then 9 and 10 as each client arrives |

Steps 1, 2, 4 and 5 run side by side. Step 3 touches what every client loads, so nothing else that touches a client's build lands while it is open.

## What is not shared

- Words. Each product has its own, complete, in every language it speaks.
- Navigation and the first run.
- The screens of a product's own idea (a music stand; a tab with a practice player).
- Brand: colours, type, icon, illustration.

## Open

- The Python packages do not yet separate targets. `music/src/scribe_music` holds the brass arranger and instruments (`arranger.py`, `instruments.py`, `difficulty.py`, `parts.py`) beside shared notation code, `engine/src/scribe_engine` holds `tab.py`, `bass_tab.py` and `tuning.py` beside the shared pipeline, and `eval/scribe_eval` has the brass and tab benchmarks side by side. The Rust side is already split (`core/targets/brass`, `core/targets/fretted`). Splitting the Python the same way is not done and not part of the folder moves.
- The desktop program's name. It serves every app; "Bandroom" without a product's name in front is the working choice.
- When the repository itself takes a neutral name.
