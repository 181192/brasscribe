# Fretscribe on Android: implementation plan

The first Fretscribe app is an Android flavour of Brasscribe's app shell in `apps/android`. Paths are
from the repository root. alphaTab facts come from the 1.8.4 jar's class list; what the tab view uses has been run on an emulator.

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
Fix a note and the screen reader. "?" and boxed "!" are drawn by an overlay of Fretscribe's own
(`fret/TabView.kt`), placed in alphaTab's render wrapper as `score/NotationOverlay.kt` is. The fret numbers
are in Fretscribe Tab, registered with alphaSkia (`AlphaSkiaTypeface.register`). The recording plays through Media3's ExoPlayer (keeps pitch when slowed; a
dependency of the Fretscribe app only), and the app follows it in the tab itself: `Tab.beat_times` says
where the tab is at a second of the recording, and the cursor and the repeat are drawn over alphaTab's
layout as the marks are. alphaTab's own player (its external-media mode) stays off: a tab view is made
anew for every size and theme and the screen owns its scroll, and a player inside the view would start
over with each of them.

**What the app needs that isn't there yet.**

| Gap | Where |
|---|---|
| `target-fretted` through FFI (JSON in, JSON out), so re-fingering is instant and offline | `core/ffi`, regenerated bindings |
| Pins as job input | engine |
| "Around fret N" / "on these strings" | core, then device |
| Change one note's pitch | device: edit the notes, re-solve |
| Provenance and saved repeats | device, beside the saved song |
| `Profile.BASS_TAB`, `Tab` models, `getTab` | `engine-client` |
| Guitar instruments in the engine | engine, when guitar comes |
| Text tab and playing instructions in Share or print | device: the core writes both (`fretted_tab_text_json`, `fretted_playing_instructions_json`), and a job on the computer has them as `tab.txt`, `tab-instructions.en.txt` and `tab-instructions.nb.txt` |
| The core command line in Bandroom (the Docker image has it) | packaging (blocks the paired-computer flow with Bandroom) |
| The recording of a job the computer made from a file outside its own audio folders (`brasscribe run <file>`): `GET /v1/jobs/{id}/input` gives a paired phone only what is in its uploads, captures and datasets | engine |
| Fretscribe's own About text and credits (it shows Brasscribe's) | app |

## Roadmap

Each is one small pull request. Fretscribe strings always carry `values-nb`.

| | What | Conflict risk with Brasscribe work |
|---|---|---|
| a | Done: flavour skeleton; "Fretscribe" on the launcher and Home | medium, once (Gradle task names, workflows) |
| b | Done: design folder in the repo, generator flags, theme, icon; no SoundFont or brass models in the Fretscribe APK | low |
| c | Done: Your instrument (guitar, bass, ukulele, mandolin), and Fretscribe's own words on the first run, Home and Settings | none |
| d0 | `engine-client`: bass tab profile, `Tab` models, `getTab`, a fixture | low |
| d | Done: open a recording, send a `tab` job to the paired computer, transcribing | medium (small seam in `PlayViewModel`) |
| e | Done in a first form: Check the song from `/tab` (tuning, capo, octave, reference pitch, key and tempo, notes to check, notes left out); a change is a new job. Still to come: Other… tunings, and the capo that would fit (the computer does not suggest one) | none |
| f1 | Done: the tab view to read: alphaTab, "?" and "!" from the data, fret numbers in Fretscribe Tab. Still to come: the layers menu, Show ? for, the tuning and capo sheet | low |
| f2 | Done in a first form: Practice. The recording as the sound with a cursor that follows it, 5% speed steps with the pitch kept, repeat by bar, a 64 dp transport, and the recording fetched from the computer for a song opened without it. Still to come: count-in and metronome, Sound (Tab, Both), the speed trainer and 1% steps, saved repeats, hiding the controls while it plays, Lock the tab, and the line that scrolls past a fixed cursor | low |
| g0 | Core: FFI export (the note index is done) | medium (bindings) |
| g | Fix a note: fretboard strip, pitch stepper, pins, provenance, undo | low |
| h | Share or print | low |
| i | Pedals and keys, Lock the tab | low |
| j | Screen-reader model for the tab | none |

## Decisions for the owner

1. **Name and applicationId.** `no.fretscribe.play` is permanent once published. Trademark and store
   checks are open; the domains are unregistered.
2. **Release key.** Brasscribe's, or a separate upload key under Play App Signing (recommended)?
3. **Pairing link.** Decided: both apps keep the shared `brasscribe://pair` link for now (a phone with both
   apps asks which one opens it), and the program on the computer is Brasscribe Bandroom, Bandroom for short,
   in both apps.
4. **First-run copy.** The flows promise "Made on this phone. Nothing goes online", but the first
   version needs a computer for every tab. Reword, or wait for an on-device bass path.
   For now the app says what is true: "Your recordings stay on your phone and your own computer", and
   that Bandroom on the computer writes down the notes.
5. **Every instrument the computer writes tab for.** Your instrument offers the guitar (6, 7, 8 strings), the
   bass (4, 5, 6), the ukulele (soprano, concert or tenor with a high or a low G, and baritone) and the mandolin.
   A ukulele or a mandolin in a full song only works when no guitar plays in it, and What is this? says so.
6. **Launcher icon.** Drawn from the mark with the art at 64% (`design/fretscribe/brand/build.py`); the
   owner has not yet looked at it on a phone's launcher shapes.
7. **Min SDK** stays 29; portrait practice is an open design question.
8. **Tab font.** Settled for Android: alphaTab draws with alphaSkia there, and a face registered with
   alphaSkia is found by its family name, so the fret numbers are in Fretscribe Tab.

## Not decided here

iOS and desktop flavours; on-device transcription.
