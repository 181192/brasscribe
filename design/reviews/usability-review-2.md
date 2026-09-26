# Usability review, second pass: Android, Studio (and Windows XAML)

**What I reviewed**

| Platform | Files |
|---|---|
| Android | `apps/android/docs/screenshots/design/`: all 56 PNGs (en light and dark, nb, 200 % text, and `17-very-uncertain-boxed`) |
| Studio | `studio/docs/screenshots/themes/`: all 52 PNGs (11 views × light, dark, contrast and nb, plus the score crops) |
| Windows | Code only: `apps/windows/src/Brasscribe.Play/Views/*.xaml`, `Dialogs/*.xaml` and `Strings/*/Resources.resw`. Windows can't render on this Mac, so every Windows verdict below is "in the code, not seen on screen". |
| Apple | Not yet reviewed. Its screenshots haven't landed. |

**Scale:** the Android screenshots are 1080 × 2400 px. That is 411 dp wide, so 1 dp = 2.625 px.

**Rule (same as the first review):**
- **P1:** a persona taps the wrong thing, loses work, or can't find or use a core feature.
- **P2:** they hesitate or misread, but recover.
- **P3:** polish.

---

## 1. First-review P1s: did they land?

Studio is a workbench and has no phone player, part view or Play export, so most P1s don't apply to it (–).

| P1 | Android | Studio | Windows (code) |
|---|---|---|---|
| **1. M/S → Mute / Only this** | **Landed.** The parts sheet has labelled Mute / Only this buttons (nb Lyd av / Bare denne) at about 47 dp. | **Landed.** The disclosure is "Parts: mute, or hear only one" (nb "Stemmer: lyd av, eller hør bare én"). The buttons inside it were collapsed in every screenshot, so they weren't seen. | **Landed.** `MixerMuteLabel` / `MixerSoloLabel` = Mute / Only this, nb Lyd av / Bare denne. |
| **2. Phone chips clipped; "on" chip looks primary** | **Partly.** All 5 chips show in two rows (three at 200 %), with nothing clipped. No screenshot shows a chip turned on, so the tonal fill + ✓ "on" state is unverified. | – | – (desktop player grid) |
| **3. Play along as a second primary** | **Landed.** Round Play is the only primary. **Mute my part** is a chip with a headphones icon. Speed and Repeat are in the same player. | – | **Landed.** `MuteMyPartToggle`; "{0} muted so you can play along". |
| **4. Done abandons notes** | **Landed.** **Finish later (215 left)**, a confirm dialog ("215 notes keep their ? marks… tap "Check them""), a score status "215 notes marked ? · Check them", and **Skip**. | – | **Landed** (strings plus `ReviewSkipButton`). |
| **5. Export: 12 files, no Print** | **Partly.** Landed: title **Share or print**, PDF only by default, **Print** as the primary, "1 file", and the "?" legend. **Missing:** the scope choice. There's no My part / Every part / Conductor's score, so the librarian can't get one PDF per player and nobody can tell which part will print. | – | **Landed.** Scope radios (`{0} (you)` / Every part / Conductor's score), `PrimaryButtonText` = Print…, and the "Every part: one PDF per player" tip. |
| **6. Phone targets under 44 pt** | **Landed.** Chips, toolbar, Listen, Change, segmented controls, sheet buttons and review buttons are 45–48 dp. "Check them" is text-only and its hit area can't be seen. | – | Previous and next bar are 48 epx. The toolbar is 40 epx (fine for a pointer). |
| **7. `brasscribe serve` in a Play error** | **Landed.** It sits only in `companion_tech_details`, under the "Details for the band's tech person" disclosure. | – (Studio may show commands) | **Landed.** `Error_ComputerUnreachable_Details` is inside an `Expander`. |
| **8. Choose output unmocked** | **Landed.** "How should the score be?" with Which band? / How hard? (three steps) / Key, the difficulty tip, and **Show the score**. See §2 for the key and 200 % issues. | – | **Landed** (`ChooseOutputPage.xaml`). |

**Known deviations**

| Deviation | Verdict |
|---|---|
| Three difficulty steps | Fine. "A bit easier" is clear. |
| Quartet hidden | Fine. Better than offering a choice that fails. |
| Concert key on "How should the score be?" | Not fine as it stands: P2-3. |
| alphaTab "?" slightly small | It isn't slight: see new P1-11. |

---

## 2. New findings

### P1

| # | Where | Problem | Fix |
|---|---|---|---|
| **9** | Android Review (`05-review`) | There's no **Change note…**. The lead text promises "Listen, then keep or change each one", but the only actions are Keep and Skip, so a wrong note can't be fixed. The note card also shows two bare note glyphs with no staff, key or neighbouring notes, so there's nothing to compare against. | Add **Change note…** / **Endre tonen …** as the second button next to Listen: pick a pitch and a length, then preview it. Show the bar on a staff as in the mockup, with the note ringed in ink. Add the "It could also be an A" hint (first review, P2-16). |
| **10** | Review, all platforms (Android "Check 215 notes") | There's no triage. A player faces 215 notes one at a time across every part, including accompaniment layers they don't play ("Strings", "Drums"). Nobody finishes that. The part chips filter the list, but the title and count stay at 215. | Start in the player's own part, with the very uncertain notes first: "**Check your part first**: 12 notes in Solo Cornet, 4 very unsure". The count follows the selected chip. Put an "All parts (215)" chip last. Fold "Strings" and "Drums" under one **Accompaniment** chip, or check them after arranging, when they are brass parts. |
| **11** | The score on Android (`09`, `11`, `17`) and in Studio | The "?" marks from alphaTab are about 45 % of spec. The boxed "?" in `17-very-uncertain-boxed` is about 8 dp and reads as a smudge, not a box. On a phone held at arm's length by a 70-year-old, the one signal that a note needs checking is invisible. | Render the marks at the spec size, 1.6 staff spaces, which is roughly 2× the current size: through alphaTab's text style, or by drawing them in an overlay from the note bounds. Draw the box stroke at no less than 1.5 dp. Check it on `17` at 100 % and 200 %. Studio can follow later (P3). |

### P2

| # | Where | Problem | Fix |
|---|---|---|---|
| 1 | Android Share or print | There's no scope selector (P1-5, the missing part). | Copy Windows: My part (you) / Every part / Conductor's score, with **My part** as the default. |
| 2 | Android score toolbar | It says "As written", not "As written for B♭". No tip is visible. Windows has both (`Score_AsWrittenFor` and tooltips). | Use `As written for {0}` and add the ⓘ tip, as on Windows. |
| 3 | Choose output, Key (Android) | "C major · As recorded" is the concert key. Every B♭ player reads D major on their part. The − / + buttons don't say what they do. | "**C major** (concert) · D major for B♭ instruments". Label the buttons **Lower** / **Higher** (nb Lavere / Høyere) with a "semitone" tooltip. |
| 4 | Android at 200 % text (`03`, `03b`, `08`, `09`) | Segmented controls break: "Concert pitch" and "A bit easier" wrap and the segments end up with different heights. The "On your computer" card squeezes its text into a column one word wide. The radio button overlaps the card text. The toolbar icons don't scale with the text. The player isn't collapsed to Play + Transport, as `system.md` §2 asks. | At ≥ 150 % font scale: stack the segments vertically (a radio list), move **Change** below the card text, and give the radio its own column. Scale the icons with the text. Collapse the practice chips behind a **Practice** button. |
| 5 | Android, several screens | A stale **"Score ready"** line sits under the header on Review, Output, Score and Share. In `17` the same slot says "Opened boxed.musicxml." (a file name with its extension). It reads like part of the page. | Make it a transient snackbar. Never show a file extension. |
| 6 | Android nb | Part names aren't translated in the score view, the part picker, the parts sheet and the title ("Solo Cornet", "Soprano Cornet", "solo cornet & brass band"), but Review says "Solokornett". The same part has two names. | Pick one convention per locale. Norwegian bands use "Solokornett", "Sopran", "Repiano", "2. kornett", "Flygelhorn". |
| 7 | Android Review chips | The part chips scroll sideways and are clipped ("Drums" / "Tr…"), which is the same class of problem as P1-2. | Wrap them, or fold them into the triage chips from new P1-10. |
| 8 | Android parts sheet | Each part row is about 120 dp, so 25 parts need a long scroll. "All parts / My part" at the top shows no selected state. The **Only this** icon is a viewfinder (center_focus), not the headphones in `icons.json`. | One row per part with the toggles at the right (about 64 dp). Show the selected segment. Use the headphones icon. |
| 9 | Android Settings | Only two rows (computer, About). There's no Display (text size, theme, high contrast), no Sound and no Help, and the phone still has no Help anywhere (first review P2-12). | Add the groups `system.md` §5 lists, plus a **Help** row. |
| 10 | Android "On your computer · the built-in demo", "On the built-in demo." | The screenshots run against the fixture engine. Under the heading "On your computer" this reads as "the app is a demo". The subtitle also starts with a lowercase letter. | Check that production shows the computer's name. If a fixture mode ships at all, label it "Example only · no computer needed". |
| 11 | Android title bar on Share or print | "(draft)" is unexplained. Is the printout a draft? | Drop it from Play titles, or explain it: "Draft: 215 notes still marked ?". |
| 12 | Studio, Core conformance (every theme) | "Could not load. Failed to fetch" gives no reason and no next step, and "Failed to fetch" stays English in nb. | "Couldn't reach Brasscribe on this computer. Is `brasscribe serve` running?" plus a **Try again** button. Localise it. |
| 13 | Studio nb | The Play button says "Spill" (first review §2: **Spill av**). | Change it to "Spill av". |
| 14 | Android dark, all parts (`11-dark`) | Inside the cursor-bar tint, the grey noteheads on dark purple look low in contrast. | Run `qa/tools/contrast.py` on `ink-dark` over the `cursor-tint` blend. If it fails, lower the tint alpha in dark. |
| 15 | No screenshots of these states | Can't verify: a chip turned on, the Repeat on/off state ("Stop repeating"), the transcribing Cancel confirmation, and the ad-lib tint with the cursor elsewhere (bar 1 is always under the cursor, so ad lib and cursor look identical). | Add screenshots of these four states. |

### P3

| # | Where | Problem | Fix |
|---|---|---|---|
| 1 | Android headers | "Mikkel — solo c…" is truncated on every screen, and "Finish later (215 left)" takes most of the Review header. | Use the short song title in headers. Move Finish later into the action row, as on desktop. |
| 2 | Android bottom sheets (Parts, Speed, Repeat) | No drag handle, and the title sits tight against the top edge. | Add a handle and 24 dp of top padding. |
| 3 | Android Speed sheet | 100 % is current, but none of the preset buttons shows as selected. | Show the selected state. |
| 4 | Android error | "Details for the band's tech person" has no chevron and is indented differently from the body text. | Use an expander with a chevron, aligned to the 16 dp margin. |
| 5 | Review note names | "B♭5 / G5" octave numbers are scientific pitch. | Drop the octave number unless two notes would read the same. Or say "high B♭". |
| 6 | nb "Home" | Android says "Hjem", Windows says "Startside". | Pick one ("Hjem"). |
| 7 | Studio viewer | The score frame has heavy black side borders (light and nb), and the "Show" select wraps onto a line by itself. | Use a hairline border. Let the toolbar wrap as a group. |
| 8 | Studio nb header | The nav wraps and the engine status drops to a second line. The native file input stays English ("Choose File / No file chosen"). | Shorten the nb tab labels or let the nav scroll. Use a styled button with localised text. |
| 9 | Studio stage graph | The stage cards in the transcribe column have uneven widths. | Give them equal widths. |
| 10 | Studio score | The small "?" (see new P1-11). | Follow the Play fix. |

---

## 3. What works well now

- The flow reads like a section leader:
  - "Not sure? Choose Brass band."
  - "You can change this later. Nothing is lost."
  - "Easier keeps the tune but avoids high notes and fast runs."
  - "Written B♭5, crotchet".
  - The nb review uses Norwegian note names correctly: B = B♭, H = B natural.
- The dialog "215 notes keep their ? marks…" is exactly right.
- The empty What is this? state has **Continue** disabled and "Choose one to continue".
- The error has a title, one reason, a disclosure for the tech person, and two ways out.
- Windows strings cover almost every §2 replacement in both languages ("Stop repeating", "♩ = {0} (slowed from {1})", "Read aloud / Les opp", "Lyd av min stemme").

## 4. P1 list for this pass

1. **Android Share or print (P1-5, partly):** there's no scope selector (My part (you) / Every part / Conductor's score). Copy the Windows `ExportDialog`.
2. **Android Review (new P1-9):** there's no **Change note…**, so wrong notes can't be fixed. The note card needs a staff and context.
3. **Review triage, all platforms (new P1-10):** 215 notes, one at a time, across every layer. Start with "your part, very unsure first", and make the count follow the selected part.
4. **"?" size in the alphaTab score, Android (new P1-11):** about 45 % of spec, and the boxed "?" is about 8 dp and unreadable. Render at 1.6 staff spaces.

Still unverified (needs screenshots): the chip "on" state (P1-2) and every Windows item (code only).
