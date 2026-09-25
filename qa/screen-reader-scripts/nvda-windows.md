# NVDA on Windows: Play and Studio acceptance script

This is an acceptance script for apps that are not built yet. Step IDs, expected strings and pass/fail rules are in [README.md](README.md).

**Setup**
- NVDA (current stable), with the NVDA key set to Insert (and Caps Lock).
- Keys:
  - NVDA+Tab: report focus
  - NVDA+↑: say the current line / focus
  - NVDA+Space: browse/focus mode (web)
  - NVDA+F7: elements list (web)
  - Speech viewer (NVDA menu → Tools) on, so the output can be copied into the result record verbatim
- Play for Windows: the same steps as [narrator-windows.md](narrator-windows.md). Differences are listed below.
- Studio: Firefox and Chrome, current. `@axe-core/playwright` must pass first in CI.

## Play for Windows under NVDA

Run S1–S14 with the keys from the Narrator script. Specific NVDA checks:

| ID | Check | Pass if |
|---|---|---|
| S2, S5, S6, S9 | UIA notifications (`RaiseNotificationEvent`) are spoken by NVDA. NVDA supports UIA notification events. **Open question:** confirm on the current NVDA version, and whether `LiveSetting` changes are needed as well | each "must contain" string appears in the Speech viewer |
| S11 | Arrows inside the score reach the app. NVDA does not use arrows for native apps unless they're in object navigation. Also check that NVDA's own review cursor (NVDA+Numpad) does not break focus | vector strings appear verbatim |
| S11 | Single-key shortcuts (U, R, P, W) don't collide with NVDA commands (NVDA uses the NVDA key for its commands) | no NVDA command fires |
| S14 | Focus highlight (NVDA Vision) follows the focused note | highlight rectangle on the note |

## Studio in the browser under NVDA

Studio is a technical workbench, so the scope is smaller. The same WCAG targets apply.

| ID | Do | Expect | Pass if |
|---|---|---|---|
| W1 | Open `http://localhost:…`; browse mode: H through the headings; D for landmarks | `<title>` "Brasscribe Studio – Runs"; headings: Runs, Pipeline, Inspector, Benchmarks; landmarks: navigation, main | axe `page-has-heading-one`, `landmark-one-main` |
| W2 | Start a run: Tab to "Run pipeline", Enter; file input; profile select | "Profile, combo box, solo"; `role="status"` updates "Stage separation, running, 12 seconds" (throttled) | live region polite, not assertive |
| W3 | Stage graph: Tab into it (one tab stop, roving tabindex), arrows between stages | "Separation, stage, done, 41 seconds, cache hit" (the stage graph is a `role="list"` or `tree`, not only an SVG) | no keyboard trap; not an image-only graph |
| W4 | Piano roll/waveform: a text alternative plus a data table toggle | "Piano roll, image, 689 notes, 31 percent uncertain"; "Show as table" → `<table>` with `<th>` | table navigable with Ctrl+Alt+arrows |
| W5 | Score view (alphaTab): the talking-score panel beside it | same strings as the vectors; NVDA switches to focus mode automatically in the score widget (it's `role="application"`, or a listbox with `aria-activedescendant`); Esc/Tab leaves | browse-mode single-letter keys (H, B, K…) are **not** swallowed outside the score widget; inside it, our keys work |
| W6 | Compare runs, benchmark tables | sortable columns announce "sorted ascending" (`aria-sort`) | |
| W7 | Zoom 400% (Ctrl+plus); Windows contrast theme → `forced-colors` | no horizontal scroll except the score/table regions; system colours used | |

**Web checks**
- `aria-live` regions exist in the DOM before content is inserted.
- Buttons are `<button>`, not `<div>`.
- Every custom widget follows the ARIA APG pattern (listbox, slider, switch).
- Dialogs use `<dialog>` with `showModal()`.
