# Notation spike: Verovio SVG drawn natively vs WKWebView

**Decision: draw Verovio's SVG natively** with the small renderer in
`Packages/BrasscribeKit/Sources/SVGRender`, and expose the score to VoiceOver as one element per part per bar,
labelled with the talking-score text.

Both options use the same engraving: Verovio 6.3.0 (commit `425dd7b`, unmodified, built as a dynamic
framework by `scripts/build-verovio.sh`) renders the golden Mikkel score (`data/golden/mikkel-arranged-band/brass-band.musicxml`,
18 parts, 132 bars as re-saved on 2026-09-26) to SVG pages. The only difference is who draws the SVG.

## What was measured

Machine: M5 Pro, macOS 26, Xcode 27.0, Debug builds. Timings come from a single run, not a
benchmark series.

| | Native (CoreGraphics) | WKWebView |
|---|---|---|
| First page on screen | **812–955 ms** (Verovio load+layout, SVG, parse, draw at 2×) | **342–782 ms** (same SVG, load + first snapshot; Verovio load not included) |
| All 40 pages | 1.4–1.9 s more for SVG + parse; draw all at 2× 159–377 ms | 330–390 ms to paint (only the visible viewport is painted) |
| Memory | app footprint +116 MB Verovio after load, +179 MB for all 40 pages parsed (`phys_footprint`, package test) | **WebContent process: +300 MB** for the 40-page document (RSS of `com.apple.WebKit.WebContent`), on top of the app's Verovio memory |
| VoiceOver | **2,376 elements** (18 parts × 132 bars), each with the spoken bar ("Bar 3, Solo Cornet. beat 1: D 5, eighth note, uncertain …"), rotors for bars, parts and uncertain notes, actions Play/Loop/Listen to original | The SVG is one `AXGroup` with no children reachable from the host process; labels would have to be injected as ARIA from JavaScript and mapped back to bars |
| Cursor and highlights | Recolour by element id at draw time (sounding notes, uncertain notes), outline box for the current bar | CSS classes via `evaluateJavaScript`, one IPC per update |
| Dark mode / high contrast | Ink colour swapped at draw time | CSS |

Commands:

```sh
cd apps/apple/Packages/NotationKit && swift test          # measureNativeRendering prints "SPIKE native: …"
cd apps/apple && make project && xcodebuild -project BrasscribePlay.xcodeproj -scheme BrasscribePlay-macOS \
  -destination 'platform=macOS' test -only-testing:BrasscribePlayTests_macOS/NotationSpikeWebView   # "SPIKE webview: …"
cd apps/apple/Packages/BrasscribeKit && swift test --filter SVGRenderTests   # renderer parse/draw of one page
```

Raw lines (2026-09-26):

```
SPIKE native: verovio load+layout 1258 ms; pages 40; svg total 6722 kB; per page renderToSVG median 495 ms,
  parse median 784 ms; first page ready 2562 ms; all pages svg+parse 5734 ms; draw all @2x 211 ms (41336 ops);
  footprint base 39 MB, +verovio 116 MB, +all pages 179 MB                          (swift test, parallel suite)
SPIKE native: first page engraved+parsed+drawn 812 ms; remaining 39 pages 1507 ms;
  per-part-per-bar accessibility elements 2376                                        (app-hosted)
SPIKE webview: pages 40; first page loaded+painted 342 ms; all pages painted 330 ms;
  WebContent RSS before 4 MB after 304 MB; AX elements 1, labelled 0, roles ["AXGroup=1"]
svg-render parse 30 ms, draw@2x 4 ms, ops 696                                         (one 3-bar page, earlier golden)
```

The `swift test` numbers are slower because the suites there run in parallel. The app-hosted
numbers are the ones to compare.

## Why native

1. **VoiceOver is the deciding criterion (§5.5).** Natively, every bar of every part is a real
   accessibility element placed where it is drawn, with custom rotors and actions. In a web view the
   engraving is one opaque group unless we write and maintain an ARIA layer in JavaScript.
2. **Memory.** The web view adds a second process of about 300 MB for the full score. That matters on
   iPhone, where the app also holds 18 samplers.
3. **Speed is comparable.** The web view paints the first page 0.3–0.5 s sooner, because it only
   rasterises what is visible. The native path shows the first page after one page of work
   (pages arrive one by one), so the difference is small in use.
4. **Size.** The renderer is about 600 lines of Swift with no dependencies. WebKit is a system
   framework, so neither option adds size.

## Limits of the native renderer (open)

- It supports what Verovio 6.3 writes: nested `svg`/`viewBox`, `defs`+`use` glyphs, `path`
  (M L H V C S Q T Z; arcs become straight lines), `polygon`/`polyline`/`rect`/`ellipse`/`circle`/`line`, `text`/`tspan`
  with the embedded SMuFL text font, and `transform`, `fill`, `color` and `stroke-width`. Other SVG
  (gradients, masks, clip paths, CSS rules beyond `@font-face`) is ignored. A Verovio upgrade needs
  the `SVGRenderTests` page check re-run.
- Parsing a full-score page (~170 kB SVG) takes 0.5–0.8 s in Debug. Release and caching parsed pages would
  bring this down; not measured.
- VoiceOver behaviour was checked through XCUITest (element labels, identifiers, the Xcode
  accessibility audit), not by a person using VoiceOver. A scripted screen-reader run is still to do.
- The web view's accessibility tree was read from the host process. VoiceOver itself may see more
  through WebKit's remote tree. It would still be SVG without musical semantics.
- iOS memory was not measured on a device.
