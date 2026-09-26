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
