# Brasscribe Studio

The browser workbench that the engine serves at `/` (`brasscribe studio`). It is written in plain TypeScript with web components and bundled with esbuild. Scores render and play with [alphaTab](https://alphatab.net) (MPL-2.0).

## Build

```sh
npm ci
npm run gen:api     # regenerate src/api/schema.d.ts from ../engine/openapi.json
npm run build       # writes ../engine/src/brasscribe_engine/static/ (committed; the engine serves it)
npm run typecheck
```

The bundle is committed, so the engine runs without Node. Rebuild and commit `static/` whenever `src/` changes.

## Run

Studio has no server of its own; the engine serves the built bundle.

```sh
cd .. && pixi run studio          # http://127.0.0.1:8765/, opens a browser
cd .. && pixi run serve --lan     # 0.0.0.0, prints a LAN URL and a pairing code
```

`npm run watch` rebuilds into the engine's `static/` on save; reload the page to pick it up.

## Test

```sh
npm test                                  # vitest: MIDI, beats, note diff, SSE reducer, MusicXML, validation, DSP
npx playwright install chromium           # once
npm run build                             # the browser tests and the catalogue run against the built bundle
npm run test:catalogue                    # the screen catalogue and its checks' own tests, no engine
scripts/screenshots.sh compare            # the catalogue at the merge base and here, and what changed
npm run test:browser                      # the built bundle as static files, no engine: opens a score in the viewer, appearance, the narrow menu
npm run e2e                               # starts `brasscribe studio --port 8799` via pixi and runs the e2e suite
STUDIO_URL=http://127.0.0.1:8799 npm run e2e   # against an engine that is already running
STUDIO_E2E_LIVE=1 npm run e2e             # also start a real pipeline run (runs models)
STUDIO_E2E_MUSESCORE=1 npm run e2e        # also run the MuseScore round trip from the UI (launches MuseScore once)
```

| Where | What | Needs |
| --- | --- | --- |
| `tests/` | unit tests (vitest, happy-dom) | nothing |
| `catalogue/` | the screen catalogue: every view in every variant, with its checks and a screenshot | the built bundle and Chromium |
| `browser/` | the viewer, appearance, Pink and the SoundFont on the built bundle | the built bundle and Chromium |
| `e2e/` | a live engine: runs, the pipeline, benchmarks, MuseScore, the Mikkel run | an engine and `data/` |

**The screen catalogue** (`catalogue/`, `npm run test:catalogue`) opens the built bundle as static files and answers the engine's API with `page.route` from `e2e/fixtures/api/responses.json`: responses an engine gave for the public-domain runs in `e2e/fixtures/compare`, a failed run, a short benchmark history and a conformance report written for it. A request the fixtures do not answer, a page error or a console error fails the view. Every view (`catalogue/views.ts`: the runs, a run's score and each of its tabs, a failed run, the viewer empty and with a score, Compare, Benchmarks, Parity, Conformance, Datasets and models, the shortcut sheet and the narrow menu) is opened in every variant: light, dark, high contrast light and dark (`prefers-contrast: more`), bokmål, 200 % zoom (720 × 500 CSS px), 320 px, and bokmål at 320 px; the narrow ones are reached the way a reader gets there, by narrowing the window after the view opened wide. Each runs these checks:
- axe-core with the WCAG 2.2 AA tags (every view and variant; serious and critical fail)
- no text cut off: by its own box or by a box around it that hides what overflows (an ellipsis too), on either axis; text a part that scrolls has out of view is not cut, but what it shows can still be cut by a box further out (every view and variant)
- the page does not scroll sideways (light, bokmål, 200 %, 320 px and bokmål at 320 px)
- text spacing (WCAG 1.4.12): with the user's spacing nothing is cut and the page still fits (light)
- the keyboard (light and 320 px, where the layout differs): Tab from the top of the page reaches everything that can be acted on (of a group of radio buttons or a tab list, the one chosen); focus never stops on something that cannot be seen or that is covered (WCAG 2.4.11); and it goes in the order of the page: the order of the document, no positive `tabindex`, and never back up the page within one column (what sits on a layer of its own, a header or a menu over the page, is left out of that last rule)

`catalogue/checks.spec.ts` shows each check failing on a view broken on purpose, and the screenshot comparison telling changed, new, gone and unchanged views apart. `catalogue/known.ts` lists the findings that are known, each for one view and variant and with its issue; it is the only place to let a finding through. An entry that matches nothing fails its view, so it goes when its issue is fixed.

**Screenshots** are not kept in git. `scripts/screenshots.sh compare` takes the catalogue's screenshots at the merge base with `origin/main` (only the screenshots there, not its checks) and then here with the checks, on the same machine, and writes `build/reports/screenshots/` (`index.html` with before, the difference and after for each changed view; `summary.md`). A pixel counts as changed when a channel moves by more than 2 (on an edge, where anti-aliasing of a fraction of a pixel lands, by more than 16), and a view with 4 or fewer such pixels (the noise measured is at most 2; a full stop is 9 or more, and the comparison's own test checks one is caught) is listed as within the noise floor, not as a change (anti-aliased edges that come out differently from run to run). Before a screenshot the page is scrolled to the top, transitions are let finish, the score's cursors (the bar and beat it is at) are left out of the pictures, since alphaTab may place them again at any moment, and a score does not scroll to its cursor: once any scroll has run out it is put back at its top and engraved once more. The catalogue's browser gives scrollbars no width (as on a Mac): on Linux a page scrollbar that comes and goes would change a score's width, and alphaTab would lay it out again, rounding its first bar differently depending on when. It exits 1 when a view changed, appeared or went away, 2 when the catalogue's own checks failed, and 3 when anything on the base's side failed (its worktree, npm packages, build or screenshots) or the comparison could not run (nothing was compared). CI does the same on every pull request that touches Studio: a changed view fails the Studio job, and its images are in the `studio-screenshots` artefact; when the change is meant, the label `screenshots-changed` on the pull request lets it through. Adding or removing the label starts CI again, and the job reads the labels as they are when it runs, only when views changed, in a step of its own, with a token that can only read. Earlier steps of the job ran the pull request's code, so that step starts bash and gh by their full paths with a clean environment; the label states that a change is meant, it is not a security boundary. The label never lets a failed check or a failed base through. `scripts/screenshots.sh record` only takes them, into `build/catalogue/screenshots/`.

The catalogue always plays without the band SoundFont, so a checkout that has it shows the same as CI. Dates come from the fixtures and the clock is fixed; the time a score took to draw is blanked before a screenshot.

**What stays in e2e** (an engine and `data/`): a real run and its stage graph over SSE, playing a bar, re-running from a manifest, a benchmark suite and the MuseScore round trip from the UI, the inspector tabs with a run's own audio, stems, piano roll and beats (the catalogue's runs have no stage files, so those tabs show their empty state), and the Mikkel score in every theme. The e2e suite's axe and reflow checks overlap the catalogue's; they stay for the views only a live engine fills.

The e2e suite needs `data/` with at least one finished Mikkel run and `data/golden/mikkel-arranged-band/`. By default it launches no MuseScore. It checks the following:
- It loads the Mikkel run, renders the 18-part score and plays bar 9 from the keyboard.
- It sets a loop and changes the speed.
- It opens the golden MusicXML (plain and `.mxl`) in the score viewer.
- It walks the talking score by bar, note, uncertain note, part and "where am I", in English and Norwegian.
- It compares the run with the golden output note by note, and shows both scores with the changed notes marked.
- It re-runs a run from its manifest, follows it over SSE, compares it with the original and deletes it again.
- It runs a benchmark suite from the UI.
- It runs axe-core on every view with the WCAG 2.2 AA tags, in light, dark and high-contrast themes and in Norwegian, and fails on any serious or critical violation.
- It checks that no view scrolls sideways at 360 px.

Screenshots go to `docs/screenshots/`.

### Rules

- **A new view** comes with an entry in `catalogue/views.ts` (which gives it the checks and the screenshots), and the fixtures it asks for in `e2e/fixtures/api/responses.json`: public-domain music only, no host names, absolute paths or machine details.
- **A found problem** that the change does not fix is an issue, and an entry in `catalogue/known.ts` only with that issue named, removed when it is fixed.
- **Reviewers** look at the `studio-screenshots` artefact and write a probe as a catalogue view or a check's test, not as a run against a live engine.

## Layout

- `src/api/`: the only code that calls the engine. Types come from `openapi.json`. A route the engine lacks shows as "needs endpoint X" in the view that uses it.
- `src/i18n.ts`: every UI string in English and Norwegian bokmål. The language follows the browser (nb, nn, no) until the header switch picks one.
- `src/lib/`: pure logic with unit tests:
  - MIDI and MusicXML readers
  - beat grids and irregular-tempo regions
  - the note-level diff (added, removed, moved, octave)
  - range and voice-crossing checks
  - FFT, spectrogram and energy
  - the talking score (`talking.ts`, checked against `docs/accessibility/talking-score-vectors.json`), built from MusicXML (`talkingxml.ts`) and navigated by note, beat, bar, part and uncertain note (`navigator.ts`)
  - the notation diff that marks changed notes in Compare (`xmldiff.ts`)
- `src/components/`: custom elements:
  - `bs-score`: alphaTab with transport, loop, speed, zoom, parts, mute and solo, and keyboard navigation
  - `bs-stage-graph`
  - `bs-audio-ab`
  - `bs-stems`
  - `bs-pianoroll`
  - `bs-beats`
- `src/views/`: runs, one run (stage graph and inspector), compare, benchmarks, conversion parity, core conformance, datasets and models, and the score viewer.

Styling is the Brasscribe design system (`design/system.md` §7, the workbench variant). `src/styles.css` imports `design/dist/web/brasscribe.css`, `fonts.css` and `studio-compat.css`, which esbuild bundles into `assets/studio-style.css`. Icons come from `design/dist/web/icons.js`, and the lockup from `design/brand/logo`. The favicons come from `design/dist/icons/web`. After a token change, run `uv run design/tokens/build.py`, then `npm run build`.

Light, dark, our high-contrast palette (`prefers-contrast: more`), forced colours and reduced motion all come from the tokens. The notation takes its ink and staff colours from them too.

Scores play with the band SoundFont when the engine serves one at `/assets/band/` (`BRASSCRIBE_BAND_SOUNDS_DIR`, set by Bandroom to its bundled phone pack), each part on its preset from `sounds/mapping.json`; otherwise with alphaTab's General MIDI sounds.

Uncertain notes are coloured and marked with a "?" above them. Below 0.4 the "?" is boxed. Every colour is repeated by a shape, a pattern or text. The keyboard shortcuts follow `qa/screen-reader-scripts/keyboard-desktop.md`; press F1 in Studio to see them.

## Test tiers

| Tier 1 (inner loop) | Tier 2 (before handoff) | Tier 3 (devices, UI) |
| --- | --- | --- |
| `scripts/check.sh fast studio` (vitest, the build, the catalogue and its checks) | `scripts/check.sh full studio` (adds the browser tests and `scripts/screenshots.sh compare`) | `npm run e2e` (starts an engine) |

See [docs/dev/verify.md](../docs/dev/verify.md).
