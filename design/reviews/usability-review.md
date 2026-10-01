# Usability review: Brasscribe Play mockups

- **Scope:** all 36 PNGs in `design/mockups/png/`, read against `design/README.md`, `design/system.md` and `design/brand/brand.md`.
- **Scale:** phone PNGs are rendered at 2x (`render.mjs`: 390 × 844 pt) and desktop PNGs at 1x. Every pt figure below uses that scale.
- **Gap:** there is no mockup of the **Choose output** step (lineup · difficulty · key, `system.md` §3), so it couldn't be reviewed. That step carries the densest jargon in the flow.

**Personas**
- **Cornet player, 70:** a village band member who uses an iPhone for photos and FaceTime. Reads music fluently and knows B♭ and concert pitch from the band room. Doesn't know what an app "export" is.
- **Band librarian:** uses a laptop and a printer. Needs parts for 25 players, printed and correct.
- **Tenor horn learner, 15:** fluent with phones, still learning to read music. Doesn't know band-room terms like "concert pitch", "ad lib." or "flug.".

---

## 1. Walkthroughs

### Cornet player, 70 (phone)

| Step | What happens | Hesitates at / misreads / mis-taps |
|---|---|---|
| First run | Reads the three points and taps **Get started**. Works well. | Nothing. The boxed "?" is taught here, which is good. |
| Home | Wants to record next week's rehearsal. | **"Import audio or video"** is the big black button, but "import" means nothing to them. Their intent, recording, is a smaller row underneath. They may tap Import and land in a file picker they don't understand. The settings gear is icon-only. There's no Help on the phone. |
| What is this? | Picks **Soloist with orchestra or band**. | "The soloist becomes the solo part; the rest becomes brass band." takes a second read. "Change" next to "Kari's MacBook" looks like a way to change the song. It's unclear whether they must change anything. |
| Transcribing | Waits. | "62 percent" is fine. "Engraving the score" makes them think of a trophy. Taps **← Home** and worries that the work is lost; the info card underneath does answer this. |
| Review | Sees "Check 12 notes". | Taps **Done** (top right) thinking it means "done with this note". The other 11 notes are then left unchecked without a word. Reads "G": is that the written G or the concert G? "Half note" is American; a British-style band says "minim". The legend "?" is only about 12 pt tall. |
| Score | Opens the full score and wants to play along. | "M"/"S" aren't on the phone, and **Mute my part** is off the right edge of the chip row (the chip is clipped by the fade). They never find it. **Count-in** is ink-filled, so it looks like the main button and gets tapped instead of Play. "Written / Concert" is understood, but they don't know which one they're looking at. |
| Part | Picks Solo Cornet. | There are two black buttons: round Play and **Play along**. The microphone icon on Play along says "it will record me", so they avoid it. "Your part is muted" appears before they asked for anything. There's no Speed or Loop control, so they can't slow bar 12 down. |
| Export | Wants a printout of their part. | The title "Export" means nothing to them. The defaults are **All parts** plus PDF and MusicXML, which makes "12 files". There's no **Print**; it's hidden inside iOS Share. "My part" doesn't say which part that is. |

### Band librarian (desktop, then phone)

| Step | What happens | Hesitates at / misreads / mis-taps |
|---|---|---|
| Home | Drags in a concert recording. Works well. | "New score" in the sidebar and "Choose a file…" are two ways in with two different names. |
| What is this? | Picks **Brass band**. | "Transcribed on this Mac" is fine for them, but it breaks the voice rule (see §2). |
| Transcribing | Leaves it running. | Cancel has no confirmation, so one stray click throws away 4 minutes of work. |
| Review | Works through the sidebar. | "4 more" is small grey text and doesn't look clickable. **Done checking** sits alone in the title bar, far from the work, with no count of what's left. |
| Score | Checks the parts before printing. | The **M / S** buttons read as "Medium / Small", or as "Solo" next to parts that are already called *Solo* Cornet and *Solo* Horn. "Score / Original" in the title bar: original what? "Video" and "Talking score" are unclear. "♩ = 102 at 75%": is 102 the real tempo? The free-time info card talks about bars 1–2 while bars 9–16 are on screen. |
| Export | Needs one PDF per player. | "Full score" and "All parts" have no explanation. The printed parts carry "?" marks, but nothing on the page says what "?" means. There's no option to print without the marks once checking is done. The dialog has both an ✕ and a Cancel. |

### Tenor horn learner, 15 (phone)

| Step | What happens | Hesitates at / misreads / mis-taps |
|---|---|---|
| Home | Wants to paste a YouTube link. | The phone has no "links can't be downloaded" tip; the desktop does. Tries **Record what's playing**, which fails on protected audio. |
| Error | Sees "Nothing was heard". | "Protected (DRM) streams" is jargon; they don't know "DRM". The recovery buttons are good. |
| What is this? | Picks **Pop or rock**, because the band plays a film medley. | There's no "Not sure?" help, and no option for band plus organ or choir. |
| Score | Looks for their part. | "Flug.", "Euph.", "Concert" and "Written" are all unfamiliar. The "?" marks look like printed performance marks. There's no legend on this screen. |
| Part | Wants to loop two bars at half speed. | The part player has no Speed or Loop, so they have to go back to the full score. "Bars 1–2 are in free time (ad lib.)": what is free time? The pale-blue ad-lib tint reads as "uncertain", because blue means uncertain everywhere else. |
| Export | Wants an MP3 to practise with. | Finds **Audio**. Works well. |

---

## 2. Jargon and copy (en and nb)

**Convention:** where a term is fine for band players but not for learners, keep the short label and add an ⓘ tip (a tooltip or popover, ≤ 1 sentence).

| Where | Now (en / nb) | Replace with (en / nb) | Tip (en / nb) |
|---|---|---|---|
| Score toolbar | Written / Concert (pitch) · Notert / Klingende tone | **As written for B♭** / **Concert pitch** · **Notert for B♭** / **Klingende** (the instrument's key comes from the selected part; "All parts" shows "As written") | "Written is what you read on your part. Concert is how it sounds on a piano." · «Notert er det du leser i stemmen din. Klingende er slik det låter på et piano.» |
| Parts panel | M / S · M / S | **Mute** (speaker-slash icon) / **Only this** (headphones icon) · **Lyd av** / **Bare denne** | "Only this: hear this part alone." · «Bare denne: hør bare denne stemmen.» |
| icons.json `mute` nb | Demp | **Lyd av** | – ("demp", like "mute" in English, is the physical mute in the bell) |
| icons.json `solo` en/nb | Solo | **Only this** · **Bare denne** (it collides with the part names Solo Cornet and Solo Horn) | as above |
| Player | Count-in · Inntelling | Keep | "One bar of clicks before the music starts." · «Én takt med klikk før musikken starter.» |
| Player (desktop) | Loop bars 12 to 13 · – | **Repeat bars [12] to [13]**, plus a **Stop repeating** button when the loop is on · **Gjenta takt [12] til [13]**, **Slutt å gjenta** | "Plays these bars over and over." · «Spiller disse taktene om og om igjen.» |
| Player | Speed 75% · Tempo 75 % | Keep; the nb must be **75 %** (with a space) | – |
| Player (desktop) | ♩ = 102 at 75% | **♩ = 102 (slowed from 136)** · **♩ = 102 (ned fra 136)** | – |
| icons.json `play` nb | Spill | **Spill av** ("Spill" is also a noun, and "Spill inn" and "Spill med" sit right next to it) | – |
| Score toolbar | Talking score · Talende partitur | **Read aloud** · **Les opp** (the export row keeps "Talking score" as the format name) | "Describes the score in words for a screen reader." · «Beskriver partituret med ord for skjermleser.» |
| Score toolbar | Video · Video | **Show video** · **Vis video** | – |
| Title bar | Score / Original | Move it into the player as **Hear: Band / Recording** · **Hør: Band / Opptak** | – |
| Part / score info | "Bars 1–2 are in free time (ad lib.)" | "Bars 1–2 have **no steady beat** (ad lib.). Their rhythms are approximate." · «Takt 1–2 har **ingen fast puls** (ad lib.). Rytmene der er omtrentlige.» | – |
| Choose output (not mocked) | lineup · difficulty · key | **Which band?** (Full brass band / Small band / Quartet) · **How hard?** (Easier / As played) · **Key** · nb **Hvilket band?** / **Hvor vanskelig?** / **Toneart** | For difficulty: "Easier keeps the tune but avoids high notes and fast runs." · «Enklere beholder melodien, men unngår høye toner og raske løp.» |
| Home primary | Import audio or video · Importer lyd eller video | **Open a recording** · **Åpne et opptak** (the subtitle names the formats) | – |
| Export title | Export · Eksporter | **Share or print** · **Del eller skriv ut** (keep "Export" only in the desktop menu bar) | – |
| Export scope | Full score / All parts / My part (phone) vs Solo Cornet only (desktop) | **Conductor's score / Every part / Solo Cornet (you)**, the same on both · **Dirigentpartitur / Alle stemmer / Solokornett (deg)** | "Every part: one PDF per player." · «Alle stemmer: én PDF per musiker.» |
| Review note line | G, half note | **Written G, minim** (en-GB) / **G, half note** (en-US) · **Notert G, halvnote** | – |
| icons.json `mark-checked` nb | Merk som kontrollert | **Behold** (glossary: Keep = Behold) | – |
| Transcribing | Engraving the score | **Laying out the pages** · **Setter opp sidene** | – |
| Transcribing | 62 percent | **62 %** in nb and **62%** in en, the same as the sidebar | – |
| Transcribing | "we'll tell you when…" | "Brasscribe will tell you when the score is ready." (the voice never says "we") | – |
| What is this? soloist | "The soloist becomes the solo part; the rest becomes brass band." | "You get the solo part, plus the accompaniment arranged for brass band." · «Du får solostemmen, og akkompagnementet arrangert for brassband.» | – |
| What is this? | – | Add below the cards: "Not sure? Choose Brass band. You can change it later." · «Usikker? Velg Brassband. Du kan endre det senere.» | – |
| Desktop What is this? | Transcribed on this Mac · Transkriberes på denne Macen | **Made on this Mac. Nothing goes online.** · **Lages på denne Macen. Ingenting sendes til nettet.** (breaks brand.md voice §7 and the avoid-list "transcribe") | – |
| Part page header | Transcribed with Brasscribe · … | **Written down by Brasscribe. Check the notes marked ? before the rehearsal.** | – |
| Phone error | Protected (DRM) streams always do. | "Streaming apps usually block recording." · «Strømmeapper stopper som regel opptak.» | – |
| Desktop error | "…or run `brasscribe serve`" | Remove it. Put it under **Details for the band's tech person** (a disclosure), as brand.md "Before and after: Apple, pairing" already requires | – |
| Review phone | Done · Ferdig | **Finish later** · **Fortsett senere** (see P1-4) | – |

---

## 3. Hierarchy

**One primary action per screen**

| Screen | Status | Fix |
|---|---|---|
| Home phone | One primary, but it's the wrong one for most users | Keep one primary. Consider making **Record with the microphone** the second row with a stronger subtitle. At minimum, rename Import (§2). |
| Score phone | Count-in (on) is ink-filled, the same as Play | "On" chips use a tonal fill, an ink border and a ✓. Ink fill is reserved for the primary. **Spec change needed:** `system.md` §5, Player bar, "chips turn ink when on". |
| Part phone / desktop | Two ink controls: round Play and Play along | Play is the only primary. Play along becomes a **Mute my part** toggle chip (headphones icon, not a microphone). |
| Review desktop | Keep, go to next ✓. "Done checking" is orphaned in the title bar | Move it into the action row as a plain button: **Finish later (9 left)**. |
| Export desktop | Export 12 files… ✓ | Drop the ✕ (Cancel already exists). |
| Error desktop | The primary is left-aligned; every other desktop screen puts it bottom right after Cancel | Right-align it, per `system.md` §2. |

**Density**
- **Desktop score** has about 30 controls across the title bar, the toolbar, the parts panel and the player. Changes:
  - Move **Read aloud** and **Show video** into a **View ▾** menu.
  - Move **Hear: Band / Recording** into the player, beside Play.
  - Move the beat counter next to "Bar 13, beat 2". It sits alone at the far right now.
  - Give the speed slider a visible "Speed" word. It is icon-only now, which breaks `system.md` §1 rule 6.
  - Result: the toolbar has 4 groups and the player has 3 (transport · position · practice).
- **Phone player:** the chip row scrolls sideways behind a fade, so Metronome and Mute my part are invisible. Show two rows (Speed · Loop · Count-in / Metronome · Mute my part), or a **Practice ▾** sheet. Never clip.
- **Part view:** the player has no Speed or Loop. Use the same player as the score view, with Mute my part on by default.

**Touch targets (phone, at 2x)**

| Control | Now | Fix |
|---|---|---|
| Player chips, toolbar (All parts, Written/Concert, zoom), Listen / Change note…, Export segmented control | 40 pt | ≥ 44 pt, and 48 pt for the player chips and the review buttons |
| Previous / next bar | A 24 pt glyph, no visible hit area | A 48 pt hit area |
| "Change" (What is this?) | Text only | A 44 pt tall button with an outline |
| "?" marks in the score | Tiny, and it isn't clear whether they respond to a tap | Make them tappable (a 44 pt hit area, then open Review at that note), and say so in the legend |
| Desktop M/S | 32 px | Fine for a pointer, but use 40 epx on Windows touch |

**Status and uncertainty**
- **Legend:** it is missing from the score view and from printed parts. Add a one-line status to the score view: **"9 notes marked ? · Check them"**, which re-opens Review and gives the only way back into it after "Finish later". Print a legend in the PDF footer: "? = Brasscribe wasn't sure. Boxed ? = very unsure." **Spec change needed:** `system.md` §5, Uncertainty legend ("Shown on Review and in the part-view overflow menu").
- **Focus colour:** the focus colour is the same blue as uncertain. `focus` #0050B3 and `uncertain` #0063A6 in light mode, and #8AB4F8 and #56B4E9 in dark. So the focus ring around the very-uncertain orange note in Review reads as "uncertain". **Token change:** use `ink` (light) or `paper` (dark) for the focus ring on notation, or give `focus` a clearly different hue.
- **Ad lib tint:** `adlib-tint` #EEF3F8 is pale blue, which suggests uncertain. Make it a neutral warm grey. The italic "ad lib." and the dashed bar lines already carry the meaning.
- **Home status:** the "Your scores" rows don't show what's still to check. Add "3 notes to check" to the subtitle.
- **Review ordering:** the phone "Still to check" list shows Bar 15 before Bar 10, and only 2 of the 11 remaining. Sort it by part, then bar, and add "+ 9 more".
- **Studio:** Studio reuses "?" and the boxed "?" for validator issues (Range, Crossing). That overloads the Play glyph meaning. Use the warning icon instead.

---

## 4. Premium polish

- **Back labels are inconsistent:** "← Home" (What is this?, transcribing, error), "← Scores" (score, export; there's no screen called Scores), "← Mikkel" (review, part). Use **Home** from the score, and the song title from its children.
- **The desktop part view has no way back** to the full score (no back button, no sidebar). Add a BackButton or keep the sidebar.
- **Centring:** the phone header titles aren't centred. "Mikkel.m4a · 4:12" and "Mikkel" sit about 8 pt right of centre. Centre them on the screen, not in the space left after the back label.
- **Margins:** the phone score toolbar and player card sit at a 12 pt inset, while everything else uses the 20 pt margin. Either align them to 20 pt, or make them clearly full-bleed.
- **Same data, different formats:** "4:12" (phone) vs "4 min 12 s" (desktop). "62 percent" vs "62%". "My part" vs "Solo Cornet only". "Listen" vs "Listen to this bar". The phone Review has no **Skip** and no "it could also be an A" hint; add both, because the hint is the most useful sentence on the screen.
- **Desktop Home score cards:** the thumbnail area has no top or side border, so the card looks cut off. Put the thumbnail inside the card outline.
- **Sidebar "New score":** it is a bordered button on Home but plain text on Transcribing. Pick one.
- **Dark mode:**
  - The icon wells on Home and the tonal **Listen** button almost disappear against the card surface. Raise `secondary` in dark by one step.
  - The loop tint in dark (brown-olive) is heavy across 6 staves. Lower its alpha.
- **Icons:**
  - Count-in uses `counter_1` (①) on Material and web, and `1.circle` on Apple. It reads as "one" or "first", not as clicks. Consider a metronome-with-bar glyph so it pairs with the custom metronome.
  - The Home gear is visually heavier than the outlined row icons. Use the outlined settings symbol.
  - The "All parts" picker has no ▾, so it reads as a label, not a menu. Add a chevron as on the part-view title.
- **The export phone sheet** has about 90 pt of empty space under the note. Use the `.medium`/`.large` detent, or move the buttons to the bottom safe area like every other primary.
- **What is this?** is shown with a choice pre-selected. `system.md` §5 says nothing is pre-selected on first run. Mock the empty state with **Continue** disabled and the hint "Choose one to continue".

---

## 5. Prioritised fixes

**Rule:** **P1** means a persona taps the wrong thing, loses work or can't find a core feature. **P2** means they hesitate or misread but recover. **P3** is polish.

### P1: must fix before shipping

| # | Screen | Problem | Fix |
|---|---|---|---|
| 1 | Score desktop, parts panel (and phone/tablet part picker) | **M / S** are mixer jargon, and "S"/"Solo" collides with the part names *Solo* Cornet and *Solo* Horn. nb "Demp" means the physical mute. | Labelled toggles **Mute** (speaker-slash) / **Only this** (headphones). nb **Lyd av** / **Bare denne**. Update `icons.json` `mute`/`solo` en and nb. |
| 2 | Score phone, player | **Mute my part** and Metronome are clipped off-screen. Count-in "on" is ink-filled and looks like the primary. | Two chip rows (or a Practice sheet), never clipped. "On" = tonal fill + ✓. Change `system.md` §5, Player bar. |
| 3 | Part phone and desktop, player | **Play along** is a second ink button with a microphone icon (reads as "records you"). Its state contradicts "Your part is muted". There's no Speed or Loop. | Play is the only primary. Replace Play along with a **Mute my part** toggle chip (headphones), on by default. Add Speed and Loop, as in the score player. |
| 4 | Review phone ("Done") and desktop ("Done checking") | Leaving silently abandons the unchecked notes, and there's no way back from the score. | Rename to **Finish later (9 left)** / **Fortsett senere (9 igjen)** and confirm: "9 notes keep their ? marks. You can check them from the score." Add the score-view status "9 notes marked ? · Check them". Add **Skip** on the phone. |
| 5 | Export (phone and desktop) | The defaults, All parts + PDF + MusicXML, make 12 files. There's no Print. "My part" doesn't name the part. The title is "Export". | Default **Solo Cornet (you)** + **PDF** only. Add a **Print** primary (phone: Print · Share… · Save to Files). Title **Share or print**. Same scope labels on every platform. |
| 6 | Every phone screen | Secondary controls are 40 pt (chips, toolbar, Listen / Change note…, segmented controls). Previous / next bar has no visible hit area. | ≥ 44 pt everywhere, 48 pt for the player and review controls. |
| 7 | Error desktop ("Can't reach Brasscribe on your computer") | It shows the terminal command `brasscribe serve`, which breaks brand.md voice §7 and the pairing rule. | Remove it from the body. Put it under a **Details for the band's tech person** disclosure. |
| 8 | Choose output (not mocked) | This flow step is unreviewable, and it holds "lineup / difficulty / key". | Mock it before build, with the §2 copy: **Which band? / How hard? / Key**, a tip on difficulty, and **Show the score** as the primary. |

### P2

| # | Screen | Problem | Fix |
|---|---|---|---|
| 9 | Score toolbar | "Written / Concert" doesn't say which key. Learners don't know the terms. | **As written for B♭ / Concert pitch** + tip (§2). Update the brand.md glossary row "Transposed view". |
| 10 | Score view, PDFs | There's no "?" legend outside Review. Printed parts carry unexplained "?" marks. | A status line with the legend on the score view, a legend in the PDF footer, and an export option "Hide ? marks" once everything is checked. Change `system.md` §5, Uncertainty legend. |
| 11 | Tokens (Review note, score focus) | `focus` (#0050B3) is almost `uncertain` (#0063A6). The ring on an orange note reads as "uncertain". | Focus on notation = `ink`/`paper`, or re-hue `focus`. |
| 12 | Home phone | "Import audio or video" is computer-speak. There's no streaming-link tip and no Help. | **Open a recording**, the streaming tip from desktop, and a Help button beside Settings. |
| 13 | Desktop score | There are too many controls, and the meaning of "Score / Original", "Video" and "Talking score" is unclear. | A View ▾ menu, **Hear: Band / Recording** in the player, "Speed" visible on the slider, and the beat counter beside the position. |
| 14 | Loop (desktop) | There's no visible way to stop the loop. | **Repeat bars [12] to [13]** + **Stop repeating** · nb **Gjenta takt … til …** / **Slutt å gjenta**. |
| 15 | Copy | "Transcribed" / "Transkriberes", "DRM", "Engraving", "free time", "we'll", "62 percent", nb "Spill", "Merk som kontrollert", "Talende partitur" | Apply the §2 replacements. |
| 16 | Review | "G, half note" doesn't say written or concert, and uses US terms. The list order is jumbled. The phone lacks the "could also be A" hint. | "Written G, minim" (en-GB), sorted list + "+ N more", the hint on the phone. |
| 17 | What is this? | The soloist description is unclear. There's no "Not sure?" option. | The §2 copy and the "Not sure? Choose Brass band" line. |
| 18 | Transcribing | Cancel discards minutes of work without asking. | Confirm first: "Stop making this score? The recording stays in Your scores." |
| 19 | Part desktop | There's no way back to the full score. | A back button or the sidebar. |
| 20 | Dark mode | The icon wells and tonal buttons almost vanish. | Raise `secondary` in dark by one step. |

### P3

| # | Screen | Problem | Fix |
|---|---|---|---|
| 21 | Phone headers | The titles are about 8 pt off-centre. The back labels are inconsistent. | Centre on the screen. Use Home / the song title. |
| 22 | Phone score | The toolbar and player sit at a 12 pt inset, not the 20 pt margin. | Align to 20 pt. |
| 23 | Desktop Home | The score-card thumbnails are outside the card border. | Put them inside the outline. |
| 24 | Sidebar | "New score" styling differs between Home and Transcribing. | Use one style. |
| 25 | Part / score | The ad-lib tint is pale blue (reads as uncertain). The dark loop tint is heavy. | A neutral ad-lib tint and a lower loop alpha. |
| 26 | Icons | The ① count-in reads as "one". The gear is heavier than the other icons. "All parts" has no chevron. | A count-in glyph paired with the metronome, the outlined gear, a ▾ on the picker. |
| 27 | Export | The desktop has both ✕ and Cancel. The phone sheet has dead space. | Drop the ✕ on desktop. Put the phone actions in the bottom safe area, or use a detent. |
| 28 | What is this? mockups | They show a pre-selected choice, which contradicts the spec. | Mock the empty state with Continue disabled. |
| 29 | Error desktop | The actions are left-aligned. | Bottom right, after the secondary. |
| 30 | Studio | The "?" glyphs are reused for validator issues. | Use the warning icon. |
| 31 | Free-time info card | It shows while the ad-lib bars are off-screen. | Show it only when bars 1–2 are in view, or anchor it to the bar. |

### Spec changes needed (so teams don't follow the old rule)

- `brand/brand.md` "Words we use":
  - The row "Transposed view" becomes **As written for B♭ / Concert pitch** · **Notert for B♭ / Klingende**.
  - Add rows: Mute / Only this · Lyd av / Bare denne (avoid M/S, Solo, Demp); Export → Share or print · Del eller skriv ut; Play (button) → Spill av.
  - The row "Repeat a passage" gains the off action: Stop repeating · Slutt å gjenta.
- `system.md` §5:
  - **Player bar:** "chips turn ink when on" becomes "chips get a tonal fill and a ✓ when on; ink is only for Play".
  - **Player bar:** the chip row wraps and never clips.
  - **Mute / solo:** replace "M and S toggles" with labelled Mute / Only this toggles.
  - **Uncertainty legend:** it is also shown on the score view and in the PDF footer.
- `tokens/tokens.json`: the `focus` hue must differ from `uncertain` (or notation uses an ink focus ring). Change `adlib-tint` to a neutral.
- `tokens/icons.json`: change `play.nb`, `mute.en/nb`, `solo.en/nb`, `mark-checked.nb`, `talking-score` (the toolbar label) and `export.en/nb` as in §2.
