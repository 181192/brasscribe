# Visual design tokens: colour, shape, contrast, motion, zoom

- **Source of truth:** [design-tokens.json](design-tokens.json).
- **Check:** `uv run qa/tools/contrast.py` exits 1 on any contrast failure and runs in CI.
- **Generated report:** [qa/reports/contrast-tokens.md](../../qa/reports/contrast-tokens.md). Every ratio below is copied from that report; don't edit numbers by hand.

## 1. Palette

| Token | Light | Dark | High contrast | Use |
|---|---|---|---|---|
| bg | `#FFFFFF` | `#121212` | `#000000` | Page, score paper |
| surface | `#F4F4F2` | `#1E1E1E` | `#000000` | Panels, player bar |
| text | `#1A1A1A` | `#EDEDED` | `#FFFFFF` | Body text |
| text-muted | `#595959` | `#B3B3B3` | `#FFFFFF` | Secondary text (still ≥ 4.5:1) |
| ink | `#000000` | `#F2F2F2` | `#FFFFFF` | Noteheads, stems, confident notes |
| staff | `#4D4D4D` | `#A6A6A6` | `#FFFFFF` | Staff lines, bar lines |
| uncertain | `#0063A6` | `#56B4E9` | `#00FFFF` | Notes with confidence 0.4–0.7 |
| very-uncertain | `#B04A00` | `#F0A04B` | `#FFFF00` | Notes with confidence < 0.4 |
| adlib-tint | `#EEF3F8` | `#1B2530` | none (`#000000`) | Background band behind free-time bars |
| loop-tint / loop-edge | `#FFF3D6` / `#8A5A00` | `#33290F` / `#E0B65C` | none / `#FFFF00` | Loop range band plus its edge markers |
| cursor | `#6B3FA0` | `#C9A7F0` | `#FF80FF` | Playback cursor line |
| focus | `#0050B3` | `#8AB4F8` | `#FFFF00` | Keyboard focus ring |
| error | `#B3261E` | `#F2B8B5` | `#FF8080` | Error text |

The uncertainty hues are the blue/orange pair from the Okabe-Ito palette, which is the pair that dichromats still tell apart. They are darkened in light theme to reach ≥ 3:1 on white. Unmodified Okabe-Ito orange `#E69F00` measures about 2.2:1 on white and would fail 1.4.11.

### Measured contrast (from the generated report)

| Pair | Light | Dark | High contrast | Min |
|---|---|---|---|---|
| text / bg | 17.40 | 16.00 | 21.00 | 4.5 |
| text-muted / surface | 6.36 | 7.95 | 21.00 | 4.5 |
| ink / adlib-tint | 18.81 | 13.86 | 21.00 | 3 |
| staff / bg | 8.45 | 7.70 | 21.00 | 3 |
| uncertain / bg | 6.30 | 8.12 | 16.75 | 3 |
| uncertain / loop-tint | 5.71 | 6.21 | 16.75 | 3 |
| very-uncertain / bg | 5.49 | 8.77 | 19.56 | 3 |
| very-uncertain / adlib-tint | 4.92 | 7.26 | 19.56 | 3 |
| cursor / bg | 7.38 | 9.16 | 9.78 | 3 |
| focus / surface | 6.81 | 7.91 | 19.56 | 3 |
| error / bg | 6.54 | 10.97 | 8.65 | 4.5 |

All 63 pairs pass (21 pairs × 3 themes).

### Colour-vision simulation (CIEDE2000, from the generated report)

The simulation uses the Machado et al. (2009) matrices at severity 1.0, plus a luminance-only view. Differences below 20 are marked weak.

| Pair (light) | Normal | Protan | Deutan | Tritan | Greyscale |
|---|---|---|---|---|---|
| ink / uncertain | 35.7 | 37.5 | 35.0 | 37.0 | 28.3 |
| ink / very-uncertain | 41.3 | 34.8 | 42.2 | 41.0 | 31.5 |
| uncertain / very-uncertain | 46.9 | 48.8 | 54.0 | 60.4 | **3.4** |
| cursor / uncertain | 23.4 | **7.0** | **1.7** | 33.9 | **3.7** |

What this means:
- Both uncertainty colours stand out from black ink for every simulated vision type.
- The two uncertainty levels **look the same in greyscale**, which matters for photocopied parts. So the level must also be encoded by shape (§2).
- The cursor and "uncertain" blue look alike to protan and deutan viewers. The cursor is therefore a full-height line with a band, never a coloured notehead (§2). Colour identity isn't needed.
- In dark and high-contrast themes some pairs are weak in greyscale; the report has the full table. The same shape rules cover them.

**Current engine output:** SwiftF0-only solo notes are red `#D0021B`. That colour passes contrast (5.67:1 on white) and differs from black under simulation (ΔE 28.6 protan, 30.7 greyscale). It still **fails 1.4.1**, because colour is its only signal: `musicxml_readability.py` reports 230 colour-only uncertain notes in the Mikkel golden output. When a part is printed in black and white, the uncertainty disappears.

## 2. Shape encoding (mandatory, all themes)

| State | Notehead | Extra mark | Talking score | MusicXML export |
|---|---|---|---|---|
| Confident (≥ 0.7) | normal | – | – | normal |
| Uncertain (0.4–0.7) | normal, colour `uncertain` | a small "?" above the note, outside the staff, like a fingering | "uncertain" | `color` + `<direction placement="above"><direction-type><words>?</words></direction-type></direction>` at the note's onset |
| Very uncertain (< 0.4) | normal, colour `very-uncertain` | a boxed "?" above the note | "very uncertain" | `color` + the same direction with `<words enclosure="rectangle">?</words>` |
| Checked by user | normal | – | – | normal |
| Free time (*ad lib*) | normal | `adlib-tint` band plus the text "ad lib." at the start, "a tempo" at the end, dashed bar lines | "Ad lib, free time…" | `<words>ad lib.</words>`, dashed `<bar-style>` |
| Loop range | – | tint band plus bracket-shaped edge markers at both ends, labelled "Loop 12–16" | "Loop set, bars 12 to 16" | – |
| Playback cursor | – | 3 px full-staff-height line (`cursor`) plus a 20% tint of the current bar | position in the status region | – |
| Focus (score) | – | 2 px `focus` outline plus a 2 px gap around the focused note or bar | the announcement | – |
| Active part | – | part name in bold plus a leading bar marker, not only highlight colour | "Part: Solo Cornet" | – |

Why "?" and not the obvious alternatives:
- **Rings or circles** near a note mean *open* (the "o" after a mute or stopped-horn sign) to brass players.
- **Parenthesised noteheads** mean *optional* or editorial, so a player might simply skip a "very uncertain" note.
- A "?" has no existing meaning in brass notation. It is the same mark on screen and in print, and it survives black-and-white photocopies.

**Open questions**
- Confirm with brass-band players that "?" and a boxed "?" read as "check this note" and not as anything else.
- MusicXML encoding, agreed with the MusicXML writer: colour on the note, plus a `?` words direction (boxed with `enclosure="rectangle"` below 0.4) at the note's onset in the same part. A `<words>` direction survives MuseScore and other editors, where `<other-technical>` is often dropped. `musicxml_readability.py` counts a coloured note as shape-encoded when such a direction sits at its onset. The MusicXML writer reports that the rectangle enclosure survives a MuseScore `mscore -o` re-export. That was tested on a test file; the Mikkel output has no note below 0.4 yet. Colour and "?" go on the attack only; tied continuations stay plain.

On Apple, `accessibilityDifferentiateWithoutColor` needs nothing extra, because the "?" marks are always on. When the setting is on, it may make the marks larger.

## 3. High-contrast theme

- **Follow the system** (EN 301 549 11.7):
  - Apple: `@Environment(\.colorSchemeContrast) == .increased`, plus "Increase Contrast" on macOS
  - Android: `UiModeManager.getContrast()` (API 34+) and high-contrast text
  - Windows: `AccessibilitySettings.HighContrast`, with contrast themes through `ThemeDictionaries["HighContrast"]` and `SystemColor*` resources
  - Studio: `@media (forced-colors: active)` and `(prefers-contrast: more)`
- In Windows contrast themes and CSS `forced-colors`, **use the system colours**, not our high-contrast token values:
  - CanvasText for ink
  - Highlight for focus and cursor
  - LinkText for the uncertain level (shape carries the level)
- The token values apply when the user picks our high-contrast theme in-app, or the platform has no system palette.
- Remove tints (ad lib, loop) and replace them with outlines. Staff lines use full ink colour.
- Keep shape encoding. Shapes carry meaning here, because system palettes collapse colour.

## 4. Reduced motion

Triggers:
- Apple: `accessibilityReduceMotion`
- Android: `Settings.Global.ANIMATOR_DURATION_SCALE == 0`, or "Remove animations"
- Windows: `UISettings.AnimationsEnabled == false`
- Studio: `@media (prefers-reduced-motion: reduce)`
- An in-app toggle, which defaults to the system setting

| Element | Default | Reduced motion |
|---|---|---|
| Playback cursor | moves continuously | jumps per beat, or per bar in "page mode" |
| Score follow | smooth scroll | page turn: the view switches when the cursor reaches the last system |
| Transcription progress | animated bar and spinner | static bar that updates in steps; the text "40 percent" stays |
| Beat indicator | pulsing dot | beat number "1 2 3 4" changes in place (no scaling or flashing) |
| Screen transitions | slide | cross-fade ≤ 150 ms or none |

Never, in any mode:
- flashing more than 3 times per second over a large area (2.3.1): at 136 bpm × 150% the beat is 3.4 Hz, so a flashing beat is not allowed
- parallax
- auto-playing video

## 5. Zoom to 400%

- **Notation zoom:**
  - 50–400% in steps of 10%, independent of UI text size.
  - Controls: pinch, **plus +/- buttons**, Ctrl/Cmd + =/-, and a numeric field (2.5.1, 2.5.7).
  - The zoom is remembered per part.
- **Reflow at high zoom:**
  - Above 200%, the score switches to **single-part, single-staff, horizontal scrolling**. The system breaks recompute so that scrolling goes in one direction only.
  - The full score at 400% needs two-dimensional scrolling. That is accepted as essential two-dimensional content (open question in the checklist, 1.4.10), and the single-part view is the reflow alternative.
- **The player bar at high zoom:**
  - It stays usable at 200% text size.
  - It collapses into one "Transport" button with a menu when there's no room.
  - It never covers the focused note (2.4.11).
- **System zoom:** macOS/iOS Zoom, Windows Magnifier, Android Magnification. Keep focus and caret tracking working: the focused note must report its screen rect.
  - A: `accessibilityFrame`
  - K: bounds in semantics
  - W: `BoundingRectangle` from the peer
  - Studio: a real DOM element or `getBoundingClientRect` on the focused note proxy
- **Studio:** browser zoom to 400% at 1280 px wide (= 320 CSS px). The UI reflows; the score canvas scrolls in one direction in single-part view.
- **Minimum sizes:**
  - Staff height is at least 6 mm on phone at 100%.
  - Touch targets are 44 pt (Apple), 48 dp (Android), and ≥ 24 CSS px (Studio).

## Open questions

1. The MusicXML encoding of uncertainty levels, and players' reading of the "?" marks (§2).
2. Whether ΔE 20 is the right "distinguishable" threshold at notehead size. It is a heuristic. A pilot with colour-blind players would settle it.
