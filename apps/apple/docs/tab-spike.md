# Tab spike: alphaTab in a web view

**Decision: draw the tab with alphaTab in a `WKWebView`**, the same engraver as Fretscribe for Android, Play for
Windows and Studio (alphaTab 1.8.4 everywhere). The Apple build uses alphaTab's browser build: the same layout
code, so a tab is laid out alike on every client. The web view only draws. The app plays the recording, keeps the
clock and moves the cursor, and the screen around the page gives VoiceOver its elements.

The other two options were a native drawing of the core's tab data (a second engraver to keep in step with alphaTab)
and Verovio (which Play for Apple already carries, but which engraves tablature differently from every other
client). Neither was built.

## What was checked

`features/tab` (`TabKit`) holds the page (`Resources/page`: `index.html`, `tab.js`) and `TabPage`, which owns the
web view. `TabPageTests` checks each point below on macOS, off screen in `swift test`. On the iPhone simulator (CI runs
the package's tests there with `xcodebuild test`) a package's tests have no window scene, where a web view does not
draw and may not even start its page: there `TabPageEverywhereTests` checks what holds without it (the rule that keeps
the page off the network is in place before its first load, and the web view is hidden from VoiceOver), and
Fretscribe's app-hosted tests on the iPhone load and draw the page, offline, in both appearances, with its cursor.

| Question | Result |
|---|---|
| Offline | The page and its files come from the app bundle under a URL scheme of the app's own (`tabpage:`), served by a `WKURLSchemeHandler`. alphaTab runs without workers, so no `file:` or module loading is involved. A content rule, compiled and in place before the page is first loaded, blocks every `http`, `https`, `ws` and `wss` request, and the page still engraves: it loads `index.html`, `alphaTab.min.js`, `tab.js` and `Bravura.woff2`, and nothing else. The font is reported loaded. `scripts/fetch-alphatab.sh` puts alphaTab into the package from the npm release, checked against its SHA-256; it is not committed. |
| Playback cursor | The app says where the recording is as a bar and a tick (960 to a quarter, as Android's `TabClock`); the page puts its cursor on the beat that sounds there, using alphaTab's bounds lookup. alphaTab's own player is off. A call from Swift to the page and back takes 0.2 ms (median) and 0.4 ms (95th percentile) on an M-series Mac, well under a frame. |
| Dark mode | The colours are passed in from the design tokens. Another appearance is the same page engraved again: about 5 ms for a 15-bar bass line. In the dark take, no pixel is left in the light ink. |
| Notes in doubt | A note's fret number takes the doubt colour through alphaTab's note style, as on Android. |
| Where things are | The page answers with its height and every bar's box, so the screen can place native elements (the marks, the bars for VoiceOver) over it. |
| Screenshots | `takeSnapshot` of a web view in an off-screen window gives the drawn page, not a blank one, so the screen catalogue can take it. |
| VoiceOver | As the notation spike found for Verovio's SVG, a web view is one opaque group to the accessibility tree. The web view is hidden from VoiceOver. In its place `TabPageView` gives one element for each bar (`TabBarReading`: the bar's number and, beat by beat, the notes that start there by string and fret, in the product's words); the screen adds the controls around the page and its marks. |

First engraving of the 15-bar bass line: about 40 ms inside alphaTab, 150 ms from a new web view to the laid-out
page, in a Debug build.

## Limits

- alphaTab signs the page under its last line. The page hides that line (alphaTab is credited in About), as Android does.
- The web view is a second process. For a tab (one staff, a few dozen bars) that costs far less than the 300 MB the
  full band score cost in the notation spike; not measured on a device.
- Text sizes: alphaTab draws at the scale it is given. The screen passes its own scale, from the text size, as
  Android's `TabSize` does.
