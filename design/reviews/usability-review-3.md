# Usability review, third pass: Android

- **Scope:** all 75 PNGs in `apps/android/docs/screenshots/design/` on main (merge `002f6e7`), in light, dark, nb and 200 % text. That includes the requested states: `04b` cancel confirmation, `09b` chip on, `09c` ad lib with the cursor elsewhere, `13b` repeat on, `13c` stop repeating, `15b` Help, and `17`/`18` very uncertain boxed.
- **Rule** (same as before): P1 means a player taps the wrong thing, loses work, or can't find or use a core feature.
- **Numbering:** the second review had new P1s 9–11. There was no P1-12.

## 1. Earlier P1s

| P1 | Verdict | Evidence |
|---|---|---|
| **5. Share or print scope** | **Landed** | `14`: WHAT shows Solo Cornet (you) (the default), Every part ("One PDF per player") and Conductor's score. Print is the primary, and the status line reads "1 file · uncertain notes keep their "?" marks". The nb version is correct (Solokornett (deg) / Alle stemmer / Dirigentpartitur). |
| **9. Change note…** | **Landed, but the editor is unverified** | `05`: **Change note…** sits under **Listen to this bar**. The bar is drawn on a staff with the note highlighted, and the hint "Uncertain. Listen to the original and the score side by side." is there. There's no screenshot of the Change note sheet itself, so I can't judge the pitch and duration picker. |
| **10. Triage** | **Partly** | Landed: "Check your part first", the chips "Solo Cornet (215)" and "Accompaniment (0) ▾", and a count that follows the chip. Still open: see new **P1-A**. On this demo, all 215 notes are in the player's own part, so triage doesn't make the job any smaller. I also can't verify "very unsure first", because the Mikkel demo has no very uncertain notes. |
| **11. "?" at spec size** | **Landed** | `17` at 100 % shows a clear "?" and a boxed "?" at about 12 dp, with the box stroke readable. `18` at 200 % zoom scales them properly. |
| **2. Chip "on" state** (unverified in pass 2) | **Landed** | `09b`: Count-in on has a tonal fill, an ink outline and a ✓, with no ink fill. The same holds in dark. `13b`: the chip reads "Repeating 1–4" and a snackbar says "Repeating bars 1 to 4". |

Other checks from the second pass, now verified:
- **Cancel confirmation (`04b`):** "Stop making this score? The recording is kept." with Keep going / Stop. Correct.
- **Stop repeating (`13c`):** present in the Repeat sheet (nb "Slutt å gjenta").
- **Ad lib with the cursor elsewhere (`09c`):** the ad-lib bar is no longer blue. The cursor tint is on bar 3 only.

## 2. P2s from the second review

| # | Verdict | Note |
|---|---|---|
| 2 As written for B♭ + tip | **Landed** | The ⓘ button sits next to the segment. |
| 3 Key display | **Landed** | "C major (concert) / D major for B♭ instruments / As recorded", with **− Lower / Higher +**. The nb reads "C-dur (klingende) / D-dur for B-instrumenter". |
| 4 200 % text | **Mostly landed** | At ≥ 150 %: the output difficulty is a radio list, the score segments stack, and the player collapses to **Practice ▾**. Still open: on What is this?, the radio in the first card still collides with the description ("like○ you practising"). The computer card is fixed. |
| 5 "Score ready" line | **Landed** | Gone. |
| 6 nb part names | **Landed** | Solokornett, Sopran-kornett, Repiano-kornett, 2. kornett. There's a new wrap bug; see P2-C. |
| 7 Review chips clipped | **Landed** | Two chips, and they wrap at 200 %. |
| 8 Parts sheet | **Mostly landed** | One row per part with the toggles at the right, and "My part" shows as selected. Still open: the **Only this** icon is still a viewfinder (center_focus), not headphones. |
| 9 Settings / Help | **Landed** | Sound (Standard / Realistic), Display (Language, Text size and reduced motion), Help and About. Home has a Help button. `15b` Help is plain and complete, in both en and nb. |
| 10 Demo wording | **Partly** | What is this? now says "Example only · no computer needed · nothing goes online". But Settings still says "Using the built-in demo". |
| 11 "(draft)" in titles | **Landed** | Titles are "Mikkel". |
| 14 Dark cursor-tint contrast | **Fine by eye** | Not measured. |

## 3. New findings

### P1

| # | Where | Problem | Fix |
|---|---|---|---|
| **P1-A** | Review, and the score status "215 notes marked ?" | The Mikkel solo part has 694 notes (from the Studio compare view), and 215 of them are marked "?": **31 %**. When a third of the notes carry a "?", the mark stops meaning "check this one". A player can't get through the review, and the printed part is covered in marks. The review screen handles this as well as a screen can; the cause is upstream. | **Engine and music-core:** calibrate the uncertain threshold. The target is ≤ 5–10 % of notes marked on a clean recording, with boxed marks only for truly doubtful ones. Merge neighbouring marks in a run into one per phrase ("bars 12–13, 6 notes"). **UI**, until the calibration lands:<br>• Sort very unsure first.<br>• Add a **Keep the rest of this bar** action.<br>• When more than 50 notes are marked, lead with "Most of these are probably right. Start with the 12 very unsure ones." |

### P2

| # | Where | Problem | Fix |
|---|---|---|---|
| P2-A | Review staff (`05`) | The selected note is outlined with a rounded square. Next to a "?", that looks like the **boxed "?"** meaning "very unsure", even when the note is only uncertain. | Show selection as a `selection-tint` column behind the note plus a caret under the staff, not a box. |
| P2-B | Change note sheet | There's no screenshot of it. | Add `05b-change-note` (light, nb, 200 %) so the picker can be reviewed. |
| P2-C | Parts sheet, nb (`10-nb`) | "Repiano-kornett" breaks as "Repiano-kornet / t". | Hyphenate at the compound joint (Repiano-/kornett), or give the name column the space and let the toggles wrap below it. |
| P2-D | What is this? at 200 % (`03-font200`) | The radio overlaps the first card's description. | Give the radio its own trailing column with a fixed width, top-aligned. |

### P3

| # | Problem | Fix |
|---|---|---|
| P3-A | The Review header still holds "Finish later (215 left)" (first review, P3-1). | Move it into the action row under Skip. |
| P3-B | Speed presets show no selected state (100 % is current). | Show the selected state. |
| P3-C | The Only this icon is a viewfinder. | Use headphones, as in `icons.json`. |
| P3-D | Settings uses an ⓘ icon for Language, and still says "Using the built-in demo". | Use a language/globe icon. Use the same "Example only · no computer needed" wording. |
| P3-E | nb is inconsistent: the score toggle says "Notert for B♭", but the output says "B-instrumenter". | In Norwegian, B already means B♭. Use "Notert for B" and "B-instrumenter" everywhere. |
| P3-F | Repeat on (`13b`) has no loop bracket or "Gjenta 1–4" label on the score, only the tint. | Draw the loop-edge brackets and the label, per `system.md` §6. |

## 4. Remaining P1s (Android)

1. **P1-A, uncertainty rate:** 31 % of the solo notes are marked "?". This needs the engine and music-core to calibrate the threshold. Meanwhile, the UI sorts very unsure first, adds a "Keep the rest of this bar" action, and adds a "most are probably right" lead line when more than 50 notes are marked.

Everything else from the P1 list has landed on Android. The only thing left to check is the Change note editor, which has no screenshot (P2-B).

---

# Apple

- **Scope:** all 72 PNGs in `apps/apple/docs/screenshots/` on main (`1c8d80a`). That is 12 screens on iPhone, iPad and macOS, in light and dark. There are no nb screenshots.
- **Scale:** the iPhone screenshots are 1206 × 2622 px at 3x (402 pt wide), iPad is 2x and macOS is 2x.
- **Home list:** every Home screenshot shows the empty "Your scores" state (macOS shows a single "Mikkel"). The finding about the populated list comes from the team lead's check in the live simulator. I haven't seen it myself.

## A1. First-review and second-review P1s

| P1 | iPhone | iPad | macOS |
|---|---|---|---|
| 1 Mute / Only this | – (parts are in the sheet) | **Landed** (Parts button) | **Landed.** The parts panel has labelled Mute / Only this and "your part" under Solo Cornet. |
| 2 Chips clipped / on state | **Landed.** Two columns, and "on" is a tonal fill + outline + ✓ (Repeat, Count-in, Mute my part). | **Landed** | **Landed** |
| 3 Play along → Mute my part | **Landed** | **Landed** | **Landed** |
| 4 Finish later | **Landed.** Confirm dialog, "Check them" on the score, Skip. | **Landed** | **Landed** |
| 5 Share or print scope | **Landed.** My part (Solo Cornet) / Every part / Conductor's score, **Print** as the primary, and a "Show ? marks" toggle with a footer legend. | **Landed** | **Landed** (Print… as the primary, then Save…, then Cancel) |
| 6 Targets ≥ 44 pt | **Landed** (chips and buttons ≥ 48 pt) | **Landed** | Fine for a pointer. The parts panel buttons are small (see A3). |
| 7 No CLI command in errors | **Landed** | **Landed** | **Landed** |
| 8 Choose output | **Landed.** "C major (concert) · D major for B♭ · A major for E♭ instruments", with − Lower / + Higher. | **Landed** | **Landed** |
| 9 Change note… | **Partly.** See **P1-B**. | **Landed** | **Landed** |
| 10 Triage | **Landed.** Your part (215) / Other parts (121) / All parts (336). | **Landed** | **Landed** |
| 11 "?" size | **Landed.** The "?" is about 1.6 staff spaces in the part view. | **Landed** | **Landed** |
| Ad lib with the cursor elsewhere | **Landed.** The part view at bar 9 has no blue tint on the ad-lib bars, and shows the "Bars 1–7 have no steady beat" note. | | |
| Repeat on / off | **Landed.** The "Repeat 12–13" label, loop-edge brackets, and on iPad/macOS the **Stop repeating** control. | | |

## A2. New P1s (Apple)

| # | Where | Problem | Fix |
|---|---|---|---|
| **P1-B** | iPhone, Review (`iphone-review-*`) | **Listen to this bar** and **Change note…** are below the fold. They sit hidden under the Skip / Keep bar, and only a grey sliver shows at about 1720 px. The staff card is about 440 pt tall but only its top third holds music. So a player sees Keep and Skip and never finds out they can listen or change the note, which undoes P1-9 on the platform most players use. | Size the staff card to its content (about 140 pt at this zoom). Put **Listen to this bar** and **Change note…** directly under the note name, above the fold at the default text size. At large Dynamic Type, keep them visible, even if the list below scrolls. |
| **P1-C** | Home, "Your scores" (reported by the team lead from the live simulator, dark) | Rows have almost no vertical padding, and several recordings share the title "20260815_155324", so a player can't tell their recordings apart or find last week's rehearsal. This is the same defect as Studio P1-3. | Title = the name the user gave it. Otherwise use the imported file name without its extension, or "Recording, 26 Sep 19:02" for microphone captures. **Never use a bare timestamp.** If two titles still match, add the time as a subtitle. Rows are at least 60 pt tall (`system.md` §5, List rows) with the title plus one subtitle line ("Full band · 132 bars · Today · 215 to check"). Add a populated Home screenshot (5+ scores, light and dark) to the set. |
| **P1-A** (cross-platform, from the Android section) | Review and the score status | "336 notes marked ?", of which 215 are in Solo Cornet: 31 % of the solo notes. | Engine and music-core calibration, plus the interim UI steps in the Android section. |

## A3. P2 / P3 (Apple)

| # | Where | Problem | Fix |
|---|---|---|---|
| P2-E | iPhone player chip "Recording" (waveform icon) | It reads as "start recording", like the microphone problem in the first review. iPad and macOS label the same thing correctly as **Hear the band / Recording**. | On iPhone, use the same segmented control, **Hear: Band / Recording**, or label the chip "Hear the recording". |
| P2-F | iPhone / iPad score toggle | It says "As written / Concert" (iPhone) or "As written / Concert pitch" (iPad), without the key. The macOS part view already says "As written for B♭". | Use "As written for B♭" (the key from the part, plain "As written" for All parts) and "Concert pitch" everywhere, plus the ⓘ tip. |
| P2-G | Review note name | "Written A#, dotted eighth note": an ASCII "#" on iPhone and US note values. Android uses "crotchet / quaver". | Use ♯/♭ glyphs, and the same en-GB note values as Android (the brass-band convention). |
| P2-H | iPhone Review header | Back + "Finish later (336 left)" + "Mikkel · Ch…" (truncated) are crammed together. The count is 336 (all parts) while the triage says 215 (your part). | Put **Finish later** as the plain button in the bottom bar or the toolbar trailing slot, with a count that follows the selected triage segment. Title "Check the notes". |
| P2-I | Review snippet (all Apple) | The selected note is outlined with a rounded box, which reads as the **boxed "?"** (very unsure). This is the same issue as Android P2-A. | Show selection as `selection-tint` behind the note plus a caret below the staff. |
| P2-J | No nb screenshots | The nb strings are said to be complete, but they're unverified for truncation (for example "Fortsett senere (336 igjen)" in the iPhone header, "Lyd av min stemme" on a chip). | Add nb screenshots for iPhone review, score, part, export and output. |
| P3-G | macOS parts panel | The Mute / Only this buttons are about 24 pt tall, with 11 pt labels, and 20 rows of them. That's small for older users even with a pointer. | Use the `.regular` control size (28 pt+) and 13 pt labels. |
| P3-H | iPhone Share or print | "More formats" is squeezed against the list edge, and its subtitle wraps under the chevron. | Use the standard `NavigationLink` row height with a one-line subtitle ("MusicXML, MIDI and 2 more"). |
| P3-I | macOS Share or print | "Every part: one PDF per player." shows even when My part is selected. | Show the caption only for Every part, or put it inline as on iPhone. |
| P3-J | iPhone first run | The "Practise with the band" icon is a crosshair. | Use headphones or `music.note.list`. |
| P3-K | iPhone cancel confirmation | The popover anchors on the back button and covers the step title. It offers only **Stop**, and "keep going" means tapping outside. | Use `.confirmationDialog` from the Cancel button with **Stop making the score** / **Keep going**, as on Android. |

## A4. Remaining P1s (Apple)

1. **P1-B, iPhone Review:** Listen and Change note… are hidden below the fold under an oversized staff card. Shrink the card and bring both buttons into view.
2. **P1-C, Home "Your scores":** titles are duplicated as timestamps and the rows have too little padding. Use meaningful titles, rows ≥ 60 pt with a subtitle, and add a populated screenshot.
3. **P1-A, cross-platform:** the uncertainty rate (31 % of solo notes marked). This belongs to the engine and music-core.
