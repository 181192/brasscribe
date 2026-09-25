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

## Test

```sh
npm test                                  # vitest: MIDI, beats, note diff, SSE reducer, MusicXML, validation, DSP
npx playwright install chromium           # once
npm run e2e                               # starts `brasscribe studio --port 8799` via pixi and runs the e2e suite
STUDIO_URL=http://127.0.0.1:8799 npm run e2e   # against an engine that is already running
STUDIO_E2E_LIVE=1 npm run e2e             # also start a real pipeline run (runs models)
```

The e2e suite needs `data/` with at least one finished Mikkel run and `data/golden/mikkel-arranged-band/`. It checks the following:
- It loads the Mikkel run, renders the 18-part score and plays bar 9 from the keyboard.
- It sets a loop and changes the speed.
- It opens the golden MusicXML in the score viewer.
- It compares the run with the golden output note by note and runs the MuseScore round trip.
- It runs a benchmark suite from the UI.
- It runs axe-core on every view with the WCAG 2.2 AA tags and fails on any serious or critical violation.
- It checks that no view scrolls sideways at 360 px.

Screenshots go to `docs/screenshots/`.

## Layout

- `src/api/`: the only code that calls the engine. Types come from `openapi.json`. A route the engine lacks shows as "needs endpoint X" in the view that uses it.
- `src/lib/`: pure logic with unit tests:
  - MIDI and MusicXML readers
  - beat grids and irregular-tempo regions
  - the note-level diff (added, removed, moved, octave)
  - range and voice-crossing checks
  - FFT, spectrogram and energy
- `src/components/`: custom elements:
  - `bs-score`: alphaTab with transport, loop, speed, zoom, parts, mute and solo, and keyboard navigation
  - `bs-stage-graph`
  - `bs-audio-ab`
  - `bs-stems`
  - `bs-pianoroll`
  - `bs-beats`
- `src/views/`: runs, one run (stage graph and inspector), compare, benchmarks, conversion parity, core conformance, datasets and models, and the score viewer.

Colours come from `docs/accessibility/design-tokens.json`: light, dark and high contrast (`prefers-contrast: more`). Every colour is repeated by shape, pattern or text. The keyboard shortcuts follow `qa/screen-reader-scripts/keyboard-desktop.md`; press F1 in Studio to see them.
