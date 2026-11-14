# Third-party licences the apps ship

Every app carries the licence texts of what it ships: a file in its package, opened from About (Settings in the
desktop apps). The files are written from one list, so an app cannot name a library without its licence, or ship one
that the list does not know.

| | |
|---|---|
| `components.json` | Every component: its licence, the copyright lines that go with it, a note where one is needed (a modification, where the source is), and the apps that carry it. `sets` names groups of apps; `not_shipped` names the dependencies no app ships (tests and build tools). |
| `upstream/` | Notice files that a component's makers publish with it and that are too long to retype (ONNX Runtime's third-party notices), one per version. A component's `upstream` names the file and where the build pins the version; when the build moves to a new version, `check` asks for that version's file. |
| `windows-notices.targets` | Imported by the three Windows apps: copies the Windows App SDK's and the .NET runtime's own licence and notice files from their packages into `Licences\` beside the app's file, which names them. The release builds fail when one is missing. |
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
- The reader of sheet music from pictures (homr, AGPL-3.0) has no component of its own, because no app ships it:
  Bandroom fetches it on the user's computer, from PyPI and from homr's release on GitHub, only when the user asks
  for it in Settings, where its licence and its source are shown first. It must stay that way: a component for it
  here would mean an app carries it, and then that app would have to take the AGPL. Both builds stop if what they
  stage holds an adapter's environment or the homr package (`apps/bandroom/macos/scripts/check-no-reader-bundled.sh`:
  the Mac stager and both release builds call it; the Windows staging step has the same check of its own). Bandroom's file says where it
  comes from in pixi's note, and `THIRD_PARTY_NOTICES.md` has the whole of it.

[THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md) says the same in prose, with what is downloaded and what only
development uses.
