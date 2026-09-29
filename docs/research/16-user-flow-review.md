# 16 · User flow review: from recording to "my part"

**Status (2026-09-29):** the top 5 fixes (§5) are on `main` and released in v0.2.0: the core's `tune` flag on Android, each mapped part in its seat's own clef, Full brass band disabled for whole-band takes, the percussion refusal with the "empty" part source, «Demp stemmen min», and "How should the score be?" reachable from every score. Refused job options carry a code the apps word in en and nb. Open: P1-5 and the other Windows findings, because Windows `main` still has no "What do you play?" (`feat/my-instrument-windows` is unmerged).

**Question.** Does each step of Brasscribe Play (Android, Apple iOS/iPadOS/macOS, Windows) and Studio make sense? Does the player understand what is happening, and do they get the right part? The review looks hardest at players who are **not** the solo cornet.

**Method.** The flows were walked in code and strings (en + nb) on `origin/main` at `157d9df`. Sources:
- `apps/android` (`values/strings.xml`, `values-nb/strings.xml`)
- `apps/apple` (`App/Localizable.xcstrings`)
- `apps/windows` (`tools/Strings/gen_resw.py`, which generates both `.resw`)
- `studio/src/i18n.ts`
- the engine (`engine/src/brasscribe_engine/{profiles,stages,api}.py`)
- the seat tables in core and music:
  - `core/brasscribe-core/src/instruments.rs:418-571`
  - `music/src/brasscribe_music/instruments.py:266-431`
  - `nb_part_name` in `core/brasscribe-core/src/talking_score.rs:810`

The outcomes for the bass trombone and percussion seats were checked by running `seat_part` / `with_reading` / `seat_lineup` in `music`. The screens were checked against the committed screenshots:
- `apps/android/docs/screenshots/{my-instrument,design,music-stand}`
- `apps/apple/docs/screenshots`, `apps/apple/docs/responsive`
- `site/shots`

No new captures were needed. The existing renders cover every screen discussed except "Who plays the tune?", the quartet-refused card and the percussion notice, and none of those three has a harness scene yet (see P3-10).

**Windows note.** On `main`, Windows has no "What do you play?" at all. `feat/my-instrument-windows` (unmerged) adds it with the same copy as Android. The Windows findings below are about `main` unless they say otherwise.

---

## 1. Flow map

```
First run ─ "Scores for your band, from any recording."  [Get started]
   └─ "What do you play?"  (Android, Apple; Windows only on feat/my-instrument-windows)
        Instrument tiles (11) → Which part? (if >1) → You read (low brass, if >1 clef)
        [Continue]  ·  I conduct or listen  ·  Not now (never asked again)
Home ─ Open a recording · Record with the microphone · Record what's playing (Android/Mac/Win)
        · Open a score (MusicXML → straight to Score)
   └─ "What is this?"  One instrument · Brass band · Soloist with orchestra or band · Pop or rock
        (nothing preselected; "Not sure? Choose Brass band.")  + where it runs (phone / computer)
        └─ Making the score  "Step n of m"  (progress, time left, Cancel)
             phone (solo):     Getting the recording ready → Listening for the notes → Listening again
                               → Finding the beat → Arranging
             computer (engine): Sending → Finding the beat → Separating… → Writing down the notes
                               → Arranging for brass band → Laying out the pages
             error → Problem screen ("The score couldn't be made", Try again / Back to Home)
             └─ Review "Check the notes"  Yours (n) / Others / All   ─┐ (skipped when nothing is marked)
                  "Your part is arranged" notice → [Show my part] ────┼──→ Score (Apple: skips Output)
                  └─ [Choose output] → "How should the score be?"    │
                       Who played this? (solo take only)              │
                       Which band?  Full brass band* · Small band · Quartet   (*default)
                          (+ "· your part: X")
                       Who plays the tune?  (soloist recordings, tune-capable seat, not quartet)
                       How hard?  Easier · A bit easier · As played*
                       Key  Lower / Higher  "D major (concert) · E major on your part"
                       [Show the score]
                       └─ Score  part chip "Euphonium (you)" + source pill + mapped-seat banner
                            Play · Speed · Repeat · Count-in · Metronome · Mute my part
                            Parts sheet: Mute / Only this / Make this my part
                            Music stand (Android, Apple; not on Windows)
                            Share or print: <part> (you) · Every part · Conductor's score
                                            × PDF · MusicXML · Audio · MIDI · Talking score · Braille
Settings ─ Your instrument › What you play · computer · sound · display · stand · keyboard · about
Studio ─ New run (file or source, profile, title, MP3, large models) → stage graph → score tab
         (no lineup, seat, reads, lead, difficulty or key controls; run details show seat/reads/lead)
```

**The seat-to-part table** (core `SEAT_PARTS`, `instruments.rs:455-474`). Italic means a different key. "reads" is the `reads` option.

| Seat | Full band | Small band | Quartet | reads | tune |
|---|---|---|---|---|---|
| Soprano Cornet (E♭) | own | *Solo Cornet* | *1st Cornet* | treble | yes |
| Solo / Repiano / 2nd / 3rd Cornet | own | Solo / 2nd / 2nd / 2nd | 1st / 2nd / 2nd / 2nd | treble | yes |
| Flugelhorn | own | own | 2nd Cornet | treble | yes |
| Solo / 1st / 2nd Horn (E♭) | own | Solo Horn | Tenor Horn | treble | yes |
| 1st / 2nd Baritone | own | Euphonium | Euphonium | treble, bass | **no** |
| 1st / 2nd Trombone | own | 1st Trombone | Euphonium | treble, bass | yes |
| Bass Trombone (concert, bass clef) | own | *E♭ Bass* | *Euphonium* | bass | no |
| Euphonium | own | own | own | treble, bass | yes |
| E♭ Bass | own | own | *Euphonium* | treble, bass | no |
| B♭ Bass | own | own | Euphonium | treble, bass | no |
| Percussion | own | none | none | none | no |

**Important caveat to the table.** The "Full band" column is only reached by the layered arranger. That means orchestra-with-soloist on the engine, and solo takes. A **Brass band** or **Pop or rock** recording is always arranged for the small band or the quartet, whatever the player picks (see P1-3).

---

## 2. Per-persona walkthroughs

In each walkthrough, "phone" means Android and iOS, which behave the same unless noted.

### 2.1 Althorn / tenor horn player (2nd Horn, E♭, inner part)
1. **What do you play?**
   - The tile reads «Althorn · i Ess», or "Tenor Horn · in E♭".
   - Which part: «Solo althorn · 1. althorn · 2. althorn». In English it is "Solo Horn · 1st Horn · 2nd Horn": the tile says *Tenor Horn* and the parts say *Horn*.
   - No clef question, which is right.
2. **What is this? Brass band. Making the score.** Fine.
3. **Review.** Their part is arranged, so the notice «Stemmen din er arrangert» appears. That is good and honest.
   - On Apple, **Show my part** jumps straight to the score and skips Choose output (`App/Views/ReviewView.swift:390-400`). They never see the band or difficulty choice.
4. **Choose output.** "Full brass band · your part: 2. althorn" is preselected. What they actually get is the small band (P1-3). The score then opens on **Solo althorn** with the banner «Det lille bandet har ingen 2. althorn — viser Solo althorn». So they get the notice for a lineup they didn't choose.
5. **Score.** Treble clef, in E♭, correct. The source pill says «Arrangert ut fra harmoniene i bandet».
   - «Lyd av min stemme» can be read as "sound of my part", not "mute my part" (P2-1).

**Result.** They get a correct E♭ treble part. It is the Solo Horn line, not theirs, and the label says full band when it isn't.

### 2.2 Baritone (1st Baritone) or euphonium player
1. **Tile.** Baryton → 1./2. baryton → «Du leser»: «G-nøkkel i B» (default) or «F-nøkkel, klingende».
   - The screenshot `first-run-chosen-nb-light.png` shows «Du leser» cut off at the bottom above the sticky Continue button. On a phone the player may press Continue without seeing the clef choice. The default is safe, but they don't know they had a choice.
2. **Choose output, soloist recording.**
   - **Android** offers "Who plays the tune? · Du: 1. baryton" even though the core says the baritone can't carry the tune (P1-1). Choosing it fails after **Show the score** with «Melodien kan ikke gå på stemmen din i dette bandet.» That is a dead end: nothing says why, or what to pick instead.
   - **Apple** and the Windows branch hide it correctly.
   - Euphonium players get the choice on all platforms, and it works (not in the quartet).
3. **Small band or quartet.** The baritone maps to Euphonium, in the same key and clef. The notice (`iphone-nb-part-seat-notice-light.png`) is fine. On Android the banner is cut off: «…viser E…» (`my-instrument/score-nb-light.png`).
4. **Bass clef readers** get their part in F-nøkkel at concert pitch. Other parts stay transposed, which is right.
   - The toolbar label on Apple says «Notert for B♭»: it uses English note names in the Norwegian UI (`App/Views/ScoreScreen.swift:317,325`).
5. **Changing the instrument later in Settings.**
   - Apple re-points "(you)" in **old** band scores to the new seat (`App/PracticeModel.swift:136-167`), while the caption promises «Partiturer du har fra før, beholder stemmen du valgte».
   - The part was written in the old seat's clef, so a switch from euphonium/bass clef to cornet leaves a bass-clef Euphonium part marked "(you)" on some scores and not on others.

### 2.3 Trombone and bass trombone
- **1st and 2nd Trombone.** Treble in B♭ by default, or bass clef, as it sounds.
  - Norwegian school and church players mostly read bass clef. The default follows the brass band convention (`instruments.rs` reads `[treble, bass]`), which is right for a brass band, but the question sits below the fold (see 2.2).
  - In the quartet the trombone maps to Euphonium. If they left «Du leser» at its default, that part is treble clef in B♭.
- **Bass Trombone: they get the wrong clef in the small band and the quartet (P1-2).**
  - The seat reads bass clef only, so no clef question is shown. The apps store `reads = null` (the default): Android `ui/WhatDoYouPlayScreen.kt:145`, Apple `App/Seats.swift:140`.
  - The mapped part is E♭ Bass (small band) or Euphonium (quartet). `with_reading(…, None)` leaves it as it is. Verified: small band → **E♭ Bass, treble clef, E♭ (chromatic −21)**; quartet → **Euphonium, treble clef, B♭**.
  - The bass trombonist, who reads bass clef at concert pitch, is given a transposed treble-clef part. The notice says «…skrevet for Ess», which a bass trombonist won't know how to act on.
- **"Who plays the tune?"** Android shows it for the bass trombone (P1-1). The engine then refuses: "the Bass Trombone does not carry the tune".

### 2.4 E♭ and B♭ bass
- **Tile.** «Ess-bass» / «B-bass» → «Du leser» G-nøkkel i Ess (or i B) / F-nøkkel, klingende. Good.
- **Full band and small band:** their own part.
- **Quartet:** Euphonium.
  - For the B♭ bass it is the same key, but the part sits an octave above where they usually play. The notice says only "the closest", not that it sits higher.
  - For the E♭ bass the notice says «…Eufonium, skrevet for B». An E♭ bass player reading treble clef would have to transpose by a fourth. There is no "write it in E♭ for me" option (P2-4).
- **Tune:** Android offers "Du: Ess-bass" (P1-1), then refuses it.
- **Solo take of the bass line on the phone:** the window is now the instrument's range (`pipeline.rs:366-368`), so it works, with the known confidence caveats for tuba.

### 2.5 Slagverk / percussion
**What they see.** A «Slagverk» tile, with its one part chosen automatically, and no clef question. **What they get:**

| Recording | Result |
|---|---|
| Soloist with orchestra or band (engine, full band) | A real Percussion part from the drums stem (`arranger.rs:897-899`), labelled «Fra opptaket». The only case that works. With no drums in the recording, the part is **empty** but labelled «Arrangert ut fra harmoniene i bandet», and printed with that footer (Studio report, `arranger.py:480-481`, `519-520`). |
| Brass band / Pop or rock (engine) | Always small band or quartet (P1-3), so **never a percussion part**. The notice says «Det lille bandet har ingen slagverkstemme. Brasscribe åpner alle stemmene.», although the player picked "Full brass band". |
| **Solo take (phone or engine)** | `seat_lineup("percussion")` makes one drum-kit part with range 0–127 (`instruments.rs:542`, `pipeline.rs:366-368`). The pitch trackers' notes from the drummer's take are all kept and drawn as unpitched hits, mostly `B5 x` (`musicxml.py:62-86`). The part is labelled «Fra opptaket ditt». Nobody refuses it; this is **nonsense output presented as theirs** (P1-4). |
| Small band / quartet | No part, so the score opens on every part. "Mute my part" is hidden. Fine. |

**Missing capability.** There is no percussion transcription for a solo take, and none for a band take outside orchestra-with-soloist. The honest short-term fix is to say so up front, and not to invent a part (P1-4).

### 2.6 Flugelhorn and soprano cornet
- **Flugelhorn.** Its own part in the full and small band, and 2nd Cornet in the quartet (same key). "Who plays the tune?" is offered and works. Fine.
- **Soprano.**
  - The tile «Sopran · Ess-kornett» gives the part name «Sopran-kornett»: three spellings on one screen (P3-1).
  - Small band / quartet: Solo Cornet / 1st Cornet written in **B♭**. The notice says «skrevet for B». The soprano player has to transpose a fourth up in their head (P2-4), or play the cornet.
  - Full band, faithful mode: the Soprano part is **empty** (no climax doubling in faithful) but labelled "arranged" (P2-6).

### 2.7 A beginner who doesn't know their transposition
- **Instrument tiles.** Only some tiles carry the key sub-line («Althorn · i Ess», «Sopran · Ess-kornett»). Kornett, Baryton, Eufonium and the trombones have none, so "i Ess" looks like the only thing that matters.
- **Which part?** It has no "Vet ikke" (don't know) option. A beginner who plays "the 3rd one" in a school band must guess, and Continue stays blocked until they do.
- **«Du leser: G-nøkkel i B / F-nøkkel, klingende».** This is jargon to a beginner:
  - there is no picture of the clef;
  - there is no "Look at the start of your music" hint;
  - «klingende» is not explained on this screen.

  The only explanation of written vs concert pitch is the ⓘ on the score toolbar.
- **Choose output key line.** "E major on your part" is good, as long as they know "concert".
- **Result.** A wrong answer is recoverable in Settings. But because of Apple's re-pointing (2.2) and the no-reopen gap (P2-3), fixing it later doesn't always fix the score they already have.

---

## 3. Findings

### P1: wrong part, dead end, or false output

**P1-1. Android offers "Who plays the tune?" to seats that can't carry it, then fails.**
- **Where.** `apps/android/core-bridge/src/main/kotlin/no/brasscribe/play/core/RustCoreBridge.kt:114` builds `Seat(...)` without the FFI's `tune`. The default `tune = reads.isNotEmpty()` (`apps/android/model/src/main/kotlin/no/brasscribe/play/model/CoreBridge.kt:52`) makes every non-percussion seat tune-capable. The core says no for the baritones, Bass Trombone, E♭ Bass and B♭ Bass (`instruments.rs:418`).
- **What goes wrong.** "Du: Ess-bass" is shown. After **Show the score** the player gets «Melodien kan ikke gå på stemmen din i dette bandet.» (`lead_seat_refused`), with no way forward.
- **Fix.** Pass `it.tune` from `SeatInfo`, and remove the default. Also make the refusal line say what to do: «…Velg «Solokornett (som vanlig)».»

**P1-2. The bass trombonist is given a treble-clef transposed part in the small band and the quartet.**
- **Where.** `with_reading` (`instruments.rs:551`, `instruments.py:399`) only rewrites the clef when `reads` is set. The apps drop `reads` when it equals the seat's default (Android `ui/WhatDoYouPlayScreen.kt:145`, `PlayViewModel.kt:163`; Apple `App/Seats.swift:140`).
- **What goes wrong.** For the bass trombone the default *is* bass clef, so nothing is sent. The mapped E♭ Bass or Euphonium part comes out in treble clef, E♭ or B♭. Verified in `music`.
- **Fix (core, one place).** When `reads` is None, use the **seat's** own reading (`seat.reads[0]`) for the mapped part. That gives bass clef at concert pitch for the bass trombone. Every other seat's first reading already matches its mapped part's clef. Add a seat-table test: "bass-trombone × minimal/quartet → bass clef, chromatic 0".

**P1-3. "Full brass band" is the default, but band and pop recordings are always made for the small band.**
- **Where.**
  - `eval/brasscribe_eval/arrange_song.py:90` (`--lineup` choices are minimal and quartet only)
  - `core/brasscribe-core/src/arranger.rs:925-930` (a non-layered composition gets minimal)
  - `apps/android/app/src/main/kotlin/no/brasscribe/play/Lineup.kt:60` (`FULL → MINIMAL` silently)
  - engine `profiles.py` default `full`, dropped as a default (Studio report B1)
- **What goes wrong.** The Brass band profile is the one "Not sure?" recommends. The output card says «Fullt brassband · Omtrent 25 musikere · stemmen din: 2. althorn». The player gets 8 parts, then a notice about "the small band", and percussion is never there.
- **Validation is wrong too.** `lead=seat` is checked against the full band while the small band is what gets arranged, so 1st Baritone is refused even though it would work (Euphonium).
- **Fix.**
  - Until `arrange_song` can write the full band, **disable the Full card for non-layered takes**, with the reason «Kommer senere for opptak av hele bandet» / "Not yet for whole-band recordings", and **default to Small band** for them.
  - Compute "your part: …" against the lineup that will actually be made.
  - Validate `lead` against the same lineup.

**P1-4. The percussion seat produces a nonsense drum part from a solo take, labelled as the player's own.**
- **Where.**
  - `instruments.rs:542` `seat_lineup` / `pipeline.rs:366-368` (window = drum kit 0–127)
  - `music/…/instruments.py:390-396`, engine solo profile
- **What goes wrong.** Whatever the pitch trackers report for a drummer's take is drawn as `x` noteheads and marked «Fra opptaket ditt».
- **Fix.**
  - In the core, `seat_lineup("percussion")` should be an error, and the solo pipeline should refuse it with a message the player can read.
  - In the apps, when the seat is percussion and the take is "Ett instrument", show before processing: «Brasscribe kan ikke skrive ned slagverk fra et soloopptak ennå. Ta opp bandet, så får du slagverkstemmen når bandet har trommer.» / "Brasscribe can't write down percussion from a solo take yet. Record the band; you get a percussion part when the recording has drums." Offer **Change what I play** and **Record anyway (no part for me)**.
  - In the picker, add a sub-line on the Slagverk tile: «Bare fra opptak med trommer» / "Only from recordings with drums".
  - Separately, an empty Percussion part must not be labelled "arranged" (P2-6).

**P1-5. Windows `main` has no "my instrument": your part is guessed, and export picks the wrong part in Norwegian.**
- **Where.**
  - `ScoreViewModel.cs:159, 275-284`: "My part" is the first part whose name contains "Solo".
  - `ExportViewModel.cs:85-86` compares the localised name with the English one. In nb it never matches, so export defaults to part 0: **the Soprano Cornet PDF is labelled "(deg)"**.
  - The mixer shows English part names in nb (`PlayerViewModel.cs:16,102`).
- **Fix.**
  - Merge `feat/my-instrument-windows` once it passes P1-1 and P1-2 (its stopgap `TuneInstruments` in `Seats/SeatCatalog.cs:124` should read the core's `tune` once bound).
  - Match export parts by part id, not name.
  - Localise mixer names through `part_name_nb`.

### P2: confusing, or right but not understood

**P2-1. «Lyd av min stemme» is ambiguous, and mute has four wordings.**
- **Where.**
  - `values-nb/strings.xml:283` («Lyd av min stemme», «Lyd av»); Apple and Windows use the same wording.
  - The first run says «Skru av lyden på stemmen din» (Android) / «Skru av stemmen din» (Apple) / «Slå av lyden på stemmen din» (Windows), and the seat body says «slår av lyden på den».
- **Why it's a problem.** «Lyd av min stemme» can be read as "the sound of my part". As a checked toggle (`iphone-nb-part-seat-notice-light.png`, "✓ Lyd av min stemme") it reads as "my part's sound is on".
- **Fix.** Use **«Demp stemmen min»** (toggle) and «Demp» / «Demp %1$s» in the parts rows, and «demper den når du spiller med» in the body. Studio already uses «Demp» (`stems.col.mute`). Use one form, «stemmen min», everywhere («Vis stemmen min», «Bare stemmen min» already do).

**P2-2. The "You read" question is below the fold, and a beginner has no help with it.**
- **Where.** Android `ui/WhatDoYouPlayScreen.kt:172-176` (screenshot `first-run-chosen-nb-light.png` shows it cut off under the sticky Continue), Apple `App/Views/WhatDoYouPlayView.swift`.
- **Fix.**
  - When a low-brass part is chosen, scroll «Du leser» into view.
  - Give each option a small clef glyph, and add a hint: «Se på starten av notene dine: 𝄞 = G-nøkkel, 𝄢 = F-nøkkel.» / "Look at the start of your music: 𝄞 treble, 𝄢 bass."
  - Explain «klingende» inline: «F-nøkkel, klingende (som på piano)».

**P2-3. "You can change this later. Nothing is lost." is not true for band takes on the phone.**
- **Where.** Android and Apple reach Choose output only from Review, or via "Write for another instrument…" for solo takes (Android `ui/ScoreScreen.kt:604`, Apple `App/Views/ScoreScreen.swift:491-497`). Apple's "Show my part" skips it (`ReviewView.swift:390-400`). Windows has "How should the score be?…" in the View menu.
- **Fix.** Add "Band, difficulty and key…" / «Band, vanskelighet og toneart …» to the score's ⋯ / View menu on all platforms. Make Apple's "Show my part" go through Output the first time.

**P2-4. A mapped part in another key is only described. Soprano, E♭ Bass and Bass Trombone players can't use it.**
- **Where.** `mapped_other_*` («…skrevet for B.») on Android `values-nb/strings.xml:615-616` and Apple `App/Seats.swift:165-208`.
- **Fix.**
  - Short term: make the wording actionable: «…skrevet for B-instrument. Spiller du Ess-kornett, må du transponere, eller velg Fullt brassband.»
  - Missing capability: the core already rewrites the seat's part for `reads=bass` (`with_reading`). A sibling `with_key(seat)` could write the mapped part in the **seat's** transposition, so the soprano gets Solo Cornet in E♭ and the E♭ Bass gets Euphonium in E♭. Range checks already come from the instrument table.

**P2-5. The Apple Settings change re-points "(you)" in existing scores, against its own caption.**
- **Where.** `App/PracticeModel.swift:136-167` uses the current seat unless `piece.myPart` is set.
- **Fix.** Store the resolved seat part on the `Piece` when it is first opened, as Android stores the per-score choice. Or change the caption to what happens.

**P2-6. Empty parts are labelled "Arranged from the band's harmony", and their PDFs carry that footer.**
- **Where.** `arranger.rs:1000-1025` `part_sources`: the Percussion part with no drums, and the Soprano part in faithful mode.
- **Fix.** Add a fourth source, `empty`, labelled «Tom i dette arrangementet» / "Nothing to play in this arrangement". Leave empty parts out of "Every part" exports.

**P2-7. Errors are one generic message, often with raw English.**
- **Where.**
  - Android: every failure is `SCORE_FAILED`, and the re-arrange status shows the raw exception (`PlayViewModel.kt:647-653`); computer-score open failure shows "Try an MP3, WAV…" (`:779`).
  - Apple: one reason for everything (`FlowViews.swift:331-350`).
  - Windows: a timeout is treated as a user cancel (`TranscriptionViewModel.cs:230-234`), and the quartet 422 is shown as generic.
  - Engine: 422 texts are English and use seat ids ("the minimal brass has no part for the seat percussion", `instruments.py:425`).
- **Fix.**
  - Have the engine return a machine code with each 422 (`seat_no_tune`, `quartet_needs_group`, `reads_not_offered`, …) and map them to app copy.
  - Add three problem screens:
    - "Can't reach your computer": **Check connection**, **Pair again**
    - "The recording is too short": minimum 1 s, as Windows already checks (`StartViewModel.cs:153`)
    - "Your computer's Brasscribe is too old"

**P2-8. "You can leave this screen; Brasscribe will tell you…", but nothing does.**
- **Where.** Android `ui/ProfileScreen.kt:206-268` (Back cancels without asking, `PlayViewModel.kt:297-301`); Windows (Back is disabled and there is no notification).
- **Fix.** Either post a local notification on completion, or say «Hold appen åpen til partituret er klart.» / "Keep the app open until the score is ready." Make Back ask the same "Stop making this score?" as Cancel.

**P2-9. Apple's step checklist jumps back to step 1 on "Making the audio" / "Working".**
- **Where.** `FlowViews.swift:250` (`firstIndex ?? 0`, where `.rendering` and `.working` are not in the list). Android drops `contour.*` stages that have no kind (`PlayViewModel.kt:85-89`).
- **Fix.** Map unknown stages to the current step, not to 0. Map `contour` to transcribe, as Windows does (`TranscriptionViewModel.cs:101-109`).

**P2-10. Android's mapped-seat banner is cut off.**
- **Where.** `my-instrument/score-nb-light.png`: «Det lille bandet har ingen 1. baryton — viser E…».
- **Fix.** Let it wrap to two lines. Its whole point is the part name at the end.

### P3: wording and consistency

- **P3-1. Norwegian part-name spelling** (`talking_score.rs:810-834`). «Solokornett» is closed, «Sopran-kornett» and «Repiano-kornett» are hyphenated, and «Solo althorn» is open. The tile adds «Sopran · Ess-kornett».
  - Pick one rule: «Soprankornett, Solokornett, Repianokornett, Soloalthorn», with ordinals «1. althorn».
  - Then use `Seat.nbName` (already in the FFI, unused on Android) for the tiles.
- **P3-2. English horn naming.** The tile says "Tenor Horn", the parts say "Solo/1st/2nd Horn", and the quartet part is "Tenor Horn".
  - Use "Solo Tenor Horn / 1st Tenor Horn…" in UI copy, or keep "Horn" and make the tile "Tenor horn (E♭ horn)".
  - Norwegian «althorn» is right. Keep it: a Norwegian «tenorhorn» is a B♭ instrument.
- **P3-3. Key sub-lines on tiles.** Give every tile its key or none: «Kornett · i B», «Baryton · i B», «Ess-bass · i Ess». Then "i Ess" doesn't look special, and the beginner learns their key.
- **P3-4. Lineup names.** The library says «Fullt band»; the Output card says «Fullt brassband». The Apple profile detail says «korps», everywhere else says «band». Use «Fullt brassband» / «Lite band» / «Kvartett» everywhere, and «band» in the profile detail.
- **P3-5. «Fortsett» carries three meanings**: Continue, "Keep going" in the cancel dialog, and «Fortsett senere». Use «Fortsett å lage» for Keep going and «Sjekk resten senere» for Finish later.
- **P3-6. «Velg resultat»** (Android `choose_output`) matches neither "Choose output" nor the screen title. Use «Velg band og vanskelighet» / "Choose band and difficulty".
- **P3-7. English sentence starts differ** in the mapped notices: "This small band has no…" vs "The small band has no…" (Android `values/strings.xml:615-620`, `632-633`). Use one form.
- **P3-8. Apple key names in nb**: «Notert for B♭» and «Notert (E♭)» (`ScoreScreen.swift:317,325`). Use `KeyNames` (B, Ess, …).
- **P3-9. Studio.**
  - The seat is shown in English in nb (`views/run.ts:267-280`); lineup and difficulty are not shown at all.
  - `stage.k.separate` and `stage.k.vote` are dead keys.
  - «Stemmespor» collides with «stemme» (part). Use «Lydspor».
- **P3-10. Screenshots missing** for "Who plays the tune?", the quartet-unavailable card, the percussion notice, and "You read" on iPad/Mac. Add harness scenes (Apple `ScreenshotScenes.swift`, Android `MyInstrumentScreensTest.kt`, Windows `PreviewScenes.cs`).
- **P3-11. Microphone denied.** The status line says to go to Settings, but there is no button to get there (Android `ui/HomeScreen.kt:81-130`, Apple `RecordViews.swift:41`). On Mac the place is "System Settings". Add **Open Settings**.
- **P3-12. Android About** shows a debug line, `CoreBridge: …` (`ui/CompanionScreen.kt:170`).

---

## 4. Implications for adding trumpet as a lead instrument

Trumpet itself is designed elsewhere. For this flow, adding it touches:
- **Seat table.** The trumpet is not a brass-band part, so every lineup column maps it (for example to Solo Cornet or 1st Cornet, same key). `exact` is then always false.
  - The mapped notices assume "this lineup lacks your seat". For a trumpet they will fire in the **full** band too ("Det fulle bandet har ingen trompet…"). Android and Apple have no full-band variant of the same-key notice (only Windows' branch does), so one is needed.
- **Tile grid.** There are 11 tiles today. A 12th changes the grid. The trumpet needs a key sub-line (see P3-3) so it isn't confused with cornet.
- **Tune.** It must come from the core's `tune`, not an app-side list (P1-1 on Android, and the Windows stopgap `SeatCatalog.cs:124`).
- **Solo take.** The window follows the seat's `pro` range, so a trumpet solo take works like a cornet one.
  - It needs a part name in `part_name_nb` and a `<midi-bank>` or sound, or the part falls back silently (`docs/plan/my-instrument.md` §4.2).

---

## 5. Top 5 fixes

1. **Android: pass the core's `tune` into `Seat`** (`RustCoreBridge.kt:114`). This removes the dead-end "Who plays the tune?" for baritones, the bass trombone and the basses. (P1-1)
2. **Core: default a mapped part to the seat's own reading.** The bass trombonist then gets bass clef at concert pitch in the small band and the quartet, not a treble part in E♭ or B♭. (P1-2)
3. **Show the lineup that will actually be made.** Disable "Full brass band" for band and pop takes until the full-band arranger exists, default them to Small band, and base "your part" and `lead` validation on that lineup. (P1-3)
4. **Percussion: refuse a solo take for the Slagverk seat and say why before processing.** Label empty parts as empty, not "arranged". (P1-4, P2-6)
5. **Plain mute wording and a way back to Choose output.** Use «Demp stemmen min» everywhere, and add "Band, difficulty and key…" to the score menu, so "You can change this later" is true. (P2-1, P2-3)
