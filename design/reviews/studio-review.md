# Studio review: accessibility, clarity and clutter

**What I measured**
- **Live app:** Studio (engine 0.1.0) running on port 8810, driven with Playwright at 1440 × 1000, 320 × 800 and 200 % root font. All 11 views were covered: Runs, Run (Score / Piano roll / Beats / Manifest tabs), Score viewer, Compare, Benchmarks, Conversion parity, Core conformance, and Datasets and models.
- **Automated checks:** axe-core with the WCAG 2.2 AA tags. For each view, my script measured the font size of every visible text node (in characters), the size of every interactive element, reflow at 320 px, and the 1.4.12 text-spacing override.
- **Contrast:** calculated from the tokens in `design/dist/web/brasscribe.css`.
- **Screenshots:** the checked-in ones in `studio/docs/screenshots/themes/` (light, dark, contrast, nb).

**Priority rule**
- **P1:** a contributor can't read the page comfortably, gets lost, or misses the thing the page is for.
- **P2:** they hesitate, but manage.
- **P3:** polish.

---

## 1. WCAG 2.2 AA and Norwegian UU: measured results

| Criterion | Result | Evidence |
|---|---|---|
| **1.4.3 Contrast (text)** | **Pass** | Light: `text-muted` #5E5A52 is 6.1–6.9:1 on bg, surface and raised; warning #8A5A00 is 4.9–5.9:1. Dark: muted #B4B0A7 is 7.2–8.6:1. axe found 0 contrast failures in all 11 views. |
| **1.4.4 Resize text** | **Pass** | Sizes are in rem. At a 200 % root font nothing is clipped and there's no horizontal scroll. Only the SVG wordmark stays at a fixed size. |
| **1.4.10 Reflow** | **Pass, but poor** | At 320 px only the tables and the graph scroll sideways. But the header (7 tabs, the engine status and the language picker) wraps into about 300 px, so no page content appears on the first screen. |
| **1.4.11 Non-text contrast** | **Fail (borderline)** | Stage cards use `--bc-border` #E4E1DA for their outline, and dashed vs solid is how the graph shows "from cache" vs "ran". That outline is 1.2:1 in light (#34322D is 1.35:1 in dark). The text "cache hit" carries the same state, so no information is lost, but the component boundary and its state are not perceivable. |
| **1.4.12 Text spacing** | **Pass** | With the 1.4.12 override, only visually hidden helpers overflow. |
| **2.5.8 Target size (minimum)** | **Pass**, mostly through the spacing exception | Undersized targets pass only because of the space around them: the run-list title links (16 px tall), "All runs" (19 px), the radio inputs (18 px wide, but their labels are clickable) and the language `<select>` (28 px). The footer links are inline text, which is exempt. |
| **axe (A/AA/2.1/2.2)** | **0 violations** in all 11 views | |
| **Text size (UU, readability)** | **The real problem** | See the table below. |

**What share of the text is small (by character count)**

| View | < 14 px | < 16 px | Main size |
|---|---|---|---|
| Runs | 96 % | 100 % | 13 px |
| Run | 76 % | 95 % | 13 px, meta at 12 px |
| Manifest | 99 % | 100 % | 12 px |
| Benchmarks | 97 % | 100 % | 13 px |
| Parity | 99 % | 100 % | 13 px |
| Conformance | 99 % | 100 % | 13 px |
| Registry | 92 % | 99 % | 13 px |

- **Why it is small:** the body token is 14 px (`--bc-type-studio-body-size: 0.875rem`). But `styles.css` sets `0.8125rem` (13 px) on tables, `.small`, `.hint`, legends, `dl.kv`, the status bar, the engine status and the language picker. `.stage-node .meta`, `pre.json` and `kbd` are `0.75rem` (12 px).
- **The standard:** WCAG sets no minimum font size, so this passes the law. Uutilsynet's guidance and Digdir's Designsystemet use 16 px as the body default. With 12–13 px, a contributor at 100 % zoom on a laptop is reading footnote-sized text all day.

---

## 2. Findings

### P1

| # | View | Problem | Fix |
|---|---|---|---|
| **P1-1** | All | Almost all text is 12–13 px, and controls are 32 px tall. | **Set the Studio type scale to: body 16 px, tables and meta 14 px, mono 14 px, and nothing under 14 px.** Set `--bc-type-studio-body-size` to 1rem. Replace every `0.8125rem` in `styles.css` with `0.875rem`, and every `0.75rem` with `0.875rem`. Controls are 36 px (40 px for the primary). Table rows get at least 36 px with `padding-block: 8px`. Keep the density with tighter spacing and fewer columns (P1-3…6), not with small type. Update `system.md` §7 ("Body 14 px" becomes 16 px, and "Control height 32" becomes 36). |
| **P1-2** | Runs, "Start a run" | There's no hierarchy, and the form reads as a config file. Problems:<br>• Both source fields show at once: the file picker and the "smoke-global" dataset select, though Audio file is selected.<br>• The profile help is a 4-line dump of the stage chain in mono names.<br>• "Allow heavy models on cache misses" is jargon, and it's on by default.<br>• "Start run" is a small button lost at the left edge. | Show only the field for the chosen source. Give the profile one plain sentence ("Soloist with band: the solo part plus a brass-band accompaniment"), and put the stage chain in a **Stages** disclosure. Relabel the checkboxes **Make an MP3 of the score** and **Use the large models if nothing is cached (slower, needs the GPU)**. Make **Start run** the one primary, 40 px, at the end of the form. |
| **P1-3** | Runs, "All runs" | Five runs have the same title, "20260815_155324", so they can't be told apart. The failed ones look the same as the successful ones apart from a small pill. There are 41 rows with no filter by status. | Title = the given title, or the input file name plus the time ("mikkel.wav · 26 Sep 19:02"). Never use a bare timestamp id; the id moves to a muted second line. Add **Status** filter chips (All / Failed / Running) and a count. Make the whole row the link, at least 36 px tall. |
| **P1-4** | Run page | The page is 3042 px tall, with 120 controls and about 14,600 words. The top of the page is the 12-card mono stage graph. The score, which is what the page is for, starts at about 900 px. Then 21 validator rows are expanded below it. There's no single next step. | New order:<br>1. **Header:** title, status, one sentence ("12 stages · 10 from cache · 16.5 s"), and one primary (**Open score**, or **Re-run** if the run failed).<br>2. **Score and inspector.**<br>3. **Checks:** summary lines ("20 crossings: Bass Trombone above 2nd Trombone, bars 47–126 · Show all"), with the table collapsed.<br>4. **Stages:** a disclosure, closed by default when the run succeeded and open when it failed, with the failing stage highlighted. |
| **P1-5** | Run header | There are six same-weight buttons: MusicXML, PDF, MIDI, Compare…, Re-run and Delete run. Delete sits in the same row as the everyday actions. | One **Download ▾** menu (MusicXML, PDF, MIDI), then **Compare…** and **Re-run**. Move Delete into a **More ▾** menu with an in-page confirmation ("Delete this run and its files? This can't be undone."). |
| **P1-6** | Navigation | There are 7 equal top-level tabs. Three of them are for maintainers only (Conversion parity, Core conformance, Datasets and models). A new contributor doesn't know where to start or what each page is for. | Group the nav into **Work** (Runs, Score viewer, Compare) and **Quality ▾** (Benchmarks, Conversion parity, Core conformance, Datasets and models). Every page gets a one-line "Use this to…" under its `<h1>`. When there are no runs, the Runs page shows **Try the demo (Mikkel)** as the primary. |

### P2

| # | View | Problem | Fix |
|---|---|---|---|
| P2-1 | Run, stage graph | 1.4.11: the node outlines are 1.2:1, and dashed vs solid is hard to see. The names are mono identifiers (`transcribe.orchestra.muscriptor`). | Outline in `--bc-border-strong` (3.3:1). Add a small **cached** tag as text. Show a plain label ("Orchestra notes") with the identifier underneath in muted mono. |
| P2-2 | Benchmarks | 17 suites × 5 columns. "CPU (cached model outputs)" is repeated on every row. Two bulk buttons have the same weight. The latest result sits in a separate section further down. | Put the latest pass/fail and the date **in each suite row**, and drop the "Runs on" column (group the rows under **CPU** / **GPU** headings instead). Move "Needs" into the row's disclosure. **Run all CPU suites** is the primary; "Run all suites" is secondary, with "(needs the GPU, about N min)". |
| P2-3 | Conversion parity | Seven models with about 20 rows each, all "pass" (2,718 words). | One summary line per model ("basic-pitch: 21 of 21 variants pass · threshold F1 0.98"), collapsed. Expand to see the table. Show failures first, and open them by default. |
| P2-4 | Core conformance | All 356 passing cases are listed. | Show the "356 of 356 identical" summary and the per-set table, then only failing cases, with **Show all 356 cases** as a disclosure. Keep the in-page error from review 2 (P2-12) for when the fetch fails. |
| P2-5 | Datasets and models | Absolute paths are shown, including another agent's worktree (`/Users/k/private/brasscribe/.claude/worktrees/agent-ae0a…/data/eval/…`). Fingerprints and SHA-256 hashes sit in the main table. The licence column says "not stated" in plain text. | Show paths relative to the repo (`data/eval/urmp-brass`). Fix the registry so it resolves against the main checkout. Put the SHA and fingerprint in a row disclosure or a copy button. Show "not stated" as a warning chip with a tooltip ("Check the licence before sharing outputs"). |
| P2-6 | Score viewer, empty | Before a file is loaded, the whole disabled toolbar and a blank 200 px box are shown, and the "Show" select is empty. | Use an empty state: a drop zone plus the primary **Open a MusicXML file**, and "Or open a run's score from Runs". Show the toolbar only once a score is loaded. |
| P2-7 | Score toolbar (Run and Viewer) | 14 controls sit in one row that wraps unevenly ("Show" drops onto its own line). Play and Stop, the bar field + Go, and "Repeat bars" + Repeat are separate actions with no grouping. | Three groups: transport (Play/Pause, bar field, previous/next), practice (Speed, Repeat bars … to …, Repeat on/off) and view (Zoom, Show part). Drop **Stop** (Pause plus the bar field covers it) and **Go** (commit the bar on Enter or blur). |
| P2-8 | Header at narrow widths | 1.4.10 passes, but at 320 px the header is about 300 px tall. | Below 600 px, show the nav as a **Menu** button, and put the engine status and the language picker inside it. |
| P2-9 | Jargon without an explanation | Unexplained terms: profile ids, "cache hit", "heavy models", "mutex", layers/stems, "F1 / P / R", "golden", "Composition", "tick 10200". A validator message reads "phrase at tick 10200 needed per-note octave fitting". | Studio may use technical terms, but explain each once: add a **What's this?** tooltip on column headers and legends, plus a short glossary page linked from the footer. Validator messages use bar and beat, never ticks ("E♭ Bass, bar 107 beat 2: moved notes by an octave to fit the range"). |
| P2-10 | Compare | The A and B selects show full run ids (about 70 characters). "Previous/Next difference" look disabled even when differences exist, and they give no reason when there aren't any. | In the options, show the title, then the profile and time; move the id into a tooltip. Say "No differences in Soprano Cornet" on the buttons themselves (disabled plus a reason), or hide them. |

### P3

| # | Problem | Fix |
|---|---|---|
| P3-1 | The wordmark SVG doesn't scale with the text at 200 %. | Size it in `em` or `rem`. |
| P3-2 | The spacing between sections isn't consistent (for example `h2` margins against card padding on Run vs Bench). | Use one vertical rhythm: `--bc-space-6` between sections and `--bc-space-3` inside them. |
| P3-3 | The tonal secondary buttons on bg have no outline, so they read as labels in the contrast theme and in dark. | Add a 1 px `border-strong` outline to the secondary buttons in Studio. |
| P3-4 | In nb, the native file input is English ("Choose File / No file chosen"). This is still open from review 2. | Use a styled button with localised text (Runs has already done this; the Viewer hasn't). |
| P3-5 | The "Keyboard: Space listens…" and "Press F1 or ?" hints sit in a 13 px footer. | Keep them, at 14 px, with the ⓘ icon aligned. |
| P3-6 | The stage-graph cards in the transcribe column have uneven widths. | Give them equal widths. |

---

## 3. What to hide behind a disclosure

| Collapse by default | Where |
|---|---|
| The stage chain in the profile help | Runs, start form |
| The stage graph | Run, after a success; open it on failure |
| Validator warnings, grouped by kind | Run |
| The manifest JSON rows: Host, Parameters, Options | Run, Manifest tab. Keep Run, Profile, Status, Input and Git visible. |
| "Needs" and the history per suite | Benchmarks |
| Passing variants and passing cases | Parity, Conformance |
| Fingerprints, SHA-256 hashes, absolute paths | Datasets and models |
| Stop, Go, and the note-source table beside the score | Score toolbar. Move the note-source table to the Piano roll tab, where it matters. |

## 4. Where a contributor gets lost

1. **First visit:** there are 7 tabs and no "start here". Fix: P1-6, with the demo as the primary.
2. **Starting a run:** it isn't clear whether the file or the dataset item will be used, and whether "heavy models" is safe to leave on. Fix: P1-2.
3. **Finding their run:** the titles are identical timestamps. Fix: P1-3.
4. **On a run:** they must scroll past the graph to reach the score, and there's no single next action. Fix: P1-4 and P1-5.
5. **A run failed:** the failing stage looks like any other card, apart from a slightly thicker border. Fix: P1-4 (open the graph on failure and highlight the failing stage, with its error message inline).
6. **Quality pages:** it isn't obvious whether anything needs attention, because everything is listed and everything passes. Fix: P2-2…4 (failures first, passes collapsed).
