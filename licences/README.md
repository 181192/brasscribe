# Third-party licences the apps ship

Every app carries the licence texts of what it ships: a file in its package, opened from About (Settings in the
desktop apps). The files are written from one list, so an app cannot name a library without its licence, or ship one
that the list does not know.

| | |
|---|---|
| `components.json` | Every component: its licence, the copyright lines that go with it, a note where one is needed (a modification, where the source is), and the apps that carry it. `sets` names groups of apps; `not_shipped` names the dependencies no app ships (tests and build tools). |
| `cargo.json` | The Rust crates of `core/Cargo.lock` with their licences, written by `scripts/licences.py sync-cargo`. |
| `texts/` | Each licence's text, once. |
| `dist/<app>.txt` | What each app ships, written by `scripts/licences.py build`. Committed; the builds take them from here. |

## Changing it

- A new library in an app: add it to the component it belongs to (`covers`), or add a component with its licence, its
  copyright lines and its apps. Then `scripts/licences.py build`.
- A change of `core/Cargo.lock`: `scripts/licences.py sync-cargo`, then `build`.
- A dependency only tests or the build use: `not_shipped`.

`scripts/licences.py check` fails when a file in `dist/` is not what the list gives, when a dependency of a build
(the Gradle version catalogue, the NuGet package versions, Studio's `package.json`, `core/Cargo.lock`) is in neither
list, or when a text is missing or unused. CI runs it on every change.

## What the check does not see

- Libraries that come in through another library on Android (Gradle resolves them at build time). They are listed by
  group in `components.json`; after a larger dependency update, compare with
  `./gradlew :products:brasscribe:dependencies --configuration releaseRuntimeClasspath` (and `:products:fretscribe`).
- Code copied into a library an app builds from source (what sfizz carries): listed by hand from its source tree.
- Microsoft's own third-party notices for ONNX Runtime and the Windows App SDK, which are several hundred kilobytes
  each: the files name where they are instead of repeating them.
- What Bandroom installs on the user's computer with pixi (Python and its packages) is not shipped in the app; the
  packages bring their licence files with them.

[THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md) says the same in prose, with what is downloaded and what only
development uses.
