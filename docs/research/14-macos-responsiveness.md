# 14. macOS responsiveness audit (Brasscribe Play)

Owner feedback: the Mac app "doesn't resize as a user would expect, and some screens expand to full height".
This audit renders every macOS screen at the window sizes people actually use and compares the result
with the macOS Human Interface Guidelines and [design/system.md](../../design/system.md) §2.

## How it was measured

- **Harness:** `apps/apple/AppTests/LayoutHarness.swift` and `ResponsiveLayoutTests.swift`, in the macOS
  app unit-test target. Each screen is built the way `RootView` builds it on the Mac (the library in a
  `NavigationSplitView` sidebar, the screen in the detail column's `NavigationStack`), hosted in an
  `NSHostingView` inside a borderless window that is never ordered front, and drawn with
  `cacheDisplay(in:to:)`. Nothing appears on screen. When the macOS unit tests run, the test host now
  starts an app with no window and no Dock icon (`App/AppEntry.swift`). The layout tests use their own
  score library in the temporary folder, and don't browse the network for engines.
- **Fixture:** Old Hundredth (`apps/fixtures/old-hundredth`), with the band sounds staged, the connection
  staged as "Connected to Brasscribe on Studio Mac", and the lived-in library from the `home-full`
  screenshot scene.
- **Sizes:** each screen's own minimum, then 900×600, 1024×700, 1280×800, 1512×900 (the visible area of
  a MacBook), 1920×1080 and 2560×1400. These are window sizes. The unified toolbar (52 pt) isn't drawn
  by a borderless window, so the content is rendered at W × (H − 52).
- **Minimum:** the window's content minimum is what SwiftUI hands the window (`NSHostingView` with
  `.minSize`, then `NSWindow.contentMinSize`), measured for each screen. A window never goes below that
  minimum, so when a requested size is smaller, the render is taken at the size the window grows to.
  That's the behaviour the owner sees.
- **Sheets** open at their ideal size (`fittingSize`), clamped to their minimum and maximum. That's how
  a SwiftUI sheet sizes itself on macOS.
- **Regenerating:** `TEST_RUNNER_BRASSCRIBE_RESPONSIVE_SHOTS=1 xcodebuild … test -only-testing:BrasscribePlayTests_macOS/ResponsiveLayoutTests`
  writes the thumbnails and `measurements.json` to `apps/apple/docs/responsive/`. Without the variable,
  the test renders and measures but writes nothing.

### Limits of the harness

- On macOS 26 the sidebar and the inspector float in Liquid Glass, which only the window server draws.
  The harness draws their SwiftUI content onto a flat grey panel in the same place.
- Toolbar items aren't drawn: the window toolbar (Settings, Share or print, Check the notes, Finish
  later) and the `.cancellationAction` / `.confirmationAction` buttons a macOS sheet shows along its
  bottom edge (Change note's Cancel/Save, Read aloud's Done).
- System alerts and confirmation dialogs (Edit title, Delete, Stop making this score?, Finish checking
  later?) are `NSAlert`s. AppKit sizes them, so they aren't audited here.
- The pairing "waiting for the computer to allow this Mac" state lives in a view's private state and
  can't be reached from a test yet. The match code is rendered on its own, and the pairing ways appear
  in `settings-pairing`.
- Read aloud's row text is empty in the render (the part is chosen in `onAppear`). The layout is still
  representative.
- Accessibility frames aren't available off screen, so the phase-2 assertions will need geometry probes.
- A real window was compared with the harness using the committed `docs/screenshots/macos-score-light.png`.
  Both show the same inspector overflow and the same wrapping of the player bar.

## Expected behaviour

From the macOS HIG (Layout, Windows, Sheets, Split views) and design/system.md §2:

| Kind | Expected |
|---|---|
| Window minimum | One stable minimum for the whole window, big enough that no control clips: about 800 × 560 (sidebar 240 plus a 560 pt detail). It shouldn't change from screen to screen. |
| Forms, cards, empty states, problem screens | Hug their content, top-aligned in a reading column of at most 720 pt (Home 920). No stretching to the window height. |
| Actions of a page | Follow the content, trailing-aligned in the same column (system.md: "Bottom right of the content, after Cancel"). A bottom bar only when the content scrolls under it. |
| Score, lists, the stand | Fill the window. The score is full width. Side panels (the inspector) scroll and never set the window's height. |
| Sidebar | 240–340 pt. It collapses when the window is too narrow for sidebar plus detail, rather than squeezing the detail. |
| Sheets | Size to their content, with a sensible minimum (about 480 pt wide) and a maximum (about 680 pt wide and the screen height minus a margin). Longer content scrolls inside. A title and a way to close. |

## Findings

| # | Where | Finding | Expected |
|---|---|---|---|
| **F1** | Score (all parts, one part) | **The score asks for a window of at least 1291 × 855 (the part view 1291 × 935).** On macOS the inspector's `PartsPanel` isn't in a scroll view, so all 18 part rows plus the Sound section count toward the window's minimum height. The ~1051 pt of detail width comes from the inspector (320) plus the practice bar's minimum. Opening a score grows the window to that size, beyond a 1280 × 800 display and taller than a MacBook's visible area (900). **This is the "expands to full height" the owner reports.** Wherever the window is shorter, the inspector is cut off at the bottom (Sound section, My part). | The inspector scrolls. The score screen's minimum is set by the notation and the player bar only, well below the window minimum. |
| **F2** | Every screen | **The window has no real minimum height,** and a minimum width that changes: Home 583 × 68, What is this? 500 × 136, Transcribing 427 × 128, Choose output 588 × 128, Review 688 × 132, Problem 399 × 184, stand 151 × 124. At those sizes controls clip or wrap mid-word ("Can-cel", "Co…", "Keep, / go to / next"). | One window minimum (about 800 × 560), set once at the root, with nothing clipped at it. |
| **F3** | Moving between screens | The minimum changes on every screen (583 → 1291 → 151), so the window jumps in size when a score opens and never shrinks back. | A stable minimum. Content adapts to the window, not the other way round. |
| **F4** | What is this?, Choose output, Transcribing, Review, Problem screens | **Page actions are pinned to the window bottom** with `safeAreaInset(.bottom)`. On a 1080 or 1400 window they sit 600–1000 pt below the content. On Problem screens they're full-width buttons (max 480) in the window's bottom-right corner, not under the reading column. | Actions follow the content, trailing-aligned inside the reading column. A pinned bar only when the content is taller than the window. |
| **F5** | Home, wide | The way-in grid (`adaptive(minimum: 220)`) makes three columns for two cards, leaving an empty third. | Two equal columns (or the two cards fill the row). |
| **F6** | Sidebar | The sidebar never collapses. At 900 wide it keeps 288 of the 900 pt, and at the 583 minimum the detail is 295 pt. | Collapse the sidebar when the detail would get narrower than its minimum (about 560). The sidebar button brings it back. |
| **F7** | Settings sheet | The ideal size is **744 × 1023** (1194 when pairing), taller than a 900 window and the MacBook visible area. On the Mac it has **no title and no Done button** (the toolbar is iOS only), so Escape is the only way out. | About 560–640 wide. Height fits the content up to the screen minus a margin, then scrolls. Title "Settings" and a Done button. |
| **F8** | Share or print sheet | A fixed `frame(width: 620, height: 720)`: it doesn't shrink on a small screen and doesn't hug shorter content. | Width 560–680. Height to the content, with a maximum. The actions stay at the bottom. |
| **F9** | Change note sheet | `minHeight: 360` plus a `Spacer()`: the content is ~170 pt, and the lower half is empty. | Hug the content. |
| **F10** | First run sheet | `minHeight: 640`: a gap of ~300 pt between the three points and Get started. | Hug the content. The button follows the points. |
| **F11** | Record what's playing sheet | The form is ~190 pt in a 360 minimum, with blank space below. Record with the microphone is a fixed 420 × 360 with centred content (acceptable). | Hug the content. |
| **F12** | Read aloud sheet | A list in a 480 × 560 minimum sheet. It fills and scrolls (correct). | — |
| **F13** | Music stand | A 151 × 124 minimum. In landscape at ≥ 900 wide the stand goes two-up even with one page, so the page sits in the left half and the right half is empty. In the harness the page is also clipped on its left edge at 900–2560 (part names cut). **Confirm this in the macOS VM before fixing:** it may come from the harness's resize order. | Centre a single page. Two-up only when there are two pages. The stand minimum is the window minimum. |
| **F14** | Review | The note list is a fixed 280, and the detail capped at 720 and centred (correct). The list fills the height (correct). The actions are pinned at the bottom (F4). Keep wraps at the minimum (F2). | F2 and F4. |
| **F15** | Score inspector | "Only this" wraps onto two lines at the 320 inspector width (also visible in the real screenshot). | Keep it on one line (icon + label, or a slightly wider inspector minimum). |
| **F16** | What is this? | Cards in the same grid row have different heights. | Equal heights per row. |

What is already right: the score and the stand fill the window at every size, Home and the flow screens
cap their column (920 and 720) and top-align, and Review's list fills the height.

## Screens × sizes

"Asked for" is the window size requested. "Got" is the window the content allows (a window grows to
its minimum). Click a thumbnail for the larger image.

### Home, empty

Window content minimum reported by SwiftUI: **583 × 16** (a window of 583 × 68).

| Asked for | Got (window) | Render | Notes |
|---|---|---|---|
| min | 583 × 68 | [![home-empty min](../../apps/apple/docs/responsive/home-empty-min.jpg)](../../apps/apple/docs/responsive/home-empty-min.jpg) | The window shrinks to 583 × 68, leaving only the sidebar lockup (F2). |
| 900 × 600 | 900 × 600 | [![home-empty 900x600](../../apps/apple/docs/responsive/home-empty-900x600.jpg)](../../apps/apple/docs/responsive/home-empty-900x600.jpg) | The sidebar keeps 288 of the 900 pt; the content still fits. |
| 1024 × 700 | 1024 × 700 | [![home-empty 1024x700](../../apps/apple/docs/responsive/home-empty-1024x700.jpg)](../../apps/apple/docs/responsive/home-empty-1024x700.jpg) |  |
| 1280 × 800 | 1280 × 800 | [![home-empty 1280x800](../../apps/apple/docs/responsive/home-empty-1280x800.jpg)](../../apps/apple/docs/responsive/home-empty-1280x800.jpg) |  |
| 1512 × 900 | 1512 × 900 | [![home-empty 1512x900](../../apps/apple/docs/responsive/home-empty-1512x900.jpg)](../../apps/apple/docs/responsive/home-empty-1512x900.jpg) |  |
| 1920 × 1080 | 1920 × 1080 | [![home-empty 1920x1080](../../apps/apple/docs/responsive/home-empty-1920x1080.jpg)](../../apps/apple/docs/responsive/home-empty-1920x1080.jpg) |  |
| 2560 × 1400 | 2560 × 1400 | [![home-empty 2560x1400](../../apps/apple/docs/responsive/home-empty-2560x1400.jpg)](../../apps/apple/docs/responsive/home-empty-2560x1400.jpg) | 920 pt column, centred and top-aligned (correct). The way-in grid leaves an empty third column (F5). |

### Home, with scores

Window content minimum reported by SwiftUI: **583 × 16** (a window of 583 × 68).

| Asked for | Got (window) | Render | Notes |
|---|---|---|---|
| min | 583 × 68 | [![home-scores min](../../apps/apple/docs/responsive/home-scores-min.jpg)](../../apps/apple/docs/responsive/home-scores-min.jpg) | Same as empty: 583 × 68 (F2). |
| 900 × 600 | 900 × 600 | [![home-scores 900x600](../../apps/apple/docs/responsive/home-scores-900x600.jpg)](../../apps/apple/docs/responsive/home-scores-900x600.jpg) |  |
| 1024 × 700 | 1024 × 700 | [![home-scores 1024x700](../../apps/apple/docs/responsive/home-scores-1024x700.jpg)](../../apps/apple/docs/responsive/home-scores-1024x700.jpg) |  |
| 1280 × 800 | 1280 × 800 | [![home-scores 1280x800](../../apps/apple/docs/responsive/home-scores-1280x800.jpg)](../../apps/apple/docs/responsive/home-scores-1280x800.jpg) |  |
| 1512 × 900 | 1512 × 900 | [![home-scores 1512x900](../../apps/apple/docs/responsive/home-scores-1512x900.jpg)](../../apps/apple/docs/responsive/home-scores-1512x900.jpg) |  |
| 1920 × 1080 | 1920 × 1080 | [![home-scores 1920x1080](../../apps/apple/docs/responsive/home-scores-1920x1080.jpg)](../../apps/apple/docs/responsive/home-scores-1920x1080.jpg) |  |
| 2560 × 1400 | 2560 × 1400 | [![home-scores 2560x1400](../../apps/apple/docs/responsive/home-scores-2560x1400.jpg)](../../apps/apple/docs/responsive/home-scores-2560x1400.jpg) | Correct: the column is capped, the list hugs its rows, top-aligned. |

### Home, offline

Window content minimum reported by SwiftUI: **583 × 16** (a window of 583 × 68).

| Asked for | Got (window) | Render | Notes |
|---|---|---|---|
| min | 583 × 68 | [![home-offline min](../../apps/apple/docs/responsive/home-offline-min.jpg)](../../apps/apple/docs/responsive/home-offline-min.jpg) |  |
| 1280 × 800 | 1280 × 800 | [![home-offline 1280x800](../../apps/apple/docs/responsive/home-offline-1280x800.jpg)](../../apps/apple/docs/responsive/home-offline-1280x800.jpg) |  |

### Home, needs pairing

Window content minimum reported by SwiftUI: **583 × 16** (a window of 583 × 68).

| Asked for | Got (window) | Render | Notes |
|---|---|---|---|
| min | 583 × 68 | [![home-needs-pairing min](../../apps/apple/docs/responsive/home-needs-pairing-min.jpg)](../../apps/apple/docs/responsive/home-needs-pairing-min.jpg) |  |
| 1280 × 800 | 1280 × 800 | [![home-needs-pairing 1280x800](../../apps/apple/docs/responsive/home-needs-pairing-1280x800.jpg)](../../apps/apple/docs/responsive/home-needs-pairing-1280x800.jpg) |  |

### What is this?

Window content minimum reported by SwiftUI: **500 × 84** (a window of 500 × 136).

| Asked for | Got (window) | Render | Notes |
|---|---|---|---|
| min | 500 × 136 | [![source min](../../apps/apple/docs/responsive/source-min.jpg)](../../apps/apple/docs/responsive/source-min.jpg) | 500 × 136: "Can-cel" wraps and Continue truncates to "Co…" (F2). |
| 900 × 600 | 900 × 600 | [![source 900x600](../../apps/apple/docs/responsive/source-900x600.jpg)](../../apps/apple/docs/responsive/source-900x600.jpg) |  |
| 1024 × 700 | 1024 × 700 | [![source 1024x700](../../apps/apple/docs/responsive/source-1024x700.jpg)](../../apps/apple/docs/responsive/source-1024x700.jpg) |  |
| 1280 × 800 | 1280 × 800 | [![source 1280x800](../../apps/apple/docs/responsive/source-1280x800.jpg)](../../apps/apple/docs/responsive/source-1280x800.jpg) |  |
| 1512 × 900 | 1512 × 900 | [![source 1512x900](../../apps/apple/docs/responsive/source-1512x900.jpg)](../../apps/apple/docs/responsive/source-1512x900.jpg) |  |
| 1920 × 1080 | 1920 × 1080 | [![source 1920x1080](../../apps/apple/docs/responsive/source-1920x1080.jpg)](../../apps/apple/docs/responsive/source-1920x1080.jpg) | Cancel and Continue are pinned to the window bottom, about 600 pt below the cards (F4). |
| 2560 × 1400 | 2560 × 1400 | [![source 2560x1400](../../apps/apple/docs/responsive/source-2560x1400.jpg)](../../apps/apple/docs/responsive/source-2560x1400.jpg) | The actions sit about 1000 pt below the content (F4). Cards in the same row have different heights (F16). |

### Transcribing

Window content minimum reported by SwiftUI: **427 × 76** (a window of 427 × 128).

| Asked for | Got (window) | Render | Notes |
|---|---|---|---|
| min | 427 × 128 | [![transcribing min](../../apps/apple/docs/responsive/transcribing-min.jpg)](../../apps/apple/docs/responsive/transcribing-min.jpg) | 427 × 128 (F2). |
| 900 × 600 | 900 × 600 | [![transcribing 900x600](../../apps/apple/docs/responsive/transcribing-900x600.jpg)](../../apps/apple/docs/responsive/transcribing-900x600.jpg) |  |
| 1024 × 700 | 1024 × 700 | [![transcribing 1024x700](../../apps/apple/docs/responsive/transcribing-1024x700.jpg)](../../apps/apple/docs/responsive/transcribing-1024x700.jpg) |  |
| 1280 × 800 | 1280 × 800 | [![transcribing 1280x800](../../apps/apple/docs/responsive/transcribing-1280x800.jpg)](../../apps/apple/docs/responsive/transcribing-1280x800.jpg) |  |
| 1512 × 900 | 1512 × 900 | [![transcribing 1512x900](../../apps/apple/docs/responsive/transcribing-1512x900.jpg)](../../apps/apple/docs/responsive/transcribing-1512x900.jpg) |  |
| 1920 × 1080 | 1920 × 1080 | [![transcribing 1920x1080](../../apps/apple/docs/responsive/transcribing-1920x1080.jpg)](../../apps/apple/docs/responsive/transcribing-1920x1080.jpg) | Cancel is pinned bottom-right, far from the steps (F4). |
| 2560 × 1400 | 2560 × 1400 | [![transcribing 2560x1400](../../apps/apple/docs/responsive/transcribing-2560x1400.jpg)](../../apps/apple/docs/responsive/transcribing-2560x1400.jpg) |  |

### Choose output

Window content minimum reported by SwiftUI: **588 × 76** (a window of 588 × 128).

| Asked for | Got (window) | Render | Notes |
|---|---|---|---|
| min | 588 × 128 | [![output min](../../apps/apple/docs/responsive/output-min.jpg)](../../apps/apple/docs/responsive/output-min.jpg) | 588 × 128: only the action bar shows (F2). |
| 900 × 600 | 900 × 600 | [![output 900x600](../../apps/apple/docs/responsive/output-900x600.jpg)](../../apps/apple/docs/responsive/output-900x600.jpg) |  |
| 1024 × 700 | 1024 × 700 | [![output 1024x700](../../apps/apple/docs/responsive/output-1024x700.jpg)](../../apps/apple/docs/responsive/output-1024x700.jpg) |  |
| 1280 × 800 | 1280 × 800 | [![output 1280x800](../../apps/apple/docs/responsive/output-1280x800.jpg)](../../apps/apple/docs/responsive/output-1280x800.jpg) |  |
| 1512 × 900 | 1512 × 900 | [![output 1512x900](../../apps/apple/docs/responsive/output-1512x900.jpg)](../../apps/apple/docs/responsive/output-1512x900.jpg) |  |
| 1920 × 1080 | 1920 × 1080 | [![output 1920x1080](../../apps/apple/docs/responsive/output-1920x1080.jpg)](../../apps/apple/docs/responsive/output-1920x1080.jpg) |  |
| 2560 × 1400 | 2560 × 1400 | [![output 2560x1400](../../apps/apple/docs/responsive/output-2560x1400.jpg)](../../apps/apple/docs/responsive/output-2560x1400.jpg) | Back and Show the score are pinned about 1000 pt below the choices (F4). |

### Score, all parts

Window content minimum reported by SwiftUI: **1291 × 803** (a window of 1291 × 855).

| Asked for | Got (window) | Render | Notes |
|---|---|---|---|
| min | 1291 × 855 | [![score-all min](../../apps/apple/docs/responsive/score-all-min.jpg)](../../apps/apple/docs/responsive/score-all-min.jpg) | The minimum is 1291 × 855 (F1), so every smaller requested size grows to it. |
| 900 × 600 | 1291 × 855 | [![score-all 900x600](../../apps/apple/docs/responsive/score-all-900x600.jpg)](../../apps/apple/docs/responsive/score-all-900x600.jpg) | Asked for 900 × 600, got 1291 × 855. The inspector is cut off at the bottom (Sound section). |
| 1024 × 700 | 1291 × 855 | [![score-all 1024x700](../../apps/apple/docs/responsive/score-all-1024x700.jpg)](../../apps/apple/docs/responsive/score-all-1024x700.jpg) | Same: grows to 1291 × 855. |
| 1280 × 800 | 1291 × 855 | [![score-all 1280x800](../../apps/apple/docs/responsive/score-all-1280x800.jpg)](../../apps/apple/docs/responsive/score-all-1280x800.jpg) | Same: grows to 1291 × 855, wider and taller than a 1280 × 800 display. |
| 1512 × 900 | 1512 × 900 | [![score-all 1512x900](../../apps/apple/docs/responsive/score-all-1512x900.jpg)](../../apps/apple/docs/responsive/score-all-1512x900.jpg) |  |
| 1920 × 1080 | 1920 × 1080 | [![score-all 1920x1080](../../apps/apple/docs/responsive/score-all-1920x1080.jpg)](../../apps/apple/docs/responsive/score-all-1920x1080.jpg) | The score fills (correct) and the inspector fits. |
| 2560 × 1400 | 2560 × 1400 | [![score-all 2560x1400](../../apps/apple/docs/responsive/score-all-2560x1400.jpg)](../../apps/apple/docs/responsive/score-all-2560x1400.jpg) | The score fills (correct). |

### Score, one part

Window content minimum reported by SwiftUI: **1291 × 883** (a window of 1291 × 935).

| Asked for | Got (window) | Render | Notes |
|---|---|---|---|
| min | 1291 × 935 | [![score-part min](../../apps/apple/docs/responsive/score-part-min.jpg)](../../apps/apple/docs/responsive/score-part-min.jpg) | 1291 × 935 (F1). The part view needs even more height than all parts. |
| 900 × 600 | 1291 × 935 | [![score-part 900x600](../../apps/apple/docs/responsive/score-part-900x600.jpg)](../../apps/apple/docs/responsive/score-part-900x600.jpg) | Grows to 1291 × 935, which doesn't fit a 13" MacBook Air's visible area. |
| 1024 × 700 | 1291 × 935 | [![score-part 1024x700](../../apps/apple/docs/responsive/score-part-1024x700.jpg)](../../apps/apple/docs/responsive/score-part-1024x700.jpg) |  |
| 1280 × 800 | 1291 × 935 | [![score-part 1280x800](../../apps/apple/docs/responsive/score-part-1280x800.jpg)](../../apps/apple/docs/responsive/score-part-1280x800.jpg) |  |
| 1512 × 900 | 1512 × 935 | [![score-part 1512x900](../../apps/apple/docs/responsive/score-part-1512x900.jpg)](../../apps/apple/docs/responsive/score-part-1512x900.jpg) | Grows to 1512 × 935, taller than the MacBook visible area. |
| 1920 × 1080 | 1920 × 1080 | [![score-part 1920x1080](../../apps/apple/docs/responsive/score-part-1920x1080.jpg)](../../apps/apple/docs/responsive/score-part-1920x1080.jpg) |  |
| 2560 × 1400 | 2560 × 1400 | [![score-part 2560x1400](../../apps/apple/docs/responsive/score-part-2560x1400.jpg)](../../apps/apple/docs/responsive/score-part-2560x1400.jpg) |  |

### The music stand

Window content minimum reported by SwiftUI: **151 × 72** (a window of 151 × 124).

| Asked for | Got (window) | Render | Notes |
|---|---|---|---|
| min | 151 × 124 | [![stand min](../../apps/apple/docs/responsive/stand-min.jpg)](../../apps/apple/docs/responsive/stand-min.jpg) | 151 × 124: unusable, with the controls clipped (F2, F13). |
| 900 × 600 | 900 × 600 | [![stand 900x600](../../apps/apple/docs/responsive/stand-900x600.jpg)](../../apps/apple/docs/responsive/stand-900x600.jpg) |  |
| 1024 × 700 | 1024 × 700 | [![stand 1024x700](../../apps/apple/docs/responsive/stand-1024x700.jpg)](../../apps/apple/docs/responsive/stand-1024x700.jpg) |  |
| 1280 × 800 | 1280 × 800 | [![stand 1280x800](../../apps/apple/docs/responsive/stand-1280x800.jpg)](../../apps/apple/docs/responsive/stand-1280x800.jpg) | Two pages side by side with only one page: the right half is empty. The page is clipped at the left (F13, to check in the VM). |
| 1512 × 900 | 1512 × 900 | [![stand 1512x900](../../apps/apple/docs/responsive/stand-1512x900.jpg)](../../apps/apple/docs/responsive/stand-1512x900.jpg) |  |
| 1920 × 1080 | 1920 × 1080 | [![stand 1920x1080](../../apps/apple/docs/responsive/stand-1920x1080.jpg)](../../apps/apple/docs/responsive/stand-1920x1080.jpg) |  |
| 2560 × 1400 | 2560 × 1400 | [![stand 2560x1400](../../apps/apple/docs/responsive/stand-2560x1400.jpg)](../../apps/apple/docs/responsive/stand-2560x1400.jpg) | One short system in the left half; nothing scales up (F13). |

### Review (Check the notes)

Window content minimum reported by SwiftUI: **688 × 80** (a window of 688 × 132).

| Asked for | Got (window) | Render | Notes |
|---|---|---|---|
| min | 688 × 132 | [![review min](../../apps/apple/docs/responsive/review-min.jpg)](../../apps/apple/docs/responsive/review-min.jpg) | 688 × 132: Keep wraps onto three lines (F2). |
| 900 × 600 | 900 × 600 | [![review 900x600](../../apps/apple/docs/responsive/review-900x600.jpg)](../../apps/apple/docs/responsive/review-900x600.jpg) |  |
| 1024 × 700 | 1024 × 700 | [![review 1024x700](../../apps/apple/docs/responsive/review-1024x700.jpg)](../../apps/apple/docs/responsive/review-1024x700.jpg) |  |
| 1280 × 800 | 1280 × 800 | [![review 1280x800](../../apps/apple/docs/responsive/review-1280x800.jpg)](../../apps/apple/docs/responsive/review-1280x800.jpg) |  |
| 1512 × 900 | 1512 × 900 | [![review 1512x900](../../apps/apple/docs/responsive/review-1512x900.jpg)](../../apps/apple/docs/responsive/review-1512x900.jpg) |  |
| 1920 × 1080 | 1920 × 1080 | [![review 1920x1080](../../apps/apple/docs/responsive/review-1920x1080.jpg)](../../apps/apple/docs/responsive/review-1920x1080.jpg) | Skip and Keep are pinned bottom-right, far from the note (F4). The note list fills the height (correct). |
| 2560 × 1400 | 2560 × 1400 | [![review 2560x1400](../../apps/apple/docs/responsive/review-2560x1400.jpg)](../../apps/apple/docs/responsive/review-2560x1400.jpg) |  |

### Problem: nothing was heard

Window content minimum reported by SwiftUI: **399 × 132** (a window of 399 × 184).

| Asked for | Got (window) | Render | Notes |
|---|---|---|---|
| min | 399 × 184 | [![problem-silence min](../../apps/apple/docs/responsive/problem-silence-min.jpg)](../../apps/apple/docs/responsive/problem-silence-min.jpg) | 399 × 184 (F2). |
| 900 × 600 | 900 × 600 | [![problem-silence 900x600](../../apps/apple/docs/responsive/problem-silence-900x600.jpg)](../../apps/apple/docs/responsive/problem-silence-900x600.jpg) |  |
| 1024 × 700 | 1024 × 700 | [![problem-silence 1024x700](../../apps/apple/docs/responsive/problem-silence-1024x700.jpg)](../../apps/apple/docs/responsive/problem-silence-1024x700.jpg) |  |
| 1280 × 800 | 1280 × 800 | [![problem-silence 1280x800](../../apps/apple/docs/responsive/problem-silence-1280x800.jpg)](../../apps/apple/docs/responsive/problem-silence-1280x800.jpg) |  |
| 1512 × 900 | 1512 × 900 | [![problem-silence 1512x900](../../apps/apple/docs/responsive/problem-silence-1512x900.jpg)](../../apps/apple/docs/responsive/problem-silence-1512x900.jpg) |  |
| 1920 × 1080 | 1920 × 1080 | [![problem-silence 1920x1080](../../apps/apple/docs/responsive/problem-silence-1920x1080.jpg)](../../apps/apple/docs/responsive/problem-silence-1920x1080.jpg) | The actions are full-width buttons pinned to the window's bottom-right corner, not under the column (F4). |
| 2560 × 1400 | 2560 × 1400 | [![problem-silence 2560x1400](../../apps/apple/docs/responsive/problem-silence-2560x1400.jpg)](../../apps/apple/docs/responsive/problem-silence-2560x1400.jpg) | Same, about 1000 pt from the text (F4). |

### Problem: copy-protected

Window content minimum reported by SwiftUI: **399 × 132** (a window of 399 × 184).

| Asked for | Got (window) | Render | Notes |
|---|---|---|---|
| min | 399 × 184 | [![problem-copy-protected min](../../apps/apple/docs/responsive/problem-copy-protected-min.jpg)](../../apps/apple/docs/responsive/problem-copy-protected-min.jpg) |  |
| 1280 × 800 | 1280 × 800 | [![problem-copy-protected 1280x800](../../apps/apple/docs/responsive/problem-copy-protected-1280x800.jpg)](../../apps/apple/docs/responsive/problem-copy-protected-1280x800.jpg) |  |

### Problem: can't open the file

Window content minimum reported by SwiftUI: **391 × 132** (a window of 391 × 184).

| Asked for | Got (window) | Render | Notes |
|---|---|---|---|
| min | 391 × 184 | [![problem-cant-open min](../../apps/apple/docs/responsive/problem-cant-open-min.jpg)](../../apps/apple/docs/responsive/problem-cant-open-min.jpg) |  |
| 1280 × 800 | 1280 × 800 | [![problem-cant-open 1280x800](../../apps/apple/docs/responsive/problem-cant-open-1280x800.jpg)](../../apps/apple/docs/responsive/problem-cant-open-1280x800.jpg) |  |

## Sheets

A sheet opens at its ideal size, within its minimum and maximum (sizes in pt; ∞ = no limit). The
buttons a macOS sheet shows along its bottom edge aren't drawn (see Limits).

| Sheet | Min | Ideal (opens at) | Max | Render |
|---|---|---|---|---|
| settings | 480 × 520 | 744 × 1023 | ∞ × ∞ | [![settings](../../apps/apple/docs/responsive/sheet-settings.jpg)](../../apps/apple/docs/responsive/sheet-settings.jpg) |
| settings-pairing | 480 × 520 | 744 × 1194 | ∞ × ∞ | [![settings-pairing](../../apps/apple/docs/responsive/sheet-settings-pairing.jpg)](../../apps/apple/docs/responsive/sheet-settings-pairing.jpg) |
| export | 620 × 720 | 620 × 720 | 620 × 720 | [![export](../../apps/apple/docs/responsive/sheet-export.jpg)](../../apps/apple/docs/responsive/sheet-export.jpg) |
| talking-score | 480 × 560 | 480 × 560 | ∞ × ∞ | [![talking-score](../../apps/apple/docs/responsive/sheet-talking-score.jpg)](../../apps/apple/docs/responsive/sheet-talking-score.jpg) |
| change-note | 420 × 360 | 420 × 360 | ∞ × ∞ | [![change-note](../../apps/apple/docs/responsive/sheet-change-note.jpg)](../../apps/apple/docs/responsive/sheet-change-note.jpg) |
| first-run | 520 × 640 | 678 × 640 | ∞ × ∞ | [![first-run](../../apps/apple/docs/responsive/sheet-first-run.jpg)](../../apps/apple/docs/responsive/sheet-first-run.jpg) |
| record-mic | 420 × 360 | 420 × 360 | 420 × 360 | [![record-mic](../../apps/apple/docs/responsive/sheet-record-mic.jpg)](../../apps/apple/docs/responsive/sheet-record-mic.jpg) |
| record-capture | 480 × 360 | 531 × 360 | ∞ × ∞ | [![record-capture](../../apps/apple/docs/responsive/sheet-record-capture.jpg)](../../apps/apple/docs/responsive/sheet-record-capture.jpg) |
| match-code | 40 × 64 | 185 × 116 | ∞ × 116 | [![match-code](../../apps/apple/docs/responsive/sheet-match-code.jpg)](../../apps/apple/docs/responsive/sheet-match-code.jpg) |

## Next

Phase 2 fixes every finding above, adds an assertion to the harness for each one (for example, the
window minimum stays the same on every screen and nothing clips at it, the score's minimum height
doesn't depend on the number of parts, forms and sheets are no taller than their content plus padding
at 1080, and the reading column is capped at 2560), and retakes the thumbnails. Resize and zoom
XCUITests belong in the macOS VM, never on a Mac someone is using.
