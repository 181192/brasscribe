# Fretscribe on Android: implementation plan

The first Fretscribe app is an Android flavour of Brasscribe's app shell in `apps/android`. Paths are
from the repository root. alphaTab facts come from the 1.8.4 jar's class list and are not yet run on a device.

## Architecture

**Flavour.** One dimension, `product`, in `apps/android/app/build.gradle.kts`:
- `brasscribe` is the default and overrides nothing: its applicationId, versionCode and signing stay.
- `fretscribe` sets `applicationId = "no.fretscribe.play"` and its own version.
- `namespace` stays `no.brasscribe.play`, so `R`, packages and imports are untouched. Library modules get
  no flavours.

**Shared and per flavour.**

| Shared (`src/main`) | Per flavour (`src/brasscribe`, `src/fretscribe`) |
|---|---|
| Pairing, connection, capture, import, transcribing, problem, settings shell, `ScoreController`, `engine-client`, `audio`, `pitch` | `Product.kt`: name, pair scheme, root composable, engine profiles |
| `PlayViewModel` (pairing, upload, progress) | Fretscribe screens and `FretViewModel` under `src/fretscribe/kotlin/no/brasscribe/play/fret/` |
| `res/values/strings.xml` | Overrides for `app_name` and the lines that say "Brasscribe", in `values` and `values-nb`; new `fs_*` strings |
| | `themes.xml` window colours, launcher icon, display font, generated design |

Brasscribe's files stay in `src/main`; nothing moves. `MainActivity` calls `Product.Root(vm)`.

**Tokens and theme.** The app uses the generated theme API in 17 files, so Fretscribe's Android output
keeps the same Kotlin type and field names, generated from its own tokens into its own dist. Missing
roles are aliased (`brass*` from `brand*`, `staff` from `string`, `veryUncertain` from `uncertain`,
`adlibTint` from `loop-tint`, pink from standard). The neutral rename waits for the quiet moment.
`design/tokens/build.py` takes `--tokens`, `--out` and `--only`; its defaults are Brasscribe's. The design
is in `design/fretscribe/`, the research and the plan in `docs/fretscribe/`.

**Tab rendering.** alphaTab from `tab.musicxml`; the `/tab` JSON is the data model for Check the song,
Fix a note and the screen reader. "?" and boxed "!" are drawn with the existing
`score/NotationOverlay.kt`. The recording plays through alphaTab's external-media mode driving Media3
(keeps pitch when slowed; a new dependency), synced from `Tab.beat_times`.

**What the app needs that isn't there yet.**

| Gap | Where |
|---|---|
| `target-fretted` through FFI (JSON in, JSON out), so re-fingering is instant and offline | `core/brasscribe-ffi`, regenerated bindings |
| Pins as job input | engine |
| "Around fret N" / "on these strings" | core, then device |
| Change one note's pitch | device: edit the notes, re-solve |
| Provenance and saved repeats | device, beside the saved song |
| `Profile.BASS_TAB`, `Tab` models, `getTab` | `engine-client` |
| Guitar instruments in the engine | engine, when guitar comes |
| Text tab and playing instructions exports | core, later |
| The core command line in Bandroom (the Docker image has it) | packaging (blocks the paired-computer flow with Bandroom) |
| The recording on the phone for songs opened from the job list | `GET /v1/jobs/{id}/input` |

## Roadmap

Each is one small pull request. Fretscribe strings always carry `values-nb`.

| | What | Conflict risk with Brasscribe work |
|---|---|---|
| a | Done: flavour skeleton; "Fretscribe" on the launcher and Home | medium, once (Gradle task names, workflows) |
| b | Done: design folder in the repo, generator flags, theme, icon; no SoundFont or brass models in the Fretscribe APK | low |
| c | Done: Your instrument (bass only), and Fretscribe's own words on the first run, Home and Settings | none |
| d0 | `engine-client`: bass tab profile, `Tab` models, `getTab`, a fixture | low |
| d | Done: open a recording, send a `bass-tab` job to the paired computer, transcribing | medium (small seam in `PlayViewModel`) |
| e | Done in a first form: Check the song from `/tab` (tuning, octave, reference pitch, key and tempo, notes to check); a change is a new job. Still to come: capo, Other… tunings, changes for a song opened from Your songs | none |
| f1 | Tab view: alphaTab, "?" and "!" overlay, font test | low |
| f2 | Practice: the recording as the sound, 5% speed steps, repeat by bar, 64 dp transport | low |
| g0 | Core: FFI export (the note index is done) | medium (bindings) |
| g | Fix a note: fretboard strip, pitch stepper, pins, provenance, undo | low |
| h | Share or print | low |
| i | Pedals and keys, Lock the tab | low |
| j | Screen-reader model for the tab | none |

## Decisions for the owner

1. **Name and applicationId.** `no.fretscribe.play` is permanent once published. Trademark and store
   checks are open; the domains are unregistered.
2. **Release key.** Brasscribe's, or a separate upload key under Play App Signing (recommended)?
3. **Pairing link.** Both apps claiming `brasscribe://pair` gives a chooser when both are installed:
   shared scheme, or a second `fretscribe://` link in Bandroom's QR code? Does Bandroom keep its name?
4. **First-run copy.** The flows promise "Made on this phone. Nothing goes online", but the first
   version needs a computer for every tab. Reword, or wait for an on-device bass path.
   For now the app says what is true: "Your recordings stay on your phone and your own computer", and
   that Fretscribe on the computer writes down the notes.
5. **Bass only first?** The engine accepts only `bass-4/5/6`. Your instrument offers the bass, and lists
   guitar, ukulele and mandolin as "Later".
6. **Launcher icon.** Drawn from the mark with the art at 64% (`design/fretscribe/brand/build.py`); the
   owner has not yet looked at it on a phone's launcher shapes.
7. **Min SDK** stays 29; portrait practice is an open design question.
8. **Tab font.** alphaTab on Android resolves fonts by system family name; if the test fails, the first
   version ships without Fretscribe Tab numerals.

## Not decided here

iOS and desktop flavours; guitar; on-device bass transcription.
