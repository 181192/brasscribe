# Fretscribe plan

Fretscribe turns a recording into tablature, with standard notation alongside when wanted, for guitar,
bass, ukulele and mandolin. It shares its transcription engine with Brasscribe; the two are separate
products built from one codebase.

## Principles

- **One spine, two targets.** Everything up to the canonical score (`composition.json`: pitch, timing,
  confidence, what was heard) is shared. What a player does with it is target-specific: brass-band
  arranging for Brasscribe, string and fret choice for Fretscribe. The targets never depend on each
  other.
- **The shared core knows no instruments.** Instrument tables, arrangers, difficulty models and part
  metadata live in the targets. Enforced by crate boundaries and a dependency check in CI.
- **Extract on the second use.** Code moves into the shared core only when Fretscribe actually needs it.
- **Tests follow reach.** A core change runs both targets' benchmarks and goldens; a target change runs
  its own.
- **Rust first for new target code.** Fretscribe's fingering and technique logic is written once in Rust
  and called from the engine through the existing bindings; no second Python reference.
- **Separate products.** Own name, icon, store listings, site, wording and release tags
  (`brasscribe-vX.Y.Z`, `fretscribe-vX.Y.Z`); one app shell built as two flavours.

## Design

Fretscribe's design started outside this repository and now lives in it: the design in
[`design/fretscribe/`](../../../design/fretscribe/), the research and these plans in `docs/fretscribe/`.

1. Done: independent research, written without reading Brasscribe
   ([`research/01`–`04`](../research/): UX, accessibility, tab domain, brand directions).
2. Done: comparison with Brasscribe ([`differences.md`](../../../design/fretscribe/differences.md)).
3. Done: brand ([`brand/brand.md`](../../../design/fretscribe/brand/brand.md), mark, lockups, the
   Fretscribe Tab font), tokens ([`tokens/tokens.json`](../../../design/fretscribe/tokens/tokens.json),
   contrast report with 0 failures), design system as a list of differences from Brasscribe's
   ([`system.md`](../../../design/fretscribe/system.md)), user flows
   ([`flows.md`](../../../design/fretscribe/flows.md)).
4. Done: mockups of Check the song, Fix a note and Practice in phone landscape
   (`design/fretscribe/mockups/screens.src.html`; `build.py` beside it writes `screens.html`).
5. Next: Practice in portrait, Your instrument, the recording preflight, Norwegian copy, then tests with
   players (a blind guitarist, a low-vision player and a pedal-only player among them).
6. Next: both design systems published as design-system pages, regenerated when `design/` changes.
7. Owner actions: register `fretscribe.app` and `fretscribe.no` (and `brasscribe.app`/`.no`), create the
   `fretscribe` GitHub repo for the site. Check trademarks and app stores for the name first.

## Done

Shared tooling:

- The contrast check reads any product's token file.
- Tests keep instrument knowledge out of the shared core modules, in Rust and in the Python reference.
  The shared modules were already clean, so no code had to move.
- The design system page is generated from `design/`.

Bass tab, from a recording to a file:

- `core/target-fretted`: tunings as data for guitar, bass, ukulele and mandolin; string and fret
  assignment with a hand span in millimetres; styles, pins, alternatives and a playability check; tuning
  suggestion, playing techniques, chord shapes and staying in position. Bass lines stay low on the neck,
  and isolated high notes are set aside instead of dragging the hand up.
- Tab MusicXML from `target-fretted`: tab, tab and notation, or notation; capo folded into the staff
  tuning (what MuseScore keeps); doubt as "?" and a processing instruction; "!" over a rest for a note
  with no place. Every note names its source note, so an app can match a note it changed.
- The engine's `bass-tab` profile, through a `fret`/`tab` subcommand on the core command line: bass stem
  or bass alone → notes → shared beats and quantization → string and fret. The result is at
  `/v1/jobs/{id}/tab` with alternatives, tuning suggestions, octave shift, reference pitch, tempo, key
  and meter. Options: instrument, tuning, capo, style, recording, octave, layout.
- Export: `tab.musicxml`, `tab.pdf`, `tab.mid`, and as text `tab.txt` (the tab) and `tab-instructions.en.txt` and
  `tab-instructions.nb.txt` (playing instructions in words).
- The Docker image and a new worktree carry the core command line, so bass tabs work there.
- The `bass-tab` benchmark, 16 Slakh tracks: onset and pitch F1 0.86 (song) and 0.89 (bass alone); hand
  travel 0.9 and 0.6 frets per note; "?" marks right about 9 times in 10, catching about a third of the
  wrong notes. Synthesized low-register set: fine from E1 up, weak on the low B string (F1 about 0.73,
  5% octave errors).

The app:

- Fretscribe is built as a second Android app from Brasscribe's code (the `fretscribe` product flavour).
- It wears its own design: colours and title font generated from its tokens, its launcher icon, and no
  band SoundFont or brass models in its APK. Its screens and wording are still Brasscribe's.

Known gaps: real recordings unmeasured; tempo and meter right on about 70% of songs and 60% of lone
basses; the low B string; Bandroom does not bundle the core command line yet; dense bars are cramped on
the page. Open issues: #66–#70, #75–#77.

## Next

1. The Fretscribe app's own screens, in the order of [`android-app.md`](android-app.md): Your
   instrument, opening a recording and asking the paired computer for a bass tab, Check the song, the
   tab view and Practice, Fix a note, Share or print.
2. `target-fretted` through the core's bindings, so the phone can move a note to another string without
   asking the computer.
3. Bandroom bundles the core command line, so a paired phone can ask any computer for a bass tab.
4. Real recordings in the benchmark; tempo and meter on a lone bass; the low B string.
5. Guitar: single-note lines, then chords (GuitarSet for evaluation).

## At the first quiet moment: split the core

Needs a window with no open branches touching `core/`, `music/` or `engine/` pipeline code: merge or
rebase what is open, then freeze those areas for the duration. Each step is one PR with goldens
unchanged.

1. Move brass-specific modules (`instruments`, `arranger`, `difficulty`, brass part metadata) out of the
   shared core into `target-brass`; add the dependency check.
2. Split `musicxml` into a generic writer with a per-part hook (staff details, `<technical>` elements)
   plus brass part metadata; introduce `InstrumentSpec` (range, transposition, staff type, playback
   program).
3. Split `pipeline` into shared transcription, which produces the composition, and a `Target` that
   arranges it. The engine profile chooses the target.
4. Split the benchmark gates into shared transcription gates and per-target suites.
5. Make the design tooling product-neutral: the token roles `brass`, `brass-text` and `brass-tint`
   become `brand*` (Fretscribe's tokens already use `brand*`), and the generated theme gets neutral type
   names. Until then `design/tokens/build.py` writes Fretscribe's Android theme under Brasscribe's names,
   through the alias map in Fretscribe's tokens. The tokens build and the mockup renderer then serve
   both products on every platform.

## First Fretscribe: bass tab

1. Done: the `target-fretted` crate and the engine profile (above). Tab difficulty is not written yet.
2. Eval: GuitarSet (string-level ground truth), plus DadaGP tabs to check fingering against human
   choices.
3. The app on Android first (alphaTab renders tab and notation already), then Apple (Verovio's tab
   support needs checking) and Windows.
4. Site: source in this repository, built output pushed to the `fretscribe` repo's Pages, own domain.

## After that

- Single-note guitar lines and fingerpicking, tab and notation together.
- Techniques from the pitch curve: bends, slides, vibrato; then hammer-on and pull-off.
- Chords: chord detection and standard shapes as the fallback for strummed parts.
- Ukulele and mandolin tunings; banjo's short fifth string.
- Guitar and bass sound pack for playback.
- Rename this repository to a neutral name once both sites are on their own domains.

## Open decisions

- Final umbrella and crate names (working names: `scribe-core`, `target-brass`, `target-fretted`).
- Whether Bandroom keeps its name as the shared companion for both products.
- Apple rendering: the tab research points to alphaTab on every platform (MPL-2.0, tab and notation,
  Guitar Pro import and GP7 export). Verovio is LGPL, which is a concern inside an iOS app, and that
  applies to Brasscribe's Apple app as well before any App Store release.
- Guitar Pro export: players expect it; plan it for after the first version via alphaTab.
- Training and test data: DadaGP is research-only; use it for evaluation, never ship it.
