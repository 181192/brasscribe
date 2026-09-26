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
npm run e2e                               # starts `brasscribe studio --port 8799` via pixi and runs the e2e suite
STUDIO_URL=http://127.0.0.1:8799 npm run e2e   # against an engine that is already running
STUDIO_E2E_LIVE=1 npm run e2e             # also start a real pipeline run (runs models)
STUDIO_E2E_MUSESCORE=1 npm run e2e        # also run the MuseScore round trip from the UI (launches MuseScore once)
```

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

Uncertain notes are coloured and marked with a "?" above them. Below 0.4 the "?" is boxed. Every colour is repeated by a shape, a pattern or text. The keyboard shortcuts follow `qa/screen-reader-scripts/keyboard-desktop.md`; press F1 in Studio to see them.
